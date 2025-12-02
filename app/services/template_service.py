import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from models.vehicle import Vehicle


class TemplateService:
    """
    Manages loading and searching of service_templates.json.
    This is the source of truth for "Smart Service Doc" generation.
    """

    def __init__(self):
        self.templates: Dict[str, Dict] = {}
        self._load_templates()

    def _load_templates(self):
        """Load service_templates.json from assets"""
        # Path relative to app/services/
        base_path = Path(__file__).parent.parent.parent
        template_path = base_path / "assets" / "data" / "service_templates.json"

        if not template_path.exists():
            print(f"⚠️ service_templates.json not found at {template_path}")
            return

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                self.templates = json.load(f)
            print(f"✅ Loaded {len(self.templates)} service templates")
        except Exception as e:
            print(f"❌ Failed to load service_templates.json: {e}")

    def search_candidates(
        self, query: str, vehicle: Vehicle, limit: int = 20
    ) -> List[Dict]:
        """
        Find potential matching leaf nodes based on keyword overlap.
        Filters by vehicle tags (e.g. requires_ice).
        """
        query_terms = set(query.lower().split())
        candidates = []

        # Pre-calculate vehicle flags
        is_ice = (
            "electric" not in vehicle.engine.lower()
            or "hybrid" in vehicle.engine.lower()
        )
        is_diesel = "diesel" in vehicle.engine.lower()

        for leaf_id, data in self.templates.items():
            # 1. Check tags
            tags = data.get("tags", [])
            if "requires_ice" in tags and not is_ice:
                continue
            if "requires_diesel" in tags and not is_diesel:
                continue

            # 2. Score by keyword match
            text = (data.get("name", "") + " " + data.get("description", "")).lower()
            score = 0
            for term in query_terms:
                if term in text:
                    score += 1

            # Boost exact phrase match
            if query.lower() in text:
                score += 5

            if score > 0:
                candidates.append(
                    {
                        "id": leaf_id,
                        "name": data.get("name"),
                        "description": data.get("description"),
                        "score": score,
                    }
                )

        # Sort by score desc
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

    def get_template(self, leaf_id: str) -> Optional[Dict]:
        return self.templates.get(leaf_id)


template_service = TemplateService()
