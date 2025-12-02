"""
Template Loader Service - Vehicle-aware navigation tree loading
Loads v3 templates based on powertrain type with vehicle-specific filtering

PERFORMANCE: Templates are cached aggressively since they rarely change.
"""

import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from functools import lru_cache
from models.vehicle import Vehicle
from services.performance import template_cache


class TemplateLoader:
    """Loads and filters navigation templates based on vehicle powertrain"""

    TEMPLATE_DIR = Path(__file__).parent.parent.parent / "swooptemplates"
    FALLBACK_NAV_TREE = Path(__file__).parent.parent.parent / "assets" / "data" / "nav_tree.json"

    TEMPLATE_MAP = {
        "ICE_GASOLINE": "v3_ice_gasoline_template.json",
        "ICE_DIESEL": "v3_ice_diesel_template.json",
        "HYBRID": "v3_hybrid_template.json",
        "EV": "v3_ev_template.json",
    }

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._fallback_template: Optional[Dict] = None
        self._load_all_templates()

    def _load_all_templates(self):
        """Preload all templates into memory on startup, with fallback to nav_tree.json"""
        loaded_count = 0
        
        # First, try to load v3 templates
        for powertrain, filename in self.TEMPLATE_MAP.items():
            template_path = self.TEMPLATE_DIR / filename

            if not template_path.exists():
                print(f"⚠️ Template not found: {template_path} - will use fallback")
                continue

            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    template_data = json.load(f)

                # Validate template structure
                self._validate_template(template_data, powertrain)

                self._cache[powertrain] = template_data
                loaded_count += 1
                print(
                    f"✅ Loaded template: {powertrain} ({len(json.dumps(template_data))} bytes)"
                )
            except Exception as e:
                print(f"⚠️ Failed to load {powertrain} template: {e}")
        
        # Load fallback nav_tree.json for powertrains without v3 templates
        if self.FALLBACK_NAV_TREE.exists():
            try:
                with open(self.FALLBACK_NAV_TREE, "r", encoding="utf-8") as f:
                    self._fallback_template = json.load(f)
                    # Wrap in v3-compatible structure
                    self._fallback_template = self._convert_v2_to_v3_structure(self._fallback_template)
                print(f"✅ Loaded fallback nav_tree.json")
            except Exception as e:
                print(f"⚠️ Failed to load fallback nav_tree: {e}")
        
        # Populate cache with fallback for missing powertrains
        for powertrain in self.TEMPLATE_MAP.keys():
            if powertrain not in self._cache and self._fallback_template:
                self._cache[powertrain] = self._fallback_template.copy()
                print(f"📋 Using fallback template for: {powertrain}")
        
        # SERVERLESS FALLBACK: If no templates loaded, use hardcoded minimal template
        if not self._cache:
            print("⚠️ No templates found - using hardcoded minimal template for serverless")
            minimal_template = self._get_hardcoded_minimal_template()
            for powertrain in self.TEMPLATE_MAP.keys():
                self._cache[powertrain] = minimal_template.copy()
        
        print(f"✅ Template loader ready: {len(self._cache)} powertrains configured")
    
    def _get_hardcoded_minimal_template(self) -> Dict:
        """Hardcoded minimal template for serverless environments where files aren't available"""
        return {
            "template_type": "UNIVERSAL",
            "template_version": "3.0",
            "systems": {
                "engine": {
                    "label": "Engine",
                    "icon": "engine",
                    "children": {
                        "oil_change": {"label": "Oil Change", "service_type": "oil_change"},
                        "timing": {"label": "Timing Belt/Chain", "service_type": "timing"},
                        "cooling": {"label": "Cooling System", "service_type": "cooling"}
                    }
                },
                "brakes": {
                    "label": "Brakes",
                    "icon": "brake",
                    "children": {
                        "pads_rotors": {"label": "Pads & Rotors", "service_type": "brake_pads"},
                        "fluid": {"label": "Brake Fluid", "service_type": "brake_fluid"},
                        "calipers": {"label": "Calipers", "service_type": "calipers"}
                    }
                },
                "suspension": {
                    "label": "Suspension & Steering",
                    "icon": "suspension",
                    "children": {
                        "shocks_struts": {"label": "Shocks & Struts", "service_type": "shocks"},
                        "alignment": {"label": "Alignment", "service_type": "alignment"},
                        "ball_joints": {"label": "Ball Joints", "service_type": "ball_joints"}
                    }
                },
                "electrical": {
                    "label": "Electrical",
                    "icon": "electrical",
                    "children": {
                        "battery": {"label": "Battery", "service_type": "battery"},
                        "alternator": {"label": "Alternator", "service_type": "alternator"},
                        "starter": {"label": "Starter", "service_type": "starter"}
                    }
                },
                "transmission": {
                    "label": "Transmission",
                    "icon": "transmission",
                    "children": {
                        "fluid": {"label": "Fluid Service", "service_type": "trans_fluid"},
                        "clutch": {"label": "Clutch", "service_type": "clutch"}
                    }
                },
                "diagnostics": {
                    "label": "Diagnostics",
                    "icon": "diagnostic",
                    "children": {
                        "check_engine": {"label": "Check Engine Light", "service_type": "cel_diag"},
                        "performance": {"label": "Performance Issues", "service_type": "performance_diag"}
                    }
                }
            },
            "_metadata": {
                "source": "hardcoded_serverless_fallback",
                "note": "Minimal template for when file templates are unavailable"
            }
        }
    
    def _convert_v2_to_v3_structure(self, v2_template: Dict) -> Dict:
        """Convert v2 nav_tree.json to v3 template structure"""
        return {
            "template_type": "UNIVERSAL",
            "template_version": "3.0",
            "systems": v2_template.get("roots", {}),
            "_metadata": {
                "source": "nav_tree.json",
                "converted": True
            }
        }

    def _validate_template(self, template: Dict, powertrain: str):
        """Validate template structure"""
        required_keys = ["template_type", "template_version"]
        for key in required_keys:
            if key not in template:
                raise ValueError(f"Template {powertrain} missing required key: {key}")

        if template["template_type"] != powertrain:
            raise ValueError(
                f"Template type mismatch: expected {powertrain}, got {template['template_type']}"
            )

        # Version check: Allow 3.x (e.g. 3.0, 3.1)
        version = template["template_version"]
        try:
            # Future-proofing: Check major version only
            major = int(version.split(".")[0])
            if major != 3:
                raise ValueError(
                    f"Unsupported major template version: {version}. Expected 3.x"
                )
        except (ValueError, IndexError):
            # Fallback for non-standard version strings
            if version not in ["3.0", "3.1"]:
                raise ValueError(f"Unsupported template version: {version}")

    def determine_powertrain(
        self, engine: str, transmission: Optional[str] = None
    ) -> str:
        """
        Determine powertrain type from engine description

        Logic:
        - Diesel engine → ICE_DIESEL
        - Gasoline + electric/hybrid → HYBRID
        - Pure electric (no ICE) → EV
        - Default gasoline → ICE_GASOLINE
        """
        engine_lower = engine.lower()
        trans_lower = transmission.lower() if transmission else ""

        # Diesel detection
        if any(
            kw in engine_lower for kw in ["diesel", "turbodiesel", "tdi", "hdi", "dci"]
        ):
            return "ICE_DIESEL"

        # EV detection (no ICE)
        if any(kw in engine_lower for kw in ["electric", "battery", "bev"]) and not any(
            kw in engine_lower for kw in ["hybrid", "plug-in", "phev"]
        ):
            return "EV"

        # Hybrid detection
        if any(
            kw in engine_lower + trans_lower
            for kw in [
                "hybrid",
                "phev",
                "hev",
                "plug-in",
                "electric motor",
                "e-cvt",
                "hybrid synergy",
            ]
        ):
            return "HYBRID"

        # Default to gasoline ICE
        return "ICE_GASOLINE"

    def get_template(self, vehicle: Vehicle) -> Dict[str, Any]:
        """
        Get template for vehicle with dynamic filtering

        Args:
            vehicle: Vehicle object with year/make/model/engine

        Returns:
            Filtered template dictionary ready for navigation
        """
        powertrain = self.determine_powertrain(vehicle.engine)
        base_template = self._cache.get(powertrain)

        if not base_template:
            raise ValueError(f"Template not found for powertrain: {powertrain}")

        # Deep copy to avoid mutating cache
        import copy

        template = copy.deepcopy(base_template)

        # Apply vehicle-specific filters
        template = self._apply_vehicle_filters(template, vehicle)

        return template

    def _apply_vehicle_filters(self, template: Dict, vehicle: Vehicle) -> Dict:
        """
        Filter template nodes based on vehicle features

        Hides irrelevant sections:
        - 4WD/AWD systems if 2WD
        - Turbo/supercharger if naturally aspirated
        - Manual transmission sections if automatic
        """
        # Extract features from vehicle
        features = self._extract_vehicle_features(vehicle)

        # Recursively filter all sections
        filtered = {}
        for key, value in template.items():
            if key.startswith("_"):
                # Keep metadata as-is
                filtered[key] = value
            elif isinstance(value, dict):
                filtered_section = self._filter_section(value, features)
                if filtered_section:  # Only include if not empty
                    filtered[key] = filtered_section
            else:
                filtered[key] = value

        return filtered

    def _extract_vehicle_features(self, vehicle: Vehicle) -> Dict[str, bool]:
        """Extract boolean feature flags from vehicle"""
        engine_lower = vehicle.engine.lower()

        return {
            "has_turbo": any(
                kw in engine_lower
                for kw in ["turbo", "supercharged", "boosted", "twin-turbo"]
            ),
            "is_diesel": "diesel" in engine_lower,
            "is_hybrid": "hybrid" in engine_lower,
            "is_ev": "electric" in engine_lower and "hybrid" not in engine_lower,
            "is_4wd": any(kw in engine_lower for kw in ["4wd", "awd", "4x4"]),
            "is_manual": "manual" in engine_lower,
        }

    def _filter_section(
        self, section: Dict, features: Dict[str, bool]
    ) -> Optional[Dict]:
        """
        Recursively filter a section based on vehicle features

        Returns None if entire section should be hidden
        """
        # Check if section has requires_feature constraint
        requires = section.get("requires_feature", [])
        if requires:
            if not self._check_requirements(requires, features):
                return None  # Hide this section

        # Filter nested sections
        filtered = {}
        for key, value in section.items():
            if isinstance(value, dict):
                filtered_child = self._filter_section(value, features)
                if filtered_child:
                    filtered[key] = filtered_child
            else:
                filtered[key] = value

        return filtered if filtered else None

    def _check_requirements(
        self, requires: List[str], features: Dict[str, bool]
    ) -> bool:
        """Check if vehicle meets feature requirements"""
        for req in requires:
            req_lower = req.lower()

            # Feature mapping
            if req_lower in ["4wd", "awd"] and not features.get("is_4wd"):
                return False
            if req_lower == "turbo" and not features.get("has_turbo"):
                return False
            if req_lower == "manual" and not features.get("is_manual"):
                return False
            if req_lower == "diesel" and not features.get("is_diesel"):
                return False
            if req_lower == "hybrid" and not features.get("is_hybrid"):
                return False

        return True

    def get_searchable_nodes(self, template: Dict) -> List[Dict[str, Any]]:
        """
        Extract all searchable nodes from template for search indexing

        Returns list of {id, title, description, content_id, chunk_type, path, tags}
        """
        searchable = []

        def traverse(node: Dict, path: List[str] = [], parent_title: str = ""):
            if isinstance(node, dict):
                # Get current node's title, fallback to parent or generate from key
                current_title = node.get("title", parent_title)

                # Check if this is a leaf node with content
                if node.get("type") and node.get("content_id"):
                    content_id = node.get("content_id", "")

                    # If no title, generate from content_id
                    if not current_title:
                        current_title = content_id.replace("_", " ").title()

                    # Extract tags from path and title
                    tags = path + [
                        word.lower() for word in current_title.split() if len(word) > 3
                    ]

                    searchable.append(
                        {
                            "id": content_id,
                            "title": current_title,
                            "description": node.get("description", ""),
                            "content_id": content_id,
                            "chunk_type": node.get("type", ""),
                            "path": path,
                            "tags": list(set(tags)),  # Dedupe tags
                        }
                    )

                # Recurse into children with current title as parent
                for key, value in node.items():
                    if not key.startswith("_") and isinstance(value, dict):
                        new_path = path + [key]
                        traverse(value, new_path, current_title)

        traverse(template)
        return searchable

    def convert_to_flutter_format(self, template: Dict) -> List[Dict]:
        """
        Convert template to Flutter-compatible navigation structure

        Transforms nested dict into list of NavigationNode objects with:
        - Full path tracking for breadcrumbs
        - chunk_type extraction for content generation
        - Searchable flag propagation
        """
        categories = []

        # Map top-level sections to categories
        section_map = {
            "vehicle_info": {"title": "Vehicle Info", "icon": "info"},
            "dtcs": {"title": "Diagnostic Trouble Codes", "icon": "warning"},
            "tsbs_bulletins": {"title": "TSBs & Recalls", "icon": "document_text"},
            "maintenance": {"title": "Maintenance & Fluids", "icon": "oil_barrel"},
            "specifications": {"title": "Specifications", "icon": "list_bullet"},
            "diagrams": {"title": "Wiring & Diagrams", "icon": "map"},
            "parts_labor": {"title": "Parts & Labor", "icon": "wrench"},
            "systems": {"title": "Systems & Repairs", "icon": "engineering"},
        }

        for section_key, section_data in template.items():
            if section_key.startswith("_"):
                continue  # Skip metadata

            if section_key in section_map and isinstance(section_data, dict):
                mapping = section_map[section_key]
                category = {
                    "id": section_key,
                    "title": mapping["title"],
                    "icon": mapping["icon"],
                    "path": [section_key],
                    "subcategories": self._build_subcategories(
                        section_data, [section_key]
                    ),
                }
                categories.append(category)

        return categories

    def _build_subcategories(self, section: Dict, parent_path: List[str]) -> List[Dict]:
        """Recursively build subcategory tree with full paths and chunk metadata"""
        subcategories = []

        for key, value in section.items():
            if key.startswith("_") or not isinstance(value, dict):
                continue

            # Filter out UI Meta
            if key.lower() == "ui_meta" or value.get("title", "").lower() == "ui meta":
                continue

            current_path = parent_path + [key]

            # Create subcategory
            subcat = {
                "id": key,
                "title": value.get("title", key.replace("_", " ").title()),
                "path": current_path,
            }

            # Extract chunk metadata if this is a leaf node
            if "type" in value:
                subcat["chunk_type"] = value["type"]
            if "content_id" in value:
                subcat["content_id"] = value["content_id"]
            if "description" in value:
                subcat["description"] = value["description"]
            if "searchable" in value:
                subcat["searchable"] = value["searchable"]

            # Add icon if exists
            if "icon" in value:
                subcat["icon"] = value["icon"]

            # Recurse if has nested children (not a leaf node)
            if not subcat.get("chunk_type"):
                children = self._build_subcategories(value, current_path)
                if children:
                    subcat["subcategories"] = children

            subcategories.append(subcat)

        return subcategories


# Singleton instance
template_loader = TemplateLoader()
