from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

ChunkType = Literal[
    "fluid_capacity",
    "torque_spec",
    "part_location",
    "known_issues",
    "removal_steps",
    "wiring_diagram",
    "diagram",
    "diag_flow",
    "labor_time",
    "tsb",
    "part_info",
    "diagram_svg",
]


class SourceCitation(BaseModel):
    """Track where each fact came from"""

    source_type: Literal[
        "nhtsa",
        "tsb",
        "forum",
        "public_manual",
        "api",
        "reddit",
        "youtube",
        "warning",
        "vision_analysis",
        "other",
    ]
    url: Optional[str] = None
    tsb_number: Optional[str] = None
    description: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    upvotes: Optional[int] = None  # For forum posts
    video_thumbnail: Optional[str] = None  # YouTube thumbnail URL
    video_timestamp: Optional[str] = None  # Best timestamp (e.g., "2:45")

    @property
    def is_high_confidence(self) -> bool:
        """
        Determine if this source is high-confidence for auto-approval.
        High confidence = NHTSA, TSB, public manual, or forum post with 50+ upvotes
        """
        if self.source_type in ["nhtsa", "tsb", "public_manual"]:
            return self.confidence >= 0.85
        elif (
            self.source_type in ["forum", "reddit"]
            and self.upvotes
            and self.upvotes >= 50
        ):
            return self.confidence >= 0.8
        return False


class ServiceChunk(BaseModel):
    id: Optional[str] = None
    content_id: Optional[str] = None  # Added for One-to-One Architecture
    vehicle_key: str
    chunk_type: ChunkType
    title: str
    content_html: str
    content_text: str
    images: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Anti-hallucination fields
    source_cites: list[SourceCitation] = Field(default_factory=list)
    verification_status: Literal[
        "unverified",
        "pending_review",
        "verified",
        "auto_verified",
        "community_verified",
        "flagged",
    ] = "unverified"
    requires_human_review: bool = False
    consensus_score: Optional[float] = None  # Agreement % from sources (0.0-1.0)
    consensus_badge: Optional[str] = None  # e.g., "85% - 7 Sources"

    # Structured data field (for spec chunks: spec_items, for others: content_html)
    data: Optional[dict] = Field(default_factory=dict)

    # Template versioning
    template_version: Optional[str] = "1.0"

    # Safety-critical flag (auto-determined by chunk_type)
    @property
    def is_safety_critical(self) -> bool:
        """
        Safety-critical chunks ALWAYS require human review regardless of source confidence.
        These are: torque specs, wiring diagrams, diagnostic flows.
        """
        return self.chunk_type in ["torque_spec", "wiring_diagram", "diag_flow"]

    @property
    def can_auto_approve(self) -> bool:
        """
        Determine if chunk qualifies for auto-approval.

        Criteria:
        - NOT safety-critical (no torque_spec, wiring_diagram, diag_flow)
        - Has 3+ source citations
        - All sources are high-confidence

        This auto-approves ~70-80% of chunks after a few months.
        """
        if self.is_safety_critical:
            return False

        if len(self.source_cites) < 3:
            return False

        # All sources must be high-confidence
        return all(source.is_high_confidence for source in self.source_cites)

    verified: bool = False
    cost_to_generate: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "vehicle_key": "2011_ford_f150_50",
                "chunk_type": "known_issues",
                "title": "Common No-Start Issues",
                "content_html": "<ul><li>Fuel pump driver module failure (TSB 13-6-9)</li></ul>",
                "content_text": "Fuel pump driver module failure (TSB 13-6-9)",
                "tags": ["no_start", "fuel_system", "tsb"],
                "source_cites": [
                    {
                        "source_type": "tsb",
                        "tsb_number": "13-6-9",
                        "description": "NHTSA TSB for FPDM failures",
                        "confidence": 0.95,
                    }
                ],
                "verification_status": "verified",
                "verified": True,
                "cost_to_generate": 0.00057,
            }
        }


class ChunkGenerationJob(BaseModel):
    vehicle_key: str
    chunk_type: ChunkType
    context: str
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    result_chunk_id: Optional[str] = None
    error: Optional[str] = None
    cost: float = 0.0
