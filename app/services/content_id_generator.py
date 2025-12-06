"""
Content ID Generator - Deterministic chunk identification.

The Golden Rule: AI fills VALUES, never KEYS.
Content IDs are ALWAYS deterministic, NEVER AI-generated.

Format: {chunk_type}:{component}
Examples:
  - fluid_capacity:engine_oil
  - torque_spec:drain_plug
  - procedure:oil_change
"""

import re
from typing import Optional, List, Tuple
from services.schema_service import get_schema_service, SchemaService


def normalize_vehicle_key(
    year: int, 
    make: str, 
    model: str, 
    engine: Optional[str] = None
) -> str:
    """
    Create standardized vehicle key from vehicles.json format.
    
    CRITICAL: This must produce consistent keys that match what the 
    frontend sends from the booking flow.
    
    Format: {year}_{make}_{model}_{engine}
    
    Model Cleanup (handles vehicles.json format):
    - "Aveo (T200/T250)" → "aveo"
    - "F-150 (Eleventh generation)" → "f-150"
    - "Civic (Eighth generation, North America)" → "civic"
    
    Engine Cleanup (extracts displacement):
    - "1.6L Ecotec I4 (108 hp)" → "1.6l"
    - "5.4L Triton V8" → "5.4l"
    - "2.0L K20Z3 i-VTEC I4 (Si)" → "2.0l"
    - "3.5L V6 EcoBoost" → "3.5l_ecoboost"
    
    Examples:
    - 2007, Chevrolet, "Aveo (T200/T250)", "1.6L Ecotec I4" → "2007_chevrolet_aveo_1.6l"
    - 2019, Honda, Accord, "2.0T" → "2019_honda_accord_2.0t"
    - 2018, Ford, "F-150", "5.0L Coyote V8" → "2018_ford_f-150_5.0l"
    """
    # Clean make
    make_clean = _normalize_component(make)
    
    # Clean model - strip generation info in parentheses
    model_clean = _clean_model_name(model)
    
    if engine:
        # Clean engine - extract displacement and key features
        engine_clean = _clean_engine_name(engine)
        return f"{year}_{make_clean}_{model_clean}_{engine_clean}"
    else:
        return f"{year}_{make_clean}_{model_clean}"


def _clean_model_name(model: str) -> str:
    """
    Clean model name from vehicles.json format.
    
    Removes generation info and parenthetical descriptors.
    "Aveo (T200/T250)" → "aveo"
    "F-150 (Eleventh generation)" → "f-150"
    "Civic (Eighth generation, North America)" → "civic"
    "Camry" → "camry"
    """
    if not model:
        return ""
    
    # Remove anything in parentheses (generation info)
    cleaned = re.sub(r'\s*\([^)]*\)', '', model)
    
    # Basic normalization
    return _normalize_component(cleaned)


def _clean_engine_name(engine: str) -> str:
    """
    Clean engine name from vehicles.json format.
    
    Extracts displacement and key features (turbo, ecoboost, etc).
    
    "1.6L Ecotec I4 (108 hp)" → "1.6l"
    "5.4L Triton V8" → "5.4l"
    "2.0L K20Z3 i-VTEC I4 (Si)" → "2.0l"
    "3.5L V6 EcoBoost" → "3.5l_ecoboost"
    "2.0T" → "2.0t"
    "2.7L EcoBoost V6" → "2.7l_ecoboost"
    "5.0L Coyote V8" → "5.0l"
    "1.5L Turbo" → "1.5t"
    """
    if not engine:
        return ""
    
    engine_lower = engine.lower().strip()
    
    # Extract displacement (e.g., "2.0l", "3.5l", "5.4l")
    displacement_match = re.search(r'(\d+\.?\d*)\s*l', engine_lower)
    if not displacement_match:
        # Try matching just numbers with t (turbo shorthand)
        turbo_match = re.search(r'(\d+\.?\d*)t', engine_lower)
        if turbo_match:
            return f"{turbo_match.group(1)}t"
        # Fallback to basic normalization
        return _normalize_component(engine)
    
    displacement = displacement_match.group(1)
    
    # Check for turbo indicators
    # Note: "ecotec" is GM's NA engine line, NOT turbo
    # "ecoboost" is Ford's TURBO line
    turbo_keywords = ['turbo', 'ecoboost', 'tsi', 'tfsi', 'turbocharged']
    is_turbo = any(t in engine_lower for t in turbo_keywords)
    is_specifically_t = re.search(r'\d+\.?\d*t\b', engine_lower)  # "2.0T" style
    
    # Check for EcoBoost (Ford's branding, worth keeping)
    is_ecoboost = 'ecoboost' in engine_lower
    
    # Build the engine key
    if is_specifically_t or (is_turbo and not is_ecoboost):
        return f"{displacement}t"
    elif is_ecoboost:
        return f"{displacement}l_ecoboost"
    else:
        return f"{displacement}l"


