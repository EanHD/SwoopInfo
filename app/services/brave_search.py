"""
Brave Search API Integration
FREE tier: 2k queries/month, then $3/month
Real-world tips, forum fixes, YouTube videos
"""

import httpx
from typing import Optional, Dict, Any, List
from models.vehicle import Vehicle
from models.chunk import SourceCitation
from config import settings
import os


class BraveSearchService:
    def __init__(self):
        self.base_url = os.getenv(
            "BRAVE_BASE_URL", "https://api.search.brave.com/res/v1"
        )
        self.api_key = settings.brave_api_key
        self.timeout = 10.0
        self.enabled = bool(self.api_key and self.api_key != "your_brave_key_here")

    def _get_headers(self) -> Dict[str, str]:
        """Get required headers for Brave Search API"""
        return {"Accept": "application/json", "X-Subscription-Token": self.api_key}

    async def search_community_consensus(
        self, vehicle: Vehicle, concern: str
    ) -> Dict[str, Any]:
        """
        Run the 'Free MVP' search strategy with PRO UPGRADES (11-query pattern):
        1. Reddit (MechanicAdvice/JustRolledIntoTheShop)
        2. TSB/Common Fix/Labor Hours
        3. YouTube (Watch pages)
        4. Specific Forums (F150Forum, GM-Trucks, Honda-Tech, BobIsTheOilGuy)
        5. TightTorque & AutoZone (Torque Specs)
        6. TSBSearch & OBD-Codes (TSBs)
        7. Labor-Guides & FreeAutoMechanic (Labor Times)
        """
        if not self.enabled:
            return {"success": False, "error": "Brave Search API not configured"}

        queries = [
            # 1. Reddit Consensus (upvotes matter)
            f"site:reddit.com/r/MechanicAdvice OR site:reddit.com/r/JustRolledIntoTheShop OR site:reddit.com/r/AskMechanics {vehicle.year} {vehicle.make} {vehicle.model} {concern}",
            # 2. General Consensus with quality signals
            f"{vehicle.year} {vehicle.make} {vehicle.model} {concern} TSB OR service bulletin OR repair procedure OR labor time",
            # 3. YouTube Video Evidence (how-to + diagnostics)
            f"site:youtube.com/watch {vehicle.year} {vehicle.make} {vehicle.model} {concern} how to OR diagnostic OR repair",
            # 4. Specialized Forums (model-specific expertise)
            f"site:f150forum.com OR site:gm-trucks.com OR site:honda-tech.com OR site:fordtechmakuloco.com OR site:bobistheoilguy.com OR site:chryslerminivan.net {vehicle.model} {concern}",
            # 5. Torque Specs (high-quality technical sites)
            f"site:tighttorque.com OR site:torquecars.com {vehicle.year} {vehicle.make} {vehicle.model} torque specs",
            f"site:autozone.com/diy/repair-guides OR site:repairpal.com/estimator torque specs {vehicle.model}",
            # 6. TSB Databases (OEM-level data)
            f"site:tsbsearch.com OR site:safercar.gov OR site:nhtsa.gov {vehicle.year} {vehicle.make} {vehicle.model} {concern}",
            f"site:obd-codes.com OR site:troublecodes.net {vehicle.model} {concern}",
            # 7. Labor Guides (verified times)
            f"site:labor-guides.com OR site:alldata.com OR site:mitchell1.com {vehicle.year} {vehicle.make} {vehicle.model} {concern} labor time",
            f"site:freeautomechanic.com OR site:2carpros.com {vehicle.year} {vehicle.make} {vehicle.model} {concern}",
            # 8. OEM Resources (if publicly available)
            f"site:ford.com OR site:gm.com OR site:toyota.com OR site:honda.com service manual {vehicle.year} {vehicle.model} {concern}",
            # 9. Technical Blogs & Mechanic Networks
            f"site:yourmechanic.com OR site:carcomplaints.com OR site:carsurvey.org {vehicle.year} {vehicle.make} {vehicle.model} {concern}",
        ]

        all_results = []
        total_cost = 0.0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for q in queries:
                try:
                    url = f"{self.base_url}/web/search"
                    params = {
                        "q": q,
                        "count": 20,  # DEEPER BRAVE: Increased to 20 results per query
                        "search_lang": "en",
                    }

                    response = await client.get(
                        url, headers=self._get_headers(), params=params
                    )
                    response.raise_for_status()
                    data = response.json()

                    results = data.get("web", {}).get("results", [])
                    all_results.extend(results)
                    total_cost += 0.001  # Approximate cost per query

                except Exception as e:
                    print(f"Brave search error for query '{q}': {e}")
                    continue

        # Deduplicate results by URL
        unique_results = {r["url"]: r for r in all_results}.values()

        citations = []
        for result in unique_results:
            url = result.get("url", "")
            title = result.get("title", "")
            description = result.get("description", "")

            source_type = "other"
            if "reddit.com" in url:
                source_type = "reddit"
            elif "youtube.com" in url or "youtu.be" in url:
                source_type = "youtube"
            elif (
                "forum" in url
                or "gm-trucks" in url
                or "honda-tech" in url
                or "bobistheoilguy" in url
            ):
                source_type = "forum"
            elif "nhtsa" in url or "tsbsearch" in url:
                source_type = "tsb"

            citations.append(
                SourceCitation(
                    source_type=source_type,
                    url=url,
                    description=f"{title} - {description[:100]}...",
                    confidence=(
                        0.8
                        if source_type in ["reddit", "forum", "youtube", "tsb"]
                        else 0.6
                    ),
                )
            )

        return {
            "success": True,
            "results": list(unique_results),
            "citations": citations,
            "cost": total_cost,
        }

    async def search_mechanic_tips(
        self, vehicle: Vehicle, concern: str
    ) -> Dict[str, Any]:
        """
        Search for real-world mechanic tips and forum discussions.
        Returns top 3 results from forums, YouTube, and mechanic sites.
        """
        if not self.enabled:
            return {"success": False, "error": "Brave Search API not configured"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Build search query
                query = f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.engine} {concern} site:reddit.com OR site:youtube.com OR site:f150forum.com OR site:bobistheoilguy.com"

                url = f"{self.base_url}/web/search"
                params = {
                    "q": query,
                    "count": 5,  # Get top 5 results
                    "search_lang": "en",
                }

                response = await client.get(
                    url, headers=self._get_headers(), params=params
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("web", {}).get("results", [])
                citations = []

                for result in results[:3]:  # Top 3 only
                    url = result.get("url", "")
                    title = result.get("title", "")
                    description = result.get("description", "")

                    # Determine source type
                    source_type = "forum"
                    if "youtube.com" in url or "youtu.be" in url:
                        source_type = "other"

                    # Try to extract upvotes from reddit links (if available in snippet)
                    upvotes = None
                    if "reddit.com" in url and "upvote" in description.lower():
                        # Simple heuristic - would need actual Reddit API for accurate counts
                        upvotes = 25  # Conservative estimate

                    citations.append(
                        SourceCitation(
                            source_type=source_type,
                            url=url,
                            description=f"{title[:100]}",
                            confidence=0.75,  # Forum/web sources get medium confidence
                            upvotes=upvotes,
                        )
                    )

                return {
                    "success": True,
                    "results": results[:3],
                    "citations": citations,
                    "cost": 0.001,  # Approximate cost per search
                }
            except httpx.HTTPStatusError as e:
                return {
                    "success": False,
                    "error": f"Brave Search API error: {e.response.status_code}",
                    "cost": 0.001,
                }
            except Exception as e:
                return {"success": False, "error": str(e), "cost": 0.0}

    async def search_tsb(self, vehicle: Vehicle, tsb_number: str) -> Dict[str, Any]:
        """Search for specific TSB information"""
        if not self.enabled:
            return {"success": False, "error": "Brave Search API not configured"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                query = (
                    f"TSB {tsb_number} {vehicle.year} {vehicle.make} {vehicle.model}"
                )

                url = f"{self.base_url}/web/search"
                params = {"q": query, "count": 3}

                response = await client.get(
                    url, headers=self._get_headers(), params=params
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("web", {}).get("results", [])

                return {"success": True, "results": results, "cost": 0.001}
            except Exception as e:
                return {"success": False, "error": str(e), "cost": 0.0}

    async def search_diagram_images(
        self, vehicle: Vehicle, component: str
    ) -> Dict[str, Any]:
        """
        DISABLED UNTIL DIAGRAMS ARE PERFECT
        Search for wiring diagram images.
        """
        # DIAGRAMS DISABLED UNTIL PERFECT
        print(f"⏸️ DIAGRAM SEARCH DISABLED: {component}")
        return {
            "success": False,
            "error": "Diagram search disabled",
            "results": [],
            "cost": 0.0,
        }


brave_search_service = BraveSearchService()
