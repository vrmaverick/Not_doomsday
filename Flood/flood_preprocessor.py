"""
flood_preprocessor.py
=====================
Takes raw output from flood_api.get_flood_data() and transforms it
into a concise, structured format optimized for LLM-based flood prediction.

Extracts key hydrological indicators:
  - Discharge summary stats (historical vs forecast)
  - Trend analysis (rising/falling/stable)
  - Spike detection (sudden surges)
  - Forecast risk signals (max projections)

Usage:
    from flood_api import get_flood_data
    from flood_preprocessor import preprocess

    raw = get_flood_data(lat=29.76, lng=-95.36)
    result = preprocess(raw, location_name="Houston, TX")

    print(result["llm_prompt"])
"""

import math
from typing import Optional


def preprocess(flood_data: dict, location_name: str = "Unknown") -> dict:
    """
    Transform raw flood data into LLM-ready prediction context.

    Args:
        flood_data:    Output from flood_api.get_flood_data().
        location_name: Human-readable name of the location.

    Returns:
        Dict with keys:
            summary    (dict) : Structured stats and patterns
            events     (list) : Condensed daily data
            llm_prompt (str)  : Ready-to-use prompt string for an LLM
    """
    if flood_data.get("error") or not flood_data.get("daily"):
        return {
            "summary": {"total_days": 0, "location": location_name},
            "events": [],
            "llm_prompt": f"No flood/river discharge data available for {location_name}.",
        }

    daily = flood_data["daily"]
    historical = [d for d in daily if not d["is_forecast"]]
    forecast = [d for d in daily if d["is_forecast"]]

    # --- Historical analysis ---
    hist_vals = [d["discharge_m3s"] for d in historical if d["discharge_m3s"] is not None]
    hist_stats = _calc_stats(hist_vals, "historical")

    # --- Forecast analysis ---
    fcast_means = [d.get("mean") for d in forecast if d.get("mean") is not None]
    fcast_maxes = [d.get("max") for d in forecast if d.get("max") is not None]
    fcast_stats = _calc_stats(fcast_means, "forecast_mean")
    fcast_max_stats = _calc_stats(fcast_maxes, "forecast_max")

    # --- Trend detection (last 7 days of historical) ---
    recent_7 = hist_vals[-7:] if len(hist_vals) >= 7 else hist_vals
    trend = _detect_trend(recent_7)

    # --- Spike detection (day-over-day changes) ---
    spikes = []
    for i in range(1, len(hist_vals)):
        prev = hist_vals[i - 1]
        curr = hist_vals[i]
        if prev and prev > 0:
            pct_change = ((curr - prev) / prev) * 100
            if abs(pct_change) > 30:
                spikes.append({
                    "date": historical[i]["date"],
                    "from": prev,
                    "to": curr,
                    "pct_change": round(pct_change, 1),
                })

    # --- Forecast risk: check if max projections exceed historical peaks ---
    hist_peak = max(hist_vals) if hist_vals else 0
    hist_avg = sum(hist_vals) / len(hist_vals) if hist_vals else 0
    forecast_risk_days = []
    for d in forecast:
        fmax = d.get("max")
        if fmax and hist_peak > 0 and fmax > hist_peak * 1.2:
            forecast_risk_days.append({
                "date": d["date"],
                "projected_max": round(fmax, 2),
                "vs_hist_peak_pct": round(((fmax - hist_peak) / hist_peak) * 100, 1),
            })

    # --- Build summary ---
    summary = {
        "location": location_name,
        "grid_coords": flood_data.get("location", {}),
        "total_days": len(daily),
        "historical": {
            "days": len(historical),
            **hist_stats,
        },
        "forecast": {
            "days": len(forecast),
            "mean_stats": fcast_stats,
            "max_stats": fcast_max_stats,
        },
        "trend_7d": trend,
        "spikes_detected": len(spikes),
        "spikes": spikes[:5],
        "forecast_risk_days": len(forecast_risk_days),
        "forecast_risks": forecast_risk_days[:5],
    }

    # --- Condensed events ---
    events = []
    for d in daily:
        entry = {
            "date": d["date"],
            "type": "forecast" if d["is_forecast"] else "historical",
            "discharge": d["discharge_m3s"],
        }
        if d["is_forecast"]:
            entry["mean"] = d.get("mean")
            entry["max"] = d.get("max")
            entry["min"] = d.get("min")
        events.append(entry)

    # --- LLM prompt ---
    llm_prompt = _build_prompt(summary, events)

    return {
        "summary": summary,
        "events": events,
        "llm_prompt": llm_prompt,
    }


