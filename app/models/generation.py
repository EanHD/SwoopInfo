from pydantic import BaseModel, Field
from typing import Optional


class GenerateChunksRequest(BaseModel):
    year: str
    make: str
    model: str
    engine: str
    concern: str = Field(..., description="Customer complaint or job description")
    dtc_codes: Optional[list[str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "year": "2011",
                "make": "Ford",
                "model": "F-150",
                "engine": "5.0L",
                "concern": "cranks no start, died while driving",
            }
        }


class GenerateChunksResponse(BaseModel):
    vehicle_key: str
    concern: str
    chunks_found: int
    chunks_generated: int
    chunks: list
    related_chunks: list = []
    compiled_html: str
    total_cost: float
    generation_time_seconds: float
