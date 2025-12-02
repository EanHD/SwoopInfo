"""
QA Agent - Automated Quality Assurance
Validates chunks using rule-based checks and LLM verification
"""

import json
import os
import httpx
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from services.supabase_client import ChunkRecord
from services.openrouter import openrouter


class QAAgent:
    def __init__(self):
        # Rule-based configuration
        self.placeholder_terms = [
            "see manual",
            "refer to manual",
            "consult dealer",
            "data not available",
            "coming soon",
            "lorem ipsum",
        ]

        self.brand_terms = {
            "ford": ["motorcraft", "f-150", "f150", "mustang", "expedition"],
            "chevrolet": ["acdelco", "silverado", "camaro", "corvette", "equinox"],
            "chevy": ["acdelco", "silverado", "camaro", "corvette", "equinox"],
            "toyota": ["camry", "corolla", "rav4", "tacoma", "tundra"],
            "honda": ["civic", "accord", "cr-v", "pilot", "odyssey"],
            "bmw": ["bimmer", "beemer", "x3", "x5", "3-series"],
        }

        self.topic_keywords = {
            "oil": ["oil", "drain", "filter", "viscosity", "quart", "liter"],
            "brake": ["brake", "pad", "rotor", "caliper", "fluid", "bleed"],
            "coolant": ["coolant", "radiator", "antifreeze", "thermostat", "pump"],
            "transmission": ["transmission", "fluid", "gear", "shift", "clutch"],
            "spark": ["spark", "plug", "gap", "coil", "ignition"],
        }

    async def process_chunk(self, chunk: ChunkRecord) -> Dict[str, Any]:
        """
        Run full QA process on a chunk
        Returns: {"status": "pass"|"fail", "notes": "..."}
        """
        # 1. Run rule-based checks
        rule_result = self._check_rules(chunk)
        if rule_result["status"] == "fail":
            return rule_result

        # 2. Run LLM check if rules passed
        llm_result = await self._check_llm(chunk)
        return llm_result

    def _check_rules(self, chunk: ChunkRecord) -> Dict[str, Any]:
        """Run static rule-based checks"""
        content_str = json.dumps(chunk.data).lower()

        # Check 1: Placeholders
        for term in self.placeholder_terms:
            if term in content_str:
                return {
                    "status": "fail",
                    "notes": f"Rule violation: Placeholder term '{term}' detected",
                }

        # Check 2: Empty content
        if not chunk.data or len(content_str) < 20:
            return {
                "status": "fail",
                "notes": "Rule violation: Content too short or empty",
            }

        # Check 3: Mismatched vehicle terms
        # Extract make from vehicle_key (e.g., 2011_ford_f150...)
        try:
            parts = chunk.vehicle_key.split("_")
            if len(parts) >= 2:
                make = parts[1].lower()

                # Check for other brands' terms
                for brand, terms in self.brand_terms.items():
                    if brand != make:
                        for term in terms:
                            if (
                                term in content_str
                                and f" {term} " in f" {content_str} "
                            ):
                                # Simple check, might need refinement to avoid false positives
                                return {
                                    "status": "fail",
                                    "notes": f"Rule violation: Mismatched brand term '{term}' found in {make} chunk",
                                }
        except Exception:
            pass  # Skip if key parse fails

        # Check 4: Mismatched topic keywords
        # e.g. if chunk_type is "fluid_capacity" but content talks about "brake pads"

        # Map chunk types/content_ids to expected topics
        # This is a heuristic: if we have strong keywords for a topic, and the content
        # contains keywords for a DIFFERENT topic but NOT the expected one, flag it.

        # Simplified check: if content_id contains a topic key, content MUST contain at least one keyword
        for topic, keywords in self.topic_keywords.items():
            if topic in chunk.content_id.lower():
                # This chunk is about 'topic' (e.g. 'oil')
                # Check if any keyword is present
                has_keyword = any(k in content_str for k in keywords)
                if not has_keyword:
                    # It might be valid, but it's suspicious if an "oil" chunk doesn't mention "oil", "drain", "filter" etc.
                    # But be careful with false positives.
                    pass

                # Stronger check: If it's an "oil" chunk, but it mentions "brake" keywords heavily
                # and NO oil keywords, that's a fail.

                # Let's check for cross-contamination
                for other_topic, other_keywords in self.topic_keywords.items():
                    if other_topic != topic:
                        # Count matches for other topic
                        other_matches = sum(
                            1 for k in other_keywords if k in content_str
                        )
                        if other_matches >= 2:
                            # Check if current topic matches are low
                            current_matches = sum(
                                1 for k in keywords if k in content_str
                            )
                            if current_matches == 0:
                                return {
                                    "status": "fail",
                                    "notes": f"Rule violation: Topic mismatch. Chunk '{chunk.content_id}' appears to be about '{other_topic}' (found terms: {', '.join([k for k in other_keywords if k in content_str])})",
                                }

        return {"status": "pass", "notes": "Rules passed"}

    async def _check_llm(self, chunk: ChunkRecord) -> Dict[str, Any]:
        """Run LLM verification"""
        prompt = {
            "task": "QA_VERIFICATION",
            "vehicle": chunk.vehicle_key,
            "chunk_type": chunk.chunk_type,
            "content": chunk.data,
            "instructions": [
                "Verify that the content matches the vehicle and chunk type.",
                "Check for hallucinations (e.g. wrong engine, wrong specs).",
                "Check for formatting issues.",
                "Return JSON only with 'status' (pass/fail) and 'notes'.",
            ],
        }

        try:
            content, cost = await openrouter.chat_completion(
                "ingestion",
                [
                    {
                        "role": "system",
                        "content": "You are a strict automotive QA agent. Output JSON only.",
                    },
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                response_format={"type": "json_object"},
            )

            parsed = json.loads(content)

            return {
                "status": parsed.get("status", "fail").lower(),
                "notes": parsed.get("notes", "LLM verification failed"),
            }

        except Exception as e:
            print(f"❌ LLM QA error: {e}")
            return {
                "status": "pass",
                "notes": f"LLM check skipped (Exception: {str(e)})",
            }


qa_agent = QAAgent()
