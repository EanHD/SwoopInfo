"""
Belt Diagram Test Data - Real-World Reference Cases
Each case contains mathematically verified pulley positions and routing.
"""

# Ground Truth: 2008 Cadillac CTS 3.6L LLT (GM High Feature V6)
GM36_REFERENCE = {
    "pulleys": [
        {"id": "P1", "cx": 523, "cy": 563, "r": 83, "label": "CRANK"},
        {"id": "P2", "cx": 370, "cy": 642, "r": 62, "label": "A/C"},
        {"id": "P3", "cx": 677, "cy": 413, "r": 57, "label": "TENS"},
        {"id": "P4", "cx": 587, "cy": 273, "r": 47, "label": "ALT"},
        {"id": "P5", "cx": 420, "cy": 213, "r": 72, "label": "W/P"},
        {"id": "P6", "cx": 180, "cy": 243, "r": 60, "label": "P/S"},
    ],
    "route": ["P1", "P2", "P3", "P4", "P5", "P6", "P1"],
    "wrap": {"P2": "under", "P3": "over", "P4": "over", "P5": "under", "P6": "over"},
    "name": "2008 Cadillac CTS 3.6L LLT",
    "tensioner_id": "P3"
}

# Ford 5.4L Triton (F-150 / Expedition)
FORD54_REFERENCE = {
    "pulleys": [
        {"id": "P1", "cx": 400, "cy": 600, "r": 90, "label": "CRANK"},
        {"id": "P2", "cx": 250, "cy": 520, "r": 55, "label": "A/C"},
        {"id": "P3", "cx": 180, "cy": 380, "r": 45, "label": "IDLE"},
        {"id": "P4", "cx": 280, "cy": 250, "r": 50, "label": "TENS"},
        {"id": "P5", "cx": 450, "cy": 200, "r": 65, "label": "ALT"},
        {"id": "P6", "cx": 580, "cy": 300, "r": 55, "label": "W/P"},
        {"id": "P7", "cx": 550, "cy": 450, "r": 40, "label": "P/S"},
    ],
    "route": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P1"],
    "wrap": {"P2": "under", "P3": "over", "P4": "under", "P5": "over", "P6": "under", "P7": "over"},
    "name": "2007 Ford F-150 5.4L Triton",
    "tensioner_id": "P4"
}

# Honda K20A (Civic Si / RSX Type-S)
HONDA_K20_REFERENCE = {
    "pulleys": [
        {"id": "P1", "cx": 400, "cy": 550, "r": 75, "label": "CRANK"},
        {"id": "P2", "cx": 550, "cy": 480, "r": 50, "label": "A/C"},
        {"id": "P3", "cx": 600, "cy": 320, "r": 45, "label": "TENS"},
        {"id": "P4", "cx": 450, "cy": 220, "r": 60, "label": "ALT"},
        {"id": "P5", "cx": 280, "cy": 280, "r": 55, "label": "P/S"},
    ],
    "route": ["P1", "P2", "P3", "P4", "P5", "P1"],
    "wrap": {"P2": "under", "P3": "over", "P4": "under", "P5": "over"},
    "name": "2006 Honda Civic Si K20Z3",
    "tensioner_id": "P3"
}

# Placeholder for Vision-extracted data (will be filled by AI)
GM36_FROM_VISION = {
    "pulleys": [
        {"id": "P1", "cx": 557, "cy": 446, "r": 131, "label": "CRANK"},
        {"id": "P2", "cx": 392, "cy": 195, "r": 126, "label": "ALT"},
        {"id": "P3", "cx": 578, "cy": 177, "r": 109, "label": "AC"},
        {"id": "P4", "cx": 362, "cy": 552, "r": 98, "label": "PS"},
        {"id": "P5", "cx": 249, "cy": 251, "r": 89, "label": "WP"},
        {"id": "P6", "cx": 626, "cy": 449, "r": 85, "label": "TENS"},
        {"id": "P7", "cx": 195, "cy": 277, "r": 70, "label": "IDLER"}
    ],
    "route": ["P1", "P4", "P7", "P5", "P2", "P3", "P6", "P1"],
    "wrap": {"P2": "over", "P3": "over", "P4": "under", "P5": "over", "P6": "under", "P7": "over"},
    "name": "Belt Diagram From Vision (pully1.jpeg)",
    "tensioner_id": "P6"
}
