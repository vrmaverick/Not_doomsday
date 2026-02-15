"""
earthquake_preprocessor.py
==========================
Takes raw output from earthquake_api.get_earthquakes() and transforms it
into a concise, structured format optimized for LLM-based earthquake prediction.

Extracts key seismic indicators:
  - Activity summary & magnitude stats
  - Temporal patterns (event frequency, acceleration)
  - Depth profile analysis
  - Geographic clustering info
  - Recent event timeline

Usage:
    from earthquake_api import get_earthquakes
    from earthquake_preprocessor import preprocess

    raw = get_earthquakes(lat=35.68, lng=139.69, radius_km=300)
    result = preprocess(raw, location_name="Tokyo, Japan")

    # Dict format for programmatic use
    print(result["summary"])

    # LLM-ready prompt string
    print(result["llm_prompt"])
"""

from datetime import datetime, timezone
from typing import Optional
import math


def preprocess(quakes: list[dict], location_name: str = "Unknown") -> dict:
    """
    Transform raw earthquake data into LLM-ready prediction context.

    Args:
        quakes:        List of earthquake dicts from earthquake_api.get_earthquakes().
        location_name: Human-readable name of the queried location.

    Returns:
        Dict with keys:
            summary      (dict) : Structured stats and patterns
            events       (list) : Condensed event list (most recent first)
            llm_prompt   (str)  : Ready-to-use prompt string for an LLM
    """
    if not quakes:
        return {
            "summary": {"total_events": 0, "location": location_name},
            "events": [],
            "llm_prompt": f"No recent earthquake data available for {location_name}.",
        }

    # --- Parse timestamps and sort by time (newest first) ---
    parsed = []
    for q in quakes:
        t = None
        if q.get("time"):
            try:
                t = datetime.fromisoformat(q["time"])
            except (ValueError, TypeError):
                pass
        parsed.append({**q, "_dt": t})

    parsed = [p for p in parsed if p["_dt"] is not None]
    parsed.sort(key=lambda x: x["_dt"], reverse=True)

    if not parsed:
        return {
            "summary": {"total_events": 0, "location": location_name},
            "events": [],
            "llm_prompt": f"No valid earthquake data for {location_name}.",
        }

    # --- Basic stats ---
    mags = [p["mag"] for p in parsed if p["mag"] is not None]
    depths = [p["depth_km"] for p in parsed if p["depth_km"] is not None]
    lats = [p["lat"] for p in parsed if p["lat"] is not None]
    lngs = [p["lng"] for p in parsed if p["lng"] is not None]

    mag_avg = round(sum(mags) / len(mags), 2) if mags else None
    mag_max = round(max(mags), 2) if mags else None
    mag_min = round(min(mags), 2) if mags else None
    depth_avg = round(sum(depths) / len(depths), 2) if depths else None
    depth_min = round(min(depths), 2) if depths else None
    depth_max = round(max(depths), 2) if depths else None

    # --- Time span & frequency ---
    newest = parsed[0]["_dt"]
    oldest = parsed[-1]["_dt"]
    span_days = max((newest - oldest).total_seconds() / 86400, 0.01)
    events_per_day = round(len(parsed) / span_days, 2)

    # --- Temporal acceleration ---
    # Compare event frequency in first half vs second half of the time window
    midpoint = oldest + (newest - oldest) / 2
    first_half = [p for p in parsed if p["_dt"] <= midpoint]
    second_half = [p for p in parsed if p["_dt"] > midpoint]
    half_days = max(span_days / 2, 0.01)
    freq_early = len(first_half) / half_days
    freq_recent = len(second_half) / half_days

    if freq_early > 0:
        accel_ratio = round(freq_recent / freq_early, 2)
    else:
        accel_ratio = None

    if accel_ratio is not None:
        if accel_ratio > 1.5:
            trend = "accelerating"
        elif accel_ratio < 0.67:
            trend = "decelerating"
        else:
            trend = "stable"
    else:
        trend = "unknown"

    # --- Time gaps between consecutive events ---
    gaps_hours = []
    for i in range(len(parsed) - 1):
        gap = (parsed[i]["_dt"] - parsed[i + 1]["_dt"]).total_seconds() / 3600
        gaps_hours.append(round(gap, 1))
    avg_gap_hours = round(sum(gaps_hours) / len(gaps_hours), 1) if gaps_hours else None
    min_gap_hours = min(gaps_hours) if gaps_hours else None

    # --- Magnitude distribution buckets ---
    buckets = {"minor_2_3": 0, "light_3_4": 0, "moderate_4_5": 0, "strong_5_6": 0, "major_6_plus": 0}
    for m in mags:
        if m < 3:
            buckets["minor_2_3"] += 1
        elif m < 4:
            buckets["light_3_4"] += 1
        elif m < 5:
            buckets["moderate_4_5"] += 1
        elif m < 6:
            buckets["strong_5_6"] += 1
        else:
            buckets["major_6_plus"] += 1

    # --- Geographic spread (simple std dev of coords) ---
    lat_center = round(sum(lats) / len(lats), 4) if lats else None
    lng_center = round(sum(lngs) / len(lngs), 4) if lngs else None
    lat_spread = round(_std(lats), 4) if len(lats) > 1 else 0
    lng_spread = round(_std(lngs), 4) if len(lngs) > 1 else 0
    is_clustered = lat_spread < 0.5 and lng_spread < 0.5

    # --- Build summary dict ---
    summary = {
        "location": location_name,
        "total_events": len(parsed),
        "time_span_days": round(span_days, 1),
        "magnitude": {
            "min": mag_min,
            "max": mag_max,
            "avg": mag_avg,
            "distribution": buckets,
        },
        "depth_km": {
            "min": depth_min,
            "max": depth_max,
            "avg": depth_avg,
        },
        "temporal": {
            "events_per_day": events_per_day,
            "trend": trend,
            "acceleration_ratio": accel_ratio,
            "avg_gap_hours": avg_gap_hours,
            "min_gap_hours": min_gap_hours,
        },
        "geographic": {
            "center": {"lat": lat_center, "lng": lng_center},
            "spread": {"lat_std": lat_spread, "lng_std": lng_spread},
            "clustered": is_clustered,
        },
    }

    # --- Condensed event list ---
    events = []
    for p in parsed:
        events.append({
            "mag": p["mag"],
            "depth_km": round(p["depth_km"], 1) if p["depth_km"] else None,
            "lat": round(p["lat"], 3) if p["lat"] else None,
            "lng": round(p["lng"], 3) if p["lng"] else None,
            "time": p["_dt"].strftime("%Y-%m-%d %H:%M UTC"),
            "place": p["place"],
        })

    # --- LLM-ready prompt ---
    llm_prompt = _build_prompt(summary, events)

    # Generate coordinate → risk map
    from earthquake_mapper import generate_map
    coord_map = generate_map(events)

    return {
        "summary": summary,
        "events": events,
        "llm_prompt": llm_prompt,
        "coordinate_map": coord_map,
    }


