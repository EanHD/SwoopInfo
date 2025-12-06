from fastapi import APIRouter, HTTPException, Body
from models.chunk import ServiceChunk
from services.supabase_client import supabase_service
from services.vision import vision_service
from typing import List, Dict, Any

router = APIRouter()


@router.post("/vin-image")
async def verify_vin_image(data: Dict[str, Any] = Body(...)):
    """
    Verify a VIN from an image.
    Expects JSON: { "image": "base64_string", "expected_vin": "optional_vin_to_compare" }
    """
    image_data = data.get("image")
    expected_vin = data.get("expected_vin")
    
    if not image_data:
        raise HTTPException(status_code=400, detail="Image data required")

    result = await vision_service.extract_vin_from_image(image_data)
    
    if not result["success"]:
        return {"verified": False, "extracted_vin": None, "message": result["error"]}
        
    extracted_vin = result["vin"]
    
    response = {
        "verified": True,
        "extracted_vin": extracted_vin,
        "match": False
    }
    
    if expected_vin:
        # Normalize for comparison
        norm_extracted = extracted_vin.upper().replace("I", "1").replace("O", "0").replace("Q", "0")
        norm_expected = expected_vin.upper().replace("I", "1").replace("O", "0").replace("Q", "0")
        
        # Allow for minor OCR errors (Levenshtein distance could be better, but exact/partial match for now)
        if norm_extracted == norm_expected:
            response["match"] = True
        elif norm_expected in norm_extracted: # Extracted might have extra chars
            response["match"] = True
            
    return response


@router.get("/pending-review", response_model=List[ServiceChunk])
async def get_pending_chunks():
    """
    Get all chunks pending human verification.
    For admin panel to review safety-critical content.
    """
    try:
        # Query Supabase for chunks needing review
        result = (
            supabase_service.client.table("service_chunks")
            .select("*")
            .eq("requires_human_review", True)
            .eq("verification_status", "pending_review")
            .order("created_at", desc=True)
            .execute()
        )

        return [ServiceChunk(**row) for row in result.data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{chunk_id}")
async def approve_chunk(chunk_id: str, verified_by: str = "admin"):
    """
    Approve a chunk after human verification.
    Sets verified=True and adds "Swoop Verified" status.
    """
    try:
        result = (
            supabase_service.client.table("service_chunks")
            .update(
                {
                    "verified": True,
                    "verification_status": "verified",
                    "requires_human_review": False,
                }
            )
            .eq("id", chunk_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Chunk not found")

        return {"status": "approved", "chunk_id": chunk_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flag/{chunk_id}")
async def flag_chunk(chunk_id: str, reason: str):
    """
    Flag a chunk as potentially inaccurate.
    Removes it from active use until corrected.
    """
    try:
        result = (
            supabase_service.client.table("service_chunks")
            .update({"verification_status": "flagged", "requires_human_review": True})
            .eq("id", chunk_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Chunk not found")

        return {"status": "flagged", "chunk_id": chunk_id, "reason": reason}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_verification_stats():
    """
    Get verification statistics for monitoring quality.
    Shows auto-approval effectiveness.
    """
    try:
        # Count by verification status
        total = (
            supabase_service.client.table("service_chunks")
            .select("id", count="exact")
            .execute()
        )
        verified = (
            supabase_service.client.table("service_chunks")
            .select("id", count="exact")
            .eq("verified", True)
            .execute()
        )
        auto_verified = (
            supabase_service.client.table("service_chunks")
            .select("id", count="exact")
            .eq("verification_status", "auto_verified")
            .execute()
        )
        pending = (
            supabase_service.client.table("service_chunks")
            .select("id", count="exact")
            .eq("verification_status", "pending_review")
            .execute()
        )
        flagged = (
            supabase_service.client.table("service_chunks")
            .select("id", count="exact")
            .eq("verification_status", "flagged")
            .execute()
        )

        # Calculate auto-approval rate
        auto_approval_rate = (
            round(auto_verified.count / total.count * 100, 1) if total.count > 0 else 0
        )
        total_verified_rate = (
            round((verified.count + auto_verified.count) / total.count * 100, 1)
            if total.count > 0
            else 0
        )

        return {
            "total_chunks": total.count,
            "verified_chunks": verified.count,
            "auto_verified_chunks": auto_verified.count,
            "pending_review": pending.count,
            "flagged": flagged.count,
            "auto_approval_rate": auto_approval_rate,
            "total_verification_rate": total_verified_rate,
            "human_review_savings": f"{auto_approval_rate}% of chunks auto-approved",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
