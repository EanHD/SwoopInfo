"""
NHTSA Complaints API Integration
Mines real failure patterns from consumer complaints database.
"""

import httpx
from typing import List, Dict, Optional
from datetime import datetime
import re


class NHTSAComplaintsClient:
    """Client for NHTSA Vehicle Safety Complaints database."""

    BASE_URL = "https://api.nhtsa.gov/complaints"

    async def get_common_complaints(
        self,
        year: int,
        make: str,
        model: str,
        system: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Get common failure patterns from complaints database.

        Args:
            year: Vehicle year
            make: Vehicle make
            model: Vehicle model
            system: Optional filter (e.g. "ENGINE", "TRANSMISSION")
            limit: Max complaints to fetch

        Returns:
            List of complaint summaries with patterns
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # NHTSA Complaints API endpoint
                url = f"{self.BASE_URL}/complaintsByVehicle"
                params = {
                    "make": make.upper(),
                    "model": model.upper(),
                    "modelYear": year,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                complaints = data.get("results", [])

                # Filter by system if specified
                if system:
                    complaints = [
                        c
                        for c in complaints
                        if system.upper() in c.get("components", "").upper()
                    ]

                # Limit results
                complaints = complaints[:limit]

                # Parse and structure
                return self._parse_complaints(complaints)

        except Exception as e:
            print(f"⚠️  NHTSA Complaints API error: {e}")
            return []

    def _parse_complaints(self, raw_complaints: List[Dict]) -> List[Dict]:
        """Parse raw complaints into structured failure patterns."""
        parsed = []

        for complaint in raw_complaints:
            parsed_item = {
                "odi_number": complaint.get("odiNumber"),
                "date": complaint.get("dateComplaintFiled"),
                "component": complaint.get("components", "Unknown"),
                "summary": complaint.get("summary", ""),
                "crash": complaint.get("crash", False),
                "fire": complaint.get("fire", False),
                "injury": complaint.get("numberOfInjuries", 0) > 0,
                "mileage": complaint.get("mileage"),
            }
            parsed.append(parsed_item)

        return parsed

    def analyze_patterns(self, complaints: List[Dict]) -> Dict:
        """
        Analyze complaints to find common failure patterns.

        Returns:
            {
                "most_common_components": [...],
                "failure_keywords": [...],
                "safety_critical": bool,
                "average_mileage": int,
                "complaint_count": int,
            }
        """
        if not complaints:
            return {
                "most_common_components": [],
                "failure_keywords": [],
                "safety_critical": False,
                "average_mileage": 0,
                "complaint_count": 0,
            }

        # Count components
        component_counts = {}
        keywords = {}
        total_mileage = 0
        mileage_count = 0
        safety_critical = False

        for complaint in complaints:
            # Component counting
            component = complaint.get("component", "Unknown")
            component_counts[component] = component_counts.get(component, 0) + 1

            # Keyword extraction from summary
            summary = complaint.get("summary", "").lower()
            for word in self._extract_keywords(summary):
                keywords[word] = keywords.get(word, 0) + 1

            # Mileage averaging
            if complaint.get("mileage"):
                total_mileage += complaint["mileage"]
                mileage_count += 1

            # Safety critical detection
            if (
                complaint.get("crash")
                or complaint.get("fire")
                or complaint.get("injury")
            ):
                safety_critical = True

        # Sort and limit
        most_common = sorted(
            component_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
        top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "most_common_components": [c[0] for c in most_common],
            "failure_keywords": [k[0] for k in top_keywords],
            "safety_critical": safety_critical,
            "average_mileage": (
                total_mileage // mileage_count if mileage_count > 0 else 0
            ),
            "complaint_count": len(complaints),
        }

    def _extract_keywords(self, text: str, min_length: int = 4) -> List[str]:
        """Extract meaningful keywords from complaint text."""
        # Remove common words
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "have",
            "been",
            "when",
            "while",
            "after",
            "would",
        }

        # Extract words
        words = re.findall(r"\b[a-z]+\b", text.lower())

        # Filter
        keywords = [w for w in words if len(w) >= min_length and w not in stopwords]

        return keywords


# Singleton instance
nhtsa_complaints_client = NHTSAComplaintsClient()
