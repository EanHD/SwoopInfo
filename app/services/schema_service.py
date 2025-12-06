"""
Schema Service - Single source of truth for chunk types, components, and job mappings.
Loads and validates all schema definitions from assets/data/*.json

The Three Laws of SwoopInfo:
1. AI fills VALUES, never KEYS
2. content_id = {chunk_type}:{component} - deterministic, never AI-generated
3. Cache is king - never regenerate what exists
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from functools import lru_cache


# Paths to schema files
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "data"
CHUNK_TYPES_FILE = ASSETS_DIR / "chunk_types.json"
COMPONENTS_FILE = ASSETS_DIR / "components.json"
JOB_CHUNK_MAP_FILE = ASSETS_DIR / "job_chunk_map.json"


class SchemaService:
    """
    Manages all schema definitions for SwoopInfo.
    
    This is the gatekeeper - no chunk can be created without
    matching a valid chunk_type and component from these schemas.
    """
    
    def __init__(self):
        self._chunk_types: Dict = {}
        self._components: Dict = {}
        self._job_chunk_map: Dict = {}
        self._loaded = False
    
    def load(self) -> None:
        """Load all schema files from disk."""
        if self._loaded:
            return
            
        try:
            # Load chunk types
            if CHUNK_TYPES_FILE.exists():
                with open(CHUNK_TYPES_FILE, "r") as f:
                    data = json.load(f)
                    # Remove metadata fields
                    self._chunk_types = {k: v for k, v in data.items() if not k.startswith("_")}
                print(f"✅ Loaded {len(self._chunk_types)} chunk types")
            else:
                print(f"⚠️ Chunk types file not found: {CHUNK_TYPES_FILE}")
            
            # Load components
            if COMPONENTS_FILE.exists():
                with open(COMPONENTS_FILE, "r") as f:
                    data = json.load(f)
                    self._components = {k: v for k, v in data.items() if not k.startswith("_")}
                print(f"✅ Loaded component categories: {list(self._components.keys())}")
            else:
                print(f"⚠️ Components file not found: {COMPONENTS_FILE}")
            
            # Load job chunk map
            if JOB_CHUNK_MAP_FILE.exists():
                with open(JOB_CHUNK_MAP_FILE, "r") as f:
                    data = json.load(f)
                    self._job_chunk_map = {k: v for k, v in data.items() if not k.startswith("_")}
                print(f"✅ Loaded {len(self._job_chunk_map)} job types")
            else:
                print(f"⚠️ Job chunk map file not found: {JOB_CHUNK_MAP_FILE}")
            
            self._loaded = True
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse error: {e}")
            raise
        except Exception as e:
            print(f"❌ Schema load error: {e}")
            raise
    
    def ensure_loaded(self) -> None:
        """Ensure schemas are loaded."""
        if not self._loaded:
            self.load()
    
    # =========================================================
    # CHUNK TYPES
    # =========================================================
    
    def get_chunk_type(self, type_name: str) -> Optional[Dict]:
        """Get definition for a chunk type."""
        self.ensure_loaded()
        return self._chunk_types.get(type_name)
    
    def get_all_chunk_types(self) -> Dict:
        """Get all chunk type definitions."""
        self.ensure_loaded()
        return self._chunk_types
    
    def is_valid_chunk_type(self, type_name: str) -> bool:
        """Check if a chunk type is valid."""
        self.ensure_loaded()
        return type_name in self._chunk_types
    
    def get_required_fields(self, type_name: str) -> List[str]:
        """Get required fields for a chunk type."""
        self.ensure_loaded()
        chunk_type = self._chunk_types.get(type_name, {})
        fields = chunk_type.get("fields", {})
        return [k for k, v in fields.items() if v.get("required", False)]
    
    def get_safety_critical_types(self) -> List[str]:
        """Get chunk types marked as safety critical."""
        self.ensure_loaded()
        return [
            k for k, v in self._chunk_types.items()
            if v.get("safety_critical", False)
        ]
    
    # =========================================================
    # COMPONENTS
    # =========================================================
    
    def get_components(self, category: str) -> List[str]:
        """Get all components for a category (e.g., 'fluids', 'torque_components')."""
        self.ensure_loaded()
        return list(self._components.get(category, {}).keys())
    
    def get_component_info(self, category: str, component: str) -> Optional[Dict]:
        """Get info for a specific component."""
        self.ensure_loaded()
        return self._components.get(category, {}).get(component)
    
    def is_valid_component(self, category: str, component: str) -> bool:
        """Check if a component is valid for a category."""
        self.ensure_loaded()
        return component in self._components.get(category, {})
    
    def get_all_valid_components(self) -> Set[str]:
        """Get all valid component names across all categories."""
        self.ensure_loaded()
        all_components = set()
        for category_data in self._components.values():
            if isinstance(category_data, dict):
                all_components.update(category_data.keys())
        return all_components
    
    # =========================================================
    # CONTENT ID VALIDATION
    # =========================================================
    
    def is_valid_content_id(self, content_id: str) -> bool:
        """
        Validate a content_id against schemas.
        Format: {chunk_type}:{component}
        """
        self.ensure_loaded()
        
        if ":" not in content_id:
            return False
        
        parts = content_id.split(":", 1)
        if len(parts) != 2:
            return False
        
        chunk_type, component = parts
        
        # Check chunk type is valid
        if not self.is_valid_chunk_type(chunk_type):
            return False
        
        # Some chunk types have fixed component values (not from registry)
        # These are defined in the content_id_pattern in chunk_types.json
        fixed_component_types = {
            "battery_spec": ["main"],
            "tire_spec": ["oem"],
            "jacking_point": ["location"],
            "wiper_spec": ["blades"],
            "diagnostic_info": ["obd"],
            "firing_order": ["engine"],
            "belt_routing": ["serpentine"],
        }
        
        if chunk_type in fixed_component_types:
            return component in fixed_component_types[chunk_type]
        
        # Check component is valid for this chunk type's component category
        chunk_def = self._chunk_types.get(chunk_type, {})
        component_category = chunk_def.get("component_category")
        
        if component_category:
            return self.is_valid_component(component_category, component)
        
        # If no component category specified, component can be any valid component
        return component in self.get_all_valid_components()
    
    def get_content_id_parts(self, content_id: str) -> tuple:
        """Parse content_id into (chunk_type, component)."""
        if ":" not in content_id:
            return (content_id, None)
        return tuple(content_id.split(":", 1))
    
    # =========================================================
    # JOB MAPPINGS
    # =========================================================
    
    def get_job_types(self) -> List[str]:
        """Get all job types."""
        self.ensure_loaded()
        return list(self._job_chunk_map.keys())
    
    def get_job_info(self, job_type: str) -> Optional[Dict]:
        """Get info for a job type including required chunks."""
        self.ensure_loaded()
        return self._job_chunk_map.get(job_type)
    
    def get_required_chunks_for_job(self, job_type: str) -> List[str]:
        """Get list of content_ids required for a job type."""
        self.ensure_loaded()
        job_info = self._job_chunk_map.get(job_type, {})
        return job_info.get("chunks", [])
    
    def get_jobs_requiring_component(self, component: str) -> List[str]:
        """Find all jobs that require a specific component."""
        self.ensure_loaded()
        jobs = []
        for job_type, job_info in self._job_chunk_map.items():
            chunks = job_info.get("chunks", [])
            if any(component in chunk for chunk in chunks):
                jobs.append(job_type)
        return jobs
    
    # =========================================================
    # SCHEMA VALIDATION FOR CHUNK DATA
    # =========================================================
    
    def validate_chunk_data(self, chunk_type: str, data: Dict) -> tuple:
        """
        Validate chunk data against schema.
        Returns (is_valid, errors).
        """
        self.ensure_loaded()
        
        errors = []
        chunk_def = self._chunk_types.get(chunk_type)
        
        if not chunk_def:
            return False, [f"Unknown chunk type: {chunk_type}"]
        
        fields = chunk_def.get("fields", {})
        
        # Check required fields
        for field_name, field_def in fields.items():
            if field_def.get("required", False):
                if field_name not in data:
                    errors.append(f"Missing required field: {field_name}")
                elif data[field_name] is None or data[field_name] == "":
                    errors.append(f"Empty required field: {field_name}")
        
        # Type validation
        for field_name, field_def in fields.items():
            if field_name in data and data[field_name] is not None:
                field_type = field_def.get("type")
                value = data[field_name]
                
                if field_type == "float" and not isinstance(value, (int, float)):
                    errors.append(f"Field {field_name} must be a number")
                elif field_type == "string" and not isinstance(value, str):
                    errors.append(f"Field {field_name} must be a string")
                elif field_type == "list" and not isinstance(value, list):
                    errors.append(f"Field {field_name} must be a list")
        
        return len(errors) == 0, errors


# Singleton instance
_schema_service: Optional[SchemaService] = None


def get_schema_service() -> SchemaService:
    """Get the singleton schema service instance."""
    global _schema_service
    if _schema_service is None:
        _schema_service = SchemaService()
        _schema_service.load()
    return _schema_service


# Convenience functions
@lru_cache(maxsize=1000)
def is_valid_content_id(content_id: str) -> bool:
    """Check if content_id is valid (cached)."""
    return get_schema_service().is_valid_content_id(content_id)


def get_required_chunks_for_job(job_type: str) -> List[str]:
    """Get chunks required for a job type."""
    return get_schema_service().get_required_chunks_for_job(job_type)


def validate_chunk_type(chunk_type: str) -> bool:
    """Check if chunk type is valid."""
    return get_schema_service().is_valid_chunk_type(chunk_type)
