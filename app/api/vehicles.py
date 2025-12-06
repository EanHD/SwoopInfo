from fastapi import APIRouter, HTTPException, Query
from services.nhtsa import nhtsa_service
from typing import Optional

router = APIRouter()

@router.get("/decode-vin")
async def decode_vin(vin: str = Query(..., min_length=17, max_length=17, description="17-character Vehicle Identification Number")):
    """
    Decode a VIN to get vehicle year, make, model, and specs.
    Uses NHTSA vPIC API (Free, Official).
    """
    result = await nhtsa_service.decode_vin(vin)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to decode VIN"))
        
    return result["data"]
