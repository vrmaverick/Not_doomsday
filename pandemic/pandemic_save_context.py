"""
pandemic_save_context.py
========================
Reads output from all pandemic data scripts (WHO, pytrends, GDELT, disease.sh)
and saves a combined summary to Data/Context_Json.json via context_manager.

Run AFTER the pull scripts have fetched their data.

Usage:
    python3 pandemic_save_context.py
"""

import os
import sys
import json
import csv
import glob

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from context_manager import save_to_context

# Resolve data dirs relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WHO_DIR = os.path.join(SCRIPT_DIR, "data", "who")
PYTRENDS_DIR = os.path.join(SCRIPT_DIR, "data", "pytrends")
GDELT_DIR = os.path.join(SCRIPT_DIR, "data", "gdelt")
DISEASESH_DIR = os.path.join(SCRIPT_DIR, "data", "diseasesh")


# ──────────────────────────────────────────────────────────────
# 1. WHO Summary
# ──────────────────────────────────────────────────────────────
def summarize_who() -> dict:
    """Summarize WHO GHO indicator data."""
    combined_path = os.path.join(WHO_DIR, "ALL_COMBINED.csv")
    if not os.path.exists(combined_path):
        return {"status": "no_data", "source": "WHO GHO"}

    indicators = {}
    total = 0
    years = set()
    countries = set()

    with open(combined_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            name = row.get("indicator", "unknown")
            yr = row.get("year", "")
            country = row.get("country_code", "")

            if yr:
                years.add(yr)
            if country:
                countries.add(country)

            if name not in indicators:
                indicators[name] = {"records": 0, "latest_year": ""}
            indicators[name]["records"] += 1
            if yr > indicators[name]["latest_year"]:
                indicators[name]["latest_year"] = yr

    # Top indicators by record count
    top = sorted(indicators.items(), key=lambda x: x[1]["records"], reverse=True)[:10]

    return {
        "source": "WHO GHO",
        "total_records": total,
        "indicators_tracked": len(indicators),
        "countries": len(countries),
        "year_range": f"{min(years)}–{max(years)}" if years else "unknown",
        "top_indicators": {k: v for k, v in top},
    }


# ──────────────────────────────────────────────────────────────
# 2. Google Trends Summary
# ──────────────────────────────────────────────────────────────
def summarize_pytrends() -> dict:
    """Summarize Google Trends symptom/disease search data."""
    if not os.path.exists(PYTRENDS_DIR):
        return {"status": "no_data", "source": "Google Trends"}

    csv_files = glob.glob(os.path.join(PYTRENDS_DIR, "*.csv"))
    json_files = glob.glob(os.path.join(PYTRENDS_DIR, "*.json"))

    # Parse rising queries for emerging threats
    rising_threats = []
    rising_path = os.path.join(PYTRENDS_DIR, "all_related_queries.json")
    if os.path.exists(rising_path):
        with open(rising_path, "r") as f:
            related = json.load(f)
        for term, data in related.items():
            for q in data.get("rising", []):
                val = q.get("value", 0)
                if isinstance(val, (int, float)) and val > 500:
                    rising_threats.append({
                        "query": q.get("query"),
                        "growth": val,
                        "parent_term": term,
                    })

    rising_threats.sort(key=lambda x: x["growth"], reverse=True)

    # Parse regional hotspots
    hotspots = {}
    for f in csv_files:
        if "regional_" in os.path.basename(f):
            term = os.path.basename(f).replace("regional_", "").replace(".csv", "")
            try:
                with open(f, "r") as fh:
                    reader = csv.DictReader(fh)
                    rows = list(reader)
                    if rows:
                        top_countries = rows[:5]
                        hotspots[term] = [
                            r.get("geoName", r.get("", "unknown")) for r in top_countries
                        ]
            except Exception:
                pass

    return {
        "source": "Google Trends (pytrends)",
        "data_files": len(csv_files) + len(json_files),
        "rising_threats": rising_threats[:10],
        "regional_hotspots": hotspots,
    }


# ──────────────────────────────────────────────────────────────
# 3. GDELT Summary
# ──────────────────────────────────────────────────────────────
def summarize_gdelt() -> dict:
    """Summarize GDELT disease outbreak article data."""
    if not os.path.exists(GDELT_DIR):
        return {"status": "no_data", "source": "GDELT"}

    article_counts = {}
    total_articles = 0

    for f in glob.glob(os.path.join(GDELT_DIR, "articles_*.json")):
        name = os.path.basename(f).replace("articles_", "").replace(".json", "")
        try:
            with open(f, "r") as fh:
                articles = json.load(fh)
            count = len(articles) if isinstance(articles, list) else 0
            article_counts[name] = count
            total_articles += count
        except Exception:
            pass

    # Geo hotspots
    geo_points = {}
    for f in glob.glob(os.path.join(GDELT_DIR, "geo_*.json")):
        name = os.path.basename(f).replace("geo_", "").replace(".json", "")
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            features = data.get("features", [])
            geo_points[name] = len(features)
        except Exception:
            pass

    # Sort by article volume
    top_diseases = sorted(article_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "source": "GDELT",
        "total_articles": total_articles,
        "articles_by_disease": dict(top_diseases[:10]),
        "geo_data_points": geo_points,
    }


# ──────────────────────────────────────────────────────────────
# 4. disease.sh Summary
# ──────────────────────────────────────────────────────────────
def summarize_diseasesh() -> dict:
    """Summarize disease.sh COVID + flu data."""
    if not os.path.exists(DISEASESH_DIR):
        return {"status": "no_data", "source": "disease.sh"}

    summary = {"source": "disease.sh"}

    # COVID snapshot — top 10 by active cases
    covid_path = os.path.join(DISEASESH_DIR, "covid_all_countries.json")
    if os.path.exists(covid_path):
        with open(covid_path, "r") as f:
            countries = json.load(f)
        if isinstance(countries, list):
            sorted_c = sorted(countries, key=lambda x: x.get("active", 0) or 0, reverse=True)
            summary["covid_top_active"] = [
                {
                    "country": c.get("country"),
                    "active": c.get("active"),
                    "cases": c.get("cases"),
                    "deaths": c.get("deaths"),
                }
                for c in sorted_c[:10]
            ]
            summary["covid_countries_tracked"] = len(countries)

    # Flu data
    flu_path = os.path.join(DISEASESH_DIR, "flu_ILINet.json")
    if os.path.exists(flu_path):
        with open(flu_path, "r") as f:
            flu = json.load(f)
        records = flu.get("data", flu) if isinstance(flu, dict) else flu
        if isinstance(records, list):
            summary["flu_records"] = len(records)
            if records:
                latest = records[-1] if isinstance(records[-1], dict) else {}
                summary["flu_latest"] = {
                    "week": latest.get("week"),
                    "total_ili": latest.get("totalILI"),
                }

    return summary


# ──────────────────────────────────────────────────────────────
# Main — combine all and save
# ──────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Pandemic Data → Context_Json.json")
    print("=" * 60)

    print("\n[1/4] Summarizing WHO data...")
    who = summarize_who()
    print(f"  → {who.get('total_records', 0)} records")

    print("[2/4] Summarizing Google Trends...")
    trends = summarize_pytrends()
    print(f"  → {trends.get('data_files', 0)} files, {len(trends.get('rising_threats', []))} rising threats")

    print("[3/4] Summarizing GDELT...")
    gdelt = summarize_gdelt()
    print(f"  → {gdelt.get('total_articles', 0)} articles")

    print("[4/4] Summarizing disease.sh...")
    diseasesh = summarize_diseasesh()
    print(f"  → {diseasesh.get('covid_countries_tracked', 0)} countries tracked")

    # Combine into one pandemic summary
    pandemic_summary = {
        "type": "pandemic",
        "sources": ["WHO GHO", "Google Trends", "GDELT", "disease.sh"],
        "who": who,
        "google_trends": trends,
        "gdelt": gdelt,
        "disease_sh": diseasesh,
    }

    save_to_context("pandemic", pandemic_summary)

    print("\n✅ Pandemic data saved to Context_Json.json")


if __name__ == "__main__":
    main()