from fastapi import APIRouter, HTTPException
from models.chunk import ServiceChunk
from services.supabase_client import supabase_service
from typing import List

router = APIRouter()


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
