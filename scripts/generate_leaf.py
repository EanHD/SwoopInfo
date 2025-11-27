import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "app"))

# Load environment variables from app/.env
load_dotenv(os.path.join(os.getcwd(), "app", ".env"))

from services.chunk_generator import chunk_generator
from models.vehicle import Vehicle
from models.chunk import ChunkType

import argparse

async def main():
    parser = argparse.ArgumentParser(description="Generate content for a specific leaf.")
    parser.add_argument("--leaf", required=True, help="Leaf ID to generate content for")
    parser.add_argument("--vehicle", default="2011_Ford_F-150_5.0L_V8", help="Vehicle string (Year_Make_Model_Engine)")
    args = parser.parse_args()

    # Parse vehicle string
    parts = args.vehicle.split("_")
    if len(parts) < 4:
        print("❌ Invalid vehicle format. Expected: Year_Make_Model_Engine")
        return
    
    year = parts[0]
    make = parts[1]
    model = parts[2]
    engine = "_".join(parts[3:]) # Handle engine with spaces/underscores

    # 1. Load Service Templates
    template_path = "assets/data/service_templates.json" # Use assets/data path
    if not os.path.exists(template_path):
        # Fallback to template/
        template_path = "template/service_templates.json"
    
    if not os.path.exists(template_path):
        print(f"❌ Template file not found: {template_path}")
        return

    with open(template_path, "r") as f:
        templates = json.load(f)

    leaf_id = args.leaf
    if leaf_id not in templates:
        print(f"❌ Leaf ID '{leaf_id}' not found in templates")
        return

    template = templates[leaf_id]
    print(f"🔧 Generating content for: {template['name']}")
    print(f"📝 Description: {template['description']}")
    
    # 2. Define Vehicle
    vehicle = Vehicle(
        year=year,
        make=make,
        model=model,
        engine=engine
    )
    print(f"🚙 Vehicle: {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.engine}")

    # 3. Generate Chunks
    print("\n🚀 Starting Generation...\n")
    
    generated_chunks = []
    
    for chunk_def in template["chunks"]:
        chunk_type = chunk_def["type"]
        title = chunk_def["title"]
        
        print(f"   Generating [{chunk_type}] {title}...")
        
        try:
            chunk, cost = await chunk_generator.generate_chunk(
                vehicle=vehicle,
                chunk_type=chunk_type,
                title=title,
                context=template["description"], # Use template description as context
                template_version="3.2-template"
            )
            
            generated_chunks.append(chunk)
            print(f"   ✅ Generated! Cost: ${cost:.4f} | Status: {chunk.verification_status}")
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    # 4. Output Results
    print("\n📊 Generation Summary:")
    print(f"   Total Chunks: {len(generated_chunks)}")
    
    output_file = f"generated_{leaf_id}.json"
    with open(output_file, "w") as f:
        # Convert chunks to dicts
        chunks_data = [chunk.model_dump() for chunk in generated_chunks]
        json.dump(chunks_data, f, indent=2, default=str)
        
    print(f"   💾 Saved to {output_file}")

    # Print one example chunk content
    if generated_chunks:
        print("\n📄 Example Chunk Content (First Chunk):")
        first_chunk = generated_chunks[0]
        print(f"Title: {first_chunk.title}")
        print("-" * 40)
        if first_chunk.data and "spec_items" in first_chunk.data:
             print(json.dumps(first_chunk.data["spec_items"], indent=2))
        else:
             print(first_chunk.content_text[:500] + "...")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
