"""
CarQuery API Integration
FREE, unlimited - Vehicle database (year/make/model/trim/engine)
"""

import httpx
from typing import Optional, Dict, Any, List
from models.vehicle import Vehicle
import os


class CarQueryService:
    def __init__(self):
        self.base_url = os.getenv(
            "CARQUERY_BASE_URL", "https://www.carqueryapi.com/api/0.3"
        )
        self.timeout = 10.0

    async def get_trims(self, vehicle: Vehicle) -> Dict[str, Any]:
        """Get all trims for a vehicle (includes engine options)"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                params = {
                    "cmd": "getTrims",
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                }

                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

                trims = data.get("Trims", [])

                # Try to find matching engine
                matching_trim = None
                if vehicle.engine:
                    engine_normalized = (
                        vehicle.engine.lower().replace(" ", "").replace("l", "")
                    )
                    for trim in trims:
                        trim_engine = trim.get("model_engine_cc", "")
                        if engine_normalized in str(trim_engine).lower():
                            matching_trim = trim
                            break

                return {
                    "success": True,
                    "trims": trims,
                    "matching_trim": matching_trim or (trims[0] if trims else None),
                    "source": "carquery",
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_makes(self, year: str) -> List[str]:
        """Get all makes for a given year"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                params = {"cmd": "getMakes", "year": year}
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

                return [make["make_display"] for make in data.get("Makes", [])]
            except Exception as e:
                return []

    async def get_models(self, year: str, make: str) -> List[str]:
        """Get all models for a given year and make"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                params = {"cmd": "getModels", "year": year, "make": make}
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

                return [model["model_name"] for model in data.get("Models", [])]
            except Exception as e:
                return []


carquery_service = CarQueryService()
