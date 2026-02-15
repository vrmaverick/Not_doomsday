"""
flood_mapper.py
===============
Maps a flood location's coordinates to a risk level based on
discharge levels, trends, forecast risk days, and spikes.
Called automatically by flood_preprocessor.preprocess().

Outputs to Data/flood_coordinates.json
"""

import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "Data", "flood_coordinates.json")


def discharge_to_risk(summary: dict) -> str:
    """
    Determine flood risk level from preprocessed summary.

    Uses a combination of:
      - Historical peak discharge
      - 7-day trend direction
      - Number of forecast risk days
      - Spike count
    """
    score = 0

    hist_max = summary.get("historical", {}).get("max", 0) or 0
    if hist_max >= 5000:
        score += 4
    elif hist_max >= 2000:
        score += 3
    elif hist_max >= 500:
        score += 2
    elif hist_max >= 100:
        score += 1

    trend = summary.get("trend_7d", {}).get("direction", "stable")
    if trend == "rising_fast":
        score += 3
    elif trend == "rising":
        score += 2
    elif trend == "stable":
        score += 0
    else:
        score -= 1

    risk_days = summary.get("forecast_risk_days", 0)
    if risk_days >= 10:
        score += 3
    elif risk_days >= 5:
        score += 2
    elif risk_days >= 1:
        score += 1

    spikes = summary.get("spikes_detected", 0)
    if spikes >= 5:
        score += 2
    elif spikes >= 2:
        score += 1

    if score >= 9:
        return "Critical"
    elif score >= 6:
        return "High"
    elif score >= 3:
        return "Medium"
    else:
        return "Low"


def generate_map(summary: dict) -> dict:
    """
    Generate and save a coordinate → risk level map.

    Args:
        summary: Summary dict from flood_preprocessor.preprocess().

    Returns:
        Dict of "lat,lng" → "Low"/"Medium"/"High"/"Critical".
    """
    coords = summary.get("grid_coords", {})
    lat = coords.get("lat")
    lng = coords.get("lng")

    # Load existing map to accumulate multiple locations
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            coord_map = json.load(f)
    else:
        coord_map = {}

    if lat is not None and lng is not None:
        key = f"{round(lat, 4)},{round(lng, 4)}"
        coord_map[key] = discharge_to_risk(summary)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(coord_map, f, indent=2)

    print(f"[flood_mapper] Saved {len(coord_map)} coordinates → {OUTPUT_FILE}")
    return coord_map