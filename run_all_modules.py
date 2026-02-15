import os
import sys
import json
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Earthquake"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Flood"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "solarFlare"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from context_manager import save_to_context

CONTEXT_FILE = "./Data/Context_Json.json"  # or full path if needed

def clear_last_context():
    """Delete the context file if it exists."""
    if os.path.exists(CONTEXT_FILE):
        os.remove(CONTEXT_FILE)
        print(f"[context_manager] Deleted {CONTEXT_FILE}")
    else:
        print(f"[context_manager] No context file to delete: {CONTEXT_FILE}")

def run_earthquake(lat, lng, name):
    try:
        from Earthquake.earthquake_api import get_earthquakes
        from Earthquake.earthquake_preprocessor import preprocess
        from Earthquake.earthquake_predictor import predict_risk

        raw = get_earthquakes(lat=lat, lng=lng, radius_km=500, min_mag=2.5)
        processed = preprocess(raw, location_name=name)
        prediction = predict_risk(processed)

        save_to_context("earthquake", {
            "location": name,
            "coordinates": {"lat": lat, "lng": lng},
            "events_analyzed": processed["summary"]["total_events"],
            "prediction": prediction,
            "data_summary": processed["summary"],
        })
        print(f"  ✅ Earthquake — {prediction.get('risk_level', 'UNKNOWN')}")
    except Exception as e:
        print(f"  ❌ Earthquake — {e}")


def run_flood(lat, lng, name):
    try:
        from Flood.flood_api import get_flood_data
        from Flood.flood_preprocessor import preprocess
        from Flood.flood_predictor import predict_flood_risk

        raw = get_flood_data(lat=lat, lng=lng, past_days=30, forecast_days=30)
        if raw.get("error"):
            print(f"  ❌ Flood — {raw['error']}")
            return

        processed = preprocess(raw, location_name=name)
        prediction = predict_flood_risk(processed)

        save_to_context("flood", {
            "location": name,
            "coordinates": {"lat": lat, "lng": lng},
            "days_analyzed": processed["summary"]["total_days"],
            "prediction": prediction,
            "data_summary": processed["summary"],
        })
        print(f"  ✅ Flood — {prediction.get('risk_level', 'UNKNOWN')}")
    except Exception as e:
        print(f"  ❌ Flood — {e}")


# def run_fire(lat, lng, name):
#     try:
#         fire_dir = os.path.join(PROJECT_ROOT, "Forest_fire")
#         sys.path.insert(0, fire_dir)

#         # Fire scripts use ../Data/ relative paths, so cd into Forest_fire/
#         original_dir = os.getcwd()
#         os.chdir(fire_dir)

#         from Forest_fire.Api import Fire_API
#         from Forest_fire.Predict import Predict_forest_fires
#         from Forest_fire.model import summarize_groq_fire, process_groq_to_map

#         # Step 1: Fetch fire data — needs bounding box: "minlon,minlat" and "maxlon,maxlat"
#         min_lon = lng - 5
#         min_lat = lat - 5
#         max_lon = lng + 5
#         max_lat = lat + 5
#         bbox_min = f"{min_lon},{min_lat}"
#         bbox_max = f"{max_lon},{max_lat}"
#         print("  Fetching fire data...")
#         Fire_API(bbox_min, bbox_max)

#         # Step 2: Check if any fires were found
#         fires_path = os.path.join(PROJECT_ROOT, "Data", "us_fires.json")
#         if not os.path.exists(fires_path) or os.path.getsize(fires_path) < 10:
#             os.chdir(original_dir)
#             save_to_context("fire", {
#                 "location": name,
#                 "coordinates": {"lat": lat, "lng": lng},
#                 "detections": 0,
#                 "summary": "No active fire detections in this area.",
#             })
#             print("  ✅ Fire — No active fires detected")
#             return

#         # Step 3: Extract key fields
#         print("  Preprocessing...")
#         Predict_forest_fires()

#         # Step 4: LLM prediction
#         print("  Running LLM prediction...")
#         summarize_groq_fire()

#         # Step 5: Generate coordinate map
#         process_groq_to_map()

#         # Step 5: Save to context
#         os.chdir(original_dir)

