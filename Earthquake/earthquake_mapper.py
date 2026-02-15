"""
earthquake_mapper.py
====================
Maps each earthquake event's coordinates to a risk level based on magnitude.
Called automatically by earthquake_preprocessor.preprocess().

Outputs to Data/earthquake_coordinates.json
"""

import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "Data", "earthquake_coordinates.json")

RISK_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def mag_to_risk(mag: float) -> str:
    """Convert earthquake magnitude to risk level."""
    if mag >= 6.0:
        return "Critical"
    elif mag >= 5.0:
        return "High"
    elif mag >= 4.0:
        return "Medium"
    else:
        return "Low"


def generate_map(events: list) -> dict:
    """
    Generate and save a coordinate → risk level map.

    Args:
        events: List of condensed event dicts from preprocessor.

    Returns:
        Dict of "lat,lng" → "Low"/"Medium"/"High"/"Critical".
    """
    coord_map = {}

    for e in events:
        lat = e.get("lat")
        lng = e.get("lng")
        mag = e.get("mag")

        if lat is None or lng is None or mag is None:
            continue

        key = f"{round(lat, 4)},{round(lng, 4)}"
        level = mag_to_risk(mag)

        if key in coord_map:
            if RISK_RANK.get(level, 0) > RISK_RANK.get(coord_map[key], 0):
                coord_map[key] = level
        else:
            coord_map[key] = level

    with open(OUTPUT_FILE, "w") as f:
        json.dump(coord_map, f, indent=2)

    print(f"[earthquake_mapper] Saved {len(coord_map)} coordinates → {OUTPUT_FILE}")
    return coord_map