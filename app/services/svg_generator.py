"""
SVG Generator - DISABLED UNTIL DIAGRAMS ARE PERFECT
All methods return None or placeholder to prevent diagram generation.
"""

from typing import Optional


class SVGGenerator:
    """DISABLED - Generates Swoop-branded SVGs from diagrams using Vision models."""

    async def generate_svg(
        self, image_data: bytes, diagram_type: str, vehicle_context: str, component: str
    ) -> Optional[str]:
        """DISABLED UNTIL DIAGRAMS ARE PERFECT"""
        print(f"⏸️ SVG GENERATION DISABLED: {component}")
        return None

    async def generate_svg_from_knowledge(
        self, diagram_type: str, vehicle_context: str, component: str
    ) -> Optional[str]:
        """DISABLED UNTIL DIAGRAMS ARE PERFECT"""
        print(f"⏸️ SVG GENERATION DISABLED: {component}")
        return None

    def _get_fallback_svg(self, component: str) -> str:
        """Return placeholder SVG"""
        return f"""<svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg">
  <rect width="800" height="600" fill="#0F172A"/>
  <text x="400" y="280" fill="#94A3B8" font-family="Inter, sans-serif" font-size="24" text-anchor="middle">
    Diagram Coming Soon
  </text>
  <text x="400" y="320" fill="#64748B" font-family="Inter, sans-serif" font-size="16" text-anchor="middle">
    {component}
  </text>
  <text x="400" y="360" fill="#475569" font-family="Inter, sans-serif" font-size="14" text-anchor="middle">
    This feature is being perfected
  </text>
</svg>"""


svg_generator = SVGGenerator()
