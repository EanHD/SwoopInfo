"""
Belt Diagram Test Generator
Generates SVG files for all test cases and validates output.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_data import GM36_REFERENCE, FORD54_REFERENCE, HONDA_K20_REFERENCE, GM36_FROM_VISION
from renderer import render_svg


def get_assets_path():
    """Get the assets directory path."""
    # Navigate from /backend/diagrams/belt_prototype/ to /assets/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "..", "..", "..", "assets")


def save_test(name: str, data: dict, assets_path: str):
    """Generate and save SVG for a test case."""
    if not data.get("pulleys"):
        print(f"SKIP → {name} (no pulley data)")
        return False
    
    try:
        svg = render_svg(data)
        filename = f"generated_{name.replace(' ', '_').replace('.', '_')}.svg"
        filepath = os.path.join(assets_path, filename)
        
        with open(filepath, "w") as f:
            f.write(svg)
        
        print(f"✅ SAVED → {filepath}")
        return True
    except Exception as e:
        print(f"❌ FAILED → {name}: {e}")
        return False


def main():
    """Run all test cases."""
    assets_path = get_assets_path()
    
    # Ensure assets directory exists
    os.makedirs(assets_path, exist_ok=True)
    
    print("=" * 60)
    print("SWOOP BELT DIAGRAM GENERATOR - TEST SUITE")
    print("=" * 60)
    print(f"Output directory: {assets_path}")
    print("-" * 60)
    
    tests = [
        ("GM_3_6L_Correct", GM36_REFERENCE),
        ("Ford_5_4L_Triton", FORD54_REFERENCE),
        ("Honda_K20", HONDA_K20_REFERENCE),
        ("GM_3_6L_From_Vision", GM36_FROM_VISION),
    ]
    
    success_count = 0
    for name, data in tests:
        if save_test(name, data, assets_path):
            success_count += 1
    
    print("-" * 60)
    print(f"COMPLETE: {success_count}/{len(tests)} SVGs generated")
    print("=" * 60)


if __name__ == "__main__":
    main()
