"""
GDELT — Pull articles, geographic data, timelines for disease tracking
Fixed: geo timespan must be <= 7 days
"""
import requests
import json
import os
from datetime import datetime

os.makedirs("data/gdelt", exist_ok=True)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GEO_API = "https://api.gdeltproject.org/api/v2/geo/geo"

# ============================================================
# 1. ARTICLES — multiple disease queries
# ============================================================
print("=== 1. Disease Outbreak Articles ===\n")

queries = {
    "general_outbreak": "disease outbreak epidemic",
    "bird_flu": "H5N1 bird flu avian influenza",
    "mpox": "mpox monkeypox outbreak",
    "cholera": "cholera outbreak cases",
    "dengue": "dengue fever outbreak",
    "measles": "measles outbreak cases",
    "tuberculosis": "tuberculosis TB outbreak",
    "plague": "plague outbreak cases",
    "ebola": "ebola outbreak cases",
    "meningitis": "meningitis outbreak",
    "respiratory": "respiratory illness outbreak pneumonia",
    "antimicrobial_resistance": "antibiotic resistant superbug AMR",
    "pandemic_preparedness": "pandemic preparedness WHO emergency",
    "unknown_illness": "mystery illness unknown disease unidentified",
}

for name, query in queries.items():
    print(f"  {name}...", end=" ", flush=True)
    try:
        resp = requests.get(DOC_API, params={
            "query": query,
            "mode": "artlist",
            "maxrecords": 250,  # max allowed
            "format": "json",
            "timespan": "7d",
            "sort": "datedesc"
        }, timeout=30)
        
        data = resp.json()
        articles = data.get("articles", [])
        
        with open(f"data/gdelt/articles_{name}.json", "w") as f:
            json.dump(articles, f, indent=2)
        
        print(f"{len(articles)} articles")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================
# 2. GEOGRAPHIC DATA — fixed to 7 day max
# ============================================================
print("\n=== 2. Geographic Outbreak Mentions ===\n")

geo_queries = {
    "outbreak": "disease outbreak epidemic",
    "bird_flu": "bird flu H5N1",
    "dengue": "dengue fever",
    "cholera": "cholera",
    "respiratory": "respiratory illness pneumonia",
}

for name, query in geo_queries.items():
    print(f"  geo_{name}...", end=" ", flush=True)
    try:
        resp = requests.get(GEO_API, params={
            "query": query,
            "mode": "pointdata",
            "format": "geojson",
            "timespan": "7d",  # FIXED: was 14d, max is 7d
            "maxpoints": 250
        }, timeout=30)
        
        data = resp.json()
        features = data.get("features", [])
        
        # Check for error in response
        has_error = any("ERROR" in str(f.get("properties", {}).get("name", "")) for f in features)
        
        with open(f"data/gdelt/geo_{name}.json", "w") as f:
            json.dump(data, f, indent=2)
        
        if has_error:
            print(f"API ERROR in response")
        else:
            print(f"{len(features)} points")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================
# 3. TIMELINE VOLUME — article counts over time per disease
# ============================================================
print("\n=== 3. Article Volume Timelines ===\n")

timeline_queries = {
    "bird_flu": "H5N1 bird flu",
    "mpox": "mpox monkeypox",
    "cholera": "cholera outbreak",
    "dengue": "dengue fever",
    "measles": "measles outbreak",
    "ebola": "ebola",
    "tuberculosis": "tuberculosis",
    "plague": "plague outbreak",
    "unknown_illness": "mystery illness unknown disease",
    "pandemic": "pandemic",
    "antimicrobial": "antibiotic resistant superbug",
}

# Pull multiple timespan ranges
for timespan in ["30d", "90d", "180d"]:
    print(f"\n  Timespan: {timespan}")
    for name, query in timeline_queries.items():
        print(f"    {name}...", end=" ", flush=True)
        try:
            resp = requests.get(DOC_API, params={
                "query": query,
                "mode": "timelinevol",
                "format": "json",
                "timespan": timespan
            }, timeout=30)
            
            data = resp.json()
            
            with open(f"data/gdelt/timeline_{name}_{timespan}.json", "w") as f:
                json.dump(data, f, indent=2)
            
            # Count data points
            timeline = data.get("timeline", [])
            if timeline:
                points = len(timeline[0].get("data", []))
                print(f"{points} data points")
            else:
                print(f"format: {list(data.keys())}")
        except Exception as e:
            print(f"ERROR: {e}")

# ============================================================
# 4. TONE TIMELINE — sentiment around disease terms
# ============================================================
print("\n\n=== 4. News Tone/Sentiment Timelines ===\n")

for name, query in list(timeline_queries.items())[:5]:  # top 5 only
    print(f"  tone_{name}...", end=" ", flush=True)
    try:
        resp = requests.get(DOC_API, params={
            "query": query,
            "mode": "timelinetone",
            "format": "json",
            "timespan": "90d"
        }, timeout=30)
        
        data = resp.json()
        with open(f"data/gdelt/tone_{name}.json", "w") as f:
            json.dump(data, f, indent=2)
        
        print("ok")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================
# 5. THEME-BASED — GDELT has built-in themes
# ============================================================
print("\n=== 5. GDELT Theme Searches ===\n")

theme_queries = [
    ("health_pandemic", "theme:HEALTH_PANDEMIC"),
    ("health_sars", "theme:HEALTH_SARS"),
    ("disease", "theme:DISEASE"),
    ("who", "theme:WHO"),
]

for name, query in theme_queries:
    print(f"  {name}...", end=" ", flush=True)
    try:
        resp = requests.get(DOC_API, params={
            "query": query,
            "mode": "artlist",
            "maxrecords": 100,
            "format": "json",
            "timespan": "7d",
            "sort": "datedesc"
        }, timeout=30)
        
        data = resp.json()
        articles = data.get("articles", [])
        with open(f"data/gdelt/theme_{name}.json", "w") as f:
            json.dump(articles, f, indent=2)
        print(f"{len(articles)} articles")
    except Exception as e:
        print(f"ERROR: {e}")

print(f"\n✅ Done. All data in data/gdelt/")
