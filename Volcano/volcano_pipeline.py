#!/usr/bin/env python3
"""
Volcano Data Pipeline
=====================
1. Pulls ALL data from USGS HANS API
2. Enriches with earthquake seismicity data
3. Computes composite risk scores
4. Provides location-based risk lookup

Usage:
    python volcano_pipeline.py                          # Pull all data + analyze
    python volcano_pipeline.py --location 19.4,-155.3   # Get risk for a location
    python volcano_pipeline.py --location "Hawaii"       # Named location lookup
    python volcano_pipeline.py --refresh                 # Force re-pull from APIs
"""

import requests
import json
import csv
import math
import sys
import os
from datetime import datetime, timedelta

# ============================================================
# CONFIG
# ============================================================
USGS_HANS_BASE = "https://volcanoes.usgs.gov/hans-public/api/volcano"
USGS_EQ_BASE = "https://earthquake.usgs.gov/fdsnws/event/1"

OUTPUT_DIR = "volcano_data"

# Threat level mapping for numerical scoring
THREAT_SCORES = {
    "Very High Threat": 5,
    "High Threat": 4,
    "Moderate Threat": 3,
    "Low Threat": 2,
    "Very Low Threat": 1,
    "Unassigned": 0,
}

ALERT_SCORES = {
    "WARNING": 4,
    "WATCH": 3,
    "ADVISORY": 2,
    "NORMAL": 1,
    None: 0,
    "UNASSIGNED": 0,
}

COLOR_SCORES = {
    "RED": 4,
    "ORANGE": 3,
    "YELLOW": 2,
    "GREEN": 1,
    None: 0,
    "UNASSIGNED": 0,
}

LOCATION_PRESETS = {
    "hawaii": (19.896, -155.582),
    "seattle": (47.606, -122.332),
    "portland": (45.505, -122.675),
    "anchorage": (61.217, -149.900),
    "manila": (14.599, 120.984),
    "tokyo": (35.682, 139.692),
    "naples": (40.852, 14.268),
    "mexico city": (19.432, -99.133),
}


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# STEP 1: PULL ALL USGS HANS DATA
# ============================================================
def pull_all_volcanoes():
    """Pull all US volcanoes from HANS API."""
    print("\n📡 Pulling all US volcanoes from USGS HANS API...")
    r = requests.get(f"{USGS_HANS_BASE}/getUSVolcanoes", timeout=30)
    r.raise_for_status()
    volcanoes = r.json()
    print(f"   ✅ Got {len(volcanoes)} US volcanoes")
    return volcanoes


def pull_monitored_volcanoes():
    """Pull actively monitored volcanoes."""
    print("📡 Pulling monitored volcanoes...")
    r = requests.get(f"{USGS_HANS_BASE}/getMonitoredVolcanoes", timeout=30)
    r.raise_for_status()
    data = r.json()
    print(f"   ✅ Got {len(data)} monitored volcanoes")
    return data


def pull_elevated_volcanoes():
    """Pull volcanoes with elevated alert status."""
    print("📡 Pulling elevated/active alert volcanoes...")
    r = requests.get(f"{USGS_HANS_BASE}/getElevatedVolcanoes", timeout=30)
    r.raise_for_status()
    data = r.json()
    print(f"   ✅ Got {len(data)} elevated volcanoes")
    return data


