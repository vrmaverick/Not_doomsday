"""
flood_api.py
============
A lightweight wrapper around the Open-Meteo Flood API (GloFAS v4).
Fetches river discharge data based on geographic location (lat/lng).
Includes historical data (from 1984) and forecasts (up to 7 months).

No API key required. Free and open access.

API Docs: https://open-meteo.com/en/docs/flood-api

Usage:
    from flood_api import get_flood_data

    data = get_flood_data(lat=29.76, lng=-95.36)  # Houston, TX
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

BASE_URL = "https://flood-api.open-meteo.com/v1/flood"


def get_flood_data(
    lat: float,
    lng: float,
    past_days: int = 30,
    forecast_days: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_stats: bool = True,
) -> dict:
    """
    Fetch river discharge (flood) data for a location.

    Args:
        lat:           Latitude (-90 to 90).
        lng:           Longitude (-180 to 180).
        past_days:     Days of historical data to include (default 30).
        forecast_days: Days of forecast data to include (default 30, max 210).
        start_date:    Custom start date "YYYY-MM-DD" (overrides past_days).
        end_date:      Custom end date "YYYY-MM-DD" (overrides forecast_days).
        include_stats: Include ensemble stats (mean, max, min, p25, p75).

    Returns:
        Dict with keys:
            location     (dict) : lat, lng returned by API (snapped to grid)
            daily        (list) : List of dicts with date + discharge values
            metadata     (dict) : Units and generation time
            error        (str|None) : Error message if request failed

    Raises:
        ValueError: If lat/lng are out of valid range.
    """
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not (-180 <= lng <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got {lng}")

    daily_vars = ["river_discharge"]
    if include_stats:
        daily_vars.extend([
            "river_discharge_mean",
            "river_discharge_median",
            "river_discharge_max",
            "river_discharge_min",
            "river_discharge_p25",
            "river_discharge_p75",
        ])

    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": ",".join(daily_vars),
        "timeformat": "iso8601",
    }

    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
    else:
        params["past_days"] = past_days
        params["forecast_days"] = forecast_days

    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}", "daily": [], "location": {}, "metadata": {}}
    except ValueError:
        return {"error": "Failed to parse JSON", "daily": [], "location": {}, "metadata": {}}

    if data.get("error"):
        return {"error": data.get("reason", "Unknown API error"), "daily": [], "location": {}, "metadata": {}}

    # Parse daily data into list of dicts
    raw_daily = data.get("daily", {})
    times = raw_daily.get("time", [])

    daily = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for i, date in enumerate(times):
        entry = {
            "date": date,
            "is_forecast": date > today,
            "discharge_m3s": _safe_get(raw_daily, "river_discharge", i),
        }
        if include_stats:
            entry.update({
                "mean": _safe_get(raw_daily, "river_discharge_mean", i),
                "median": _safe_get(raw_daily, "river_discharge_median", i),
                "max": _safe_get(raw_daily, "river_discharge_max", i),
                "min": _safe_get(raw_daily, "river_discharge_min", i),
                "p25": _safe_get(raw_daily, "river_discharge_p25", i),
                "p75": _safe_get(raw_daily, "river_discharge_p75", i),
            })
        daily.append(entry)

    return {
        "location": {
            "lat": data.get("latitude"),
            "lng": data.get("longitude"),
        },
        "daily": daily,
        "metadata": {
            "units": "m³/s",
            "generation_time_ms": data.get("generationtime_ms"),
            "timezone": data.get("timezone", "GMT"),
        },
        "error": None,
    }


def _safe_get(obj: dict, key: str, index: int):
    """Safely get a value from a list inside a dict."""
    arr = obj.get(key, [])
    if index < len(arr):
        val = arr[index]
        return round(val, 2) if val is not None else None
    return None


# --------------- Self Test ---------------
if __name__ == "__main__":
    print("=== Open-Meteo Flood API — Self Test ===\n")
    print("Fetching river discharge near Houston, TX (past 30 days + 30 day forecast)...\n")

    result = get_flood_data(lat=29.76, lng=-95.36)

    if result["error"]:
        print(f"Error: {result['error']}")
    else:
        print(f"Grid location: ({result['location']['lat']}, {result['location']['lng']})")
        print(f"Total data points: {len(result['daily'])}")
        print(f"Units: {result['metadata']['units']}\n")

        historical = [d for d in result["daily"] if not d["is_forecast"]]
        forecast = [d for d in result["daily"] if d["is_forecast"]]

        print(f"--- Historical ({len(historical)} days) — last 5 ---")
        for d in historical[-5:]:
            print(f"  {d['date']} | discharge={d['discharge_m3s']} m³/s")

        print(f"\n--- Forecast ({len(forecast)} days) — first 5 ---")
        for d in forecast[:5]:
            print(f"  {d['date']} | mean={d.get('mean')} max={d.get('max')} min={d.get('min')} m³/s")

    print("\n=== Test complete ===")