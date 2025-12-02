"""VehicleDatabases.com API client - THE production-ready repair data source."""

import os
import httpx
from typing import Optional, Dict, Any, List


class VehicleDatabasesService:
    def __init__(self):
        self.api_key = os.getenv("VEHICLEDATABASES_API_KEY", "")
        self.base_url = "https://api.vehicledatabases.com"
        self.enabled = bool(
            self.api_key and self.api_key != "your_vdb_key_here_do_not_commit"
        )

    async def get_repairs(
        self, vehicle: Any, concern: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get repair procedures, labor times, parts, costs."""
        if not self.enabled:
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try VIN first if available, otherwise YMM
                endpoint = f"{self.base_url}/repairs"
                params = {
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                }
                if hasattr(vehicle, "engine") and vehicle.engine:
                    params["engine"] = vehicle.engine
                if concern:
                    params["concern"] = concern

                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.get(endpoint, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data,
                        "citations": [
                            {
                                "source": "VehicleDatabases.com",
                                "url": f"{self.base_url}/repairs",
                                "confidence": "high",
                                "type": "api",
                            }
                        ],
                        "cost": 0.05,  # ~$0.05 per API call
                    }
                return {"success": False, "data": {}, "citations": [], "cost": 0.0}
        except Exception as e:
            print(f"VehicleDatabases repairs error: {e}")
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

    async def get_maintenance(
        self, vehicle: Any, mileage: int = 100000
    ) -> Dict[str, Any]:
        """Get maintenance schedules, fluid specs, torque specs."""
        if not self.enabled:
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                endpoint = f"{self.base_url}/maintenance"
                params = {
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "mileage": mileage,
                }
                if hasattr(vehicle, "engine") and vehicle.engine:
                    params["engine"] = vehicle.engine

                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.get(endpoint, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data,
                        "citations": [
                            {
                                "source": "VehicleDatabases.com",
                                "url": f"{self.base_url}/maintenance",
                                "confidence": "high",
                                "type": "api",
                            }
                        ],
                        "cost": 0.03,  # ~$0.03 per API call
                    }
                return {"success": False, "data": {}, "citations": [], "cost": 0.0}
        except Exception as e:
            print(f"VehicleDatabases maintenance error: {e}")
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

    async def get_recalls(self, vehicle: Any) -> Dict[str, Any]:
        """Get recalls for vehicle (supplements NHTSA)."""
        if not self.enabled:
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                endpoint = f"{self.base_url}/recalls"
                params = {
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                }

                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.get(endpoint, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data,
                        "citations": [
                            {
                                "source": "VehicleDatabases.com Recalls",
                                "url": f"{self.base_url}/recalls",
                                "confidence": "high",
                                "type": "api",
                            }
                        ],
                        "cost": 0.02,
                    }
                return {"success": False, "data": {}, "citations": [], "cost": 0.0}
        except Exception as e:
            print(f"VehicleDatabases recalls error: {e}")
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

    async def get_owners_manual(self, vehicle: Any) -> Dict[str, Any]:
        """Get owner's manual sections (for wiring, part locations)."""
        if not self.enabled:
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                endpoint = f"{self.base_url}/owners-manual"
                params = {
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                }

                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.get(endpoint, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data,
                        "citations": [
                            {
                                "source": "VehicleDatabases.com Owner's Manual",
                                "url": f"{self.base_url}/owners-manual",
                                "confidence": "high",
                                "type": "api",
                            }
                        ],
                        "cost": 0.02,
                    }
                return {"success": False, "data": {}, "citations": [], "cost": 0.0}
        except Exception as e:
            print(f"VehicleDatabases manual error: {e}")
            return {"success": False, "data": {}, "citations": [], "cost": 0.0}


vehicledatabases_service = VehicleDatabasesService()