def pull_volcano_detail(vnum):
    """Pull detailed info for a specific volcano."""
    try:
        r = requests.get(f"{USGS_HANS_BASE}/getVolcano/{vnum}", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def pull_newest_notice(vnum):
    """Pull the latest HANS notice for a volcano."""
    try:
        r = requests.get(f"{USGS_HANS_BASE}/newestForVolcano/{vnum}", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def pull_nearby_earthquakes(lat, lon, radius_km=50, days=30, min_mag=1.0):
    """Pull recent earthquakes near a volcano from USGS Earthquake API."""
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    try:
        params = {
            "format": "geojson",
            "starttime": start.strftime("%Y-%m-%d"),
            "endtime": end.strftime("%Y-%m-%d"),
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": radius_km,
            "minmagnitude": min_mag,
            "limit": 500,
            "orderby": "time",
        }
        r = requests.get(f"{USGS_EQ_BASE}/query", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])
    except Exception:
        return []


# ============================================================
# STEP 2: BUILD ENRICHED DATASET
# ============================================================
def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def enrich_volcano(volcano, elevated_map, monitored_set):
    """Enrich a single volcano record with all useful fields."""
    vnum = volcano.get("vnum", "")
    lat = volcano.get("latitude")
    lon = volcano.get("longitude")

    # Base fields
    enriched = {
        # --- IDENTITY ---
        "vnum": vnum,
        "volcano_name": volcano.get("volcano_name", ""),
        "region": volcano.get("region", ""),
        "latitude": lat,
        "longitude": lon,
        "elevation_meters": volcano.get("elevation_meters"),

        # --- STATUS FLAGS ---
        "is_monitored": vnum in monitored_set,
        "nvews_threat": volcano.get("nvews_threat", "Unassigned"),
        "threat_score": THREAT_SCORES.get(
            volcano.get("nvews_threat", "Unassigned"), 0
        ),

        # --- ALERT STATUS (from elevated data if available) ---
        "alert_level": None,
        "color_code": None,
        "alert_score": 0,
        "color_score": 0,

        # --- OBSERVATORY ---
        "obs_abbr": volcano.get("obs_abbr", ""),
        "obs_fullname": volcano.get("obs_fullname", ""),

        # --- LINKS ---
        "volcano_url": volcano.get("volcano_url", ""),
        "volcano_image_url": volcano.get("volcano_image_url", ""),
        "hans_url": volcano.get("hans_url", ""),

        # --- SEISMICITY (enriched later) ---
        "eq_count_30d": 0,
        "eq_max_mag_30d": 0.0,
        "eq_avg_mag_30d": 0.0,
        "eq_avg_depth_km": 0.0,
        "eq_shallow_count": 0,  # depth < 5km (more relevant for volcanoes)

        # --- COMPUTED RISK SCORE ---
        "composite_risk_score": 0.0,
    }

    # Merge elevated status if available
    if vnum in elevated_map:
        elev = elevated_map[vnum]
        alert = elev.get("alert_level") or elev.get("alertLevel")
        color = elev.get("color_code") or elev.get("colorCode")
        enriched["alert_level"] = alert
        enriched["color_code"] = color
        enriched["alert_score"] = ALERT_SCORES.get(
            str(alert).upper() if alert else None, 0
        )
        enriched["color_score"] = COLOR_SCORES.get(
            str(color).upper() if color else None, 0
        )

    return enriched


def enrich_with_seismicity(enriched, earthquakes):
    """Add earthquake statistics to the enriched record."""
    if not earthquakes:
        return enriched

    mags = []
    depths = []
    shallow = 0

    for eq in earthquakes:
        props = eq.get("properties", {})
        geom = eq.get("geometry", {})
        mag = props.get("mag")
        coords = geom.get("coordinates", [0, 0, 0])
        depth = coords[2] if len(coords) > 2 else 0

        if mag is not None:
            mags.append(mag)
        if depth is not None:
            depths.append(depth)
            if depth < 5:
                shallow += 1

    enriched["eq_count_30d"] = len(earthquakes)
    enriched["eq_max_mag_30d"] = max(mags) if mags else 0.0
    enriched["eq_avg_mag_30d"] = round(sum(mags) / len(mags), 2) if mags else 0.0
    enriched["eq_avg_depth_km"] = round(sum(depths) / len(depths), 2) if depths else 0.0
    enriched["eq_shallow_count"] = shallow

    return enriched


def compute_risk_score(enriched):
    """
    Compute a composite risk score (0-100) based on available features.

    Weights:
        - Threat level (NVEWS):    25%  (long-term hazard assessment)
        - Alert level:             25%  (current activity)
        - Color code:              15%  (aviation/current state)
        - Seismicity count:        15%  (precursor activity)
        - Max earthquake mag:      10%  (intensity of seismic unrest)
        - Shallow earthquakes:     10%  (magma movement indicator)
    """
    # Normalize each component to 0-1
    threat_norm = enriched["threat_score"] / 5.0
    alert_norm = enriched["alert_score"] / 4.0
    color_norm = enriched["color_score"] / 4.0

    # Seismicity: cap at reasonable maximums for normalization
    eq_count_norm = min(enriched["eq_count_30d"] / 200.0, 1.0)
    eq_mag_norm = min(enriched["eq_max_mag_30d"] / 6.0, 1.0)
    eq_shallow_norm = min(enriched["eq_shallow_count"] / 50.0, 1.0)

    score = (
        threat_norm * 25 +
        alert_norm * 25 +
        color_norm * 15 +
        eq_count_norm * 15 +
        eq_mag_norm * 10 +
        eq_shallow_norm * 10
    )

    enriched["composite_risk_score"] = round(score, 1)
    return enriched


# ============================================================
# STEP 3: FULL PIPELINE
# ============================================================
def run_full_pipeline(with_seismicity=True, seismic_limit=None):
    """
    Run the complete data pipeline:
    1. Pull all volcano lists
    2. Enrich with alert data
    3. Optionally add seismicity
    4. Compute risk scores
    5. Save to CSV + JSON
    """
    ensure_output_dir()

    # Pull raw data
    all_volcanoes = pull_all_volcanoes()
    monitored = pull_monitored_volcanoes()
    elevated = pull_elevated_volcanoes()

    # Build lookup structures
    monitored_set = set()
    for v in monitored:
        vnum = v.get("vnum", "")
        if vnum:
            monitored_set.add(vnum)

    elevated_map = {}
    for v in elevated:
        vnum = v.get("vnum", "")
        if vnum:
            elevated_map[vnum] = v

    # Enrich each volcano
    print(f"\n🔧 Enriching {len(all_volcanoes)} volcanoes...")
    enriched_list = []
    for i, volcano in enumerate(all_volcanoes):
        enriched = enrich_volcano(volcano, elevated_map, monitored_set)

        # Add seismicity for monitored/elevated volcanoes
        if with_seismicity and enriched["is_monitored"]:
            if seismic_limit and i >= seismic_limit:
                pass  # skip seismicity for speed
            elif enriched["latitude"] and enriched["longitude"]:
                lat = enriched["latitude"]
                lon = enriched["longitude"]
                print(f"   🔍 [{i+1}/{len(all_volcanoes)}] Seismicity for {enriched['volcano_name']}...", end="")
                eqs = pull_nearby_earthquakes(lat, lon, radius_km=50, days=30)
                enriched = enrich_with_seismicity(enriched, eqs)
                print(f" {enriched['eq_count_30d']} earthquakes")

        enriched = compute_risk_score(enriched)
        enriched_list.append(enriched)

    # Sort by risk score descending
    enriched_list.sort(key=lambda x: x["composite_risk_score"], reverse=True)

    # Save to JSON
    json_path = os.path.join(OUTPUT_DIR, "volcanoes_enriched.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(enriched_list, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n💾 Saved enriched JSON → {json_path}")

    # Save to CSV
    csv_path = os.path.join(OUTPUT_DIR, "volcanoes_enriched.csv")
    if enriched_list:
        keys = enriched_list[0].keys()
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(enriched_list)
    print(f"💾 Saved enriched CSV → {csv_path}")

    # Print summary
    print_data_quality(enriched_list)
    print_top_risk(enriched_list)

    # Save elevated details separately (these are the most important)
    elevated_details = [v for v in enriched_list if v["alert_score"] > 1]
    if elevated_details:
        ep = os.path.join(OUTPUT_DIR, "elevated_volcanoes.json")
        with open(ep, "w", encoding="utf-8") as f:
            json.dump(elevated_details, f, indent=2, default=str, ensure_ascii=False)
        print(f"💾 Saved elevated details → {ep}")

    return enriched_list


# ============================================================
# STEP 4: DATA QUALITY + SUMMARY
# ============================================================
def print_data_quality(data):
    """Print data quality stats."""
    total = len(data)
    monitored = sum(1 for v in data if v["is_monitored"])
    with_alert = sum(1 for v in data if v["alert_score"] > 0)
    with_eq = sum(1 for v in data if v["eq_count_30d"] > 0)
    with_coords = sum(1 for v in data if v["latitude"] and v["longitude"])

    print("\n" + "=" * 70)
    print("  📊 DATA QUALITY")
    print("=" * 70)
    print(f"    Total volcanoes:     {total}")
    print(f"    With coordinates:    {with_coords}/{total}")
    print(f"    Monitored (has data):{monitored}/{total}")
    print(f"    With active alerts:  {with_alert}/{total}")
    print(f"    With seismic data:   {with_eq}/{total}")


def print_top_risk(data):
    """Print the highest-risk volcanoes."""
    print("\n" + "=" * 70)
    print("  🌋 TOP 15 VOLCANOES BY RISK SCORE")
    print("=" * 70)
    print(f"  {'#':<3} {'Volcano':<22} {'Region':<15} {'Threat':<12} "
          f"{'Alert':<9} {'EQ/30d':<7} {'Risk':>5}")
    print("  " + "-" * 75)
    for i, v in enumerate(data[:15]):
        alert = v['alert_level'] or '-'
        print(f"  {i+1:<3} {v['volcano_name']:<22} {v['region']:<15} "
              f"{v['nvews_threat']:<12} {alert:<9} "
              f"{v['eq_count_30d']:<7} {v['composite_risk_score']:>5}")


# ============================================================
# STEP 5: LOCATION-BASED RISK LOOKUP
# ============================================================
def get_nearby_volcanoes(data, user_lat, user_lon, radius_km=500, top_n=10):
    """Find volcanoes near a user location, sorted by proximity."""
    nearby = []
    for v in data:
        if v["latitude"] and v["longitude"]:
            dist = haversine_km(user_lat, user_lon, v["latitude"], v["longitude"])
            v_copy = dict(v)
            v_copy["distance_to_user_km"] = round(dist, 1)
            nearby.append(v_copy)

    nearby.sort(key=lambda x: x["distance_to_user_km"])
    within_radius = [v for v in nearby if v["distance_to_user_km"] <= radius_km]

    return within_radius[:top_n]


def location_risk_lookup(data, user_lat, user_lon):
    """Find nearby volcanoes and print risk summary."""
    print(f"\n📍 Location risk lookup: ({user_lat}, {user_lon})")

    nearby = get_nearby_volcanoes(data, user_lat, user_lon, radius_km=500, top_n=10)
    print(f"   Found {len(nearby)} volcanoes within 500km")

    if nearby:
        print(f"\n   {'Volcano':<22} {'Dist (km)':<10} {'Alert':<10} "
              f"{'Threat':<15} {'EQ/30d':<8} {'Risk':>5}")
        print("   " + "-" * 72)
        for v in nearby:
            alert_str = v['alert_level'] or 'Normal'
            print(f"   {v['volcano_name']:<22} {v['distance_to_user_km']:<10} "
                  f"{alert_str:<10} {v['nvews_threat']:<15} "
                  f"{v['eq_count_30d']:<8} {v['composite_risk_score']:>5}")
    else:
        print("   No volcanoes found within 500km.")

    # Save result
    result = {
        "user_location": {"lat": user_lat, "lon": user_lon},
        "nearby_volcanoes": nearby,
    }
    result_path = os.path.join(OUTPUT_DIR, "risk_assessment.json")
    ensure_output_dir()
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n💾 Saved assessment → {result_path}")

    return result


# ============================================================
# MAIN
# ============================================================
def main():
    # Parse arguments
    location = None

    for i, arg in enumerate(sys.argv):
        if arg == "--location" and i + 1 < len(sys.argv):
            location = sys.argv[i + 1]

    # STEP 1: Run pipeline (or load cached data)
    json_path = os.path.join(OUTPUT_DIR, "volcanoes_enriched.json")

    if os.path.exists(json_path) and "--refresh" not in sys.argv:
        print(f"📂 Loading cached data from {json_path}")
        print(f"   (use --refresh to re-pull from APIs)")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = run_full_pipeline(with_seismicity=True, seismic_limit=None)

    # STEP 2: If location given, do risk lookup
    if location:
        if "," in location:
            parts = location.split(",")
            user_lat = float(parts[0].strip())
            user_lon = float(parts[1].strip())
        else:
            loc_lower = location.lower().strip()
            if loc_lower in LOCATION_PRESETS:
                user_lat, user_lon = LOCATION_PRESETS[loc_lower]
            else:
                print(f"❌ Unknown location: {location}")
                print(f"   Use lat,lon format or one of: {list(LOCATION_PRESETS.keys())}")
                return

        location_risk_lookup(data, user_lat, user_lon)

    elif "--analyze-only" not in sys.argv and data:
        print("\n" + "=" * 70)
        print("  Location-based risk lookup")
        print("=" * 70)
        print("\n  Usage:")
        print('    python volcano_pipeline.py --location "Hawaii"')
        print('    python volcano_pipeline.py --location "Seattle"')
        print('    python volcano_pipeline.py --location "Anchorage"')
        print('    python volcano_pipeline.py --location 19.4,-155.3')
        print(f"\n  Data cached in {OUTPUT_DIR}/ — use --refresh to update\n")


if __name__ == "__main__":
    main()
