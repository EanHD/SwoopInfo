from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from models.vehicle import Vehicle
from services.template_service import template_service
from services.openrouter import openrouter
from services.chunk_generator import chunk_generator
import json

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    vehicle: Vehicle


class ChatResponse(BaseModel):
    message: str
    leaf_id: Optional[str] = None
    chunks: List[Dict[str, Any]] = []


@router.post("/chat/generate", response_model=ChatResponse)
async def generate_chat_response(request: ChatRequest):
    """
    Smart Service Doc Generator Endpoint.
    1. Parses user query to find EXACT nav_tree leaf ID.
    2. Generates ONLY the chunks defined in service_templates.json for that leaf.
    3. Returns a structured report.
    """

    # 1. Find Candidates
    candidates = template_service.search_candidates(request.query, request.vehicle)

    if not candidates:
        return ChatResponse(
            message="I couldn't find a specific service procedure for that. Please check the full repair manual in the Navigation tab."
        )

    # 2. LLM Intent Parsing
    # We give the LLM the user query and the top candidates.
    # It must pick the BEST match or "NONE".

    candidates_text = "\n".join(
        [
            f"- ID: {c['id']}\n  Name: {c['name']}\n  Desc: {c['description']}"
            for c in candidates
        ]
    )

    prompt = f"""You are an expert automotive service advisor.
    
User Query: "{request.query}"
Vehicle: {request.vehicle.year} {request.vehicle.make} {request.vehicle.model} {request.vehicle.engine}

Available Service Procedures (Candidates):
{candidates_text}

Task: Identify the SINGLE best matching Procedure ID from the list above that answers the user's query.
- If the user is asking for a specific repair, spec, or procedure that matches one of the candidates, return that ID.
- If NONE of the candidates are a good match, return "NONE".

Rules:
- Return ONLY the ID string (or "NONE").
- Do not add any explanation or punctuation.
"""

    try:
        leaf_id, _ = await openrouter.chat_completion(
            "ingestion",  # Use fast/free model
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        leaf_id = leaf_id.strip()

        # Clean up potential markdown
        if leaf_id.startswith("`"):
            leaf_id = leaf_id.replace("`", "")

    except Exception as e:
        print(f"LLM Intent Parsing Failed: {e}")
        return ChatResponse(
            message="I'm having trouble understanding that request right now."
        )

    if leaf_id == "NONE" or not template_service.get_template(leaf_id):
        return ChatResponse(
            message="I can help with that in the full repair section, but I don't have a quick report for it yet."
        )

    # 3. Generate Chunks
    template = template_service.get_template(leaf_id)
    chunks_def = template.get("chunks", [])

    if not chunks_def:
        return ChatResponse(
            message=f"I found the topic '{template['name']}', but it has no content definitions."
        )

    # Use chunk_generator to generate the bundle
    # We reuse generate_leaf_bundle logic but we might want to customize it
    # actually generate_leaf_bundle is perfect.

    bundle_result = await chunk_generator.generate_leaf_bundle(
        vehicle=request.vehicle, leaf_id=leaf_id, chunks_def=chunks_def
    )

    # Format results for response
    generated_chunks = []
    results = bundle_result.get("results", {})

    for key, res in results.items():
        if res.get("status") == "success":
            chunk = res.get("chunk")
            # Convert chunk model to dict
            chunk_dict = chunk.dict() if hasattr(chunk, "dict") else chunk
            generated_chunks.append(chunk_dict)

    return ChatResponse(
        message=f"Here is the Custom Service Report for {template['name']}.",
        leaf_id=leaf_id,
        chunks=generated_chunks,
    )
