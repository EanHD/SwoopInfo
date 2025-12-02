from tavily import TavilyClient
from config import settings
from models.vehicle import Vehicle
from models.chunk import SourceCitation
from typing import Dict, Any, List
import os
import asyncio


class TavilySearchService:
    def __init__(self):
        self.api_key = settings.tavily_api_key
        self.enabled = bool(self.api_key and self.api_key != "your_tavily_key_here")
        if self.enabled:
            self.client = TavilyClient(api_key=self.api_key)
        else:
            self.client = None

    async def search_deep_research(
        self, vehicle: Vehicle, concern: str
    ) -> Dict[str, Any]:
        """
        Run Tavily Pro search for PDFs, TSBs, YouTube transcripts, and deep research.
        Enhanced query: Includes OEM sites, service bulletins, repair manuals, YouTube transcripts
        """
        if not self.enabled or not self.client:
            return {"success": False, "error": "Tavily API not configured"}

        # Enhanced query with more diverse sources
        query = f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.engine} {concern} service bulletin OR repair procedure OR torque specs OR labor time site:ford.com OR site:gm.com OR site:toyota.com OR site:honda.com OR site:tsbsearch.com OR site:alldata.com OR site:mitchell1.com OR filetype:pdf OR site:youtube.com"

        try:
            # Run synchronous Tavily client in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    query=query,
                    search_depth="advanced",
                    include_domains=[],
                    exclude_domains=[],
                    include_answer=True,
                    include_raw_content=False,
                    include_images=False,
                    max_results=5,
                ),
            )

            results = response.get("results", [])
            citations = []

            for result in results:
                url = result.get("url", "")
                title = result.get("title", "")
                content = result.get("content", "")

                source_type = "web"
                if url.endswith(".pdf"):
                    source_type = "pdf"
                elif "tsb" in url.lower():
                    source_type = "tsb"

                citations.append(
                    SourceCitation(
                        source_type=source_type,
                        url=url,
                        description=f"{title} - {content[:100]}...",
                        confidence=0.9 if source_type == "pdf" else 0.8,
                    )
                )

            return {
                "success": True,
                "results": results,
                "citations": citations,
                "cost": 0.005,  # Tavily advanced search is pricier
            }

        except Exception as e:
            return {"success": False, "error": str(e), "cost": 0.0}


tavily_service = TavilySearchService()
