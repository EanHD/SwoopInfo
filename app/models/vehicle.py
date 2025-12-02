from pydantic import BaseModel, Field
from typing import Optional


class Vehicle(BaseModel):
    year: str
    make: str
    model: str
    engine: str

    @property
    def key(self) -> str:
        """Generate canonical vehicle key for caching - MUST be 100% consistent"""
        # Normalize EVERYTHING: lowercase, no spaces, no dots, no dashes
        year = str(self.year)
        make = self.make.lower().strip().replace(" ", "")
        model = self.model.lower().strip().replace(" ", "").replace("-", "")
        # Engine: remove dots, spaces, keep letters (5.0L -> 50l)
        engine = self.engine.lower().strip().replace(".", "").replace(" ", "")

        return f"{year}_{make}_{model}_{engine}"


class VehicleConcern(BaseModel):
    vehicle: Vehicle
    concern: str = Field(..., description="Customer complaint or job description")
    dtc_codes: Optional[list[str]] = None