def _calc_stats(values: list, label: str) -> dict:
    """Calculate basic stats for a list of values."""
    if not values:
        return {"min": None, "max": None, "avg": None, "std": None}
    avg = round(sum(values) / len(values), 2)
    return {
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "avg": avg,
        "std": round(_std(values), 2),
    }


def _detect_trend(values: list) -> dict:
    """Simple linear trend detection."""
    if len(values) < 3:
        return {"direction": "insufficient_data", "slope": 0}

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    slope = numerator / denominator if denominator != 0 else 0

    if y_mean > 0:
        pct_per_day = (slope / y_mean) * 100
    else:
        pct_per_day = 0

    if pct_per_day > 5:
        direction = "rising_fast"
    elif pct_per_day > 1:
        direction = "rising"
    elif pct_per_day < -5:
        direction = "falling_fast"
    elif pct_per_day < -1:
        direction = "falling"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "slope_m3s_per_day": round(slope, 2),
        "pct_change_per_day": round(pct_per_day, 2),
    }


def _build_prompt(summary: dict, events: list) -> str:
    """Build a concise prompt string for LLM flood risk assessment."""
    s = summary
    h = s["historical"]
    f = s["forecast"]
    t = s["trend_7d"]

    lines = [
        f"=== FLOOD / RIVER DISCHARGE REPORT: {s['location']} ===",
        f"Grid: ({s['grid_coords'].get('lat')}, {s['grid_coords'].get('lng')})",
        f"Data: {h['days']} days historical + {f['days']} days forecast",
        "",
        f"HISTORICAL DISCHARGE (m³/s):",
        f"  min={h.get('min')} avg={h.get('avg')} max={h.get('max')} std={h.get('std')}",
        "",
        f"7-DAY TREND: {t['direction']} (slope={t['slope_m3s_per_day']} m³/s/day, {t['pct_change_per_day']}%/day)",
        "",
        f"FORECAST (m³/s):",
        f"  Mean projection: min={f['mean_stats'].get('min')} avg={f['mean_stats'].get('avg')} max={f['mean_stats'].get('max')}",
        f"  Max projection:  min={f['max_stats'].get('min')} avg={f['max_stats'].get('avg')} max={f['max_stats'].get('max')}",
        "",
        f"SPIKES DETECTED: {s['spikes_detected']}",
    ]

    for sp in s.get("spikes", []):
        lines.append(f"  {sp['date']}: {sp['from']} → {sp['to']} m³/s ({sp['pct_change']}% change)")

    lines.append(f"\nFORECAST RISK DAYS (projected max > 120% of historical peak): {s['forecast_risk_days']}")
    for r in s.get("forecast_risks", []):
        lines.append(f"  {r['date']}: projected max={r['projected_max']} m³/s ({r['vs_hist_peak_pct']}% above peak)")

    # Add recent historical data
    hist_events = [e for e in events if e["type"] == "historical"]
    fcast_events = [e for e in events if e["type"] == "forecast"]

    lines.append(f"\nRECENT DISCHARGE (last 10 days):")
    for e in hist_events[-10:]:
        lines.append(f"  {e['date']} | {e['discharge']} m³/s")

    lines.append(f"\nFORECAST (next 10 days):")
    for e in fcast_events[:10]:
        lines.append(f"  {e['date']} | mean={e.get('mean')} max={e.get('max')} min={e.get('min')} m³/s")

    lines.append("")
    lines.append(
        "Based on the river discharge patterns above (historical levels, 7-day trend, "
        "forecast projections, spike history, and risk days), assess the flood risk for this region."
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
    from flood_api import get_flood_data
    import json

    print("Fetching flood data...\n")
    raw = get_flood_data(lat=29.76, lng=-95.36)

    result = preprocess(raw, location_name="Houston, TX")

    print("=== SUMMARY ===")
    print(json.dumps(result["summary"], indent=2))

    print(f"\n=== LLM PROMPT ({len(result['llm_prompt'])} chars) ===")
    print(result["llm_prompt"])