"""
Concern → Nav Tree Mapper

Maps customer-reported concerns (from diagnostic wizard) to relevant nav_tree paths.
This ensures we always return structured, verifiable data instead of AI hallucinations.

Usage:
    from services.concern_mapper import concern_mapper
    
    paths = concern_mapper.map_concern_to_nav_paths(
        category="warning_light",
        symptoms=["check engine light on", "rough idle"],
        additional_info="light came on after filling gas"
    )
    # Returns: ["Warning Lights & Indicators/Check Engine Light (MIL)", 
    #           "Symptoms & Diagnostics/Performance Issues/Running Problems/Rough Idle"]
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class ConcernMapper:
    """Maps diagnostic wizard concerns to nav_tree paths."""
    
    def __init__(self):
        self._nav_tree: Optional[Dict] = None
        self._keyword_index: Dict[str, List[str]] = {}
        self._load_nav_tree()
    
    def _load_nav_tree(self):
        """Load nav_tree.json and build keyword index."""
        nav_tree_path = Path(__file__).parent.parent.parent / "assets" / "data" / "nav_tree.json"
        
        try:
            with open(nav_tree_path, 'r') as f:
                self._nav_tree = json.load(f)
            self._build_keyword_index()
        except Exception as e:
            print(f"⚠️ Could not load nav_tree.json: {e}")
            self._nav_tree = {"roots": {}}
    
    def _build_keyword_index(self):
        """Build reverse index: keyword → nav_tree paths."""
        self._keyword_index = {}
        
        def index_node(node: Any, path: str):
            """Recursively index nodes."""
            if isinstance(node, dict):
                # Extract tags
                tags = node.get('tags', [])
                for tag in tags:
                    if tag not in self._keyword_index:
                        self._keyword_index[tag] = []
                    self._keyword_index[tag].append(path)
                
                # Extract from node title (the key)
                title_keywords = self._extract_keywords(path.split('/')[-1])
                for kw in title_keywords:
                    if kw not in self._keyword_index:
                        self._keyword_index[kw] = []
                    if path not in self._keyword_index[kw]:
                        self._keyword_index[kw].append(path)
                
                # Recurse into 'sub'
                if 'sub' in node:
                    for child_name, child_node in node['sub'].items():
                        index_node(child_node, f"{path}/{child_name}")
        
        # Index all roots
        for root_name, root_node in self._nav_tree.get('roots', {}).items():
            index_node(root_node, root_name)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract searchable keywords from text."""
        # Normalize
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        words = text.split()
        
        # Filter short/common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'is', 'are', 'was', 'were'}
        return [w for w in words if len(w) > 2 and w not in stopwords]
    
    # ==================== CATEGORY MAPPINGS ====================
    
    # Direct mapping from wizard categories to nav_tree roots
    CATEGORY_TO_ROOTS = {
        "warning_light": [
            "Warning Lights & Indicators"
        ],
        "noise": [
            "Symptoms & Diagnostics/Noises"
        ],
        "performance": [
            "Symptoms & Diagnostics/Performance Issues",
            "Engine"
        ],
        "leak": [
            "Symptoms & Diagnostics/Leaks"
        ],
        "climate": [
            "HVAC"
        ],
        "electrical": [
            "Electrical & Lighting"
        ],
        "transmission": [
            "Transmission & Driveline"
        ],
        "brakes": [
            "Brakes & Traction Control"
        ],
        "steering": [
            "Steering & Suspension"
        ],
        "vibration": [
            "Symptoms & Diagnostics/Vibrations"
        ]
    }
    
    # Symptom keyword → specific nav paths
    SYMPTOM_KEYWORDS = {
        # Warning lights
        "check engine": ["Warning Lights & Indicators/Check Engine Light (MIL)"],
        "mil": ["Warning Lights & Indicators/Check Engine Light (MIL)"],
        "abs light": ["Warning Lights & Indicators/ABS Warning"],
        "airbag light": ["Warning Lights & Indicators/Airbag (SRS) Warning"],
        "srs light": ["Warning Lights & Indicators/Airbag (SRS) Warning"],
        "tpms": ["Warning Lights & Indicators/TPMS Warning"],
        "tire pressure": ["Warning Lights & Indicators/TPMS Warning"],
        "oil light": ["Warning Lights & Indicators/Oil Pressure Warning"],
        "temperature light": ["Warning Lights & Indicators/Temperature Warning"],
        "overheating": ["Warning Lights & Indicators/Temperature Warning", "Symptoms & Diagnostics/Performance Issues/Overheating"],
        "battery light": ["Warning Lights & Indicators/Battery/Charging Warning"],
        "charging": ["Warning Lights & Indicators/Battery/Charging Warning"],
        "brake light": ["Warning Lights & Indicators/Brake Warning"],
        "traction control": ["Warning Lights & Indicators/Traction Control Off"],
        "power steering light": ["Warning Lights & Indicators/Power Steering Warning"],
        "maintenance required": ["Warning Lights & Indicators/Maintenance Required"],
        
        # Noises
        "knocking": ["Symptoms & Diagnostics/Noises/Engine Noises/Knocking/Pinging"],
        "pinging": ["Symptoms & Diagnostics/Noises/Engine Noises/Knocking/Pinging"],
        "ticking": ["Symptoms & Diagnostics/Noises/Engine Noises/Ticking/Tapping"],
        "tapping": ["Symptoms & Diagnostics/Noises/Engine Noises/Ticking/Tapping"],
        "squealing": ["Symptoms & Diagnostics/Noises/Engine Noises/Squealing on Startup", "Symptoms & Diagnostics/Noises/Brake Noises/Squealing When Braking"],
        "grinding brakes": ["Symptoms & Diagnostics/Noises/Brake Noises/Grinding When Braking"],
        "whining steering": ["Symptoms & Diagnostics/Noises/Steering Noises/Whining When Turning"],
        "clunking": ["Symptoms & Diagnostics/Noises/Steering Noises/Clunking Over Bumps", "Symptoms & Diagnostics/Noises/Suspension Noises/Clunking Over Bumps"],
        
        # Performance
        "won't start": ["Symptoms & Diagnostics/Performance Issues/No Start"],
        "no start": ["Symptoms & Diagnostics/Performance Issues/No Start"],
        "cranks": ["Symptoms & Diagnostics/Performance Issues/No Start/Cranks But Won't Start"],
        "no crank": ["Symptoms & Diagnostics/Performance Issues/No Start/No Crank, No Start"],
        "rough idle": ["Symptoms & Diagnostics/Performance Issues/Running Problems/Rough Idle"],
        "stalling": ["Symptoms & Diagnostics/Performance Issues/Running Problems/Stalling"],
        "hesitation": ["Symptoms & Diagnostics/Performance Issues/Running Problems/Hesitation on Acceleration"],
        "loss of power": ["Symptoms & Diagnostics/Performance Issues/Running Problems/Loss of Power"],
        "surging": ["Symptoms & Diagnostics/Performance Issues/Running Problems/Surging"],
        
        # Leaks
        "oil leak": ["Symptoms & Diagnostics/Leaks/Engine Oil Leaks"],
        "coolant leak": ["Symptoms & Diagnostics/Leaks/Coolant Leaks"],
        "antifreeze leak": ["Symptoms & Diagnostics/Leaks/Coolant Leaks"],
        "transmission leak": ["Symptoms & Diagnostics/Leaks/Transmission Leaks"],
        "power steering leak": ["Symptoms & Diagnostics/Leaks/Other Leaks/Power Steering Leak"],
        "brake fluid leak": ["Symptoms & Diagnostics/Leaks/Other Leaks/Brake Fluid Leak"],
        "fuel leak": ["Symptoms & Diagnostics/Leaks/Other Leaks/Fuel Leak"],
        
        # Vibrations
        "vibration idle": ["Symptoms & Diagnostics/Vibrations/Vibration at Idle"],
        "vibration driving": ["Symptoms & Diagnostics/Vibrations/Vibration While Driving"],
        "vibration braking": ["Symptoms & Diagnostics/Vibrations/Vibration When Braking"],
        "steering wheel shake": ["Symptoms & Diagnostics/Vibrations/Steering Wheel Shake"],
    }
    
    def map_concern_to_nav_paths(
        self,
        category: str,
        symptoms: List[str] = None,
        additional_info: str = "",
        max_paths: int = 5
    ) -> List[str]:
        """
        Map a customer concern to relevant nav_tree paths.
        
        Args:
            category: Wizard category (warning_light, noise, performance, etc.)
            symptoms: List of symptom descriptions
            additional_info: Free-text additional context
            max_paths: Maximum number of paths to return
            
        Returns:
            List of nav_tree paths in order of relevance
        """
        paths = []
        symptoms = symptoms or []
        
        # 1. Start with category-level paths
        category_lower = category.lower().replace(" ", "_")
        if category_lower in self.CATEGORY_TO_ROOTS:
            paths.extend(self.CATEGORY_TO_ROOTS[category_lower])
        
        # 2. Match symptoms to specific paths
        combined_text = " ".join(symptoms).lower() + " " + additional_info.lower()
        
        for keyword, keyword_paths in self.SYMPTOM_KEYWORDS.items():
            if keyword in combined_text:
                for p in keyword_paths:
                    if p not in paths:
                        paths.append(p)
        
        # 3. Keyword search in index for anything we missed
        keywords = self._extract_keywords(combined_text)
        for kw in keywords:
            if kw in self._keyword_index:
                for p in self._keyword_index[kw][:2]:  # Limit per keyword
                    if p not in paths:
                        paths.append(p)
        
        # 4. Deduplicate and limit
        seen = set()
        unique_paths = []
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)
        
        return unique_paths[:max_paths]
    
    def get_chunks_for_path(self, nav_path: str) -> List[str]:
        """
        Get the chunk types needed for a specific nav_tree path.
        
        Args:
            nav_path: Full path like "Warning Lights & Indicators/Check Engine Light (MIL)"
            
        Returns:
            List of chunk IDs like ["diagnostic_info:obd", "dtc:common"]
        """
        parts = nav_path.split('/')
        node = self._nav_tree.get('roots', {})
        
        # Navigate to the node
        for part in parts:
            if part in node:
                node = node[part]
            elif 'sub' in node and part in node['sub']:
                node = node['sub'][part]
            else:
                return []  # Path not found
        
        # Return chunks if defined, otherwise default set
        if isinstance(node, dict) and 'chunks' in node:
            return node['chunks']
        
        # Default chunks based on tags
        tags = node.get('tags', []) if isinstance(node, dict) else []
        default_chunks = ['overview', 'specifications', 'common_problems']
        
        if 'diagnostic' in tags or 'dtc' in tags:
            default_chunks.extend(['diagnostic_info:obd', 'dtc:common'])
        if 'critical' in tags:
            default_chunks.append('known_issue:critical')
        if 'electrical' in tags:
            default_chunks.extend(['wiring_diagram', 'connector_pinout'])
        
        return default_chunks
    
    def get_job_type_for_concern(
        self,
        category: str,
        symptoms: List[str] = None
    ) -> Optional[str]:
        """
        Map concern to a job_chunk_map.json job type.
        
        Returns:
            Job type like "check_engine_light", "brake_pads_front", etc.
        """
        symptoms = symptoms or []
        combined = f"{category} {' '.join(symptoms)}".lower()
        
        # Direct mappings
        JOB_MAPPINGS = {
            "check engine": "check_engine_light",
            "oil change": "oil_change",
            "brake pad": "brake_pads_front",
            "brake noise": "brake_pads_front",
            "battery": "battery_replacement",
            "alternator": "alternator",
            "starter": "starter",
            "coolant": "coolant_flush",
            "transmission fluid": "transmission_service",
            "spark plug": "spark_plugs",
            "belt": "serpentine_belt",
            "tire rotation": "tire_rotation",
            "wiper": "wiper_blades",
            "headlight": "headlight_bulb",
            "air filter": "air_filter",
            "cabin filter": "cabin_filter",
        }
        
        for keyword, job_type in JOB_MAPPINGS.items():
            if keyword in combined:
                return job_type
        
        # Category-based fallback
        CATEGORY_JOBS = {
            "warning_light": "diagnostic",
            "noise": "diagnostic",
            "performance": "diagnostic",
            "leak": "diagnostic",
            "climate": "diagnostic",
            "electrical": "diagnostic",
            "transmission": "diagnostic",
            "brakes": "brake_pads_front",
        }
        
        return CATEGORY_JOBS.get(category.lower(), "diagnostic")
    
    def build_structured_request(
        self,
        vehicle_key: str,
        category: str,
        symptoms: List[str],
        additional_info: str = ""
    ) -> Dict[str, Any]:
        """
        Build a fully structured request for SwoopInfo API.
        
        This is what the diagnostic wizard output should become before
        being sent to the chunk generator.
        
        Returns:
            {
                "vehicle_key": "2019_honda_accord_20t",
                "nav_paths": [...],
                "chunk_ids": [...],
                "job_type": "diagnostic",
                "concern_text": "...",
                "priority": "normal"
            }
        """
        nav_paths = self.map_concern_to_nav_paths(
            category=category,
            symptoms=symptoms,
            additional_info=additional_info
        )
        
        # Collect all chunks needed
        all_chunks = set()
        for path in nav_paths:
            chunks = self.get_chunks_for_path(path)
            all_chunks.update(chunks)
        
        job_type = self.get_job_type_for_concern(category, symptoms)
        
        # Determine priority
        priority = "normal"
        combined = f"{category} {' '.join(symptoms)} {additional_info}".lower()
        if any(word in combined for word in ["critical", "won't start", "no brakes", "overheating", "smoke"]):
            priority = "high"
        if any(word in combined for word in ["fire", "smoke", "fuel leak", "brake failure"]):
            priority = "critical"
        
        return {
            "vehicle_key": vehicle_key,
            "nav_paths": nav_paths,
            "chunk_ids": list(all_chunks),
            "job_type": job_type,
            "concern_text": f"[{category.upper()}] {'; '.join(symptoms)}. {additional_info}".strip(),
            "priority": priority
        }


# Singleton instance
concern_mapper = ConcernMapper()


# Convenience function
def map_diagnostic_concern(
    vehicle_key: str,
    category: str,
    symptoms: List[str],
    additional_info: str = ""
) -> Dict[str, Any]:
    """
    Convenience function to map diagnostic wizard output to structured request.
    
    Example:
        result = map_diagnostic_concern(
            vehicle_key="2019_honda_accord_20t",
            category="warning_light",
            symptoms=["check engine light on", "rough idle"],
            additional_info="came on after filling gas"
        )
    """
    return concern_mapper.build_structured_request(
        vehicle_key=vehicle_key,
        category=category,
        symptoms=symptoms,
        additional_info=additional_info
    )
