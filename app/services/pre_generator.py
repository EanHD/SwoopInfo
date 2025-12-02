from datetime import datetime, timedelta
from services.supabase_client import supabase_service
from services.performance import BatchDBWriter, parallel_generate_with_semaphore
from models.vehicle import Vehicle
import asyncio


class PreGenerator:
    # Map content_id to chunk_type
    BASELINE_CHUNKS = {
        "engine_oil_capacity": "spec",
        "oil_filter_location": "part_location",
        "torque_specs_common": "torque_spec",
        "serpentine_belt_diagram": "diagram",
        "engine_oil_type": "spec",
    }

    def __init__(self):
        self.last_pre_gen_time = None
        self.min_interval = timedelta(hours=1)

    async def trigger_pre_generation(self, vehicle_key: str):
        """
        Trigger background generation of baseline chunks.
        Rate limited to 1 vehicle per hour system-wide.

        PERFORMANCE: Uses parallel generation + batch DB writes.
        """
        # 1. Check Rate Limit
        now = datetime.utcnow()

        # Check in-memory first
        if (
            self.last_pre_gen_time
            and (now - self.last_pre_gen_time) < self.min_interval
        ):
            print(
                f"⏳ Pre-generation skipped: Rate limit active (Last: {self.last_pre_gen_time})"
            )
            return

        # Update lock
        self.last_pre_gen_time = now
        print(f"🚀 Starting PARALLEL pre-generation for {vehicle_key}")

        # 2. Parse Vehicle
        try:
            parts = vehicle_key.split("_")
            # Handle simple parsing, might need robust logic if key format varies
            if len(parts) < 4:
                print(f"❌ Invalid vehicle key format: {vehicle_key}")
                return

            vehicle = Vehicle(
                year=parts[0],
                make=parts[1],
                model="_".join(parts[2:-1]) if len(parts) > 4 else parts[2],
                engine=parts[-1],
            )
        except Exception as e:
            print(f"❌ Error parsing vehicle key {vehicle_key}: {e}")
            return

        # 3. Check which chunks need generation (in parallel)
        from services.chunk_generator import chunk_generator

        # First, check what already exists (single DB query)
        existing_chunks = await supabase_service.get_chunks_for_vehicle(vehicle_key)
        existing_ids = {c.content_id for c in existing_chunks}

        # Identify what needs to be generated
        chunks_to_generate = []
        for content_id, chunk_type in self.BASELINE_CHUNKS.items():
            if content_id not in existing_ids:
                chunks_to_generate.append((content_id, chunk_type))

        if not chunks_to_generate:
            print(f"✅ All baseline chunks already exist for {vehicle_key}")
            return

        print(f"⚡ Generating {len(chunks_to_generate)} baseline chunks in parallel...")

        # 4. Generate ALL chunks in parallel (no sequential sleeps)
        generation_tasks = []
        chunk_metadata = []  # Track content_id for each task

        for content_id, chunk_type in chunks_to_generate:
            concern = content_id.replace("_", " ")
            title = content_id.replace("_", " ").title()

            # Map chunk_type to the generator's expected format
            chunk_type_map = {
                "spec": "fluid_capacity",
                "part_location": "part_location",
                "torque_spec": "torque_spec",
                "diagram": "wiring_diagram",
            }
            ct_string = chunk_type_map.get(chunk_type, "known_issues")

            # Create generation task
            generation_tasks.append(
                chunk_generator.generate_chunk(
                    vehicle=vehicle,
                    chunk_type=ct_string,
                    title=title,
                    context=concern,
                    dtc_codes=[],
                )
            )
            chunk_metadata.append((content_id, chunk_type))

        # PERF: Run ALL generations in parallel with semaphore
        results = await parallel_generate_with_semaphore(generation_tasks)

        # 5. Batch save ALL generated chunks (single DB operation)
        batch_writer = BatchDBWriter()
        total_cost = 0.0
        success_count = 0

        for i, result in enumerate(results):
            content_id, chunk_type = chunk_metadata[i]

            if isinstance(result, Exception):
                print(f"❌ Pre-generation failed for {content_id}: {result}")
                continue

            service_chunk, cost = result
            total_cost += cost
            success_count += 1

            # Build chunk data for batch save
            chunk_data = {
                "vehicle_key": vehicle_key,
                "content_id": content_id,
                "chunk_type": chunk_type,
                "template_type": "ICE_GASOLINE",
                "title": service_chunk.title,
                "data": {
                    "content_html": service_chunk.content_html,
                    "content_text": service_chunk.content_text,
                    "sources": [
                        cite.url for cite in service_chunk.source_cites if cite.url
                    ],
                    "consensus_score": service_chunk.consensus_score,
                    "consensus_badge": service_chunk.consensus_badge,
                },
                "sources": [cite.url for cite in service_chunk.source_cites if cite.url]
                or ["Generated content"],
                "verification_status": service_chunk.verification_status,
                "source_confidence": (
                    service_chunk.consensus_score
                    if service_chunk.consensus_score
                    else 0.75
                ),
                "content_text": service_chunk.content_text,
                "qa_status": "pending",
            }
            await batch_writer.add(chunk_data)

        # PERF: Single bulk DB write
        saved_records = await batch_writer.flush(supabase_service)
        print(
            f"✅ Pre-generated {success_count} chunks (total cost: ${total_cost:.4f})"
        )
        print(f"💾 Batch saved {len(saved_records)} pre-generated chunks")


pre_generator = PreGenerator()
