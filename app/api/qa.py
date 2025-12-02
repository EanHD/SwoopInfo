"""
QA API - Quality Assurance Endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Query
from typing import Dict, Any, List, Optional
from services.supabase_client import supabase_service
from services.qa_agent import qa_agent
from services.qa_repair import qa_repair_agent
from services.qa_scheduler import qa_scheduler
from datetime import datetime

router = APIRouter()


@router.get("/qa/health")
async def get_qa_health():
    """
    Get health status of the QA Scheduler
    """
    return qa_scheduler.get_health()


@router.post("/qa/repair")
async def repair_chunks(
    chunk_ids: Optional[List[str]] = None,
    batch_size: int = Query(10, ge=1, le=50),
    background_tasks: BackgroundTasks = None,
):
    """
    Attempt to repair failed chunks.
    If chunk_ids is provided, repairs those specific chunks.
    Otherwise, repairs all chunks with qa_status='fail'.
    """
    chunks_to_process = []

    if chunk_ids:
        chunks_to_process = await supabase_service.get_chunks_by_ids(chunk_ids)
    else:
        chunks_to_process = await supabase_service.get_failed_chunks(limit=batch_size)

    if not chunks_to_process:
        return {
            "status": "complete",
            "message": "No failed chunks found to repair",
            "processed": 0,
        }

    results = {"repaired": 0, "skipped": 0, "failed": 0, "details": []}

    for chunk in chunks_to_process:
        repair_result = await qa_repair_agent.repair_chunk(chunk)

        status = repair_result["status"]
        results[status] += 1
        results["details"].append(
            {"chunk_id": chunk.id, "status": status, "reason": repair_result["reason"]}
        )

    return {
        "status": "success",
        "summary": {
            "total_processed": len(chunks_to_process),
            "repaired": results["repaired"],
            "skipped": results["skipped"],
            "failed": results["failed"],
        },
        "details": results["details"],
    }


@router.post("/qa/run")
async def run_qa(
    batch_size: int = Query(10, ge=1, le=50), background_tasks: BackgroundTasks = None
):
    """
    Run QA agent on pending chunks.
    Process a batch of chunks and return results.
    """
    # Get pending chunks
    chunks = await supabase_service.get_pending_qa_chunks(limit=batch_size)

    if not chunks:
        return {
            "status": "complete",
            "message": "No pending chunks to process",
            "processed": 0,
        }

    results = []

    for chunk in chunks:
        # Run QA
        qa_result = await qa_agent.process_chunk(chunk)

        # Update database
        success = await supabase_service.update_chunk_qa_status(
            chunk_id=chunk.id,
            qa_status=qa_result["status"],
            qa_notes=qa_result["notes"],
            last_qa_reviewed_at=datetime.utcnow().isoformat(),
        )

        results.append(
            {
                "chunk_id": chunk.id,
                "vehicle_key": chunk.vehicle_key,
                "content_id": chunk.content_id,
                "old_status": chunk.qa_status,
                "new_status": qa_result["status"],
                "notes": qa_result["notes"],
                "updated": success,
            }
        )

    return {"status": "success", "processed": len(results), "results": results}


@router.get("/qa/metrics/live")
async def get_live_metrics():
    """
    Get live QA metrics for monitoring
    """
    stats = await supabase_service.get_qa_stats()

    # Calculate progress
    total = stats.get("total", 0)
    pending = stats.get("pending", 0)
    processed = total - pending
    progress = (processed / total * 100) if total > 0 else 0

    return {
        "status": "active",
        "current_cycle_progress": f"{progress:.1f}%",
        "pending_items": pending,
        "next_scheduled_run": (
            qa_scheduler.next_run_time.isoformat()
            if hasattr(qa_scheduler, "next_run_time") and qa_scheduler.next_run_time
            else "now"
        ),
        "quarantined_total": stats.get("quarantined_total", 0),
        "manual_review_required": stats.get(
            "banned_total", 0
        ),  # Using banned as proxy for now, or add specific count
    }


@router.get("/qa/report")
async def get_qa_report():
    """
    Get QA statistics and report
    """
    stats = await supabase_service.get_qa_stats()

    # Get regeneration stats (mock or query)
    # In production, add specific queries for regeneration counts

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
        "summary": f"Total: {stats['total']} | Pass: {stats['pass']} | Fail: {stats['fail']} | Pending: {stats['pending']}",
    }
