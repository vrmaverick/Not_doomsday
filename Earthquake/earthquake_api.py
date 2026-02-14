"""
earthquake_api.py
=================
A lightweight wrapper around the USGS Earthquake Hazards Program API.
Fetches earthquake data based on geographic location (latitude/longitude + radius).

No API key required. Free and open access.

API Docs: https://earthquake.usgs.gov/fdsnws/event/1/

Usage:
    from earthquake_api import get_earthquakes, get_earthquake_by_id

    # Fetch recent quakes near a location
    quakes = get_earthquakes(lat=37.77, lng=-122.42, radius_km=500)

    # Get details for a specific earthquake
    quake = get_earthquake_by_id("us7000n123")
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"


def get_earthquakes(
    lat: float,
    lng: float,
    radius_km: int = 250,
    min_mag: float = 2.5,
    max_mag: Optional[float] = None,
    days_back: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch earthquakes near a geographic point.

    Args:
        lat:        Center latitude (-90 to 90).
        lng:        Center longitude (-180 to 180).
        radius_km:  Search radius in km from center (max 20001).
        min_mag:    Minimum magnitude to include (default 2.5).
        max_mag:    Maximum magnitude to include (optional).
        days_back:  How many days back to search (default 30).
                    Ignored if start_date/end_date are provided.
        start_date: Start date as "YYYY-MM-DD" (overrides days_back).
        end_date:   End date as "YYYY-MM-DD" (overrides days_back).
        limit:      Max number of results (default 100, API max 20000).

    Returns:
        List of earthquake dicts, each containing:
            id         (str)   : Unique event ID
            mag        (float) : Magnitude
            place      (str)   : Human-readable location description
            time       (str)   : ISO 8601 UTC timestamp
            lat        (float) : Epicenter latitude
            lng        (float) : Epicenter longitude
            depth_km   (float) : Depth in kilometers
            alert      (str|None) : PAGER alert level (green/yellow/orange/red)
            tsunami    (bool)  : Whether a tsunami alert was issued
            detail_url (str)   : Link to full event page on USGS

    Raises:
        ValueError: If lat/lng are out of valid range.
    """
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not (-180 <= lng <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got {lng}")

    if start_date and end_date:
        starttime = start_date
        endtime = end_date
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)
        starttime = start.strftime("%Y-%m-%d")
        endtime = end.strftime("%Y-%m-%d")

    params = {
        "format": "geojson",
        "latitude": lat,
        "longitude": lng,
        "maxradiuskm": radius_km,
        "minmagnitude": min_mag,
        "starttime": starttime,
        "endtime": endtime,
        "limit": limit,
        "orderby": "time",
    }
    if max_mag is not None:
        params["maxmagnitude"] = max_mag

    try:
        resp = requests.get(f"{BASE_URL}/query", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[earthquake_api] Request failed: {e}")
        return []
    except ValueError:
        print("[earthquake_api] Failed to parse JSON response")
        return []

    return _parse_features(data.get("features", []))


def get_earthquake_by_id(event_id: str) -> Optional[dict]:
    """
    Fetch a single earthquake by its USGS event ID.

    Args:
        event_id: USGS event ID (e.g. "us7000n123").

    Returns:
        Earthquake dict (same format as get_earthquakes), or None if not found.
    """
    params = {
        "format": "geojson",
        "eventid": event_id,
    }
    try:
        resp = requests.get(f"{BASE_URL}/query", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[earthquake_api] Request failed: {e}")
        return None

    features = data.get("features", [])
    if not features:
        return None
    return _parse_features(features)[0]


def _parse_features(features: list) -> list[dict]:
    """Parse GeoJSON features into clean earthquake dicts."""
    results = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None, None])

        ts = props.get("time")
        time_str = (
            datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            if ts
            else None
        )

        results.append({
            "id": f.get("id"),
            "mag": props.get("mag"),
            "place": props.get("place"),
            "time": time_str,
            "lat": coords[1],
            "lng": coords[0],
            "depth_km": coords[2],
            "alert": props.get("alert"),
            "tsunami": bool(props.get("tsunami")),
            "detail_url": props.get("url"),
        })
    return results


# --------------- Quick self-test ---------------
if __name__ == "__main__":
    print("=== USGS Earthquake API — Self Test ===\n")
    print("Fetching quakes near San Francisco (500km, mag 3+, last 30 days)...\n")

    quakes = get_earthquakes(lat=37.77, lng=-122.42, radius_km=500, min_mag=3.0)

    if not quakes:
        print("No earthquakes found (or request failed).")
    else:
        print(f"Found {len(quakes)} earthquake(s):\n")
        for q in quakes[:10]:
            print(f"  M{q['mag']:<5} | {q['time']} | {q['place']}")
            print(f"         coords=({q['lat']}, {q['lng']})  depth={q['depth_km']}km")
            print(f"         alert={q['alert']}  tsunami={q['tsunami']}")
            print()

    print("--- Single event lookup test ---")
    if quakes:
        test_id = quakes[0]["id"]
        single = get_earthquake_by_id(test_id)
        if single:
            print(f"  Fetched event {test_id}: M{single['mag']} — {single['place']}")
        else:
            print(f"  Could not fetch event {test_id}")

    print("\n=== Test complete ===")