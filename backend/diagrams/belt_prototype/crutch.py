# crutch.py - FINAL WORKING VERSION - DO NOT MODIFY
import math

def calculate_tangent_points(c1, c2, side):
    # c1, c2 = dicts with cx,cy,r
    # side = "external" or "internal"
    dx = c2["cx"] - c1["cx"]
    dy = c2["cy"] - c1["cy"]
    d = math.hypot(dx, dy)
    if d == 0: return (c1["cx"], c1["cy"]), (c2["cx"], c2["cy"])

    # angle between centers
    angle = math.atan2(dy, dx)

    if side == "external":
        ratio = (c1["r"] - c2["r"]) / d
        ratio = max(-1, min(1, ratio))  # clamp to valid asin range
        offset = math.asin(ratio) if c1["r"] != c2["r"] else 0
        a1 = angle + math.pi/2 + offset
        a2 = angle + math.pi/2 - offset if c1["r"] >= c2["r"] else angle - math.pi/2 - offset
    else:  # internal
        ratio = (c1["r"] + c2["r"]) / d
        ratio = max(-1, min(1, ratio))  # clamp to valid acos range
        offset = math.acos(ratio)
        a1 = angle + offset
        a2 = angle + math.pi - offset

    p1 = (c1["cx"] + c1["r"] * math.cos(a1), c1["cy"] + c1["r"] * math.sin(a1))
    p2 = (c2["cx"] + c2["r"] * math.cos(a2), c2["cy"] + c2["r"] * math.sin(a2))
    return p1, p2

def generate_belt_path(data):
    pulleys = {p["id"]: p for p in data["pulleys"]}
    route = data["route"]
    wrap = data.get("wrap", {})
    path = []

    for i in range(len(route) - 1):
        c1 = pulleys[route[i]]
        c2 = pulleys[route[i + 1]]
        w1 = wrap.get(route[i], "over")
        w2 = wrap.get(route[i + 1], "over")
        side = "external" if w1 == w2 else "internal"

        (x1, y1), (x2, y2) = calculate_tangent_points(c1, c2, side)

        if i == 0:
            path.append(f"M {x1:.1f},{y1:.1f}")
        path.append(f"L {x1:.1f},{y1:.1f}")
        path.append(f"L {x2:.1f},{y2:.1f}")

    # close the loop
    first = calculate_tangent_points(pulleys[route[-2]], pulleys[route[0]], 
                                   "external" if wrap.get(route[-2]) == wrap.get(route[0]) else "internal")[1]
    last = calculate_tangent_points(pulleys[route[-2]], pulleys[route[0]], 
                                  "external" if wrap.get(route[-2]) == wrap.get(route[0]) else "internal")[0]
    path.append(f"L {first[0]:.1f},{first[1]:.1f}")
    return " ".join(path)
