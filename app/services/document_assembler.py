from models.chunk import ServiceChunk
from models.vehicle import Vehicle

# FACTORY MANUAL CSS - Professional service document styling
FACTORY_MANUAL_CSS = """
        body {
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 30px;
            background: #f8f8f8;
            color: #1a1a1a;
            line-height: 1.6;
        }
        .header-stripe {
            height: 12px;
            background: linear-gradient(90deg, #003087, #005eb8, #0072ce);
            margin-bottom: 0;
        }
        .header {
            background: #003087;
            color: white;
            padding: 24px 30px;
            margin-bottom: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 26px;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .header p {
            margin: 12px 0 0 0;
            opacity: 0.95;
            font-size: 16px;
        }
        .section {
            background: white;
            padding: 24px 28px;
            margin-bottom: 20px;
            border-radius: 0 6px 6px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border-left: 6px solid #005eb8;
        }
        .section h2 {
            margin: 0 0 18px 0;
            color: #003087;
            border-bottom: 3px solid #003087;
            padding-bottom: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-size: 18px;
        }
        .chunk {
            margin-bottom: 24px;
            padding-bottom: 18px;
            border-bottom: 1px solid #e0e0e0;
        }
        .chunk:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        .chunk h3 {
            color: #005eb8;
            margin: 0 0 12px 0;
            font-weight: 600;
            font-size: 16px;
        }
        .verified {
            display: inline-block;
            background: #10b981;
            color: white;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .unverified {
            display: inline-block;
            background: #f59e0b;
            color: white;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .warning {
            background: #fff0f0;
            border-left: 8px solid #c00;
            padding: 14px 18px;
            margin: 16px 0;
            border-radius: 0 6px 6px 0;
            font-weight: bold;
            color: #900;
        }
        .note {
            background: #f0f7ff;
            border: 1px solid #005eb8;
            padding: 12px 16px;
            margin: 14px 0;
            border-radius: 6px;
            color: #003087;
        }
        ul {
            margin: 12px 0;
            padding-left: 22px;
        }
        li {
            margin: 8px 0;
        }
        .step {
            background: #fafafa;
            padding: 14px 18px;
            margin: 12px 0;
            border-left: 4px solid #0072ce;
            border-radius: 0 4px 4px 0;
        }
"""


class DocumentAssembler:

    def compile_diagnostic_document(
        self, vehicle: Vehicle, concern: str, chunks: list[ServiceChunk]
    ) -> str:
        """
        Compile relevant chunks into a beautiful, focused diagnostic document.
        2-3 pages max, not 40 pages of noise.
        Professional factory manual styling.
        """

        # Group chunks by type
        chunks_by_type = {}
        for chunk in chunks:
            if chunk.chunk_type not in chunks_by_type:
                chunks_by_type[chunk.chunk_type] = []
            chunks_by_type[chunk.chunk_type].append(chunk)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{vehicle.year} {vehicle.make} {vehicle.model} - {concern}</title>
    <style>{FACTORY_MANUAL_CSS}
    </style>
</head>
<body>
    <div class="header-stripe"></div>
    <div class="header">
        <h1>{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.engine or ''}</h1>
        <p><strong>SERVICE DOCUMENT:</strong> {concern.upper()}</p>
    </div>
"""

        # Known Issues first (most valuable for diagnosis)
        if "known_issues" in chunks_by_type:
            html += '    <div class="section">\n'
            html += "        <h2>⚠️ Known Issues & TSBs</h2>\n"
            for chunk in chunks_by_type["known_issues"]:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Diagnostic Flow
        if "diag_flow" in chunks_by_type:
            html += '    <div class="section">\n'
            html += "        <h2>🔍 Diagnostic Flow</h2>\n"
            for chunk in chunks_by_type["diag_flow"]:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Part Locations
        if "part_location" in chunks_by_type:
            html += '    <div class="section">\n'
            html += "        <h2>📍 Component Locations</h2>\n"
            for chunk in chunks_by_type["part_location"]:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Removal Steps
        if "removal_steps" in chunks_by_type:
            html += '    <div class="section">\n'
            html += "        <h2>🔧 Removal & Installation</h2>\n"
            for chunk in chunks_by_type["removal_steps"]:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Specs (Torque, Fluids)
        spec_types = ["torque_spec", "fluid_capacity"]
        spec_chunks = [
            c for t in spec_types if t in chunks_by_type for c in chunks_by_type[t]
        ]
        if spec_chunks:
            html += '    <div class="section">\n'
            html += "        <h2>📊 Specifications</h2>\n"
            for chunk in spec_chunks:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Wiring Diagrams
        if "wiring_diagram" in chunks_by_type:
            html += '    <div class="section">\n'
            html += "        <h2>⚡ Wiring Diagrams</h2>\n"
            for chunk in chunks_by_type["wiring_diagram"]:
                verified_badge = (
                    '<span class="verified">✓ Verified</span>'
                    if chunk.verified
                    else '<span class="unverified">⚠ Unverified</span>'
                )
                html += f'        <div class="chunk">\n'
                html += f"            <h3>{chunk.title}{verified_badge}</h3>\n"
                html += f"            {chunk.content_html}\n"
                html += "        </div>\n"
            html += "    </div>\n"

        html += """</body>
</html>"""

        return html


document_assembler = DocumentAssembler()
