"""
Deterministic Chunk Generator v2.0
===================================

This generator creates chunks using ONLY the defined schema.
AI fills VALUES, never KEYS.

Key principles:
1. content_id is ALWAYS deterministic (from schema)
2. Check cache FIRST - never regenerate existing data
3. Validate all output against chunk_types.json schema
4. Safety-critical data starts quarantined
"""

import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from services.schema_service import get_schema_service
from services.content_id_generator import (
    normalize_vehicle_key,
    build_content_id,
    parse_content_id,
    get_chunks_for_job,
)
from services.supabase_client import SupabaseService, supabase_service
from services.openrouter import openrouter
from services.nhtsa import nhtsa_service
from services.carquery import carquery_service


@dataclass
class GenerationResult:
    """Result of generating a single chunk."""
    content_id: str
    success: bool
    cached: bool  # True if retrieved from cache instead of generated
    error: Optional[str] = None
    data: Optional[Dict] = None


@dataclass  
class BatchGenerationResult:
    """Result of generating multiple chunks."""
    vehicle_key: str
    total_requested: int
    cached: int
    generated: int
    failed: int
    results: List[GenerationResult]
    duration_ms: int


async def llm_generate(prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
    """Helper to call LLM with standard settings."""
    messages = [{"role": "user", "content": prompt}]
    response, _ = await openrouter.chat_completion(
        model_key="structured",  # Use Gemini for structured data extraction
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response


class DeterministicChunkGenerator:
    """
    Generate chunks using deterministic content_ids from schema.
    
    The Three Laws:
    1. AI fills VALUES, never KEYS
    2. content_id = {chunk_type}:{component} - always from schema
    3. Cache is king - never regenerate what exists
    """
    
    def __init__(self, supabase: SupabaseService = None):
        self.supabase = supabase or supabase_service
        self.schema = get_schema_service()
    
    # =========================================================
    # MAIN GENERATION METHODS
    # =========================================================
    
    async def generate_chunk(
        self,
        vehicle_key: str,
        content_id: str,
        force: bool = False
    ) -> GenerationResult:
        """
        Generate a single chunk for a vehicle.
        
        Args:
            vehicle_key: Normalized vehicle key (e.g., "2019_honda_accord_2.0t")
            content_id: Schema-defined content_id (e.g., "fluid_capacity:engine_oil")
            force: If True, regenerate even if chunk exists (use sparingly!)
        
        Returns:
            GenerationResult with success/failure info
        """
        # Step 1: Validate content_id
        if not self.schema.is_valid_content_id(content_id):
            return GenerationResult(
                content_id=content_id,
                success=False,
                cached=False,
                error=f"Invalid content_id: {content_id}"
            )
        
        # Step 2: Check cache (unless force=True)
        if not force:
            existing = await self.supabase.get_chunk_by_content_id(
                vehicle_key, content_id
            )
            if existing:
                return GenerationResult(
                    content_id=content_id,
                    success=True,
                    cached=True,
                    data=existing.model_dump()
                )
        
        # Step 3: Parse content_id
        chunk_type, component = parse_content_id(content_id)
        
        # Step 4: Generate based on chunk type
        try:
            if chunk_type == "fluid_capacity":
                data = await self._generate_fluid_capacity(vehicle_key, component)
            elif chunk_type == "torque_spec":
                data = await self._generate_torque_spec(vehicle_key, component)
            elif chunk_type == "procedure":
                data = await self._generate_procedure(vehicle_key, component)
            elif chunk_type == "part_location":
                data = await self._generate_part_location(vehicle_key, component)
            else:
                data = await self._generate_generic(vehicle_key, chunk_type, component)
            
            if not data:
                return GenerationResult(
                    content_id=content_id,
                    success=False,
                    cached=False,
                    error="Generation returned no data"
                )
            
            # Step 5: Validate data against schema
            is_valid, errors = self.schema.validate_chunk_data(chunk_type, data)
            if not is_valid:
                print(f"⚠️ Validation warnings for {content_id}: {errors}")
            
            # Step 6: Save to database
            chunk_record = await self.supabase.save_chunk(
                vehicle_key=vehicle_key,
                content_id=content_id,
                chunk_type=chunk_type,
                template_type=chunk_type,  # Use chunk_type as template_type
                title=data.get("title", f"{chunk_type}: {component}"),
                content_text=data.get("content_text", ""),
                data=data,
                sources=data.get("sources", []),
                source_confidence=data.get("confidence", 0.5),
                verification_status="pending_review",
                qa_status="pending",
            )
            
            if chunk_record:
                return GenerationResult(
                    content_id=content_id,
                    success=True,
                    cached=False,
                    data=chunk_record.model_dump()
                )
            else:
                return GenerationResult(
                    content_id=content_id,
                    success=False,
                    cached=False,
                    error="Failed to save chunk to database"
                )
                
        except Exception as e:
            print(f"❌ Generation error for {content_id}: {e}")
            return GenerationResult(
                content_id=content_id,
                success=False,
                cached=False,
                error=str(e)
            )
    
    async def generate_for_job(
        self,
        vehicle_key: str,
        job_type: str,
        force: bool = False
    ) -> BatchGenerationResult:
        """
        Generate all chunks needed for a job type.
        
        Args:
            vehicle_key: Normalized vehicle key
            job_type: Job type from job_chunk_map.json (e.g., "oil_change")
            force: If True, regenerate even if chunks exist
        
        Returns:
            BatchGenerationResult with stats and individual results
        """
        start_time = datetime.utcnow()
        
        # Get required chunks for this job
        required_ids = get_chunks_for_job(job_type)
        
        if not required_ids:
            return BatchGenerationResult(
                vehicle_key=vehicle_key,
                total_requested=0,
                cached=0,
                generated=0,
                failed=0,
                results=[],
                duration_ms=0
            )
        
        # Generate each chunk
        results = []
        cached = 0
        generated = 0
        failed = 0
        
        for content_id in required_ids:
            result = await self.generate_chunk(vehicle_key, content_id, force)
            results.append(result)
            
            if result.cached:
                cached += 1
            elif result.success:
                generated += 1
            else:
                failed += 1
        
        duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return BatchGenerationResult(
            vehicle_key=vehicle_key,
            total_requested=len(required_ids),
            cached=cached,
            generated=generated,
            failed=failed,
            results=results,
            duration_ms=duration
        )
    
    async def generate_for_vehicle(
        self,
        year: int,
        make: str,
        model: str,
        engine: Optional[str] = None,
        job_types: Optional[List[str]] = None
    ) -> Dict[str, BatchGenerationResult]:
        """
        Generate all chunks for a vehicle across multiple job types.
        
        Args:
            year, make, model, engine: Vehicle info
            job_types: List of job types to generate for (defaults to common jobs)
        
        Returns:
            Dict mapping job_type to BatchGenerationResult
        """
        vehicle_key = normalize_vehicle_key(year, make, model, engine)
        
        if not job_types:
            job_types = [
                "oil_change",
                "brake_pads_front", 
                "brake_pads_rear",
                "spark_plugs",
            ]
        
        results = {}
        for job_type in job_types:
            print(f"📦 Generating chunks for {vehicle_key} / {job_type}...")
            results[job_type] = await self.generate_for_job(vehicle_key, job_type)
            
            # Log summary
            r = results[job_type]
            print(f"   ✅ Cached: {r.cached}, Generated: {r.generated}, Failed: {r.failed}")
        
        return results
    
    # =========================================================
    # CHUNK TYPE SPECIFIC GENERATORS
    # =========================================================
    
    async def _generate_fluid_capacity(
        self, 
        vehicle_key: str, 
        component: str
    ) -> Dict[str, Any]:
        """Generate fluid capacity data (e.g., engine_oil, coolant)."""
        
        # Parse vehicle info
        parts = vehicle_key.split("_")
        year = parts[0]
        make = parts[1].title()
        model = "_".join(parts[2:-1]).replace("_", " ").title() if len(parts) > 3 else parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        # Component display names
        component_names = {
            "engine_oil": "Engine Oil",
            "transmission": "Transmission Fluid",
            "coolant": "Coolant",
            "brake_fluid": "Brake Fluid",
            "power_steering": "Power Steering Fluid",
            "differential": "Differential Fluid",
            "transfer_case": "Transfer Case Fluid",
        }
        
        display_name = component_names.get(component, component.replace("_", " ").title())
        
        # Build prompt for LLM
        prompt = f"""You are an automotive technician database. Provide EXACT factory specifications.

Vehicle: {year} {make} {model} {engine}
Request: {display_name} capacity and specifications

Respond in this EXACT JSON format:
{{
  "capacity_value": <number in quarts for oil/trans, gallons for coolant>,
  "capacity_unit": "quarts" or "gallons",
  "spec": "<fluid specification, e.g., 0W-20, Dexron VI>",
  "filter_part": "<OEM filter part number if applicable>",
  "notes": "<any important notes about this fluid>"
}}

CRITICAL: Only provide data you are CERTAIN about. If unsure, use null for that field.
Do NOT make up part numbers. Real data only."""

        try:
            response = await llm_generate(prompt, max_tokens=500, temperature=0.1)
            
            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = f"{display_name} Capacity"
                data["content_text"] = f"{display_name}: {data.get('capacity_value', 'N/A')} {data.get('capacity_unit', '')} - {data.get('spec', 'See manual')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6  # LLM data starts lower confidence
                return data
            
        except Exception as e:
            print(f"❌ LLM error for fluid_capacity:{component}: {e}")
        
        # Return placeholder if generation fails
        return {
            "title": f"{display_name} Capacity",
            "capacity_value": None,
            "capacity_unit": "quarts",
            "spec": "Refer to owner's manual",
            "notes": "Data verification in progress",
            "content_text": f"{display_name}: Verification in progress",
            "sources": [],
            "confidence": 0.0,
        }
    
    async def _generate_torque_spec(
        self, 
        vehicle_key: str, 
        component: str
    ) -> Dict[str, Any]:
        """Generate torque specification data."""
        
        parts = vehicle_key.split("_")
        year = parts[0]
        make = parts[1].title()
        model = "_".join(parts[2:-1]).replace("_", " ").title() if len(parts) > 3 else parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        # Component display names
        component_names = {
            "drain_plug": "Oil Drain Plug",
            "oil_filter": "Oil Filter (if applicable)",
            "wheel_lug_nuts": "Wheel Lug Nuts",
            "spark_plugs": "Spark Plugs",
            "front_caliper_bracket": "Front Caliper Bracket Bolts",
            "rear_caliper_bracket": "Rear Caliper Bracket Bolts",
            "front_caliper_slide": "Front Caliper Slide Pins",
            "rear_caliper_slide": "Rear Caliper Slide Pins",
        }
        
        display_name = component_names.get(component, component.replace("_", " ").title())
        
        prompt = f"""You are an automotive technician database. Provide EXACT factory torque specifications.

Vehicle: {year} {make} {model} {engine}
Component: {display_name}

Respond in this EXACT JSON format:
{{
  "torque_value": <number>,
  "torque_unit": "ft-lb" or "Nm",
  "torque_sequence": "<pattern if applicable, e.g., star pattern, null if N/A>",
  "thread_locker": "<Loctite type if required, null if not>",
  "notes": "<any critical notes about this torque spec>"
}}

CRITICAL: Only provide data you are CERTAIN about. Safety-critical specs must be accurate.
If unsure of exact value, provide a safe range or null."""

        try:
            response = await llm_generate(prompt, max_tokens=500, temperature=0.1)
            
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = f"{display_name} Torque Spec"
                data["content_text"] = f"{display_name}: {data.get('torque_value', 'N/A')} {data.get('torque_unit', 'ft-lb')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.5  # Torque specs are safety-critical, lower confidence
                return data
                
        except Exception as e:
            print(f"❌ LLM error for torque_spec:{component}: {e}")
        
        return {
            "title": f"{display_name} Torque Spec",
            "torque_value": None,
            "torque_unit": "ft-lb",
            "notes": "Refer to factory service manual",
            "content_text": f"{display_name}: Refer to factory service manual",
            "sources": [],
            "confidence": 0.0,
        }
    
    async def _generate_procedure(
        self, 
        vehicle_key: str, 
        component: str
    ) -> Dict[str, Any]:
        """Generate procedure steps."""
        
        parts = vehicle_key.split("_")
        year = parts[0]
        make = parts[1].title()
        model = "_".join(parts[2:-1]).replace("_", " ").title() if len(parts) > 3 else parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        procedure_names = {
            "oil_change": "Oil Change Procedure",
            "brake_pads_front": "Front Brake Pad Replacement",
            "brake_pads_rear": "Rear Brake Pad Replacement",
            "spark_plugs": "Spark Plug Replacement",
            "coolant_flush": "Coolant Flush Procedure",
        }
        
        display_name = procedure_names.get(component, component.replace("_", " ").title())
        
        prompt = f"""You are an automotive technician. Write professional service procedure steps.

Vehicle: {year} {make} {model} {engine}
Procedure: {display_name}

Respond in this EXACT JSON format:
{{
  "steps": [
    "Step 1: ...",
    "Step 2: ...",
    ...
  ],
  "tools_required": ["tool1", "tool2", ...],
  "estimated_time": "<time in minutes>",
  "difficulty": "easy" | "moderate" | "difficult",
  "warnings": ["warning1", "warning2", ...]
}}

Keep steps concise but complete. Include safety warnings."""

        try:
            response = await llm_generate(prompt, max_tokens=1000, temperature=0.3)
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = display_name
                steps_text = "\n".join(data.get("steps", []))
                data["content_text"] = f"{display_name}\n\n{steps_text}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
                
        except Exception as e:
            print(f"❌ LLM error for procedure:{component}: {e}")
        
        return {
            "title": display_name,
            "steps": ["Refer to factory service manual for complete procedure."],
            "tools_required": [],
            "estimated_time": "Varies",
            "content_text": f"{display_name}: Refer to factory service manual",
            "sources": [],
            "confidence": 0.0,
        }
    
    async def _generate_part_location(
        self, 
        vehicle_key: str, 
        component: str
    ) -> Dict[str, Any]:
        """Generate part location information."""
        
        parts = vehicle_key.split("_")
        year = parts[0]
        make = parts[1].title()
        model = "_".join(parts[2:-1]).replace("_", " ").title() if len(parts) > 3 else parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        location_names = {
            "oil_filter": "Oil Filter",
            "oil_drain_plug": "Oil Drain Plug",
            "obd_port": "OBD-II Port",
            "fuse_box": "Fuse Box",
            "battery": "Battery",
        }
        
        display_name = location_names.get(component, component.replace("_", " ").title())
        
        prompt = f"""You are an automotive technician. Describe the location of this component.

Vehicle: {year} {make} {model} {engine}
Component: {display_name}

Respond in this EXACT JSON format:
{{
  "location_description": "<clear description of where to find this component>",
  "access_notes": "<how to access it, any panels to remove>",
  "visual_reference": "<nearby components for reference>"
}}

Be specific to this vehicle when possible."""

        try:
            response = await llm_generate(prompt, max_tokens=500, temperature=0.2)
            
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = f"{display_name} Location"
                data["content_text"] = f"{display_name}: {data.get('location_description', 'See manual')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.7
                return data
                
        except Exception as e:
            print(f"❌ LLM error for part_location:{component}: {e}")
        
        return {
            "title": f"{display_name} Location",
            "location_description": "Refer to owner's manual or service manual",
            "content_text": f"{display_name}: Location verification in progress",
            "sources": [],
            "confidence": 0.0,
        }
    
    async def _generate_generic(
        self, 
        vehicle_key: str, 
        chunk_type: str,
        component: str
    ) -> Dict[str, Any]:
        """Generic fallback generator for other chunk types."""
        
        parts = vehicle_key.split("_")
        year = parts[0]
        make = parts[1].title()
        model = parts[2].title() if len(parts) > 2 else ""
        engine = parts[-1] if len(parts) > 3 else ""
        
        # Route to specialized generators based on chunk type
        if chunk_type == "battery_spec":
            return await self._generate_battery_spec(vehicle_key)
        elif chunk_type == "tire_spec":
            return await self._generate_tire_spec(vehicle_key)
        elif chunk_type == "brake_spec":
            return await self._generate_brake_spec(vehicle_key, component)
        elif chunk_type == "diagnostic_info":
            return await self._generate_diagnostic_info(vehicle_key)
        elif chunk_type == "filter_spec":
            return await self._generate_filter_spec(vehicle_key, component)
        elif chunk_type == "wiper_spec":
            return await self._generate_wiper_spec(vehicle_key)
        elif chunk_type == "bulb_spec":
            return await self._generate_bulb_spec(vehicle_key, component)
        elif chunk_type == "jacking_point":
            return await self._generate_jacking_point(vehicle_key)
        elif chunk_type == "reset_procedure":
            return await self._generate_reset_procedure(vehicle_key, component)
        
        return {
            "title": f"{chunk_type}: {component}",
            "content_text": f"Data for {chunk_type}:{component} on {year} {make} {model} - verification in progress",
            "sources": [],
            "confidence": 0.0,
        }

    async def _generate_battery_spec(self, vehicle_key: str) -> Dict[str, Any]:
        """Generate battery specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        prompt = f"""Vehicle: {year} {make} {model} {engine}
Request: Battery specifications

Respond in this EXACT JSON format:
{{
  "group_size": "<BCI group size, e.g., 24F, 35, H6, 48>",
  "cca": <Cold Cranking Amps as number>,
  "terminal_type": "top_post" or "side_post",
  "hold_down_type": "<description>",
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=300, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = "Battery Specifications"
                data["voltage"] = 12
                data["content_text"] = f"Battery: Group {data.get('group_size', 'N/A')}, {data.get('cca', 'N/A')} CCA"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
        except Exception as e:
            print(f"❌ LLM error for battery_spec: {e}")
        
        return {"title": "Battery Specifications", "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_tire_spec(self, vehicle_key: str) -> Dict[str, Any]:
        """Generate tire specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        prompt = f"""Vehicle: {year} {make} {model} {engine}
Request: OEM tire specifications

Respond in this EXACT JSON format:
{{
  "size": "<tire size, e.g., 225/45R17>",
  "front_pressure_psi": <number>,
  "rear_pressure_psi": <number>,
  "lug_pattern": "<bolt pattern, e.g., 5x114.3>",
  "rotation_pattern": "front_to_rear" or "x_pattern" or "forward_cross",
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=300, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = "Tire Specifications"
                data["content_text"] = f"Tires: {data.get('size', 'N/A')}, {data.get('front_pressure_psi', 'N/A')} PSI"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
        except Exception as e:
            print(f"❌ LLM error for tire_spec: {e}")
        
        return {"title": "Tire Specifications", "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_brake_spec(self, vehicle_key: str, position: str) -> Dict[str, Any]:
        """Generate brake specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        prompt = f"""Vehicle: {year} {make} {model} {engine}
Request: {position.title()} brake specifications

Respond in this EXACT JSON format:
{{
  "rotor_diameter_mm": <number>,
  "rotor_min_thickness_mm": <minimum machining thickness>,
  "rotor_discard_thickness_mm": <discard thickness>,
  "pad_min_thickness_mm": <minimum pad thickness, typically 2-3mm>,
  "is_vented": true or false,
  "has_wear_sensor": true or false,
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=300, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = f"{position.title()} Brake Specifications"
                data["position"] = position
                data["content_text"] = f"{position.title()} Brakes: Min rotor {data.get('rotor_min_thickness_mm', 'N/A')}mm, Min pad {data.get('pad_min_thickness_mm', 'N/A')}mm"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.5  # Safety critical - lower confidence
                return data
        except Exception as e:
            print(f"❌ LLM error for brake_spec: {e}")
        
        return {"title": f"{position.title()} Brake Specifications", "position": position, "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_diagnostic_info(self, vehicle_key: str) -> Dict[str, Any]:
        """Generate OBD and diagnostic information."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        
        prompt = f"""Vehicle: {year} {make} {model}
Request: OBD-II port location and diagnostic info

Respond in this EXACT JSON format:
{{
  "obd_location": "<exact location, e.g., Under dash, left of steering column>",
  "obd_protocol": "CAN",
  "common_codes": [
    {{"code": "P0xxx", "description": "Common issue description"}}
  ],
  "notes": "<any important diagnostic notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=400, temperature=0.1)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = "Diagnostic Information"
                data["content_text"] = f"OBD Port: {data.get('obd_location', 'Under dashboard')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.7
                return data
        except Exception as e:
            print(f"❌ LLM error for diagnostic_info: {e}")
        
        return {"title": "Diagnostic Information", "obd_location": "Under dashboard, driver side", "content_text": "OBD Port: Under dashboard", "sources": [], "confidence": 0.3}

    async def _generate_filter_spec(self, vehicle_key: str, filter_type: str) -> Dict[str, Any]:
        """Generate filter specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        engine = parts[-1] if len(parts) > 3 else ""
        
        filter_names = {"engine_air": "Engine Air Filter", "cabin_air": "Cabin Air Filter", "fuel": "Fuel Filter"}
        display = filter_names.get(filter_type, filter_type.replace("_", " ").title())
        
        prompt = f"""Vehicle: {year} {make} {model} {engine}
Request: {display} specifications

Respond in this EXACT JSON format:
{{
  "oem_part_number": "<OEM part number>",
  "common_aftermarket": ["<aftermarket part number>"],
  "location_description": "<where the filter is located>",
  "replacement_difficulty": "easy" or "moderate" or "hard",
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=300, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = display
                data["filter_type"] = filter_type
                data["content_text"] = f"{display}: {data.get('location_description', 'See manual')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
        except Exception as e:
            print(f"❌ LLM error for filter_spec: {e}")
        
        return {"title": display, "filter_type": filter_type, "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_wiper_spec(self, vehicle_key: str) -> Dict[str, Any]:
        """Generate wiper blade specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        
        prompt = f"""Vehicle: {year} {make} {model}
Request: Wiper blade sizes

Respond in this EXACT JSON format:
{{
  "driver_length_inches": <number>,
  "passenger_length_inches": <number>,
  "rear_length_inches": <number or null if no rear wiper>,
  "attachment_type": "j_hook" or "pinch_tab" or "bayonet" or "push_button",
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=200, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = "Wiper Blade Specifications"
                data["content_text"] = f"Wipers: Driver {data.get('driver_length_inches', 'N/A')}\", Passenger {data.get('passenger_length_inches', 'N/A')}\""
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.7
                return data
        except Exception as e:
            print(f"❌ LLM error for wiper_spec: {e}")
        
        return {"title": "Wiper Blade Specifications", "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_bulb_spec(self, vehicle_key: str, light_type: str) -> Dict[str, Any]:
        """Generate light bulb specifications."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        
        light_names = {
            "headlight_low": "Low Beam Headlight",
            "headlight_high": "High Beam Headlight",
            "fog": "Fog Light",
            "brake": "Brake Light",
            "turn_front": "Front Turn Signal",
            "turn_rear": "Rear Turn Signal",
        }
        display = light_names.get(light_type, light_type.replace("_", " ").title())
        
        prompt = f"""Vehicle: {year} {make} {model}
Request: {display} bulb type

Respond in this EXACT JSON format:
{{
  "bulb_type": "<bulb type, e.g., H11, 9005, 7443>",
  "wattage": <number or null>,
  "is_led_oem": true or false,
  "replacement_difficulty": "easy" or "moderate" or "hard",
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=200, temperature=0.1)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = display
                data["light_type"] = light_type
                data["content_text"] = f"{display}: {data.get('bulb_type', 'N/A')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
        except Exception as e:
            print(f"❌ LLM error for bulb_spec: {e}")
        
        return {"title": display, "light_type": light_type, "content_text": "Verification in progress", "sources": [], "confidence": 0.0}

    async def _generate_jacking_point(self, vehicle_key: str) -> Dict[str, Any]:
        """Generate safe jacking point locations."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        
        prompt = f"""Vehicle: {year} {make} {model}
Request: Safe jacking and jack stand points

Respond in this EXACT JSON format:
{{
  "front_jack_point": "<where to place jack at front>",
  "rear_jack_point": "<where to place jack at rear>",
  "front_stand_points": "<where to place jack stands at front>",
  "rear_stand_points": "<where to place jack stands at rear>",
  "pinch_weld_safe": true or false,
  "warnings": ["<any safety warnings>"],
  "notes": "<any important notes>"
}}

CRITICAL: Safety information. Only provide if CERTAIN."""

        try:
            response = await llm_generate(prompt, max_tokens=400, temperature=0.1)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = "Jacking Points"
                data["content_text"] = f"Front: {data.get('front_jack_point', 'See manual')}, Rear: {data.get('rear_jack_point', 'See manual')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.4  # Safety critical - requires verification
                return data
        except Exception as e:
            print(f"❌ LLM error for jacking_point: {e}")
        
        return {
            "title": "Jacking Points",
            "front_jack_point": "Refer to owner's manual",
            "rear_jack_point": "Refer to owner's manual",
            "content_text": "SAFETY: Always refer to owner's manual for jack points",
            "warnings": ["Always use jack stands", "Never work under a vehicle supported only by a jack"],
            "sources": [],
            "confidence": 0.0,
        }

    async def _generate_reset_procedure(self, vehicle_key: str, system: str) -> Dict[str, Any]:
        """Generate service light reset procedures."""
        parts = vehicle_key.split("_")
        year, make, model = parts[0], parts[1].title(), parts[2].title()
        
        system_names = {
            "oil_life": "Oil Life Monitor",
            "tire_pressure": "TPMS",
            "maintenance_required": "Maintenance Required Light",
        }
        display = system_names.get(system, system.replace("_", " ").title())
        
        prompt = f"""Vehicle: {year} {make} {model}
Request: How to reset the {display}

Respond in this EXACT JSON format:
{{
  "method": "button_sequence" or "dash_menu" or "obd_tool",
  "steps": ["Step 1...", "Step 2...", "Step 3..."],
  "requires_obd": true or false,
  "notes": "<any important notes>"
}}

Only provide data you are CERTAIN about."""

        try:
            response = await llm_generate(prompt, max_tokens=400, temperature=0.1)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                data["title"] = f"{display} Reset Procedure"
                data["system"] = system
                data["content_text"] = f"Reset {display}: {data.get('method', 'See manual')}"
                data["sources"] = ["LLM Generation - Verify before use"]
                data["confidence"] = 0.6
                return data
        except Exception as e:
            print(f"❌ LLM error for reset_procedure: {e}")
        
        return {"title": f"{display} Reset Procedure", "system": system, "content_text": "Verification in progress", "sources": [], "confidence": 0.0}


# Singleton instance
_generator: Optional[DeterministicChunkGenerator] = None


def get_deterministic_generator() -> DeterministicChunkGenerator:
    """Get singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = DeterministicChunkGenerator()
    return _generator