#         summary_path = os.path.join(PROJECT_ROOT, "Data", "fire_summary.json")
#         if os.path.exists(summary_path):
#             with open(summary_path, "r") as f:
#                 fire_result = json.load(f)

#             save_to_context("fire", {
#                 "location": name,
#                 "coordinates": {"lat": lat, "lng": lng},
#                 "detections": fire_result.get("data_count", 0),
#                 "summary": fire_result.get("summary", ""),
#             })
#             print(f"  ✅ Fire — saved")
#         else:
#             print("  ❌ Fire — no summary file generated")

#     except Exception as e:
#         os.chdir(original_dir)
#         print(f"  ❌ Fire — {e}")

def run_fire(lat, lng, name):
    original_dir = os.getcwd()
    try:
        fire_dir = os.path.join(PROJECT_ROOT, "Forest_fire")
        sys.path.insert(0, fire_dir)

        # Go into Forest_fire ONLY for scripts that assume ../Data
        os.chdir(fire_dir)

        from Forest_fire.Api import Fire_API
        from Forest_fire.Predict import Predict_forest_fires
        from Forest_fire.model import summarize_groq_fire, process_groq_to_map

        # Step 1: Fetch fire data — needs bounding box: "minlon,minlat" and "maxlon,maxlat"
        min_lon = lng - 5
        min_lat = lat - 5
        max_lon = lng + 5
        max_lat = lat + 5
        bbox_min = f"{min_lon},{min_lat}"
        bbox_max = f"{max_lon},{max_lat}"
        print("  Fetching fire data...")
        Fire_API(bbox_min, bbox_max)

        # Step 2: Check if any fires were found
        fires_path = os.path.join(PROJECT_ROOT, "Data", "us_fires.json")
        if not os.path.exists(fires_path) or os.path.getsize(fires_path) < 10:
            os.chdir(original_dir)
            save_to_context("fire", {
                "location": name,
                "coordinates": {"lat": lat, "lng": lng},
                "detections": 0,
                "summary": "No active fire detections in this area.",
            })
            print("  ✅ Fire — No active fires detected")
            return

        # Step 3: Extract key fields
        print("  Preprocessing...")
        Predict_forest_fires()

        # From here on, we don't *need* to stay in Forest_fire
        os.chdir(original_dir)

        # Step 4: LLM prediction (writes PROJECT_ROOT/Data/fire_summary.json)
        print("  Running LLM prediction...")
        summarize_groq_fire()

        # Step 5: Generate coordinate map (writes PROJECT_ROOT/Data/map_fire.json)
        process_groq_to_map()

        # Step 6: Save to context
        summary_path = os.path.join(PROJECT_ROOT, "Data", "fire_summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, "r") as f:
                fire_result = json.load(f)

            save_to_context("fire", {
                "location": name,
                "coordinates": {"lat": lat, "lng": lng},
                "detections": fire_result.get("data_count", 0),
                "summary": fire_result.get("summary", ""),
            })
            print("  ✅ Fire — saved")
        else:
            print("  ❌ Fire — no summary file generated")

    except Exception as e:
        os.chdir(original_dir)
        print(f"  ❌ Fire — {e}")



def run_volcano(lat, lng, name):
    try:
        volcano_dir = os.path.join(PROJECT_ROOT, "Volcano")
        sys.path.insert(0, volcano_dir)

        from Volcano.volcano_pipeline import get_nearby_volcanoes, compute_risk_score

        # Load cached enriched data
        cache_path = os.path.join(volcano_dir, "volcano_data", "volcanoes_enriched.json")
        if not os.path.exists(cache_path):
            print("  ❌ Volcano — no cached data. Run: cd Volcano && python3 volcano_pipeline.py")
            return

        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        
        # Get nearby volcanoes
        print("  Analyzing nearby volcanoes...")
        nearby = get_nearby_volcanoes(data, lat, lng, radius_km=500, top_n=10)

        # Build prediction
        max_score = max((v["composite_risk_score"] for v in nearby), default=0)
        if max_score >= 75:
            risk_level = "CRITICAL"
        elif max_score >= 50:
            risk_level = "HIGH"
        elif max_score >= 25:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        nearest = nearby[0] if nearby else None
        elevated = [v for v in nearby if v.get("alert_score", 0) >= 2]

        prediction = {
            "risk_level": risk_level,
            "risk_score": round(max_score / 10),
            "confidence": 0.7,
            "summary": 
            # f"{risk.get('nearby_count', 0)} volcanoes within 500km. "
                       f"Nearest: {nearest['volcano_name']} ({nearest['distance_km']}km away, "
                       f"risk score {nearest['composite_risk_score']}/100)" if nearest else "No nearby volcanoes.",
            "key_factors": [
                f"Nearby volcanoes: {len(nearby)}",
                f"Elevated alerts: {len(elevated)}",
                f"Max risk score: {max_score}/100",
            ],
            "pattern_detected": f"{len(elevated)} volcano(es) with elevated alert status" if elevated else "No elevated alerts",
            "recommendation": "Monitor USGS alerts closely" if elevated else "No immediate volcanic threat",
        }

        save_to_context("volcano", {
            "location": name,
            "coordinates": {"lat": lat, "lng": lng},
            "prediction": prediction,
            "nearby_count": len(nearby),
            "nearest_volcano": {
                "name": nearest["volcano_name"],
                "distance_km": nearest["distance_to_user_km"],
                "threat": nearest["nvews_threat"],
                "alert": nearest.get("alert_level"),
                "risk_score": nearest["composite_risk_score"],
            } if nearest else None,
            "elevated_volcanoes": [
                {"name": v["volcano_name"], "alert": v["alert_level"], "risk": v["composite_risk_score"]}
                for v in elevated
            ],
        })
        print(f"  ✅ Volcano — {risk_level}")

    except Exception as e:
        print(f"  ❌ Volcano — {e}")


def run_solar_flare():
    try:
        from solarFlare.solarFlarePredict import main as solar_main
        result = solar_main()
        
        if result:
            print(f"  ✅ Solar Flare — {'HIGH' if result.get('outages') == 'Yes' else 'LOW'}")
        else:
            print("  ❌ Solar Flare — no result returned")
    except Exception as e:
        print(f"  ❌ Solar Flare — {e}")
    
    risk_level = "HIGH" if result.get("outages") == "Yes" else "LOW"

    save_to_context(
        "solar_flare",
        {
            "type": "solar_flare",
            "location": "Global",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "outages_expected": result.get("outages"),
            "description": result.get("description"),
            "accuracy": result.get("accuracy"),
            "risk_level": risk_level,
            # you can add more derived fields here later if you want
        }
    )


def run_pandemic():
    try:
        pandemic_dir = os.path.join(PROJECT_ROOT, "pandemic")
        sys.path.insert(0, pandemic_dir)

        data_dirs = [
            os.path.join(pandemic_dir, "data", d)
            for d in ["who", "gdelt", "diseasesh"]
        ]
        if not any(os.path.exists(d) for d in data_dirs):
            print("  ⚠️  Pandemic — no data found, run pull scripts first")
            return

        from pandemic.pandemic_save_context import summarize_who, summarize_gdelt, summarize_diseasesh, summarize_pytrends

        save_to_context("pandemic", {
            "type": "pandemic",
            "sources": ["WHO GHO", "Google Trends", "GDELT", "disease.sh"],
            "who": summarize_who(),
            "google_trends": summarize_pytrends(),
            "gdelt": summarize_gdelt(),
            "disease_sh": summarize_diseasesh(),
        })
        print("  ✅ Pandemic — saved")
    except Exception as e:
        print(f"  ❌ Pandemic — {e}")


def run_all(lat: float, lng: float, name: str):
    """
    Run all threat modules for a given location.
    Call this from main.py after resolving coordinates.

    Args:
        lat:  Latitude
        lng:  Longitude
        name: Human-readable location name (e.g. "Houston, Texas")
    """
    print(f"📍 {name} ({lat}, {lng})\n")
    # clear_last_context()
    run_earthquake(lat, lng, name)
    run_flood(lat, lng, name)
    # run_fire(lat, lng, name)
    # run_volcano(lat, lng, name)
    # run_solar_flare()
    # run_pandemic()

    print(f"\n💾 Context_Json.json updated.")


# Self test with hardcoded value
if __name__ == "__main__":
    run_all(lat=42.36, lng=-71.06, name="Boston, Massachusetts")