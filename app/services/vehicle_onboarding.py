"""
Vehicle Onboarding Service - Prepare chunk data for new vehicles.

When a customer books a service:
1. Check what chunks already exist for the vehicle
2. Identify what's missing based on the job type
3. Generate ONLY missing chunks
4. Never regenerate existing data

This is the "Cache is King" principle in action.
"""

import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

from services.schema_service import get_schema_service
from services.content_id_generator import (
    normalize_vehicle_key,
    get_chunks_for_job,
    get_missing_chunks_for_job,
    parse_content_id,
)
from services.supabase_client import SupabaseService


@dataclass
class OnboardingResult:
    """Result of a vehicle onboarding operation."""
    vehicle_key: str
    job_type: Optional[str]
    chunks_required: int
    chunks_existing: int
    chunks_generated: int
    chunks_failed: int
    errors: List[str]
    duration_ms: int


@dataclass
class ChunkStatus:
    """Status of a chunk for a vehicle."""
    content_id: str
    exists: bool
    verified: bool
    verification_status: str
    needs_generation: bool


class VehicleOnboardingService:
    """
    Manages the process of ensuring all necessary chunks exist for a vehicle.
    """
    
    def __init__(self, supabase: SupabaseService):
        self.supabase = supabase
        self.schema = get_schema_service()
    
    async def get_vehicle_status(self, vehicle_key: str) -> Dict[str, Any]:
        """
        Get comprehensive status for a vehicle's chunks.
        
        Returns info about what chunks exist, verification status, etc.
        """
        chunks = await self.supabase.get_chunks_for_vehicle(vehicle_key)
        
        # Group by verification status
        by_status = {
            "verified": [],
            "candidate": [],
            "unverified": [],
            "banned": [],
        }
        
        for chunk in chunks:
            status = chunk.verified_status or "unverified"
            if status in by_status:
                by_status[status].append(chunk.content_id)
            else:
                by_status["unverified"].append(chunk.content_id)
        
        # Get all unique content_ids
        existing_ids = {chunk.content_id for chunk in chunks}
        
        return {
            "vehicle_key": vehicle_key,
            "total_chunks": len(chunks),
            "chunks_by_status": by_status,
            "existing_content_ids": list(existing_ids),
            "chunk_types": list({chunk.chunk_type for chunk in chunks}),
        }
    
    async def check_job_readiness(
        self, 
        vehicle_key: str, 
        job_type: str
    ) -> Dict[str, Any]:
        """
        Check if a vehicle is ready for a specific job.
        
        Returns what chunks exist, what's missing, and what needs to be generated.
        """
        # Get required chunks for this job
        required_ids = get_chunks_for_job(job_type)
        
        if not required_ids:
            return {
                "vehicle_key": vehicle_key,
                "job_type": job_type,
                "error": f"Unknown job type or no chunks defined: {job_type}",
                "ready": False,
            }
        
        # Get existing chunks
        existing_chunks = await self.supabase.get_chunks_for_vehicle(vehicle_key)
        existing_ids = {chunk.content_id for chunk in existing_chunks}
        
        # Categorize
        present = []
        missing = []
        unverified = []
        
        for content_id in required_ids:
            if content_id in existing_ids:
                # Find the chunk
                chunk = next((c for c in existing_chunks if c.content_id == content_id), None)
                if chunk:
                    if chunk.verified_status == "verified":
                        present.append(content_id)
                    else:
                        unverified.append(content_id)
                else:
                    present.append(content_id)  # Exists but couldn't find details
            else:
                missing.append(content_id)
        
        ready = len(missing) == 0
        confidence = len(present) / len(required_ids) if required_ids else 1.0
        
        return {
            "vehicle_key": vehicle_key,
            "job_type": job_type,
            "ready": ready,
            "confidence": round(confidence, 2),
            "chunks": {
                "required": required_ids,
                "present_verified": present,
                "present_unverified": unverified,
                "missing": missing,
            },
            "summary": {
                "total_required": len(required_ids),
                "verified": len(present),
                "unverified": len(unverified),
                "missing": len(missing),
            }
        }
    
    async def get_generation_queue(
        self,
        vehicle_key: str,
        job_type: Optional[str] = None,
        include_unverified: bool = False
    ) -> List[str]:
        """
        Get list of content_ids that need to be generated.
        
        Args:
            vehicle_key: The vehicle to check
            job_type: If provided, only check chunks for this job
            include_unverified: If True, include unverified chunks for regeneration
        
        Returns:
            List of content_ids that need generation
        """
        # Get existing chunks
        existing_chunks = await self.supabase.get_chunks_for_vehicle(vehicle_key)
        
        # Build set of existing content_ids
        if include_unverified:
            # Only count verified chunks as "existing"
            existing_ids = {
                chunk.content_id 
                for chunk in existing_chunks 
                if chunk.verified_status in ["verified", "candidate"]
            }
        else:
            # All chunks count as existing (don't regenerate)
            existing_ids = {chunk.content_id for chunk in existing_chunks}
        
        # Determine what's required
        if job_type:
            required_ids = set(get_chunks_for_job(job_type))
        else:
            # No job specified - can't determine what's needed
            return []
        
        # Return what's missing
        return list(required_ids - existing_ids)
    
    async def prepare_for_booking(
        self,
        year: int,
        make: str,
        model: str,
        engine: Optional[str],
        job_type: str,
    ) -> Dict[str, Any]:
        """
        Prepare a vehicle for a booking.
        
        This is called when a customer books a service.
        It checks what chunks exist and queues generation for missing ones.
        
        Args:
            year, make, model, engine: Vehicle info
            job_type: Type of job being booked (e.g., "oil_change")
        
        Returns:
            Status dict with readiness info and generation queue
        """
        # Normalize vehicle key
        vehicle_key = normalize_vehicle_key(year, make, model, engine)
        
        # Check current status
        readiness = await self.check_job_readiness(vehicle_key, job_type)
        
        # If chunks are missing, create generation queue
        generation_queue = []
        if not readiness["ready"]:
            generation_queue = readiness["chunks"]["missing"]
        
        # Register/update vehicle in swoopinfo_vehicles table
        await self._register_vehicle(year, make, model, engine, vehicle_key, "booking")
        
        return {
            "vehicle_key": vehicle_key,
            "job_type": job_type,
            "ready": readiness["ready"],
            "confidence": readiness["confidence"],
            "generation_queue": generation_queue,
            "existing_chunks": readiness["chunks"]["present_verified"] + readiness["chunks"]["present_unverified"],
            "summary": readiness["summary"],
        }
    
    async def _register_vehicle(
        self,
        year: int,
        make: str,
        model: str,
        engine: Optional[str],
        vehicle_key: str,
        source: str
    ) -> None:
        """Register or update a vehicle in the registry."""
        try:
            # Check if vehicle exists
            result = (
                self.supabase.client.table("swoopinfo_vehicles")
                .select("id, chunks_total")
                .eq("vehicle_key", vehicle_key)
                .execute()
            )
            
            # Get current chunk count
            chunks = await self.supabase.get_chunks_for_vehicle(vehicle_key)
            chunk_count = len(chunks)
            verified_count = sum(1 for c in chunks if c.verified_status == "verified")
            
            if result.data and len(result.data) > 0:
                # Update existing
                self.supabase.client.table("swoopinfo_vehicles").update({
                    "chunks_total": chunk_count,
                    "chunks_verified": verified_count,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("vehicle_key", vehicle_key).execute()
            else:
                # Insert new
                self.supabase.client.table("swoopinfo_vehicles").insert({
                    "vehicle_key": vehicle_key,
                    "year": year,
                    "make": make.lower(),
                    "model": model.lower(),
                    "engine": engine.lower() if engine else None,
                    "status": "pending",
                    "chunks_total": chunk_count,
                    "chunks_verified": verified_count,
                    "source": source,
                }).execute()
                
        except Exception as e:
            print(f"⚠️ Failed to register vehicle: {e}")
            # Non-critical, don't raise


# =========================================================
# BATCH OPERATIONS
# =========================================================

async def get_popular_vehicles() -> List[Dict]:
    """
    Get list of popular vehicles to prioritize for data generation.
    
    This returns vehicles that are common in the target market
    and should be pre-populated with data.
    """
    # These are common vehicles in the Central Valley / Los Baños area
    return [
        {"year": 2019, "make": "honda", "model": "accord", "engine": "2.0t"},
        {"year": 2019, "make": "honda", "model": "accord", "engine": "1.5t"},
        {"year": 2020, "make": "honda", "model": "civic", "engine": "2.0l"},
        {"year": 2018, "make": "toyota", "model": "camry", "engine": "2.5l"},
        {"year": 2019, "make": "toyota", "model": "camry", "engine": "3.5l_v6"},
        {"year": 2017, "make": "toyota", "model": "corolla", "engine": "1.8l"},
        {"year": 2018, "make": "ford", "model": "f-150", "engine": "5.0l"},
        {"year": 2019, "make": "ford", "model": "f-150", "engine": "3.5l_ecoboost"},
        {"year": 2018, "make": "chevrolet", "model": "silverado", "engine": "5.3l"},
        {"year": 2020, "make": "chevrolet", "model": "equinox", "engine": "1.5t"},
        {"year": 2019, "make": "nissan", "model": "altima", "engine": "2.5l"},
        {"year": 2018, "make": "nissan", "model": "rogue", "engine": "2.5l"},
        {"year": 2017, "make": "hyundai", "model": "elantra", "engine": "2.0l"},
        {"year": 2019, "make": "hyundai", "model": "sonata", "engine": "2.4l"},
        {"year": 2018, "make": "kia", "model": "optima", "engine": "2.4l"},
        {"year": 2020, "make": "mazda", "model": "mazda3", "engine": "2.5l"},
        {"year": 2019, "make": "subaru", "model": "outback", "engine": "2.5l"},
        {"year": 2018, "make": "volkswagen", "model": "jetta", "engine": "1.4t"},
        {"year": 2019, "make": "jeep", "model": "grand_cherokee", "engine": "3.6l_v6"},
        {"year": 2020, "make": "ram", "model": "1500", "engine": "5.7l_hemi"},
    ]


async def get_common_jobs() -> List[str]:
    """Get list of common job types to prioritize."""
    return [
        "oil_change",
        "brake_pads_front",
        "brake_pads_rear",
        "brake_pads_rotors_front",
        "brake_pads_rotors_rear",
        "spark_plugs",
        "coolant_flush",
        "transmission_service",
    ]


async def batch_check_readiness(
    supabase: SupabaseService,
    vehicles: List[Dict],
    job_type: str
) -> Dict[str, Any]:
    """
    Check readiness for multiple vehicles at once.
    
    Useful for planning batch generation runs.
    """
    service = VehicleOnboardingService(supabase)
    results = []
    
    for vehicle in vehicles:
        vehicle_key = normalize_vehicle_key(
            vehicle["year"],
            vehicle["make"],
            vehicle["model"],
            vehicle.get("engine")
        )
        
        readiness = await service.check_job_readiness(vehicle_key, job_type)
        results.append({
            "vehicle_key": vehicle_key,
            "ready": readiness["ready"],
            "missing_count": len(readiness["chunks"]["missing"]),
        })
    
    # Summary stats
    ready_count = sum(1 for r in results if r["ready"])
    total_missing = sum(r["missing_count"] for r in results)
    
    return {
        "job_type": job_type,
        "vehicles_checked": len(vehicles),
        "vehicles_ready": ready_count,
        "total_missing_chunks": total_missing,
        "details": results,
    }
