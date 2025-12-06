from fastapi import APIRouter, HTTPException
from models.generation import GenerateChunksRequest, GenerateChunksResponse
from models.vehicle import Vehicle, VehicleConcern
from services.chunk_generator import chunk_generator
from services.supabase_client import supabase_service
from services.document_assembler import document_assembler
from services.vehicle_validator import vehicle_validator
from services.performance import BatchDBWriter, parallel_generate_with_semaphore
import asyncio
import time
import re

router = APIRouter()


@router.post("/generate-chunks", response_model=GenerateChunksResponse)
async def generate_chunks(request: GenerateChunksRequest):
    """
    The core endpoint: determine needed chunks, fetch existing, generate missing, compile document.
    ANTI-HALLUCINATION: Validates vehicle config BEFORE generation.
    """
    start_time = time.time()

    # Build vehicle and concern objects
    vehicle = Vehicle(
        year=request.year, make=request.make, model=request.model, engine=request.engine
    )

    # CRITICAL VALIDATION: Reject invalid/hallucinated vehicle configs
    is_valid, error_msg = vehicle_validator.is_valid(vehicle)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID VEHICLE CONFIGURATION",
                "message": error_msg,
                "vehicle_key": vehicle.key,
                "chunks_generated": 0,
                "chunks_found": 0,
                "total_cost": 0.0,
            },
        )

    concern = VehicleConcern(
        vehicle=vehicle, concern=request.concern, dtc_codes=request.dtc_codes
    )

    # Helper: Simple relevance scorer for Fast Path
    def is_relevant(chunk, concern_text, dtc_codes):
        text = (chunk.title + " " + chunk.content_text).lower()
        concern_tokens = set(concern_text.lower().split())
        # Remove common stop words
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "check",
            "vehicle",
            "issue",
            "problem",
        }
        concern_tokens = concern_tokens - stop_words

        # Check for DTC match
        if dtc_codes:
            for code in dtc_codes:
                if code.lower() in text:
                    return True

        # Check for keyword overlap
        matches = 0
        for token in concern_tokens:
            if token in text:
                matches += 1

        # If > 30% of concern words match, or at least 2 strong keywords
        return matches >= 2 or (
            len(concern_tokens) > 0 and matches / len(concern_tokens) > 0.3
        )

    # FAST PATH: Check if we have ANY chunks for this vehicle already
    all_existing_chunks = await supabase_service.get_chunks_for_vehicle(vehicle.key)

    # Filter for relevance to current concern
    primary_chunks = []
    related_chunks = []

    if all_existing_chunks:
        for chunk in all_existing_chunks:
            if is_relevant(chunk, request.concern, request.dtc_codes):
                primary_chunks.append(chunk)
            else:
                related_chunks.append(chunk)

    # If we have enough RELEVANT chunks, use them (Cache Hit)
    if len(primary_chunks) >= 3:
        compiled_doc = document_assembler.compile_diagnostic_document(
            vehicle=vehicle, chunks=primary_chunks, concern=request.concern
        )

        latency = time.time() - start_time

        return GenerateChunksResponse(
            vehicle_key=vehicle.key,
            concern=request.concern,
            chunks_found=len(primary_chunks),
            chunks_generated=0,
            chunks=[c.model_dump() for c in primary_chunks],
            related_chunks=[c.model_dump() for c in related_chunks],
            compiled_html=compiled_doc,
            total_cost=0.0,
            generation_time_seconds=latency,
        )

    # SLOW PATH: Need to identify and possibly generate chunks
    # Step 1: Identify needed chunks (Grok-4-Fast decides)
    needed_chunks = await chunk_generator.identify_needed_chunks(concern)

    if not needed_chunks:
        raise HTTPException(
            status_code=400, detail="Could not determine needed information chunks"
        )

    # Step 2: Check which chunks already exist (from our previous fetch)
    # We re-use all_existing_chunks to avoid DB hit, but we need to match by type/title
    existing_map = {(c.chunk_type, c.title): c for c in all_existing_chunks}

    final_primary_chunks = []
    chunks_to_generate = []
    total_cost = 0.0

    for chunk_type, title in needed_chunks:
        if (chunk_type, title) in existing_map:
            final_primary_chunks.append(existing_map[(chunk_type, title)])
        else:
            chunks_to_generate.append((chunk_type, title))

    # Step 3: Generate missing chunks in parallel (with semaphore limiting)
    if chunks_to_generate:
        generation_tasks = [
            chunk_generator.generate_chunk(
                vehicle, chunk_type, title, request.concern, request.dtc_codes or []
            )
            for chunk_type, title in chunks_to_generate
        ]

        # PERF: Use parallel_generate_with_semaphore for rate limiting
        results = await parallel_generate_with_semaphore(generation_tasks)

        # PERF: Batch collect all chunks for single DB write
        batch_writer = BatchDBWriter()
        generated_chunks = []

        for result in results:
            # Handle exceptions from gather
            if isinstance(result, Exception):
                print(f"❌ Chunk generation failed: {result}")
                continue

            chunk, cost = result
            total_cost += cost

            # Generate content_id from title
            content_id = re.sub(
                r"[^a-z0-9_]", "", chunk.title.lower().replace(" ", "_")
            )

            # Extract sources
            sources = [s.description for s in chunk.source_cites]

            # Construct data payload
            data = {
                "content_html": chunk.content_html,
                "consensus_score": chunk.consensus_score,
                "consensus_badge": chunk.consensus_badge,
                "tags": chunk.tags,
            }

            # Map verification_status to valid DB values
            # DB ONLY accepts: pending_verification, auto_verified, rejected
            status_map = {
                "unverified": "pending_verification",
                "pending_review": "pending_verification",
                "pending_verification": "pending_verification",
                "verified": "auto_verified",
                "auto_verified": "auto_verified",
                "community_verified": "auto_verified",
                "flagged": "pending_verification",  # Flagged items need review
                "generated": "pending_verification",
                "rejected": "rejected",
            }
            db_verification_status = status_map.get(
                chunk.verification_status, "pending_verification"
            )

            # PERF: Add to batch instead of individual save
            chunk_data = {
                "vehicle_key": chunk.vehicle_key,
                "content_id": content_id,
                "chunk_type": chunk.chunk_type,
                "template_type": "ICE_GASOLINE",  # Default
                "title": chunk.title,
                "data": data,
                "sources": sources,
                "verification_status": db_verification_status,
                "source_confidence": chunk.consensus_score or 0.0,
                "content_text": chunk.content_text,
                "qa_status": "pending",
            }
            await batch_writer.add(chunk_data)
            generated_chunks.append(chunk)

        # PERF: Single bulk DB write instead of N individual writes
        saved_records = await batch_writer.flush(supabase_service)
        print(f"⚡ Batch saved {len(saved_records)} chunks")

        # Add generated chunks to final list
        for chunk in generated_chunks:
            final_primary_chunks.append(chunk)
            all_existing_chunks.append(chunk)

    # Recalculate related chunks (everything not in final_primary)
    primary_ids = {
        c.id for c in final_primary_chunks if c.id
    }  # Generated chunks might not have ID yet if not re-fetched?
    # Actually save_chunk returns the chunk with ID.
    # But wait, existing chunks from DB have IDs.

    # Simple set difference based on object identity or ID
    # Let's just use the lists.
    final_related_chunks = [
        c for c in all_existing_chunks if c not in final_primary_chunks
    ]

    # Step 4: Compile chunks into beautiful document
    compiled_html = document_assembler.compile_diagnostic_document(
        vehicle=vehicle, concern=request.concern, chunks=final_primary_chunks
    )

    generation_time = time.time() - start_time

    return GenerateChunksResponse(
        vehicle_key=vehicle.key,
        concern=request.concern,
        chunks_found=len(final_primary_chunks) - len(chunks_to_generate),
        chunks_generated=len(chunks_to_generate),
        chunks=[chunk.model_dump() for chunk in final_primary_chunks],
        related_chunks=[chunk.model_dump() for chunk in final_related_chunks],
        compiled_html=compiled_html,
        total_cost=round(total_cost, 6),
        generation_time_seconds=round(generation_time, 2),
    )
