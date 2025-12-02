"""
Streaming Generation Endpoint
Provides Server-Sent Events (SSE) for real-time generation progress.
Allows UI to show first chunks immediately while rest are generating.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models.generation import GenerateChunksRequest
from models.vehicle import Vehicle, VehicleConcern
from services.chunk_generator import chunk_generator
from services.supabase_client import supabase_service
from services.document_assembler import document_assembler
from services.vehicle_validator import vehicle_validator
from services.performance import (
    BatchDBWriter,
    ProgressTracker,
    parallel_generate_with_semaphore,
)
import asyncio
import json
import time
import re

router = APIRouter()


async def stream_generation(request: GenerateChunksRequest):
    """
    Generator function that yields SSE events as chunks are generated.
    Allows UI to display first chunks immediately (streaming preview).
    """
    start_time = time.time()

    # Build vehicle and concern objects
    vehicle = Vehicle(
        year=request.year,
        make=request.make,
        model=request.model,
        engine=request.engine,
    )

    # Validate vehicle
    is_valid, error_msg = vehicle_validator.is_valid(vehicle)
    if not is_valid:
        yield f"event: error\ndata: {json.dumps({'error': error_msg})}\n\n"
        return

    concern = VehicleConcern(
        vehicle=vehicle, concern=request.concern, dtc_codes=request.dtc_codes
    )

    # Check for existing chunks first (fast path)
    all_existing_chunks = await supabase_service.get_chunks_for_vehicle(vehicle.key)

    def is_relevant(chunk, concern_text, dtc_codes):
        text = (chunk.title + " " + chunk.content_text).lower()
        concern_tokens = set(concern_text.lower().split())
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

        if dtc_codes:
            for code in dtc_codes:
                if code.lower() in text:
                    return True

        matches = sum(1 for token in concern_tokens if token in text)
        return matches >= 2 or (
            len(concern_tokens) > 0 and matches / len(concern_tokens) > 0.3
        )

    primary_chunks = []
    related_chunks = []

    if all_existing_chunks:
        for chunk in all_existing_chunks:
            if is_relevant(chunk, request.concern, request.dtc_codes or []):
                primary_chunks.append(chunk)
            else:
                related_chunks.append(chunk)

    # If we have enough cached chunks, return immediately
    if len(primary_chunks) >= 3:
        yield f"event: cache_hit\ndata: {json.dumps({'message': 'Using cached chunks', 'count': len(primary_chunks)})}\n\n"

        for chunk in primary_chunks:
            yield f"event: chunk\ndata: {json.dumps(chunk.model_dump())}\n\n"

        compiled_doc = document_assembler.compile_diagnostic_document(
            vehicle=vehicle, chunks=primary_chunks, concern=request.concern
        )

        yield f"event: complete\ndata: {json.dumps({'chunks_found': len(primary_chunks), 'chunks_generated': 0, 'compiled_html': compiled_doc, 'total_cost': 0.0, 'generation_time_seconds': round(time.time() - start_time, 2)})}\n\n"
        return

    # Slow path: need to generate chunks
    yield f"event: status\ndata: {json.dumps({'message': 'Analyzing concern...', 'phase': 'identify'})}\n\n"

    needed_chunks = await chunk_generator.identify_needed_chunks(concern)

    if not needed_chunks:
        yield f"event: error\ndata: {json.dumps({'error': 'Could not determine needed information chunks'})}\n\n"
        return

    yield f"event: status\ndata: {json.dumps({'message': f'Generating {len(needed_chunks)} chunks...', 'phase': 'generate', 'total': len(needed_chunks)})}\n\n"

    # Check which chunks already exist
    existing_map = {(c.chunk_type, c.title): c for c in all_existing_chunks}
    final_primary_chunks = []
    chunks_to_generate = []

    for chunk_type, title in needed_chunks:
        if (chunk_type, title) in existing_map:
            chunk = existing_map[(chunk_type, title)]
            final_primary_chunks.append(chunk)
            # Stream existing chunks immediately
            yield f"event: chunk\ndata: {json.dumps(chunk.model_dump())}\n\n"
        else:
            chunks_to_generate.append((chunk_type, title))

    if chunks_to_generate:
        total_cost = 0.0
        batch_writer = BatchDBWriter()
        generated_count = 0

        # Generate chunks one by one and stream as they complete
        for i, (chunk_type, title) in enumerate(chunks_to_generate):
            yield f"event: progress\ndata: {json.dumps({'current': i + 1, 'total': len(chunks_to_generate), 'generating': title})}\n\n"

            try:
                chunk, cost = await chunk_generator.generate_chunk(
                    vehicle, chunk_type, title, request.concern, request.dtc_codes or []
                )
                total_cost += cost
                generated_count += 1

                # Stream chunk immediately as it's generated (streaming preview)
                yield f"event: chunk\ndata: {json.dumps({'title': chunk.title, 'chunk_type': chunk.chunk_type, 'content_html': chunk.content_html, 'verified': chunk.verified, 'consensus_score': chunk.consensus_score})}\n\n"

                # Add to batch for later DB write
                content_id = re.sub(
                    r"[^a-z0-9_]", "", chunk.title.lower().replace(" ", "_")
                )
                chunk_data = {
                    "vehicle_key": chunk.vehicle_key,
                    "content_id": content_id,
                    "chunk_type": chunk.chunk_type,
                    "template_type": "ICE_GASOLINE",
                    "title": chunk.title,
                    "data": {
                        "content_html": chunk.content_html,
                        "consensus_score": chunk.consensus_score,
                        "consensus_badge": chunk.consensus_badge,
                        "tags": chunk.tags,
                    },
                    "sources": [s.description for s in chunk.source_cites],
                    "verification_status": chunk.verification_status,
                    "source_confidence": chunk.consensus_score or 0.0,
                    "content_text": chunk.content_text,
                    "qa_status": "pending",
                }
                await batch_writer.add(chunk_data)
                final_primary_chunks.append(chunk)

            except Exception as e:
                yield f"event: chunk_error\ndata: {json.dumps({'title': title, 'error': str(e)})}\n\n"

        # Batch save all generated chunks
        yield f"event: status\ndata: {json.dumps({'message': 'Saving to database...', 'phase': 'save'})}\n\n"
        await batch_writer.flush(supabase_service)

    # Compile final document
    yield f"event: status\ndata: {json.dumps({'message': 'Compiling document...', 'phase': 'compile'})}\n\n"

    compiled_html = document_assembler.compile_diagnostic_document(
        vehicle=vehicle, concern=request.concern, chunks=final_primary_chunks
    )

    generation_time = time.time() - start_time

    yield f"event: complete\ndata: {json.dumps({'chunks_found': len(final_primary_chunks) - len(chunks_to_generate), 'chunks_generated': len(chunks_to_generate), 'compiled_html': compiled_html, 'total_cost': round(total_cost, 6), 'generation_time_seconds': round(generation_time, 2)})}\n\n"


@router.post("/generate-chunks-stream")
async def generate_chunks_stream(request: GenerateChunksRequest):
    """
    Stream chunk generation with Server-Sent Events.

    Returns chunks as they're generated, allowing UI to show:
    1. Immediate feedback (analyzing, generating...)
    2. First chunks within 1-2 seconds (streaming preview)
    3. Remaining chunks as they complete
    4. Final compiled document

    Event types:
    - status: Progress updates (phase, message)
    - progress: Generation progress (current/total, title)
    - chunk: Individual chunk data (stream as generated)
    - chunk_error: Error for specific chunk
    - cache_hit: All chunks found in cache
    - complete: Final response with compiled HTML
    - error: Fatal error
    """
    return StreamingResponse(
        stream_generation(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