def _build_prompt(summary: dict, events: list) -> str:
    """Build a concise prompt string an LLM can use for prediction."""
    s = summary
    mag = s["magnitude"]
    tmp = s["temporal"]
    geo = s["geographic"]
    dep = s["depth_km"]

    lines = [
        f"=== SEISMIC ACTIVITY REPORT: {s['location']} ===",
        f"Period: {s['time_span_days']} days | Total events: {s['total_events']}",
        "",
        f"MAGNITUDE: min={mag['min']} avg={mag['avg']} max={mag['max']}",
        f"  Distribution: {mag['distribution']}",
        "",
        f"DEPTH (km): min={dep['min']} avg={dep['avg']} max={dep['max']}",
        "",
        f"FREQUENCY: {tmp['events_per_day']} events/day | Trend: {tmp['trend']} (ratio={tmp['acceleration_ratio']})",
        f"  Avg gap: {tmp['avg_gap_hours']}h | Shortest gap: {tmp['min_gap_hours']}h",
        "",
        f"GEOGRAPHIC: center=({geo['center']['lat']}, {geo['center']['lng']}) | Clustered: {geo['clustered']}",
        f"  Spread: lat_std={geo['spread']['lat_std']} lng_std={geo['spread']['lng_std']}",
        "",
        "RECENT EVENTS (newest first):",
    ]

    for e in events[:15]:
        lines.append(
            f"  M{e['mag']} | {e['time']} | d={e['depth_km']}km | ({e['lat']},{e['lng']}) | {e['place']}"
        )

    if len(events) > 15:
        lines.append(f"  ... and {len(events) - 15} more events")

    lines.append("")
    lines.append(
        "Based on the seismic patterns above (frequency trend, magnitude distribution, "
        "depth profile, geographic clustering), assess the earthquake risk for this region."
    )

    return "\n".join(lines)


def _std(values: list[float]) -> float:
    """Simple standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


# --------------- Self Test ---------------
if __name__ == "__main__":
    from earthquake_api import get_earthquakes
    import json

    print("Fetching earthquake data...\n")
    raw = get_earthquakes(lat=37.77, lng=-122.42, radius_km=500, min_mag=3.0)

    result = preprocess(raw, location_name="San Francisco, CA (500km radius)")

    print("=== SUMMARY (dict) ===")
    print(json.dumps(result["summary"], indent=2))

    print("\n=== CONDENSED EVENTS ===")
    for e in result["events"][:5]:
        print(f"  M{e['mag']} | {e['time']} | {e['place']}")

    print(f"\n=== LLM PROMPT ({len(result['llm_prompt'])} chars) ===")
    print(result["llm_prompt"])