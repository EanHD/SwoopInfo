"""
NHTSA vPIC + Safety API Integration
FREE, unlimited - VIN decode, specs, TSBs, recalls
"""

import httpx
from typing import Optional, Dict, Any, List
from models.vehicle import Vehicle
from models.chunk import SourceCitation
import os


class NHTSAService:
    def __init__(self):
        self.base_url = os.getenv("NHTSA_BASE_URL", "https://vpic.nhtsa.dot.gov/api")
        self.safety_url = os.getenv(
            "NHTSA_SAFETY_URL", "https://api.nhtsa.gov/SafetyRatings"
        )
        self.timeout = 15.0

    async def get_vehicle_specs(self, vehicle: Vehicle) -> Dict[str, Any]:
        """Get vehicle specifications from NHTSA vPIC"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Use modelyear/{year}/make/{make}/model/{model} endpoint
                url = f"{self.base_url}/vehicles/GetModelsForMakeYear/make/{vehicle.make}/modelyear/{vehicle.year}?format=json"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "data": data.get("Results", []),
                    "source": "nhtsa_vpic",
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_tsbs_and_recalls(self, vehicle: Vehicle) -> Dict[str, Any]:
        """Get TSBs and recalls for a vehicle"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            results = {"tsbs": [], "recalls": [], "citations": []}

            try:
                # Get recalls
                url = f"{self.safety_url}/modelyear/{vehicle.year}/make/{vehicle.make}/model/{vehicle.model}"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                if data.get("Results"):
                    for result in data["Results"]:
                        if result.get("VehicleId"):
                            # Get detailed info for each vehicle
                            detail_url = (
                                f"{self.safety_url}/VehicleId/{result['VehicleId']}"
                            )
                            detail_response = await client.get(detail_url)
                            if detail_response.status_code == 200:
                                detail_data = detail_response.json()
                                results["recalls"].append(detail_data)

                # Create citation for NHTSA data
                if results["recalls"]:
                    results["citations"].append(
                        SourceCitation(
                            source_type="nhtsa",
                            url=f"https://www.nhtsa.gov/vehicle/{vehicle.year}/{vehicle.make}/{vehicle.model}",
                            description=f"NHTSA Safety Ratings and Recalls for {vehicle.year} {vehicle.make} {vehicle.model}",
                            confidence=0.95,
                        )
                    )

                return results
            except Exception as e:
                return {"tsbs": [], "recalls": [], "citations": [], "error": str(e)}

    async def search_tsbs(self, vehicle: Vehicle, concern: str) -> List[Dict[str, Any]]:
        """
        Search for TSBs related to a specific concern.
        Note: NHTSA doesn't have a direct TSB search API, so we use SafetyRatings data.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Search complaints database (public API)
                url = f"https://api.nhtsa.gov/complaints/complaintsByVehicle"
                params = {
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "modelYear": vehicle.year,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Filter complaints related to concern
                relevant_complaints = []
                if data.get("results"):
                    concern_lower = concern.lower()
                    for complaint in data["results"][:10]:  # Limit to 10 most relevant
                        summary = complaint.get("summary", "").lower()
                        if any(word in summary for word in concern_lower.split()):
                            relevant_complaints.append(complaint)

                return relevant_complaints
            except Exception as e:
                return []


nhtsa_service = NHTSAService()
