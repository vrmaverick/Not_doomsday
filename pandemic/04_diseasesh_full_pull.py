"""
disease.sh — Pull everything available: COVID by country, historical, flu, vaccines
Note: COVID data is mostly frozen (countries stopped reporting) but structure is useful
      and historical data is good for model training
"""
import requests
import json
import csv
import os

BASE = "https://disease.sh/v3"
os.makedirs("data/diseasesh", exist_ok=True)

# ============================================================
# 1. COVID — ALL COUNTRIES current snapshot
# ============================================================
print("=== 1. COVID-19 All Countries Snapshot ===\n")

resp = requests.get(f"{BASE}/covid-19/countries")
countries = resp.json()
with open("data/diseasesh/covid_all_countries.json", "w") as f:
    json.dump(countries, f, indent=2)

# Also save as flat CSV
if countries:
    flat_rows = []
    for c in countries:
        row = {
            "country": c.get("country"),
            "iso2": c.get("countryInfo", {}).get("iso2"),
            "iso3": c.get("countryInfo", {}).get("iso3"),
            "lat": c.get("countryInfo", {}).get("lat"),
            "lon": c.get("countryInfo", {}).get("long"),
            "continent": c.get("continent"),
            "population": c.get("population"),
            "cases": c.get("cases"),
            "deaths": c.get("deaths"),
            "recovered": c.get("recovered"),
            "active": c.get("active"),
            "critical": c.get("critical"),
            "cases_per_million": c.get("casesPerOneMillion"),
            "deaths_per_million": c.get("deathsPerOneMillion"),
            "tests": c.get("tests"),
            "tests_per_million": c.get("testsPerOneMillion"),
        }
        flat_rows.append(row)
    
    with open("data/diseasesh/covid_all_countries.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=flat_rows[0].keys())
        writer.writeheader()
        writer.writerows(flat_rows)
    
    print(f"  {len(countries)} countries saved (JSON + CSV)")

# ============================================================
# 2. COVID — HISTORICAL by country (max available)
# ============================================================
print("\n=== 2. COVID-19 Historical Data ===\n")

# Global historical — all time
print("  Global historical (all time)...", end=" ", flush=True)
resp = requests.get(f"{BASE}/covid-19/historical/all", params={"lastdays": "all"})
if resp.status_code == 200:
    data = resp.json()
    with open("data/diseasesh/covid_historical_global.json", "w") as f:
        json.dump(data, f, indent=2)
    
    # Convert to CSV
    cases = data.get("cases", {})
    deaths = data.get("deaths", {})
    recovered = data.get("recovered", {})
    
    rows = []
    for date in cases.keys():
        rows.append({
            "date": date,
            "cases": cases.get(date, 0),
            "deaths": deaths.get(date, 0),
            "recovered": recovered.get(date, 0),
        })
    
    with open("data/diseasesh/covid_historical_global.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "cases", "deaths", "recovered"])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"{len(rows)} days")

# Per-country historical — key countries
key_countries = [
    "usa", "india", "brazil", "uk", "france", "germany", "italy", "spain",
    "russia", "turkey", "south africa", "mexico", "indonesia", "philippines",
    "nigeria", "bangladesh", "pakistan", "egypt", "kenya", "colombia",
    "china", "japan", "south korea", "australia", "canada",
]

for country in key_countries:
    print(f"  {country}...", end=" ", flush=True)
    try:
        resp = requests.get(f"{BASE}/covid-19/historical/{country}", params={"lastdays": "all"})
        if resp.status_code == 200:
            data = resp.json()
            safe_name = country.replace(" ", "_")
            with open(f"data/diseasesh/covid_historical_{safe_name}.json", "w") as f:
                json.dump(data, f, indent=2)
            
            # Flatten to CSV
            timeline = data.get("timeline", {})
            cases = timeline.get("cases", {})
            deaths = timeline.get("deaths", {})
            recovered = timeline.get("recovered", {})
            
            rows = []
            for date in cases.keys():
                rows.append({
                    "date": date,
                    "country": country,
                    "cases_cumulative": cases.get(date, 0),
                    "deaths_cumulative": deaths.get(date, 0),
                    "recovered_cumulative": recovered.get(date, 0),
                })
            
            with open(f"data/diseasesh/covid_historical_{safe_name}.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            
            print(f"{len(rows)} days")
        else:
            print(f"status {resp.status_code}")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================
# 3. COVID — BY CONTINENT
# ============================================================
print("\n=== 3. COVID-19 by Continent ===\n")

resp = requests.get(f"{BASE}/covid-19/continents")
if resp.status_code == 200:
    continents = resp.json()
    with open("data/diseasesh/covid_continents.json", "w") as f:
        json.dump(continents, f, indent=2)
    for c in continents:
        print(f"  {c.get('continent')}: {c.get('cases', 0):,} cases")

# ============================================================
# 4. INFLUENZA — CDC data
# ============================================================
print("\n=== 4. Influenza Data ===\n")

flu_endpoints = {
    "ILINet": "influenza/cdc/ILINet",
    "USCL": "influenza/cdc/USCL",
    "USPHLabs": "influenza/cdc/USPHLAB",
    "USClinLabs": "influenza/cdc/USCL",
}

for name, endpoint in flu_endpoints.items():
    print(f"  {name}...", end=" ", flush=True)
    try:
        resp = requests.get(f"{BASE}/{endpoint}")
        if resp.status_code == 200:
            data = resp.json()
            with open(f"data/diseasesh/flu_{name}.json", "w") as f:
                json.dump(data, f, indent=2)
            
            # Extract records
            records = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(records, list):
                print(f"{len(records)} records")
                # Save as CSV if we can
                if records and isinstance(records[0], dict):
                    with open(f"data/diseasesh/flu_{name}.csv", "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=records[0].keys())
                        writer.writeheader()
                        writer.writerows(records)
            else:
                print(f"type: {type(records)}")
        else:
            print(f"status {resp.status_code}")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================
# 5. VACCINE COVERAGE — global
# ============================================================
print("\n=== 5. Vaccine Coverage ===\n")

# Global
print("  Global coverage...", end=" ", flush=True)
resp = requests.get(f"{BASE}/covid-19/vaccine/coverage", params={"lastdays": "all"})
if resp.status_code == 200:
    data = resp.json()
    with open("data/diseasesh/vaccine_global.json", "w") as f:
        json.dump(data, f, indent=2)
    
    if isinstance(data, dict):
        rows = [{"date": k, "doses": v} for k, v in data.items()]
        with open("data/diseasesh/vaccine_global.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "doses"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} days")

# By country
print("  Country vaccine data...", end=" ", flush=True)
resp = requests.get(f"{BASE}/covid-19/vaccine/coverage/countries", params={"lastdays": "all"})
if resp.status_code == 200:
    data = resp.json()
    with open("data/diseasesh/vaccine_countries.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"{len(data)} countries")

print(f"\n✅ Done. All data in data/diseasesh/")
