from ddgs import DDGS
from models.vehicle import Vehicle
from models.chunk import SourceCitation
from typing import Dict, Any, List
import asyncio


class DDGSearchService:
    def __init__(self):
        self.enabled = True  # DDGS is free and doesn't require a key

    async def search_instant_answers(
        self, vehicle: Vehicle, concern: str
    ) -> Dict[str, Any]:
        """
        Run DDGS for instant answers and top results.
        Query: "{year} {make} {model} {concern} torque specs OR fluid capacity OR TSB"
        """
        query = f"{vehicle.year} {vehicle.make} {vehicle.model} {concern} torque specs OR fluid capacity OR TSB"

        try:
            # DDGS is synchronous. Wrap in executor.
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self._run_ddgs, query)

            citations = []
            for result in results:
                url = result.get("href", "")
                title = result.get("title", "")
                body = result.get("body", "")

                citations.append(
                    SourceCitation(
                        source_type="web",
                        url=url,
                        description=f"{title} - {body[:100]}...",
                        confidence=0.7,
                    )
                )

            return {
                "success": True,
                "results": results,
                "citations": citations,
                "cost": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "cost": 0.0}

    def _run_ddgs(self, query: str) -> List[Dict[str, str]]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=3))


ddg_service = DDGSearchService()
