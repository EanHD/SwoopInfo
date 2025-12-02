"""
Navigation API - Vehicle-aware template loading
Replaces old services.json with dynamic v3 template loading
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from models.vehicle import Vehicle
from services.template_loader import template_loader
from services.vehicle_validator import vehicle_validator
from services.pre_generator import pre_generator

router = APIRouter()


class NavigationRequest(BaseModel):
    """Request for vehicle navigation tree"""

    year: str
    make: str
    model: str
    engine: str
    transmission: Optional[str] = None
    drivetrain: Optional[str] = None


class NavigationNodeSchema(BaseModel):
    """Single navigation node - matches Flutter NavigationNode exactly"""

    id: str
    title: str
    icon: Optional[str] = None
    content_id: Optional[str] = None
    chunk_type: Optional[str] = None  # spec/diagram/procedure/document/dtc/tsb
    description: Optional[str] = None
    path: List[str]  # Full path from root for breadcrumbs
    searchable: bool = False
    subcategories: List["NavigationNodeSchema"] = []


class SearchableNodeSchema(BaseModel):
    """Searchable node for client-side search"""

    id: str
    title: str
    description: str
    content_id: str
    chunk_type: str
    path: List[str]
    tags: List[str] = []


class NavigationResponse(BaseModel):
    """Response with vehicle-specific navigation tree"""

    vehicle_key: str
    powertrain_type: str
    template_version: str
    categories: List[NavigationNodeSchema]
    searchable_nodes: List[SearchableNodeSchema]


# Enable forward refs for recursive model
NavigationNodeSchema.model_rebuild()


@router.post("/navigation", response_model=NavigationResponse)
async def get_navigation(request: NavigationRequest, background_tasks: BackgroundTasks):
    """
    Get vehicle-specific navigation tree

    1. Validates vehicle configuration (optional - allows unverified for navigation)
    2. Determines powertrain type
    3. Loads matching v3 template
    4. Applies vehicle-specific filters (4WD, turbo, etc.)
    5. Returns Flutter-compatible tree structure
    6. Triggers background pre-generation of baseline chunks (Stage 7)
    """
    # Build vehicle object
    vehicle = Vehicle(
        year=request.year, make=request.make, model=request.model, engine=request.engine
    )

    # Optional validation - warn but don't block navigation
    is_valid, error_msg = vehicle_validator.is_valid(vehicle)
    if not is_valid:
        print(f"⚠️  Navigation loaded for unverified vehicle: {vehicle.key}")
        # Allow unverified vehicles to load navigation
        # They just won't be able to generate chunks until verified

    # Trigger background pre-generation (Stage 7)
    # This is rate-limited internally to 1 vehicle/hour system-wide
    background_tasks.add_task(pre_generator.trigger_pre_generation, vehicle.key)

    # Determine powertrain and load template
    try:
        powertrain = template_loader.determine_powertrain(
            vehicle.engine, request.transmission
        )

        # Get filtered template
        template = template_loader.get_template(vehicle)

        # Convert to Flutter format
        categories = template_loader.convert_to_flutter_format(template)

        # Extract searchable nodes
        searchable = template_loader.get_searchable_nodes(template)

        return NavigationResponse(
            vehicle_key=vehicle.key,
            powertrain_type=powertrain,
            template_version=template.get("template_version", "3.0"),
            categories=categories,
            searchable_nodes=searchable,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "TEMPLATE_LOAD_FAILED",
                "message": str(e),
                "vehicle_key": vehicle.key,
            },
        )


@router.get("/navigation/powertrains")
async def get_powertrains():
    """Get list of available powertrain templates"""
    return {
        "powertrains": list(template_loader.TEMPLATE_MAP.keys()),
        "templates": {
            pt: {"filename": filename, "loaded": pt in template_loader._cache}
            for pt, filename in template_loader.TEMPLATE_MAP.items()
        },
    }


@router.get("/navigation/search/{powertrain}")
async def get_searchable_nodes(powertrain: str):
    """
    Get all searchable nodes for a powertrain type
    Useful for building search index
    """
    if powertrain not in template_loader.TEMPLATE_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown powertrain: {powertrain}")

    template = template_loader._cache.get(powertrain)
    if not template:
        raise HTTPException(
            status_code=500, detail=f"Template not loaded: {powertrain}"
        )

    searchable = template_loader.get_searchable_nodes(template)

    return {
        "powertrain": powertrain,
        "searchable_count": len(searchable),
        "nodes": searchable,
    }
