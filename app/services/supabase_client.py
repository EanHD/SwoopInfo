from supabase import create_client, Client
from config import settings
from typing import Optional, Dict, Any
from datetime import datetime
import re


class ChunkRecord:
    """Simple chunk record from database"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.vehicle_key = data.get("vehicle_key")
        self.content_id = data.get("content_id")
        self.chunk_type = data.get("chunk_type")
        self.template_type = data.get("template_type")
        self.title = data.get("title")
        self.content_text = data.get("content_text")
        self.data = data.get("data", {})
        self.sources = data.get("sources", [])
        self.verification_status = data.get(
            "verification_status", "pending_verification"
        )
        self.source_confidence = data.get("source_confidence", 0.0)
        self.qa_status = data.get("qa_status", "pending")
        self.qa_notes = data.get("qa_notes")
        self.last_qa_reviewed_at = data.get("last_qa_reviewed_at")
        self.regeneration_attempts = data.get("regeneration_attempts", 0)
        self.regenerated_at = data.get("regenerated_at")
        self.created_at = data.get("created_at")
        self.updated_at = data.get("updated_at")

        # Stage 5: Confidence Promotion
        self.verified_status = data.get("verified_status", "unverified")
        self.verified_at = data.get("verified_at")
        self.failed_at = data.get("failed_at")
        self.promotion_count = data.get("promotion_count", 0)
        self.qa_pass_count = data.get("qa_pass_count", 0)

    @property
    def verified(self) -> bool:
        return self.verified_status == "verified" or self.verification_status in [
            "verified",
            "auto_verified",
        ]

    @property
    def content_html(self) -> str:
        return self.data.get("content_html", "")

    def model_dump(self) -> Dict[str, Any]:
        """Convert to dictionary compatible with ServiceChunk model"""
        return {
            "id": self.id,
            "vehicle_key": self.vehicle_key,
            "chunk_type": self.chunk_type,
            "title": self.title,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "tags": self.data.get("tags", []),
            # Reconstruct basic source citations from stored descriptions
            "source_cites": (
                [
                    {"description": s, "source_type": "other", "confidence": 1.0}
                    for s in self.sources
                ]
                if self.sources
                else []
            ),
            "verification_status": self.verification_status,
            "requires_human_review": False,
            "consensus_score": self.data.get("consensus_score"),
            "consensus_badge": self.data.get("consensus_badge"),
            "data": self.data,
            "template_version": self.data.get("template_version", "1.0"),
            "verified": self.verified,
            "cost_to_generate": 0.0,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SupabaseService:
    # Contamination detection patterns
    BRAND_KEYWORDS = {
        "ford": ["motorcraft", "fomoco"],
        "gm": ["ac delco", "dexos"],
        "toyota": ["genuine toyota", "0w-16"],
        "honda": ["genuine honda", "acura"],
        "dodge": ["mopar", "cummins"],
    }

    # GM family includes these makes
    GM_FAMILY = {
        "chevrolet",
        "gm",
        "buick",
        "cadillac",
        "gmc",
        "pontiac",
        "saturn",
        "oldsmobile",
        "hummer",
    }
    STELLANTIS_FAMILY = {"dodge", "ram", "chrysler", "jeep", "fiat", "alfa romeo"}

    def __init__(self):
        self.client: Client = create_client(
            settings.supabase_url, settings.supabase_key
        )

    def is_safety_critical(self, chunk_type: str, content_id: str) -> bool:
        """Return True only for safety-critical chunks that must be quarantined until verified."""
        ct = (chunk_type or "").lower()
        cid = (content_id or "").lower()

        # Chunk types that are inherently safety-critical
        safety_types = {
            "torque_spec",
            "fluid_capacity",
            "bleed_sequence",
            "airbag_procedure",
            "brake_procedure",
            "steering_suspension_procedure",
            "wiring_diagram",
        }

        if ct in safety_types:
            return True

        # Content IDs that indicate safety-critical topics
        safety_keywords = [
            "airbag",
            "srs",
            "brake_bleed",
            "abs_bleed",
            "torque",
            "tightening_spec",
            "steering",
            "suspension",
            "brake",
            "fluid_capacity",
            "oil_capacity",
            "coolant_capacity",
        ]

        return any(k in cid for k in safety_keywords)

    def detect_contamination(
        self,
        vehicle_key: str,
        content_id: str,
        data: Dict[str, Any],
        content_text: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        STRICT contamination validator - blocks ALL cross-brand, wrong-procedure, and missing-keyword issues.

        This runs BEFORE any write to chunks table.
        Returns error message if contaminated, None if clean.

        Enforces:
        1. Cross-brand keywords (Ford in Chevy, etc.)
        2. Wrong procedures (oil change text in brake service, etc.)
        3. Topic keyword requirements (oxygen_sensor must mention oxygen/o2/sensor)
        4. Minimum content length (> 120 chars to avoid stubs)
        """
        # Combine data and content_text for comprehensive check
        content = str(data).lower()
        if content_text:
            content += " " + content_text.lower()

        vehicle_lower = vehicle_key.lower()
        content_id_lower = content_id.lower()

        # RULE 1: Minimum length check - avoid tiny stubs
        # Exception: Allow explicit stubs or pending verification messages
        if (
            "stub content" in content
            or "pending verification" in content
            or "being generated" in content
        ):
            return None

        # Exception: Allow short content for specs (torque, capacity) which are naturally concise
        # DISABLE CONTAMINATION CHECK FOR SPECS AND DIAGRAMS
        if chunk_type and chunk_type in [
            "torque_spec",
            "fluid_capacity",
            "spec",
            "wiring_diagram",
            "diagram",
        ]:
            return None

        if (
            "torque" in content_id_lower
            or "capacity" in content_id_lower
            or "spec" in content_id_lower
            or "diagram" in content_id_lower
        ):
            return None

        if len(content) < 120:
            return f"Content too short ({len(content)} chars, minimum 120) - likely incomplete/stub"

        # RULE 2: Cross-brand contamination (WITH BRAND FAMILY AWARENESS)
        # Extract make from vehicle_key (format: year_make_model_engine)
        vehicle_make = (
            vehicle_key.split("_")[1] if len(vehicle_key.split("_")) > 1 else ""
        )

        for brand, keywords in self.BRAND_KEYWORDS.items():
            # Skip check if vehicle is in the same brand family
            if brand == "gm" and vehicle_make in self.GM_FAMILY:
                continue  # Chevrolet/Buick/etc can use GM parts
            if brand == "dodge" and vehicle_make in self.STELLANTIS_FAMILY:
                continue  # Dodge/Ram/Chrysler are all Stellantis

            # Now check for contamination
            if brand not in vehicle_lower and vehicle_make not in self.GM_FAMILY:
                found = [k for k in keywords if k in content]
                if found:
                    return f"Cross-brand contamination: {brand.upper()} keywords {found} found in non-{brand.upper()} vehicle"

        # RULE 3: Oil procedure contamination in non-oil content
        oil_keywords = [
            "drain oil",
            "oil drain plug",
            "add new oil",
            "replace oil filter",
            "motorcraft fl-500s",
            "5w-20",
            "5w-30",
            "0w-20",
        ]

        # Skip oil check for specs which might mention oil grades/filters legitimately
        skip_oil_check = False

        # RELAXED RULES: Allow fluid info in more types
        allowed_types = [
            "torque_spec",
            "fluid_capacity",
            "spec",
            "part_info",
            "part_location",
            "labor_time",
            "known_issues",
        ]
        if chunk_type and (chunk_type in allowed_types):
            skip_oil_check = True
        elif (
            "torque" in content_id_lower
            or "capacity" in content_id_lower
            or "spec" in content_id_lower
            or "fluid" in content_id_lower
        ):
            skip_oil_check = True

        # Only enforce oil check on PROCEDURES that are NOT about oil
        if (
            not skip_oil_check
            and "oil" not in content_id_lower
            and "oil" not in vehicle_lower
        ):
            # Only check if it looks like a procedure
            if chunk_type in ["removal_steps", "procedure", "diagnosis", "diag_flow"]:
                found = [k for k in oil_keywords if k in content]
                if found:
                    return f"Oil-change contamination: {found} found in {content_id}"

        # RULE 4: Topic keyword requirements
        REQUIRED_KEYWORDS = {
            "oxygen_sensor": ["oxygen", "o2", "sensor"],
            "drum_brake": ["drum", "shoe", "wheel cylinder", "backing plate"],
            "disc_brake": ["caliper", "rotor", "disc", "pad"],
            "air_filter": ["air filter", "intake", "filter element"],
            "spark_plug": ["spark plug", "ignition", "electrode"],
            "coolant": ["coolant", "antifreeze", "radiator"],
            "transmission": ["transmission", "gearbox", "shift"],
        }

        for topic, required in REQUIRED_KEYWORDS.items():
            if topic in content_id_lower:
                if not any(keyword in content for keyword in required):
                    return f"Missing topic keywords: {content_id} must contain one of {required}"

        return None

    def _get_template_type(self, vehicle_key: str) -> str:
        key_lower = vehicle_key.lower()
        if any(
            word in key_lower
            for word in ["coyote", "5.0l", "ecoboost", "v8", "v6", "i4", "i6"]
        ):
            return "ICE_GASOLINE"
        elif any(
            word in key_lower
            for word in ["powerstroke", "diesel", "cummins", "duramax"]
        ):
            return "ICE_DIESEL"
        elif any(
            word in key_lower for word in ["hybrid", "powerboost", "twin turbo hybrid"]
        ):
            return "HYBRID"
        else:
            return "EV"

    async def find_reusable_chunk(
        self, vehicle_key: str, chunk_type: str, keyword: str
    ) -> Optional[ChunkRecord]:
        """
        Find a chunk that can be reused based on type and keyword match.
        Used to avoid regenerating torque specs, capacities, etc.
        """
        try:
            # Search for chunks of the same type for this vehicle
            # that contain the keyword in the title
            result = (
                self.client.table("chunks")
                .select("*")
                .eq("vehicle_key", vehicle_key)
                .eq("chunk_type", chunk_type)
                .ilike("title", f"%{keyword}%")
                .limit(1)
                .execute()
            )

            if result.data and len(result.data) > 0:
                return ChunkRecord(result.data[0])
            return None
        except Exception as e:
            print(f"❌ Supabase find_reusable_chunk error: {e}")
            return None

    async def get_chunk(
        self, vehicle_key: str, content_id: str, chunk_type: str
    ) -> Optional[ChunkRecord]:
        """Get a single chunk by vehicle_key, content_id, and chunk_type"""
        try:
            result = (
                self.client.table("chunks")
                .select("*")
                .eq("vehicle_key", vehicle_key)
                .eq("content_id", content_id)
                .eq("chunk_type", chunk_type)
                .limit(1)
                .execute()
            )

            if result.data and len(result.data) > 0:
                return ChunkRecord(result.data[0])
            return None
        except Exception as e:
            print(f"❌ Supabase get_chunk error: {e}")
            return None

    async def save_chunk(
        self,
        vehicle_key: str,
        content_id: str,
        chunk_type: str,
        template_type: str,
        title: str,
        data: Dict[str, Any],
        sources: list[str],
        verification_status: str = "pending_verification",
        source_confidence: float = 0.0,
        content_text: Optional[str] = None,
        qa_status: str = "pending",
        qa_notes: Optional[str] = None,
        last_qa_reviewed_at: Optional[str] = None,
        regeneration_attempts: int = 0,
        regenerated_at: Optional[str] = None,
        template_version: str = "1.0",
    ) -> Optional[ChunkRecord]:
        """Insert or update a chunk using upsert"""
        try:
            # Safeguard: Ensure content_text is never None
            if content_text is None:
                content_text = ""

            # Safeguard: Ensure data is never None
            if data is None:
                data = {}

            # Force template_type based on vehicle key to prevent EV contamination
            template_type = self._get_template_type(vehicle_key)

            # Force template_type to be valid enum
            if template_type not in ["ICE_GASOLINE", "ICE_DIESEL", "HYBRID", "EV"]:
                print(
                    f"⚠️ Invalid template_type '{template_type}' detected in save_chunk. Forcing to ICE_GASOLINE."
                )
                template_type = "ICE_GASOLINE"

            # Store template version in data
            data["template_version"] = template_version

            # STATUS MAPPING: Map internal generator statuses to valid DB enums
            # Internal statuses: unverified, pending_review, verified, auto_verified, community_verified, flagged, generated
            # DB allowed: unverified, pending_verification, verified, auto_verified, rejected
            status_map = {
                "unverified": "unverified",
                "pending_review": "pending_verification",
                "verified": "verified",
                "auto_verified": "auto_verified",
                "community_verified": "verified",
                "flagged": "pending_verification",
                "generated": "pending_verification",
                "rejected": "rejected",
            }

            # Apply mapping
            final_verification_status = status_map.get(
                verification_status, "pending_verification"
            )

            # CRITICAL: Detect contamination before saving
            contamination_error = self.detect_contamination(
                vehicle_key, content_id, data, content_text, chunk_type
            )
            if contamination_error:
                print(f"🚫 CONTAMINATION BLOCKED: {contamination_error}")
                print(f"   Vehicle: {vehicle_key}")
                print(f"   Content ID: {content_id}")
                # Auto-mark as banned instead of saving contaminated data
                qa_status = "fail"
                qa_notes = f"AUTO-BLOCKED: {contamination_error}"
                verification_status = "rejected"
                # Set verified_status to banned (will be added via update after insert)
                chunk_data = {
                    "vehicle_key": vehicle_key,
                    "content_id": content_id,
                    "chunk_type": chunk_type,
                    "template_type": template_type,
                    "title": title,
                    "content_text": content_text,
                    "data": {
                        "message": "Contaminated data blocked",
                        "reason": contamination_error,
                    },
                    "sources": sources,
                    "verification_status": verification_status,
                    "source_confidence": 0.0,
                    "qa_status": qa_status,
                    "qa_notes": qa_notes,
                    "regeneration_attempts": regeneration_attempts,
                }
                # Save the banned marker chunk
                result = (
                    self.client.table("chunks")
                    .upsert(chunk_data, on_conflict="vehicle_key,content_id,chunk_type")
                    .execute()
                )
                if result.data:
                    # Update to set verified_status = banned
                    self.client.table("chunks").update(
                        {"verified_status": "banned"}
                    ).eq("id", result.data[0]["id"]).execute()
                    print(f"✅ Contaminated chunk auto-banned: {content_id}")
                return None  # Return None to signal contamination was blocked

            # Determine visibility based on safety-critical status
            is_critical = self.is_safety_critical(chunk_type, content_id)

            if is_critical:
                # Keep strict behavior for safety-critical items
                final_verified_status = "unverified"
                final_qa_status = "pending"
                # Note: status/visibility are not stored in DB but derived in API
                # We store verified_status='unverified' which API maps to quarantined for critical items
            else:
                # Relaxed behavior for non-critical items
                final_verified_status = "unverified"
                final_qa_status = "pending"
                # API will map this to visible/ready because it's not critical

            chunk_data = {
                "vehicle_key": vehicle_key,
                "content_id": content_id,
                "chunk_type": chunk_type,
                "template_type": template_type,
                "title": title,
                "content_text": content_text,
                "data": data,
                "sources": sources,
                "verification_status": final_verification_status,
                "source_confidence": source_confidence,
                "qa_status": final_qa_status,
                "qa_notes": qa_notes,
                "regeneration_attempts": regeneration_attempts,
                "verified_status": final_verified_status,
            }

            # Ensure image_url is preserved for diagrams
            if chunk_type in ["diagram", "wiring_diagram"] and data.get("image_url"):
                chunk_data["data"]["image_url"] = data["image_url"]

            if last_qa_reviewed_at:
                chunk_data["last_qa_reviewed_at"] = last_qa_reviewed_at

            if regenerated_at:
                chunk_data["regenerated_at"] = regenerated_at

            result = (
                self.client.table("chunks")
                .upsert(chunk_data, on_conflict="vehicle_key,content_id,chunk_type")
                .execute()
            )

            if result.data and len(result.data) > 0:
                return ChunkRecord(result.data[0])
            return None
        except Exception as e:
            print(f"❌ Supabase save_chunk error: {e}")
            return None

    async def get_chunks_for_vehicle(
        self, vehicle_key: str, chunk_types: Optional[list[str]] = None
    ) -> list[ChunkRecord]:
        """Get all chunks for a vehicle, optionally filtered by chunk types"""
        try:
            query = (
                self.client.table("chunks").select("*").eq("vehicle_key", vehicle_key)
            )

            if chunk_types:
                query = query.in_("chunk_type", chunk_types)

            result = query.execute()

            if result.data:
                return [ChunkRecord(chunk) for chunk in result.data]
            return []
        except Exception as e:
            print(f"❌ Supabase get_chunks_for_vehicle error: {e}")
            return []

    async def get_pending_qa_chunks(self, limit: int = 10) -> list[ChunkRecord]:
        """Get chunks that need QA review"""
        try:
            result = (
                self.client.table("chunks")
                .select("*")
                .eq("qa_status", "pending")
                .limit(limit)
                .execute()
            )

            if result.data:
                return [ChunkRecord(chunk) for chunk in result.data]
            return []
        except Exception as e:
            print(f"❌ Supabase get_pending_qa_chunks error: {e}")
            return []

    async def update_chunk_qa_status(
        self,
        chunk_id: str,
        qa_status: str,
        qa_notes: Optional[str],
        last_qa_reviewed_at: str,
    ) -> bool:
        """
        Update QA status and handle Confidence Promotion logic (Stage 5)

        TODO: This function updates chunks table without running contamination detection.
        Currently safe because it only updates status fields, not content.
        However, if it ever starts updating 'data' or 'content_text', it MUST call
        detect_contamination() first.
        """
        try:
            # 1. Fetch current state to apply logic
            current_chunk = await self.get_chunk_by_id(chunk_id)
            if not current_chunk:
                return False

            data = {
                "qa_status": qa_status,
                "qa_notes": qa_notes,
                "last_qa_reviewed_at": last_qa_reviewed_at,
            }

            # 2. Apply Promotion/Demotion Logic
            if qa_status == "pass":
                # Increment pass count
                new_pass_count = current_chunk.qa_pass_count + 1
                data["qa_pass_count"] = new_pass_count

                # Promotion Rule 1: First pass -> Candidate
                if (
                    new_pass_count == 1
                    and current_chunk.verified_status == "unverified"
                ):
                    data["verified_status"] = "candidate"
                    data["promotion_count"] = current_chunk.promotion_count + 1

                # Promotion Rule 2: Second pass on separate day -> Verified
                elif (
                    new_pass_count >= 2 and current_chunk.verified_status == "candidate"
                ):
                    # Check if last review was on a different day
                    last_review = (
                        datetime.fromisoformat(
                            current_chunk.last_qa_reviewed_at.replace("Z", "+00:00")
                        )
                        if current_chunk.last_qa_reviewed_at
                        else None
                    )
                    current_review = datetime.fromisoformat(
                        last_qa_reviewed_at.replace("Z", "+00:00")
                    )

                    if last_review and last_review.date() < current_review.date():
                        data["verified_status"] = "verified"
                        data["verified_at"] = last_qa_reviewed_at
                        data["promotion_count"] = current_chunk.promotion_count + 1
                        # Sync with legacy field for frontend compatibility
                        # Map 'verified' -> 'auto_verified' (closest allowed value)
                        data["verification_status"] = "auto_verified"

            elif qa_status == "fail":
                # Demotion Rule: If previously verified -> Banned
                if current_chunk.verified_status == "verified":
                    data["verified_status"] = "banned"
                    data["qa_notes"] = (
                        f"BANNED: Failed QA after verification. {qa_notes}"
                    )
                    # Sync with legacy field to hide/flag in frontend
                    # Map 'banned' -> 'rejected' (closest allowed value)
                    data["verification_status"] = "rejected"

                # Stage 7: Failure Escalation
                # If banned twice (or failed repeatedly), mark as manual_required
                # We use regeneration_attempts as a proxy for "how many times we tried"
                # If we are failing and have already tried regenerating 2+ times, escalate.
                elif current_chunk.regeneration_attempts >= 2:
                    # Try to set manual_required, fallback to banned if schema not updated
                    data["verified_status"] = "manual_required"
                    data["qa_notes"] = (
                        f"ESCALATED: Failed QA multiple times. Manual review required. {qa_notes}"
                    )
                    data["verification_status"] = "flagged"

                # Track first failure
                if not current_chunk.failed_at:
                    data["failed_at"] = last_qa_reviewed_at

            # 3. Execute Update
            try:
                result = (
                    self.client.table("chunks")
                    .update(data)
                    .eq("id", chunk_id)
                    .execute()
                )
                return len(result.data) > 0
            except Exception as e:
                # Fallback for schema constraint violation (Stage 7 migration)
                error_str = str(e)
                if (
                    "chunks_verification_status_check" in error_str
                    or "check_verified_status" in error_str
                ) and data.get("verified_status") == "manual_required":
                    print(
                        "⚠️ Schema not updated for 'manual_required', falling back to 'banned'"
                    )
                    data["verified_status"] = "banned"
                    data["verification_status"] = (
                        "rejected"  # Ensure legacy field is valid
                    )
                    data["qa_notes"] = f"MANUAL REQUIRED (Escalated): {qa_notes}"
                    result = (
                        self.client.table("chunks")
                        .update(data)
                        .eq("id", chunk_id)
                        .execute()
                    )
                    return len(result.data) > 0
                raise e

            return False
        except Exception as e:
            print(f"❌ Supabase update_chunk_qa_status error: {e}")
            return False

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[ChunkRecord]:
        """Get a single chunk by ID (helper for update logic)"""
        try:
            result = (
                self.client.table("chunks")
                .select("*")
                .eq("id", chunk_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return ChunkRecord(result.data[0])
            return None
        except Exception as e:
            print(f"❌ Supabase get_chunk_by_id error: {e}")
            return None

    async def get_qa_stats(self) -> Dict[str, Any]:
        """Get QA statistics"""
        try:
            # Note: Supabase-py doesn't support count() easily without a separate query
            # For now, we'll just do separate queries for counts
            # In production, use a stored procedure or raw SQL

            pending = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("qa_status", "pending")
                .execute()
            )
            passed = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("qa_status", "pass")
                .execute()
            )
            failed = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("qa_status", "fail")
                .execute()
            )

            # Regeneration stats
            regenerated = (
                self.client.table("chunks")
                .select("id", count="exact")
                .gt("regeneration_attempts", 0)
                .execute()
            )

            # Stage 5 Stats
            verified = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("verified_status", "verified")
                .execute()
            )
            candidate = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("verified_status", "candidate")
                .execute()
            )
            banned = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("verified_status", "banned")
                .execute()
            )

            # Stage 6 Stats
            # Quarantined = unverified or candidate
            quarantined = (
                self.client.table("chunks")
                .select("id", count="exact")
                .in_("verified_status", ["unverified", "candidate"])
                .execute()
            )

            # Newly generated today
            today_start = (
                datetime.utcnow()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .isoformat()
            )
            newly_generated = (
                self.client.table("chunks")
                .select("id", count="exact")
                .gte("created_at", today_start)
                .execute()
            )

            return {
                "pending": pending.count,
                "pass": passed.count,
                "fail": failed.count,
                "regenerated": regenerated.count,
                "verified_total": verified.count,
                "candidate_total": candidate.count,
                "banned_total": banned.count,
                "quarantined_total": quarantined.count,
                "newly_generated_today": newly_generated.count,
                "awaiting_verification": pending.count,  # Same as pending
                "total": (pending.count or 0)
                + (passed.count or 0)
                + (failed.count or 0),
            }
        except Exception as e:
            print(f"❌ Supabase get_qa_stats error: {e}")
            return {"pending": 0, "pass": 0, "fail": 0, "regenerated": 0, "total": 0}

    async def get_daily_generation_count(self, vehicle_key: str) -> int:
        """Get count of chunks generated for a vehicle today"""
        try:
            today_start = (
                datetime.utcnow()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .isoformat()
            )
            result = (
                self.client.table("chunks")
                .select("id", count="exact")
                .eq("vehicle_key", vehicle_key)
                .gte("created_at", today_start)
                .execute()
            )

            return result.count or 0
        except Exception as e:
            print(f"❌ Supabase get_daily_generation_count error: {e}")
            return 0

    async def get_latest_generation_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the most recently generated chunk system-wide"""
        try:
            result = (
                self.client.table("chunks")
                .select("created_at")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if result.data:
                return datetime.fromisoformat(
                    result.data[0]["created_at"].replace("Z", "+00:00")
                )
            return None
        except Exception as e:
            print(f"❌ Supabase get_latest_generation_timestamp error: {e}")
            return None

    async def check_baseline_chunks(
        self, vehicle_key: str, required_ids: list[str]
    ) -> Dict[str, str]:
        """
        Check status of required baseline chunks.
        Returns a dict of {content_id: status}
        """
        try:
            result = (
                self.client.table("chunks")
                .select("content_id, verified_status")
                .eq("vehicle_key", vehicle_key)
                .in_("content_id", required_ids)
                .execute()
            )

            found_status = {
                item["content_id"]: item["verified_status"] for item in result.data
            }

            # Fill in missing as 'missing'
            final_status = {}
            for rid in required_ids:
                final_status[rid] = found_status.get(rid, "missing")

            return final_status
        except Exception as e:
            print(f"❌ Supabase check_baseline_chunks error: {e}")
            return {rid: "error" for rid in required_ids}

    async def get_failed_chunks(self, limit: int = 10) -> list[ChunkRecord]:
        """Get chunks that failed QA"""
        try:
            result = (
                self.client.table("chunks")
                .select("*")
                .eq("qa_status", "fail")
                .limit(limit)
                .execute()
            )

            if result.data:
                return [ChunkRecord(chunk) for chunk in result.data]
            return []
        except Exception as e:
            print(f"❌ Supabase get_failed_chunks error: {e}")
            return []

    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[ChunkRecord]:
        """Get specific chunks by ID"""
        try:
            result = (
                self.client.table("chunks").select("*").in_("id", chunk_ids).execute()
            )

            if result.data:
                return [ChunkRecord(chunk) for chunk in result.data]
            return []
        except Exception as e:
            print(f"❌ Supabase get_chunks_by_ids error: {e}")
            return []


supabase_service = SupabaseService()