def _normalize_component(value: str) -> str:
    """Normalize a component value for use in keys."""
    if not value:
        return ""
    
    # Lowercase
    result = value.lower().strip()
    
    # Replace spaces with underscores
    result = result.replace(" ", "_")
    
    # Keep alphanumeric, underscores, hyphens, and dots
    result = re.sub(r"[^a-z0-9_\-.]", "", result)
    
    # Collapse multiple underscores
    result = re.sub(r"_+", "_", result)
    
    # Remove leading/trailing underscores
    result = result.strip("_")
    
    return result


def build_content_id(chunk_type: str, component: str) -> str:
    """
    Build a content_id from chunk type and component.
    
    This is THE ONLY way to create content_ids.
    AI cannot create these - they come from our schemas.
    
    Args:
        chunk_type: Type from chunk_types.json (e.g., "fluid_capacity")
        component: Component from components.json (e.g., "engine_oil")
    
    Returns:
        Content ID string (e.g., "fluid_capacity:engine_oil")
    
    Raises:
        ValueError: If chunk_type or component is invalid
    """
    schema = get_schema_service()
    
    # Validate chunk type
    if not schema.is_valid_chunk_type(chunk_type):
        raise ValueError(f"Invalid chunk type: {chunk_type}")
    
    # Normalize component
    component_clean = _normalize_component(component)
    
    # Build content_id
    content_id = f"{chunk_type}:{component_clean}"
    
    # Final validation
    if not schema.is_valid_content_id(content_id):
        # Log warning but allow - component might be new/unlisted
        print(f"⚠️ Content ID not in schema (may be valid): {content_id}")
    
    return content_id


def parse_content_id(content_id: str) -> Tuple[str, str]:
    """
    Parse a content_id into its components.
    
    Args:
        content_id: Full content ID (e.g., "fluid_capacity:engine_oil")
    
    Returns:
        Tuple of (chunk_type, component)
    
    Raises:
        ValueError: If content_id format is invalid
    """
    if ":" not in content_id:
        raise ValueError(f"Invalid content_id format (missing ':'): {content_id}")
    
    parts = content_id.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid content_id format: {content_id}")
    
    return (parts[0], parts[1])


def get_chunks_for_job(job_type: str) -> List[str]:
    """
    Get all content_ids required for a job type.
    
    These are the chunks that need to exist (or be generated)
    when a customer books this job type.
    
    Args:
        job_type: Job type from job_chunk_map.json (e.g., "oil_change")
    
    Returns:
        List of content_ids needed for this job
    """
    schema = get_schema_service()
    return schema.get_required_chunks_for_job(job_type)


def get_missing_chunks_for_job(
    job_type: str, 
    existing_content_ids: List[str]
) -> List[str]:
    """
    Get content_ids that are required for a job but don't exist yet.
    
    This is used when prepping for a booking - we find what's missing
    and only generate those chunks.
    
    Args:
        job_type: Job type (e.g., "oil_change")
        existing_content_ids: Content IDs that already exist for the vehicle
    
    Returns:
        List of content_ids that need to be generated
    """
    required = set(get_chunks_for_job(job_type))
    existing = set(existing_content_ids)
    return list(required - existing)


