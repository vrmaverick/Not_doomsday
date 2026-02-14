# 🌍 Earthquake API Module

Lightweight Python wrapper around the [USGS Earthquake Hazards Program API](https://earthquake.usgs.gov/fdsnws/event/1/).
Fetches real-time earthquake data based on geographic location. **No API key required.**

## Setup
```bash
pip install -r requirements.txt
```

## Quick Start
```python
from earthquake_api import get_earthquakes

# Earthquakes within 300km of Tokyo, magnitude 4+, last 7 days
quakes = get_earthquakes(lat=35.68, lng=139.69, radius_km=300, min_mag=4.0, days_back=7)

for q in quakes:
    print(f"M{q['mag']} — {q['place']} at {q['time']}")
```

## Functions

### `get_earthquakes(lat, lng, ...)`

Fetch earthquakes near a location.

| Parameter    | Type   | Default | Description                          |
|-------------|--------|---------|--------------------------------------|
| `lat`       | float  | *required* | Center latitude (-90 to 90)       |
| `lng`       | float  | *required* | Center longitude (-180 to 180)    |
| `radius_km` | int   | 250     | Search radius in km (max 20001)      |
| `min_mag`   | float  | 2.5     | Minimum magnitude                    |
| `max_mag`   | float  | None    | Maximum magnitude (optional)         |
| `days_back` | int    | 30      | Days of history to search            |
| `start_date`| str    | None    | Custom start date `"YYYY-MM-DD"`     |
| `end_date`  | str    | None    | Custom end date `"YYYY-MM-DD"`       |
| `limit`     | int    | 100     | Max results (API max: 20000)         |

### `get_earthquake_by_id(event_id)`

Fetch a single earthquake by its USGS event ID (e.g. `"us7000n123"`).

## Response Format

Each earthquake is a dict:
```python
{
    "id": "nc75082941",
    "mag": 4.2,
    "place": "15km NW of Parkfield, CA",
    "time": "2026-02-10T08:33:21+00:00",
    "lat": 36.05,
    "lng": -120.48,
    "depth_km": 8.5,
    "alert": "green",       # green / yellow / orange / red / None
    "tsunami": False,
    "detail_url": "https://earthquake.usgs.gov/earthquakes/eventpage/nc75082941"
}
```

## Self-Test
```bash
python earthquake_api.py
```

Runs a test query (San Francisco, 500km, mag 3+) and prints results.

## API Reference

- **Source:** USGS Earthquake Hazards Program
- **Docs:** https://earthquake.usgs.gov/fdsnws/event/1/
- **Auth:** None required
- **Rate limits:** Be reasonable (no rapid-fire requests)
- **Output format:** GeoJSON (parsed to Python dicts)