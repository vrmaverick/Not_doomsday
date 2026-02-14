"""
WHO GHO — Pull ALL disease data, ALL years, save as flat CSVs for model training
"""
import requests
import json
import csv
import os

BASE = "https://ghoapi.azureedge.net/api"
os.makedirs("data/who", exist_ok=True)

# Every disease indicator worth pulling
INDICATORS = {
    # Cholera
    "WHS3_49": "cholera_cases",
    "WHS3_50": "cholera_deaths",
    # Tuberculosis
    "MDG_0000000020": "tb_incidence",
    "MDG_0000000017": "tb_deaths_hiv_neg",
    "MDG_0000000018": "tb_deaths_hiv_pos",
    "MDG_0000000023": "tb_prevalence",
    "MDG_0000000022": "tb_detection_rate",
    "MDG_0000000024": "tb_treatment_success",
    "MDG_0000000030": "tb_smear_detection",
    "MDG_0000000031": "tb_smear_treatment_success",
    # Malaria
    "MALARIA001": "malaria_deaths_reported",
    "MALARIA002": "malaria_cases_estimated",
    "MALARIA003": "malaria_deaths_estimated",
    "MALARIA004": "malaria_under5_deaths",
    "MALARIA005": "malaria_incidence",
    "WHS2_152": "malaria_death_rate",
    # Measles
    "mslv": "measles_immunization_pct",
    "MCV2": "measles_mcv2_coverage",
    # Meningitis
    "MENING_3": "meningitis_epidemic_districts",
}

print(f"Pulling {len(INDICATORS)} indicators from WHO GHO...\n")

# Also save a combined flat file for model training
combined_rows = []

for code, name in INDICATORS.items():
    print(f"  [{code}] {name}...", end=" ", flush=True)
    try:
        resp = requests.get(f"{BASE}/{code}", timeout=30)
        data = resp.json()
        records = data.get("value", [])
        
        # Save raw JSON
        with open(f"data/who/{name}_raw.json", "w") as f:
            json.dump(records, f, indent=2)
        
        # Extract clean rows for CSV
        clean = []
        for r in records:
            row = {
                "indicator": name,
                "indicator_code": code,
                "country_code": r.get("SpatialDim", ""),
                "region": r.get("ParentLocation", ""),
                "region_code": r.get("ParentLocationCode", ""),
                "year": r.get("TimeDim", ""),
                "value": r.get("NumericValue"),
                "value_str": r.get("Value", ""),
                "low": r.get("Low"),
                "high": r.get("High"),
            }
            clean.append(row)
            combined_rows.append(row)
        
        # Save individual CSV
        if clean:
            with open(f"data/who/{name}.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=clean[0].keys())
                writer.writeheader()
                writer.writerows(clean)
        
        print(f"{len(records)} records")
    except Exception as e:
        print(f"ERROR: {e}")

# Save combined CSV (all indicators in one file — model training ready)
if combined_rows:
    with open("data/who/ALL_COMBINED.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=combined_rows[0].keys())
        writer.writeheader()
        writer.writerows(combined_rows)

print(f"\n✅ Done. {len(combined_rows)} total records across {len(INDICATORS)} indicators")
print(f"   Individual CSVs + raw JSON in data/who/")
print(f"   Combined training file: data/who/ALL_COMBINED.csv")

# Quick stats
years = set(r["year"] for r in combined_rows if r["year"])
countries = set(r["country_code"] for r in combined_rows if r["country_code"])
print(f"   Year range: {min(years)} — {max(years)}")
print(f"   Countries: {len(countries)}")
