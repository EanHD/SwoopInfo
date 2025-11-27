# renderer.py - Minimal belt renderer using only straight lines
from crutch import generate_belt_path

def render_svg(data):
    belt_path = generate_belt_path(data)
    
    # Generate pulley circles
    pulley_elements = []
    for p in data["pulleys"]:
        pulley_elements.append(
            f'<circle cx="{p["cx"]}" cy="{p["cy"]}" r="{p["r"]}" '
            f'fill="none" stroke="black" stroke-width="14"/>'
        )
    
    return f'''<svg viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
  <rect width="800" height="800" fill="white"/>
  <path d="{belt_path}" fill="none" stroke="black" stroke-width="14"/>
  {chr(10).join(pulley_elements)}
</svg>'''
