"""
pytrends — Pull as much search trend data as possible for pandemic signals
Saves CSVs ready for model training

NOTE: pytrends rate limits aggressively. This script has built-in delays.
      If you get 429 errors, increase DELAY_SECONDS or run in batches.
"""
from pytrends.request import TrendReq
import json
import time
import os

os.makedirs("data/pytrends", exist_ok=True)

DELAY = 3  # seconds between API calls — increase if you get 429s

pytrends = TrendReq(hl='en-US', tz=360)

# ============================================================
# 1. SYMPTOM SEARCH TRENDS — multiple time ranges
# ============================================================
print("=== 1. Symptom Search Trends ===\n")

symptom_groups = {
    "respiratory": ["fever cough", "difficulty breathing", "shortness of breath", "chest pain cough", "pneumonia symptoms"],
    "gastrointestinal": ["diarrhea vomiting", "food poisoning", "stomach flu", "dehydration symptoms", "cholera symptoms"],
    "viral_general": ["loss of smell", "body aches fever", "rash fever", "swollen lymph nodes", "fatigue fever"],
    "neurological": ["severe headache", "neck stiffness", "confusion fever", "seizure", "meningitis symptoms"],
    "hemorrhagic": ["bleeding gums", "blood in urine", "internal bleeding", "ebola symptoms", "dengue symptoms"],
}

timeframes = {
    "5y": "today 5-y",     # 5 years — weekly resolution
    "12m": "today 12-m",   # 12 months — weekly
    "3m": "today 3-m",     # 3 months — weekly (more granular)
}

for group_name, keywords in symptom_groups.items():
    for tf_label, tf_value in timeframes.items():
        print(f"  {group_name} / {tf_label}...", end=" ", flush=True)
        try:
            pytrends.build_payload(keywords, timeframe=tf_value, geo='')
            df = pytrends.interest_over_time()
            if not df.empty:
                df.to_csv(f"data/pytrends/symptoms_{group_name}_{tf_label}.csv")
                print(f"{len(df)} rows")
            else:
                print("empty")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(DELAY)

# ============================================================
# 2. DISEASE NAME TRENDS — track named diseases
# ============================================================
print("\n=== 2. Named Disease Trends ===\n")

disease_batches = [
    ["bird flu", "mpox", "cholera", "dengue", "measles"],
    ["tuberculosis", "malaria", "ebola", "zika", "plague"],
    ["meningitis", "typhoid", "hepatitis", "rabies", "anthrax"],
    ["covid", "influenza", "pneumonia", "sepsis", "MRSA"],
]

for i, batch in enumerate(disease_batches):
    for tf_label, tf_value in timeframes.items():
        print(f"  batch_{i} / {tf_label}: {batch}...", end=" ", flush=True)
        try:
            pytrends.build_payload(batch, timeframe=tf_value, geo='')
            df = pytrends.interest_over_time()
            if not df.empty:
                df.to_csv(f"data/pytrends/diseases_batch{i}_{tf_label}.csv")
                print(f"{len(df)} rows")
            else:
                print("empty")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(DELAY)

# ============================================================
# 3. REGIONAL BREAKDOWN — top disease terms by country
# ============================================================
print("\n=== 3. Regional Hotspots ===\n")

regional_terms = ["fever cough", "disease outbreak", "epidemic", "dengue", "cholera"]

for term in regional_terms:
    print(f"  regions for '{term}'...", end=" ", flush=True)
    try:
        pytrends.build_payload([term], timeframe='today 3-m', geo='')
        df = pytrends.interest_by_region(resolution='COUNTRY', inc_low_vol=False, inc_geo_code=True)
        df_filtered = df[df[term] > 0].sort_values(term, ascending=False)
        df_filtered.to_csv(f"data/pytrends/regional_{term.replace(' ', '_')}.csv")
        print(f"{len(df_filtered)} countries")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(DELAY)

# ============================================================
# 4. RELATED & RISING QUERIES — emerging threats
# ============================================================
print("\n=== 4. Related/Rising Queries ===\n")

rising_terms = ["disease outbreak", "epidemic", "virus", "infection spreading", "health emergency"]

all_rising = {}
for term in rising_terms:
    print(f"  related to '{term}'...", end=" ", flush=True)
    try:
        pytrends.build_payload([term], timeframe='today 3-m', geo='')
        related = pytrends.related_queries()
        
        term_data = {}
        for subkey in ["top", "rising"]:
            df = related.get(term, {}).get(subkey)
            if df is not None and not df.empty:
                term_data[subkey] = df.to_dict(orient="records")
                df.to_csv(f"data/pytrends/related_{term.replace(' ', '_')}_{subkey}.csv", index=False)
        
        all_rising[term] = term_data
        print("ok")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(DELAY)

with open("data/pytrends/all_related_queries.json", "w") as f:
    json.dump(all_rising, f, indent=2)

# ============================================================
# 5. SPECIFIC HIGH-RISK COUNTRIES — deeper drill
# ============================================================
print("\n=== 5. Country-Specific Trends ===\n")

# Countries that frequently see outbreaks
countries = {
    "IN": "India", "NG": "Nigeria", "BR": "Brazil", "BD": "Bangladesh",
    "PH": "Philippines", "ID": "Indonesia", "PK": "Pakistan", "CD": "Congo_DRC",
    "ET": "Ethiopia", "KE": "Kenya", "US": "United_States", "CN": "China",
}

for geo_code, geo_name in countries.items():
    print(f"  {geo_name}...", end=" ", flush=True)
    try:
        pytrends.build_payload(
            ["fever", "outbreak", "epidemic", "hospital", "infection"],
            timeframe='today 12-m',
            geo=geo_code
        )
        df = pytrends.interest_over_time()
        if not df.empty:
            df.to_csv(f"data/pytrends/country_{geo_name}.csv")
            print(f"{len(df)} rows")
        else:
            print("empty")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(DELAY)

print(f"\n✅ Done. All data in data/pytrends/")
print(f"   CSVs ready for pandas / model training")
