"""
Chunks API - Content retrieval with cache-first strategy
Single source of truth for all chunk requests
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from models.vehicle import Vehicle
from services.supabase_client import supabase_service
from services.chunk_generator import chunk_generator
from services.real_generator import real_generator
from services.advanced_generator import advanced_generator
import re

router = APIRouter()


class ChunkResponse(BaseModel):
    """Standard chunk response"""

    vehicle_key: str
    content_id: str
    chunk_type: str
    template_type: str
    template_version: str = "1.0"
    status: str  # ready/generating/error
    verification_status: str  # verified/pending/auto_verified
    source_confidence: float
    qa_status: str = "pending"
    qa_notes: Optional[str] = None
    verified_status: str = "unverified"  # unverified/candidate/verified/banned
    verified_at: Optional[str] = None
    promotion_count: int = 0
    visibility: str = "safe"  # safe/quarantined/banned
    sources: list[str]
    data: Dict[str, Any]
    generated_at: Optional[str] = None


@router.get("/chunks/{content_id}", response_model=ChunkResponse)
async def get_chunk(
    content_id: str,
    vehicle_key: str,
    chunk_type: str,
    template_type: str,
    template_version: str = "1.0",
):
    """
    Get chunk content with cache-first strategy

    Path: /api/chunks/engine_oil_capacity
    Query: ?vehicle_key=2011_ford_f150_50lv8&chunk_type=spec&template_type=ICE_GASOLINE&template_version=1.0

    Flow:
    1. Check Supabase for cached chunk
    2. If found → return immediately
    3. If missing → trigger async generation → return placeholder
    4. Frontend polls or uses websocket for completion
    """

    # Normalize template_type immediately to fix DB constraint issues
    template_type = _normalize_template_type(vehicle_key, template_type)

    # Parse vehicle key
    try:
        parts = vehicle_key.split("_")
        if len(parts) < 4:
            raise ValueError(
                "vehicle_key must have at least 4 parts: year_make_model_engine"
            )

        vehicle = Vehicle(
            year=parts[0],
            make=parts[1],
            model="_".join(parts[2:-1]) if len(parts) > 4 else parts[2],
            engine=parts[-1],
        )
    except Exception as e:
        print(f"❌ Vehicle parsing error: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vehicle_key format: {vehicle_key}. Error: {str(e)}",
        )

    # Check cache first - try Supabase database
    # Map 'diagram' to 'wiring_diagram' for DB lookup if needed
    db_chunk_type = "wiring_diagram" if chunk_type == "diagram" else chunk_type

    existing_chunk = await supabase_service.get_chunk(
        vehicle_key=vehicle_key, content_id=content_id, chunk_type=db_chunk_type
    )

    # REUSE LOGIC: If exact match missing, try to find a reusable chunk
    if not existing_chunk:
        # Try to find a chunk with similar content
        # e.g. if looking for "spark_plug_torque", search for chunks with type "torque_spec" and title "Spark Plug"

        # Extract keywords from content_id
        keywords = content_id.replace("_", " ").split()
        # Filter out common words
        keywords = [
            k
            for k in keywords
            if k not in ["engine", "system", "assembly", "components"]
        ]

        if len(keywords) > 0:
            search_term = " ".join(
                keywords[-2:]
            )  # Use last 2 words usually most specific
            print(f"♻️ Attempting reuse search for: {search_term} ({db_chunk_type})")

            reusable = await supabase_service.find_reusable_chunk(
                vehicle_key=vehicle_key, chunk_type=db_chunk_type, keyword=search_term
            )

            if reusable:
                print(f"♻️ Found reusable chunk! {reusable.id} for {content_id}")
                existing_chunk = reusable

            # FALLBACK: If removal_steps missing, try torque_spec
            if not existing_chunk and db_chunk_type == "removal_steps":
                print(f"♻️ Fallback: Searching for torque_spec for missing procedure...")
                reusable_torque = await supabase_service.find_reusable_chunk(
                    vehicle_key=vehicle_key,
                    chunk_type="torque_spec",
                    keyword=search_term,
                )
                if reusable_torque:
                    print(f"♻️ Fallback: Found torque spec! {reusable_torque.id}")
                    existing_chunk = reusable_torque
                    # We must update chunk_type to match the found chunk so frontend renders it correctly
                    chunk_type = "torque_spec"

    # Data Integrity Check: Treat NULL data/content OR banned chunks as cache miss to force regeneration
    if existing_chunk and (
        existing_chunk.data is None or existing_chunk.content_text is None
    ):
        print(
            f"⚠️ Found corrupted chunk (NULL data/content): {content_id}. Treating as cache miss."
        )
        existing_chunk = None

    # Version Check: If template_version mismatch, treat as cache miss to force regeneration
    if existing_chunk and existing_chunk.data:
        stored_version = existing_chunk.data.get("template_version", "1.0")
        if stored_version != template_version:
            print(
                f"⚠️ Template version mismatch for {content_id}: stored={stored_version}, requested={template_version}. Treating as cache miss."
            )
            existing_chunk = None

    # Force regeneration if "See Manual" stub is detected
    if (
        existing_chunk
        and existing_chunk.content_text
        and "See Manual" in existing_chunk.content_text
    ):
        print(
            f"⚠️ Found 'See Manual' stub in chunk: {content_id}. Treating as cache miss to force regeneration."
        )
        existing_chunk = None

    # Banned chunks should be deleted and regenerated
    if (
        existing_chunk
        and hasattr(existing_chunk, "verified_status")
        and existing_chunk.verified_status == "banned"
    ):
        print(f"⚠️ Found banned chunk: {content_id}. Deleting and regenerating...")
        # Delete the banned chunk (sync call, not async)
        try:
            supabase_service.client.table("chunks").delete().eq(
                "id", existing_chunk.id
            ).execute()
            print(f"✅ Deleted banned chunk: {content_id}")
        except Exception as e:
            print(f"❌ Failed to delete banned chunk: {e}")
        existing_chunk = None

    if existing_chunk:
        # Data Integrity Fix: If legacy verification_status is 'rejected', treat as banned and regenerate
        if existing_chunk.verification_status == "rejected":
            print(f"⚠️ Found rejected chunk: {content_id}. Deleting and regenerating...")
            try:
                supabase_service.client.table("chunks").delete().eq(
                    "id", existing_chunk.id
                ).execute()
                print(f"✅ Deleted rejected chunk: {content_id}")
                existing_chunk = None
            except Exception as e:
                print(f"❌ Failed to delete rejected chunk: {e}")

    if existing_chunk:
        # Get verified_status for the response
        verified_status = getattr(existing_chunk, "verified_status", "unverified")

        # For non-critical unverified items, this will return status="ready" and visibility="safe"
        # but verified_status="unverified" (yellow badge in UI)
        print(f"💾 Database hit for: {content_id}")
        return ChunkResponse(
            vehicle_key=vehicle_key,
            content_id=content_id,
            chunk_type=chunk_type,
            template_type=template_type,
            template_version=existing_chunk.data.get("template_version", "1.0"),
            status="ready",
            verification_status=existing_chunk.verification_status,
            source_confidence=existing_chunk.source_confidence,
            qa_status=existing_chunk.qa_status,
            qa_notes=existing_chunk.qa_notes,
            verified_status=verified_status,
            verified_at=getattr(existing_chunk, "verified_at", None),
            promotion_count=getattr(existing_chunk, "promotion_count", 0),
            visibility="safe",
            sources=existing_chunk.sources,
            data=existing_chunk.data,
            generated_at=existing_chunk.created_at,
        )

    # Cache miss - try to generate real data
    print(f"🌐 Database miss for: {content_id}")

    # Parse vehicle info from vehicle_key (e.g., "2011_ford_f150_50lv8")
    vehicle_parts = vehicle_key.split("_")
    if len(vehicle_parts) >= 3:
        year = vehicle_parts[0]
        make = vehicle_parts[1].capitalize()
        # Better model parsing - handle F150 -> F-150
        raw_model = "_".join(vehicle_parts[2:-1])
        if "f150" in raw_model.lower():
            model = "F-150"
        elif "f250" in raw_model.lower():
            model = "F-250"
        elif "f350" in raw_model.lower():
            model = "F-350"
        else:
            model = raw_model.replace("_", " ").title()

        print(f"📋 Parsed: {year} {make} {model}")

        # Try real generation for known_issues and recalls
        if content_id in ["known_issues", "common_problems", "tsbs"]:
            print(f"🔧 Generating real TSB/issues data from NHTSA...")
            result = await real_generator.generate_tsb_chunk(
                vehicle_key=vehicle_key, year=year, make=make, model=model
            )

            if result["success"]:
                # Generate content_text summary for search/indexing
                content_text = f"Known Issues for {year} {make} {model}. Found {len(result['data'].get('known_issues', []))} common issues."

                # Save to database
                saved = await supabase_service.save_chunk(
                    vehicle_key=vehicle_key,
                    content_id=content_id,
                    chunk_type=chunk_type,
                    template_type=template_type,
                    title=result["title"],
                    data=result["data"],
                    sources=result["sources"],
                    verification_status=result["verification_status"],
                    source_confidence=result["source_confidence"],
                    qa_status="pending",
                    content_text=content_text,
                    template_version=template_version,
                )

                if saved:
                    print(f"💾 Saved real chunk to database: {content_id}")
                    return ChunkResponse(
                        vehicle_key=vehicle_key,
                        content_id=content_id,
                        chunk_type=chunk_type,
                        template_type=template_type,
                        template_version=template_version,
                        status="ready",
                        verification_status=result["verification_status"],
                        source_confidence=result["source_confidence"],
                        qa_status="pending",
                        verified_status="unverified",
                        verified_at=None,
                        promotion_count=0,
                        sources=result["sources"],
                        data=result["data"],
                        generated_at=saved.created_at,
                    )
                else:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "db_error",
                            "message": "Failed to save TSB chunk to database",
                        },
                    )

        elif content_id in ["recalls", "safety_recalls"]:
            print(f"🔧 Generating real recall data from NHTSA...")
            result = await real_generator.generate_recall_chunk(
                vehicle_key=vehicle_key, year=year, make=make, model=model
            )

            if result["success"]:
                # Generate content_text summary
                content_text = f"Safety Recalls for {year} {make} {model}. Found {len(result['data'].get('recalls', []))} recalls."

                # Save to database
                saved = await supabase_service.save_chunk(
                    vehicle_key=vehicle_key,
                    content_id=content_id,
                    chunk_type=chunk_type,
                    template_type=template_type,
                    title=result["title"],
                    data=result["data"],
                    sources=result["sources"],
                    verification_status=result["verification_status"],
                    source_confidence=result["source_confidence"],
                    qa_status="pending",
                    content_text=content_text,
                    template_version=template_version,
                )

                if saved:
                    print(f"💾 Saved recall chunk to database: {content_id}")
                    return ChunkResponse(
                        vehicle_key=vehicle_key,
                        content_id=content_id,
                        chunk_type=chunk_type,
                        template_type=template_type,
                        template_version=template_version,
                        status="ready",
                        verification_status=result["verification_status"],
                        source_confidence=result["source_confidence"],
                        qa_status="pending",
                        verified_status="unverified",
                        verified_at=None,
                        promotion_count=0,
                        sources=result["sources"],
                        data=result["data"],
                        generated_at=saved.created_at,
                    )
                else:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "db_error",
                            "message": "Failed to save recall chunk to database",
                        },
                    )

        elif content_id in ["diagnostic_flow", "diag_flow", "troubleshooting"]:
            print(f"🔧 Generating diagnostic flow from multi-source...")
            concern = "general diagnosis"
            dtc_codes = []

            result = await advanced_generator.generate_diagnostic_flow(
                vehicle_key=vehicle_key,
                year=year,
                make=make,
                model=model,
                concern=concern,
                dtc_codes=dtc_codes,
            )

            if result["success"]:
                # Generate content_text
                content_text = (
                    f"Diagnostic Flow for {year} {make} {model}. Concern: {concern}."
                )

                saved = await supabase_service.save_chunk(
                    vehicle_key=vehicle_key,
                    content_id=content_id,
                    chunk_type=chunk_type,
                    template_type=template_type,
                    title=result["title"],
                    data=result["data"],
                    sources=result["sources"],
                    verification_status=result["verification_status"],
                    source_confidence=result["source_confidence"],
                    qa_status="pending",
                    content_text=content_text,
                    template_version=template_version,
                )

                if saved:
                    print(f"💾 Saved diagnostic flow: {content_id}")
                    return ChunkResponse(
                        vehicle_key=vehicle_key,
                        content_id=content_id,
                        chunk_type=chunk_type,
                        template_type=template_type,
                        template_version=template_version,
                        status="ready",
                        verification_status=result["verification_status"],
                        source_confidence=result["source_confidence"],
                        qa_status="pending",
                        verified_status="unverified",
                        verified_at=None,
                        promotion_count=0,
                        sources=result["sources"],
                        data=result["data"],
                        generated_at=saved.created_at,
                    )
                else:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "db_error",
                            "message": "Failed to save diagnostic flow to database",
                        },
                    )

        elif "wiring" in content_id or "diagram" in content_id:
            print(f"🔌 Generating wiring diagram...")
            system = "electrical"
            component = content_id.replace("wiring_", "").replace("_diagram", "")

            result = await advanced_generator.generate_wiring_diagram(
                vehicle_key=vehicle_key,
                year=year,
                make=make,
                model=model,
                system=system,
                component=component,
            )

            if result["success"]:
                # Generate content_text
                content_text = (
                    f"Wiring Diagram for {component} on {year} {make} {model}."
                )

                saved = await supabase_service.save_chunk(
                    vehicle_key=vehicle_key,
                    content_id=content_id,
                    chunk_type=chunk_type,
                    template_type=template_type,
                    title=result["title"],
                    data=result["data"],
                    sources=result["sources"],
                    verification_status=result["verification_status"],
                    source_confidence=result["source_confidence"],
                    qa_status="pending",
                    content_text=content_text,
                    template_version=template_version,
                )

                if saved:
                    print(f"💾 Saved wiring diagram: {content_id}")
                    return ChunkResponse(
                        vehicle_key=vehicle_key,
                        content_id=content_id,
                        chunk_type=chunk_type,
                        template_type=template_type,
                        template_version=template_version,
                        status="ready",
                        verification_status=result["verification_status"],
                        source_confidence=result["source_confidence"],
                        qa_status="pending",
                        verified_status="unverified",
                        verified_at=None,
                        promotion_count=0,
                        sources=result["sources"],
                        data=result["data"],
                        generated_at=saved.created_at,
                    )
                else:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "db_error",
                            "message": "Failed to save wiring diagram to database",
                        },
                    )

    # Fall back to REAL chunk generation using chunk_generator
    print(f"🔧 Generating REAL chunk data using web scraping + AI for: {content_id}")

    # chunk_generator already imported at top
    # Vehicle already imported at top

    # Create Vehicle object
    vehicle_obj = Vehicle(
        year=year,
        make=make,
        model=model,
        engine=parts[-1] if len(parts) > 3 else "unknown",
    )

    # Map content_id to concern/title
    concern = content_id.replace("_", " ")
    title = content_id.replace("_", " ").title()

    # Map chunk_type string to actual type
    chunk_type_map = {
        "spec": "fluid_capacity",
        "procedure": "removal_steps",
        "list": "known_issues",
        "diagram": "wiring_diagram",
        "torque_spec": "torque_spec",
        "fluid_capacity": "fluid_capacity",
        "removal_steps": "removal_steps",
        "known_issues": "known_issues",
        "part_location": "part_location",
        "wiring_diagram": "wiring_diagram",
        "diag_flow": "diag_flow",
        "labor_time": "labor_time",
        "tsb": "tsb",
        "part_info": "part_info",
    }

    # Smart mapping for generic 'spec' type
    if chunk_type == "spec" and "torque" in content_id:
        ct_string = "torque_spec"
    else:
        ct_string = chunk_type_map.get(chunk_type, "known_issues")

    try:
        # Generate real chunk using web scraping + AI
        service_chunk, cost = await chunk_generator.generate_chunk(
            vehicle=vehicle_obj,
            chunk_type=ct_string,
            title=title,
            context=concern,
            dtc_codes=[],
            template_version=template_version,
        )

        print(f"✅ Generated real chunk (cost: ${cost:.4f})")

        # Map ServiceChunk verification_status to database verification_status
        # ServiceChunk uses: unverified, pending_review, verified, auto_verified, community_verified, flagged
        # Database uses: unverified, pending_verification, verified, auto_verified, rejected
        verification_status_map = {
            "unverified": "unverified",
            "pending_review": "pending_verification",
            "verified": "verified",
            "auto_verified": "auto_verified",
            "community_verified": "verified",  # Map to verified
            "flagged": "pending_verification",  # Map flagged to pending_verification
        }
        db_verification_status = verification_status_map.get(
            service_chunk.verification_status, "pending_verification"
        )

        # Convert ServiceChunk to database format
        # Use the structured data from the generator (contains spec_items for specs, html for procedures)
        chunk_data = service_chunk.data

        # Save to database
        saved_chunk = await supabase_service.save_chunk(
            vehicle_key=vehicle_key,
            content_id=content_id,
            chunk_type=chunk_type,
            template_type=template_type,
            title=service_chunk.title,
            data=chunk_data,
            sources=[cite.url for cite in service_chunk.source_cites if cite.url]
            or ["Generated content"],
            verification_status=db_verification_status,
            source_confidence=(
                service_chunk.consensus_score if service_chunk.consensus_score else 0.75
            ),
            qa_status="pending",
            content_text=service_chunk.content_text,
            template_version=template_version,
        )

        if saved_chunk:
            print(f"💾 Saved real chunk to database: {content_id}")
            return ChunkResponse(
                vehicle_key=vehicle_key,
                content_id=content_id,
                chunk_type=chunk_type,
                template_type=template_type,
                template_version=template_version,
                status="ready",
                verification_status=service_chunk.verification_status,
                source_confidence=(
                    service_chunk.consensus_score
                    if service_chunk.consensus_score
                    else 0.75
                ),
                qa_status="pending",
                verified_status="unverified",
                verified_at=None,
                promotion_count=0,
                visibility="safe",
                sources=[cite.url for cite in service_chunk.source_cites if cite.url]
                or ["Generated content"],
                data=chunk_data,
                generated_at=saved_chunk.created_at,
            )
        else:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                content={
                    "status": "db_error",
                    "message": "Failed to save chunk to database (check constraint or contamination)",
                },
            )

    except Exception as e:
        print(f"❌ Real generation failed: {e}")
        import traceback

        traceback.print_exc()

        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Real generation failed: {str(e)}"},
        )


def _generate_stub_data(content_id: str, chunk_type: str) -> Dict[str, Any]:
    """Generate stub data for testing based on chunk type"""

    if chunk_type == "spec":
        return {
            "spec_items": [
                {"label": "Specification", "value": "Pending Verification", "unit": ""},
                {"label": "Status", "value": "Generating...", "unit": ""},
            ]
        }
    elif chunk_type == "procedure":
        return {
            "steps": [
                {
                    "title": "Procedure Pending",
                    "text": "This procedure is currently being generated and verified.",
                },
                {
                    "title": "Check Back Soon",
                    "text": "Our agents are compiling the specific steps for this vehicle.",
                },
            ]
        }
    elif chunk_type == "list":
        return {"items": ["Data pending verification", "Check back soon"]}
    elif chunk_type == "diagram":
        return {
            "storage_key": f"diagrams/{content_id}.png",
            "message": "Diagram generation not yet implemented",
        }
    else:
        return {
            "message": f"Content for {content_id} is being generated...",
            "content_id": content_id,
            "chunk_type": chunk_type,
        }

    # Cache miss - generate new chunk
    # For now, return placeholder to avoid blocking UI
    # TODO: Trigger async generation + websocket notification

    return ChunkResponse(
        vehicle_key=vehicle_key,
        content_id=content_id,
        chunk_type=chunk_type,
        template_type=template_type,
        status="generating",
        verification_status="pending",
        source_confidence=0.0,
        sources=[],
        data={
            "message": "Content is being generated. Check back in a few seconds.",
            "content_id": content_id,
            "chunk_type": chunk_type,
        },
        generated_at=None,
    )


class OnDemandRequest(BaseModel):
    vehicle_key: str
    content_id: str
    chunk_type: str
    template_type: str
    template_version: str = "1.0"


@router.post("/chunks/generate_on_demand")
async def generate_on_demand(request: OnDemandRequest):
    """
    Stage 6: On-Demand Generation with Quarantine

    1. Check if chunk exists
    2. If not, generate REAL content
    3. Save as unverified (quarantined)
    4. Return status
    """
    vehicle_key = request.vehicle_key
    content_id = request.content_id
    chunk_type = request.chunk_type
    template_type = request.template_type
    template_version = request.template_version

    # Normalize template_type immediately
    template_type = _normalize_template_type(vehicle_key, template_type)

    # 1. Check Limits (10 per vehicle per day)
    daily_count = await supabase_service.get_daily_generation_count(vehicle_key)
    if daily_count >= 10:
        raise HTTPException(
            status_code=429,
            detail="Daily generation limit reached for this vehicle (10/10)",
        )

    # 2. Check if exists
    existing = await supabase_service.get_chunk(
        vehicle_key=vehicle_key, content_id=content_id, chunk_type=chunk_type
    )

    if existing:
        # If banned, return 404
        if existing.verified_status == "banned":
            raise HTTPException(status_code=404, detail="Content unavailable (banned)")

        # If verified, return it
        if existing.verified_status == "verified":
            return {
                "status": "ready",
                "message": "Chunk already exists and is verified",
                "chunk_id": existing.id,
                "visibility": "safe",
            }

        # If unverified/candidate, return quarantined status
        return {
            "status": "pending",
            "message": "Chunk exists but is pending verification",
            "chunk_id": existing.id,
            "visibility": "quarantined",
        }

    # 3. Generate REAL content
    print(f"⚡ Generating on-demand chunk (REAL): {content_id}")

    # Parse vehicle
    try:
        parts = vehicle_key.split("_")
        if len(parts) < 4:
            raise ValueError("vehicle_key must have at least 4 parts")

        year = parts[0]
        make = parts[1]
        model = "_".join(parts[2:-1]) if len(parts) > 4 else parts[2]
        engine = parts[-1]

        vehicle = Vehicle(year=year, make=make, model=model, engine=engine)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vehicle_key format: {vehicle_key}. Error: {str(e)}",
        )

    # Map chunk_type to title
    title = content_id.replace("_", " ").title()
    context = content_id.replace("_", " ")

    # Map chunk_type string to actual type
    chunk_type_map = {
        "spec": "fluid_capacity",
        "procedure": "removal_steps",
        "list": "known_issues",
        "diagram": "wiring_diagram",
        "fluid_capacity": "fluid_capacity",
        "torque_spec": "torque_spec",
        "removal_steps": "removal_steps",
        "known_issues": "known_issues",
        "part_location": "part_location",
        "wiring_diagram": "wiring_diagram",
        "diag_flow": "diag_flow",
        "labor_time": "labor_time",
        "tsb": "tsb",
        "part_info": "part_info",
    }
    ct = chunk_type_map.get(chunk_type, chunk_type)

    try:
        # Generate using chunk_generator
        service_chunk, cost = await chunk_generator.generate_chunk(
            vehicle=vehicle,
            chunk_type=ct,
            title=title,
            context=context,
            dtc_codes=[],
            template_version=template_version,
        )

        print(f"✅ Generated real chunk (cost: ${cost:.4f})")

        # Map ServiceChunk verification_status to database verification_status
        verification_status_map = {
            "unverified": "unverified",
            "pending_review": "pending_verification",
            "verified": "verified",
            "auto_verified": "auto_verified",
            "community_verified": "verified",
            "flagged": "pending_verification",
        }
        db_verification_status = verification_status_map.get(
            service_chunk.verification_status, "pending_verification"
        )

        # Save to database
        # Use mapped chunk type for DB (e.g. diagram -> wiring_diagram)
        db_chunk_type = "wiring_diagram" if chunk_type == "diagram" else chunk_type

        saved = await supabase_service.save_chunk(
            vehicle_key=vehicle_key,
            content_id=content_id,
            chunk_type=db_chunk_type,
            template_type=template_type,
            title=service_chunk.title,
            data=service_chunk.data,
            sources=[cite.url for cite in service_chunk.source_cites if cite.url]
            or ["Generated content"],
            verification_status=db_verification_status,
            source_confidence=(
                service_chunk.consensus_score if service_chunk.consensus_score else 0.75
            ),
            qa_status="pending",
            content_text=service_chunk.content_text,
            template_version=template_version,
        )

        if saved:
            return {
                "status": "created",
                "message": "Chunk generated and quarantined for QA",
                "chunk_id": saved.id,
                "visibility": "quarantined",
                "retry_after_recheck": True,
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to save generated chunk"
            )

    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.post("/chunks/{content_id}/generate")
async def generate_chunk_endpoint(
    content_id: str,
    vehicle_key: str,
    chunk_type: str,
    template_type: str,
    template_version: str = "1.0",
    force: bool = False,
):
    """
    Explicitly trigger chunk generation

    Use force=true to regenerate even if cached
    Returns the generated chunk immediately
    """

    # Normalize template_type immediately
    template_type = _normalize_template_type(vehicle_key, template_type)

    # Check if already exists and not forcing
    if not force:
        existing = await supabase_service.get_chunk(
            vehicle_key=vehicle_key, content_id=content_id, chunk_type=chunk_type
        )
        if existing:
            # Check version mismatch
            stored_version = (
                existing.data.get("template_version", "1.0") if existing.data else "1.0"
            )
            if stored_version == template_version:
                return {
                    "status": "exists",
                    "message": "Chunk already generated. Use force=true to regenerate.",
                    "chunk_id": existing.id,
                }
            else:
                print(
                    f"⚠️ Template version mismatch for {content_id}: stored={stored_version}, requested={template_version}. Regenerating."
                )

    # Parse vehicle
    try:
        parts = vehicle_key.split("_")
        if len(parts) < 4:
            raise ValueError("vehicle_key must have at least 4 parts")

        year = parts[0]
        make = parts[1]
        model = "_".join(parts[2:-1]) if len(parts) > 4 else parts[2]
        engine = parts[-1]

        vehicle = Vehicle(year=year, make=make, model=model, engine=engine)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vehicle_key format: {vehicle_key}. Error: {str(e)}",
        )

    # Map chunk_type to title
    title = content_id.replace("_", " ").title()
    context = content_id.replace("_", " ")

    # Map chunk_type string to actual type
    chunk_type_map = {
        "spec": "fluid_capacity",
        "procedure": "removal_steps",
        "list": "known_issues",
        "diagram": "wiring_diagram",
        "fluid_capacity": "fluid_capacity",
        "torque_spec": "torque_spec",
        "removal_steps": "removal_steps",
        "known_issues": "known_issues",
        "part_location": "part_location",
        "wiring_diagram": "wiring_diagram",
        "diag_flow": "diag_flow",
        "labor_time": "labor_time",
        "tsb": "tsb",
        "part_info": "part_info",
    }
    ct = chunk_type_map.get(chunk_type, chunk_type)

    try:
        print(f"🔧 Generating chunk: {content_id} ({chunk_type})")

        # Generate using chunk_generator
        service_chunk, cost = await chunk_generator.generate_chunk(
            vehicle=vehicle,
            chunk_type=ct,
            title=title,
            context=context,
            dtc_codes=[],
            template_version=template_version,
        )

        print(f"✅ Generated chunk (cost: ${cost:.4f})")

        # Map ServiceChunk verification_status to database verification_status
        # ServiceChunk uses: unverified, pending_review, verified, auto_verified, community_verified, flagged
        # Database uses: unverified, pending_verification, verified, auto_verified, rejected
        verification_status_map = {
            "unverified": "unverified",
            "pending_review": "pending_verification",
            "verified": "verified",
            "auto_verified": "auto_verified",
            "community_verified": "verified",  # Map to verified
            "flagged": "pending_verification",  # Map flagged to pending_verification
        }
        db_verification_status = verification_status_map.get(
            service_chunk.verification_status, "pending_verification"
        )

        # Save to database
        # Use mapped chunk type for DB (e.g. diagram -> wiring_diagram)
        db_chunk_type = "wiring_diagram" if chunk_type == "diagram" else chunk_type

        saved = await supabase_service.save_chunk(
            vehicle_key=vehicle_key,
            content_id=content_id,
            chunk_type=db_chunk_type,
            template_type=template_type,
            title=service_chunk.title,
            data=service_chunk.data,  # Use the data field from ServiceChunk
            sources=[cite.url for cite in service_chunk.source_cites if cite.url]
            or ["Generated content"],
            verification_status=db_verification_status,  # Use mapped DB value
            source_confidence=(
                service_chunk.consensus_score if service_chunk.consensus_score else 0.75
            ),
            qa_status="pending",
            content_text=service_chunk.content_text,
            template_version=template_version,
        )

        if saved:
            return {
                "status": "success",
                "message": f"Chunk generated successfully (cost: ${cost:.4f})",
                "chunk_id": saved.id,
                "vehicle_key": vehicle_key,
                "content_id": content_id,
                "chunk_type": chunk_type,
                "data": saved.data,
                "content_text": saved.content_text,
                "verification_status": saved.verification_status,
                "qa_status": saved.qa_status,
                "cost": cost,
            }
        else:
            # Contamination or DB error - Return a "generating" status so UI retries instead of crashing
            print(
                f"⚠️ Chunk save failed (likely contamination). Returning 'generating' status to trigger retry."
            )
            return {
                "status": "success",  # Return success 200 OK to avoid UI crash
                "message": "Content verification failed. Regenerating...",
                "chunk_id": "temp_retry",
                "vehicle_key": vehicle_key,
                "content_id": content_id,
                "chunk_type": chunk_type,
                "data": {"message": "Verifying content accuracy..."},
                "content_text": "Verifying content...",
                "verification_status": "pending_verification",
                "qa_status": "pending",
                "cost": cost,
            }

    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback

        traceback.print_exc()
        # Return error instead of raising
        return {"status": "error", "message": f"Generation failed: {str(e)}"}


def _normalize_template_type(vehicle_key: str, template_type: str) -> str:
    """
    Force template_type to valid enum values based on vehicle key.
    Fixes constraint violation: "chunks_template_type_check"
    """
    vk = vehicle_key.lower()

    # 1. Detect from vehicle key
    if "powerstroke" in vk or "diesel" in vk:
        return "ICE_DIESEL"
    if "powerboost" in vk or "hybrid" in vk:
        return "HYBRID"
    if "lightning" in vk or "mach-e" in vk or "ev" in vk:
        return "EV"
    if "coyote" in vk or "5.0l" in vk or "ecoboost" in vk or "v8" in vk or "v6" in vk:
        return "ICE_GASOLINE"

    # 2. Fallback: If template_type is already valid, return it upper
    tt_upper = template_type.upper()
    if tt_upper in ["ICE_GASOLINE", "ICE_DIESEL", "HYBRID", "EV"]:
        return tt_upper

    # 3. Default Fallback
    return "ICE_GASOLINE"


class LeafGenerationRequest(BaseModel):
    vehicle_key: str
    leaf_id: str
    template_type: str
    chunks: List[Dict[str, str]]  # List of {type, title}
    template_version: str = "1.0"


@router.post("/chunks/generate_leaf")
async def generate_leaf_endpoint(request: LeafGenerationRequest):
    """
    Generate all chunks for a leaf node in parallel.
    """
    vehicle_key = request.vehicle_key
    leaf_id = request.leaf_id
    template_type = _normalize_template_type(vehicle_key, request.template_type)
    chunks_def = request.chunks
    template_version = request.template_version

    # Parse vehicle
    try:
        parts = vehicle_key.split("_")
        if len(parts) < 4:
            raise ValueError("vehicle_key must have at least 4 parts")

        vehicle = Vehicle(
            year=parts[0],
            make=parts[1],
            model="_".join(parts[2:-1]) if len(parts) > 4 else parts[2],
            engine=parts[-1],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid vehicle_key: {e}")

    # Check which chunks already exist to avoid re-generation
    # For now, we'll just let generate_leaf_bundle handle it?
    # No, generate_leaf_bundle generates REAL chunks. We should check DB first.

    final_response = []
    chunks_to_generate = []

    for chunk_def in chunks_def:
        chunk_type = chunk_def.get("type")
        # Map chunk type for DB (diagram -> wiring_diagram)
        db_chunk_type = "wiring_diagram" if chunk_type == "diagram" else chunk_type
        content_id = f"{leaf_id}_{chunk_type}"

        existing = await supabase_service.get_chunk(
            vehicle_key=vehicle_key, content_id=content_id, chunk_type=db_chunk_type
        )

        if existing and existing.verified_status != "banned":
            # Add to response
            final_response.append(
                {
                    "content_id": content_id,
                    "chunk_type": chunk_type,
                    "status": "ready",
                    "data": existing.data,
                    "content_text": existing.content_text,
                    "verification_status": existing.verification_status,
                    "source_confidence": existing.source_confidence,
                    "sources": existing.sources,
                }
            )
        else:
            chunks_to_generate.append(chunk_def)

    if not chunks_to_generate:
        return {"status": "success", "chunks": final_response}

    # Generate missing chunks
    print(f"⚡ Generating {len(chunks_to_generate)} missing chunks for leaf {leaf_id}")

    # Map chunk types in definition to actual generator types
    mapped_chunks_to_generate = []
    chunk_type_map = {
        "spec": "fluid_capacity",
        "procedure": "removal_steps",
        "list": "known_issues",
        "diagram": "wiring_diagram",
        "fluid_capacity": "fluid_capacity",
        "torque_spec": "torque_spec",
        "removal_steps": "removal_steps",
        "known_issues": "known_issues",
        "part_location": "part_location",
        "wiring_diagram": "wiring_diagram",
        "diag_flow": "diag_flow",
        "labor_time": "labor_time",
        "tsb": "tsb",
        "part_info": "part_info",
    }

    for c in chunks_to_generate:
        orig_type = c.get("type")
        mapped_type = chunk_type_map.get(orig_type, orig_type)
        mapped_chunks_to_generate.append(
            {
                "type": mapped_type,
                "title": c.get("title"),
                "orig_type": orig_type,  # Keep track of original type for ID
            }
        )

    # Call generator
    bundle_result = await chunk_generator.generate_leaf_bundle(
        vehicle=vehicle,
        leaf_id=leaf_id,
        chunks_def=mapped_chunks_to_generate,
        template_version=template_version,
    )

    # Save results
    results = bundle_result["results"]

    for i, c in enumerate(chunks_to_generate):
        orig_type = c.get("type")
        mapped_type = mapped_chunks_to_generate[i]["type"]
        content_id = f"{leaf_id}_{mapped_type}"  # Generator uses mapped type in ID?
        # Wait, generator returns results keyed by content_id constructed inside it.
        # Inside generate_leaf_bundle: content_id = f"{leaf_id}_{chunk_type}" where chunk_type is from chunks_def (mapped_type)

        gen_content_id = f"{leaf_id}_{mapped_type}"
        res = results.get(gen_content_id)

        if res and res["status"] == "success":
            chunk = res["chunk"]

            # Map verification status
            verification_status_map = {
                "unverified": "unverified",
                "pending_review": "pending_verification",
                "verified": "verified",
                "auto_verified": "auto_verified",
                "community_verified": "verified",
                "flagged": "pending_verification",
            }
            db_verification_status = verification_status_map.get(
                chunk.verification_status, "pending_verification"
            )

            # Save
            db_chunk_type = "wiring_diagram" if orig_type == "diagram" else orig_type
            final_content_id = (
                f"{leaf_id}_{orig_type}"  # Use original type for ID consistency?
            )
            # Actually, let's stick to the mapped type for ID to avoid confusion,
            # BUT the frontend expects ID based on template type.
            # If template says "diagram", ID is "..._diagram".
            # If we save as "..._wiring_diagram", frontend won't find it.
            # So we must save with content_id = f"{leaf_id}_{orig_type}"

            saved = await supabase_service.save_chunk(
                vehicle_key=vehicle_key,
                content_id=final_content_id,
                chunk_type=db_chunk_type,
                template_type=template_type,
                title=chunk.title,
                data=chunk.data,
                sources=[cite.url for cite in chunk.source_cites if cite.url]
                or ["Generated content"],
                verification_status=db_verification_status,
                source_confidence=(
                    chunk.consensus_score if chunk.consensus_score else 0.75
                ),
                qa_status="pending",
                content_text=chunk.content_text,
                template_version=template_version,
            )

            if saved:
                final_response.append(
                    {
                        "content_id": final_content_id,
                        "chunk_type": orig_type,
                        "status": "ready",
                        "data": saved.data,
                        "content_text": saved.content_text,
                        "verification_status": saved.verification_status,
                        "source_confidence": saved.source_confidence,
                        "sources": saved.sources,
                    }
                )
            else:
                final_response.append(
                    {
                        "content_id": final_content_id,
                        "status": "error",
                        "error": "DB Save Failed",
                    }
                )
        else:
            final_response.append(
                {
                    "content_id": f"{leaf_id}_{orig_type}",
                    "status": "error",
                    "error": res.get("error") if res else "Unknown error",
                }
            )

    return {"status": "success", "chunks": final_response}
