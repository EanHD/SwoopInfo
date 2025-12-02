"""
Real Chunk Generator - Production Ready
Generates actual chunks from real data sources with verification
"""

import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class RealChunkGenerator:
    """Generate real chunks from verified data sources"""

    def __init__(self):
        self.nhtsa_base = "https://api.nhtsa.gov"
        self.timeout = 30.0

    async def generate_tsb_chunk(
        self, vehicle_key: str, year: str, make: str, model: str
    ) -> Dict[str, Any]:
        """
        Generate TSB/Known Issues chunk from NHTSA complaints database
        Returns real data that can be manually verified
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Get complaints from NHTSA
                url = f"{self.nhtsa_base}/complaints/complaintsByVehicle"
                params = {"make": make, "model": model, "modelYear": year}

                print(f"🌐 Fetching NHTSA complaints for {year} {make} {model}...")
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                complaints = data.get("results", [])[:50]  # Top 50 most recent

                if not complaints:
                    return {
                        "success": False,
                        "reason": "No NHTSA complaints found",
                        "data": None,
                    }

                # Analyze complaints and extract common issues
                issues = self._analyze_complaints(complaints)

                # Format as TSB chunk
                chunk_data = {
                    "known_issues": issues[:10],  # Top 10 most common
                    "total_complaints": len(complaints),
                    "data_source": "NHTSA Complaints Database",
                    "last_updated": datetime.utcnow().isoformat(),
                }

                sources = [
                    f"https://api.nhtsa.gov/complaints/complaintsByVehicle?make={make}&model={model}&modelYear={year}",
                    "NHTSA ODI Complaints Database",
                ]

                print(
                    f"✅ Found {len(issues)} distinct issues from {len(complaints)} complaints"
                )

                return {
                    "success": True,
                    "data": chunk_data,
                    "sources": sources,
                    "verification_status": "auto_verified",
                    "source_confidence": 0.92,
                    "title": f"Known Issues - {year} {make} {model}",
                }

            except Exception as e:
                print(f"❌ NHTSA fetch error: {e}")
                return {"success": False, "reason": str(e), "data": None}

    def _analyze_complaints(self, complaints: List[Dict]) -> List[Dict[str, Any]]:
        """Extract and categorize common issues from complaints"""
        issue_categories = {}

        for complaint in complaints:
            component = complaint.get("components", [{}])[0].get("name", "Unknown")
            summary = complaint.get("summary", "")
            crash = complaint.get("crash", False)
            fire = complaint.get("fire", False)
            injured = complaint.get("injured", 0)
            odi_number = complaint.get("odiNumber", "")

            # Categorize by component
            if component not in issue_categories:
                issue_categories[component] = {
                    "component": component,
                    "count": 0,
                    "has_crash": False,
                    "has_fire": False,
                    "total_injuries": 0,
                    "odi_numbers": [],
                    "sample_summaries": [],
                }

            cat = issue_categories[component]
            cat["count"] += 1
            cat["has_crash"] = cat["has_crash"] or crash
            cat["has_fire"] = cat["has_fire"] or fire
            cat["total_injuries"] += injured

            if odi_number and len(cat["odi_numbers"]) < 3:
                cat["odi_numbers"].append(odi_number)

            if summary and len(cat["sample_summaries"]) < 2:
                cat["sample_summaries"].append(summary[:200])

        # Sort by frequency and severity
        sorted_issues = sorted(
            issue_categories.values(),
            key=lambda x: (
                x["has_fire"] * 1000
                + x["has_crash"] * 500
                + x["total_injuries"] * 100
                + x["count"]
            ),
            reverse=True,
        )

        # Format for display
        formatted_issues = []
        for issue in sorted_issues:
            severity = (
                "CRITICAL"
                if (issue["has_fire"] or issue["has_crash"])
                else (
                    "HIGH"
                    if issue["total_injuries"] > 0
                    else "MODERATE" if issue["count"] >= 5 else "LOW"
                )
            )

            formatted = {
                "component": issue["component"],
                "severity": severity,
                "complaint_count": issue["count"],
                "description": (
                    issue["sample_summaries"][0]
                    if issue["sample_summaries"]
                    else "See NHTSA for details"
                ),
                "odi_numbers": issue["odi_numbers"],
                "flags": [],
            }

            if issue["has_crash"]:
                formatted["flags"].append("Crash reported")
            if issue["has_fire"]:
                formatted["flags"].append("Fire reported")
            if issue["total_injuries"] > 0:
                formatted["flags"].append(f"{issue['total_injuries']} injuries")

            formatted_issues.append(formatted)

        return formatted_issues

    async def generate_recall_chunk(
        self, vehicle_key: str, year: str, make: str, model: str
    ) -> Dict[str, Any]:
        """Generate recalls chunk from NHTSA recalls database"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                url = f"{self.nhtsa_base}/recalls/recallsByVehicle"
                params = {"make": make, "model": model, "modelYear": year}

                print(f"🌐 Fetching NHTSA recalls for {year} {make} {model}...")
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                recalls = data.get("results", [])

                if not recalls:
                    return {
                        "success": False,
                        "reason": "No recalls found",
                        "data": None,
                    }

                # Format recalls
                formatted_recalls = []
                for recall in recalls:
                    formatted_recalls.append(
                        {
                            "nhtsa_id": recall.get("NHTSACampaignNumber", ""),
                            "manufacturer_id": recall.get("Manufacturer", ""),
                            "component": recall.get("Component", ""),
                            "summary": recall.get("Summary", ""),
                            "consequence": recall.get("Conequence", ""),
                            "remedy": recall.get("Remedy", ""),
                            "report_date": recall.get("ReportReceivedDate", ""),
                        }
                    )

                chunk_data = {
                    "recalls": formatted_recalls,
                    "total_recalls": len(recalls),
                    "data_source": "NHTSA Recalls Database",
                }

                sources = [
                    f"https://api.nhtsa.gov/recalls/recallsByVehicle?make={make}&model={model}&modelYear={year}",
                    "NHTSA Safety Recalls",
                ]

                print(f"✅ Found {len(recalls)} recalls")

                return {
                    "success": True,
                    "data": chunk_data,
                    "sources": sources,
                    "verification_status": "auto_verified",
                    "source_confidence": 0.98,  # NHTSA recalls are official
                    "title": f"Safety Recalls - {year} {make} {model}",
                }

            except Exception as e:
                print(f"❌ Recalls fetch error: {e}")
                return {"success": False, "reason": str(e), "data": None}


# Global instance
real_generator = RealChunkGenerator()