def validate_content_id(content_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a content_id against schemas.
    
    Args:
        content_id: Content ID to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not content_id:
        return False, "Content ID cannot be empty"
    
    if ":" not in content_id:
        return False, "Content ID must contain ':' separator"
    
    try:
        chunk_type, component = parse_content_id(content_id)
    except ValueError as e:
        return False, str(e)
    
    schema = get_schema_service()
    
    if not schema.is_valid_chunk_type(chunk_type):
        return False, f"Unknown chunk type: {chunk_type}"
    
    # Component validation is more flexible - warn but allow
    if not schema.is_valid_content_id(content_id):
        # Return True with warning - component might be new
        return True, f"Warning: Component '{component}' not in schema"
    
    return True, None


def build_chunk_key(vehicle_key: str, content_id: str) -> str:
    """
    Build a unique key for a chunk (vehicle + content).
    
    This is used for caching and deduplication.
    
    Format: {vehicle_key}::{content_id}
    Example: "2019_honda_accord_2.0t::fluid_capacity:engine_oil"
    """
    return f"{vehicle_key}::{content_id}"


def parse_chunk_key(chunk_key: str) -> Tuple[str, str]:
    """
    Parse a chunk key into vehicle_key and content_id.
    
    Args:
        chunk_key: Full chunk key
    
    Returns:
        Tuple of (vehicle_key, content_id)
    """
    if "::" not in chunk_key:
        raise ValueError(f"Invalid chunk key format: {chunk_key}")
    
    parts = chunk_key.split("::", 1)
    return (parts[0], parts[1])


# =========================================================
# COMMON CHUNK GENERATION HELPERS
# =========================================================

def get_oil_change_chunks() -> List[str]:
    """Get content_ids for oil change service."""
    return get_chunks_for_job("oil_change")


def get_brake_job_chunks(position: str = "front") -> List[str]:
    """Get content_ids for brake job."""
    job_type = f"brake_pads_{position}"
    return get_chunks_for_job(job_type)


def get_all_fluid_content_ids() -> List[str]:
    """Get all fluid capacity content_ids."""
    schema = get_schema_service()
    fluids = schema.get_components("fluids")
    return [build_content_id("fluid_capacity", f) for f in fluids]


def get_all_torque_content_ids() -> List[str]:
    """Get all torque spec content_ids."""
    schema = get_schema_service()
    components = schema.get_components("torque_components")
    return [build_content_id("torque_spec", c) for c in components]


# =========================================================
# VEHICLE KEY UTILITIES
# =========================================================

def parse_vehicle_key(vehicle_key: str) -> dict:
    """
    Parse a vehicle key into its components.
    
    Args:
        vehicle_key: e.g., "2019_honda_accord_2.0t"
    
    Returns:
        Dict with year, make, model, engine (engine may be None)
    """
    parts = vehicle_key.split("_")
    
    if len(parts) < 3:
        raise ValueError(f"Invalid vehicle key: {vehicle_key}")
    
    year = int(parts[0])
    make = parts[1]
    
    # Model and engine are tricky - engine might have underscores
    # Heuristic: if last part looks like an engine, separate it
    engine_patterns = [
        r"^\d+\.?\d*[lt]$",  # 2.0t, 3.5l
        r"^v\d+$",           # v6, v8
        r"^\d+\.?\d*l_v\d+$", # 3.5l_v6
        r"^ecoboost$",
        r"^hybrid$",
    ]
    
    remaining = parts[2:]
    engine = None
    
    # Check if last part(s) look like an engine
    for i in range(len(remaining), 0, -1):
        candidate = "_".join(remaining[i-1:])
        for pattern in engine_patterns:
            if re.match(pattern, candidate, re.IGNORECASE):
                engine = candidate
                remaining = remaining[:i-1]
                break
        if engine:
            break
    
    model = "_".join(remaining) if remaining else None
    
    return {
        "year": year,
        "make": make,
        "model": model,
        "engine": engine
    }


def is_same_vehicle(key1: str, key2: str) -> bool:
    """Check if two vehicle keys refer to the same vehicle."""
    return key1.lower() == key2.lower()


def vehicles_share_data(key1: str, key2: str) -> bool:
    """
    Check if two vehicles might share data.
    
    Same make/model from consecutive years often share specs.
    Used for suggesting data reuse.
    """
    try:
        v1 = parse_vehicle_key(key1)
        v2 = parse_vehicle_key(key2)
        
        if v1["make"] != v2["make"] or v1["model"] != v2["model"]:
            return False
        
        # Same generation (within 3 years)
        if abs(v1["year"] - v2["year"]) <= 3:
            return True
        
        return False
    except:
        return False
