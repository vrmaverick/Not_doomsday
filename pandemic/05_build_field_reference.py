"""
FIELD REFERENCE — Run this AFTER the pull scripts to generate a cheat sheet
of every field from every API, with sample values and data types.

Reads the saved JSON files and builds a summary.
"""
import json
import os
import csv
from datetime import datetime

OUTPUT_FILE = "FIELD_REFERENCE.md"

def analyze_json(filepath):
    """Load a JSON file and describe its structure"""
    with open(filepath) as f:
        data = json.load(f)
    
    info = {
        "file": filepath,
        "top_level_type": type(data).__name__,
        "fields": {},
    }
    
    # Get to the records
    records = []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        # Common patterns: {"value": [...]}, {"articles": [...]}, {"data": [...]}
        for key in ["value", "articles", "data", "features"]:
            if key in data and isinstance(data[key], list):
                records = data[key]
                info["wrapper_key"] = key
                break
        if not records:
            # It's a flat dict (like disease.sh global)
            info["fields"] = {k: {"type": type(v).__name__, "sample": str(v)[:80]} for k, v in data.items()}
            return info
    
    if records and isinstance(records[0], dict):
        info["record_count"] = len(records)
        sample = records[0]
        for key, val in sample.items():
            info["fields"][key] = {
                "type": type(val).__name__ if val is not None else "null",
                "sample": str(val)[:80],
                "nullable": any(r.get(key) is None for r in records[:100]),
            }
    
    return info


def build_reference():
    lines = []
    lines.append(f"# Pandemic API Field Reference")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append("Quick lookup of every field from every API source.\n")
    lines.append("---\n")
    
    # WHO
    lines.append("## 1. WHO GHO API")
    lines.append("Base: `https://ghoapi.azureedge.net/api`")
    lines.append("Auth: None needed")
    lines.append("Update frequency: Annual\n")
    
    who_file = "data/who/cholera_cases_raw.json"
    if os.path.exists(who_file):
        info = analyze_json(who_file)
        lines.append(f"Records in sample: {info.get('record_count', '?')}")
        lines.append(f"Wrapper key: `{info.get('wrapper_key', 'value')}`\n")
        lines.append("| Field | Type | Sample | Nullable |")
        lines.append("|-------|------|--------|----------|")
        for field, meta in info["fields"].items():
            lines.append(f"| `{field}` | {meta['type']} | `{meta['sample'][:50]}` | {meta.get('nullable', '?')} |")
        lines.append("")
        lines.append("**Key fields for model:**")
        lines.append("- `SpatialDim` → country code (ISO3)")
        lines.append("- `ParentLocationCode` → region (EUR, AFR, etc)")
        lines.append("- `TimeDim` → year (int)")
        lines.append("- `NumericValue` → the actual measurement")
        lines.append("- `Low` / `High` → confidence interval bounds")
        lines.append("- `IndicatorCode` → which disease metric\n")
    else:
        lines.append("*Run 01_who_full_pull.py first*\n")
    
    lines.append("---\n")
    
    # pytrends
    lines.append("## 2. Google Trends (pytrends)")
    lines.append("Auth: None (but rate limited)")
    lines.append("Update frequency: Weekly\n")
    lines.append("**Output format:** pandas DataFrame, saved as CSV\n")
    lines.append("| Field | Type | Description |")
    lines.append("|-------|------|-------------|")
    lines.append("| `date` (index) | datetime | Week start date |")
    lines.append("| `<keyword>` | int (0-100) | Relative search interest — 100 = peak in timeframe |")
    lines.append("| `isPartial` | bool | True if the week is incomplete (current week) |")
    lines.append("")
    lines.append("**Regional output fields:**")
    lines.append("| Field | Type | Description |")
    lines.append("|-------|------|-------------|")
    lines.append("| `geoName` (index) | str | Country name |")
    lines.append("| `geoCode` | str | ISO2 country code |")
    lines.append("| `<keyword>` | int (0-100) | Relative interest — 100 = highest country |")
    lines.append("")
    lines.append("**Related queries output:**")
    lines.append("| Field | Type | Description |")
    lines.append("|-------|------|-------------|")
    lines.append("| `query` | str | The related search term |")
    lines.append("| `value` | int | Score (top) or % growth (rising) |")
    lines.append("")
    lines.append("**Key for model:**")
    lines.append("- Values are RELATIVE (0-100), not absolute search counts")
    lines.append("- Compare across time, not across keywords in different pulls")
    lines.append("- Rising queries with value > 1000 = breakout (potential emerging threat)")
    lines.append("- Regional data = where to focus attention\n")
    
    lines.append("---\n")
    
    # GDELT
    lines.append("## 3. GDELT API")
    lines.append("Base: `https://api.gdeltproject.org/api/v2/doc/doc`")
    lines.append("Geo: `https://api.gdeltproject.org/api/v2/geo/geo`")
    lines.append("Auth: None")
    lines.append("Update frequency: Every 15 minutes\n")
    
    gdelt_file = "data/gdelt/articles_general_outbreak.json"
    if os.path.exists(gdelt_file):
        info = analyze_json(gdelt_file)
        lines.append(f"**Article fields** (from artlist mode):\n")
        lines.append("| Field | Type | Sample |")
        lines.append("|-------|------|--------|")
        for field, meta in info["fields"].items():
            lines.append(f"| `{field}` | {meta['type']} | `{meta['sample'][:50]}` |")
    else:
        lines.append("*Run 03_gdelt_full_pull.py first*\n")
    
    lines.append("")
    lines.append("**Timeline volume fields** (from timelinevol mode):")
    lines.append("```json")
    lines.append('{')
    lines.append('  "query_details": {"title": "...", "date_resolution": "day"},')
    lines.append('  "timeline": [{')
    lines.append('    "series": "Volume Intensity",')
    lines.append('    "data": [{"date": "20260116T000000Z", "value": 0.123}, ...]')
    lines.append('  }]')
    lines.append('}')
    lines.append("```\n")
    
    lines.append("**GeoJSON fields** (from geo endpoint):")
    lines.append("```json")
    lines.append('{')
    lines.append('  "type": "Feature",')
    lines.append('  "geometry": {"type": "Point", "coordinates": [lon, lat]},')
    lines.append('  "properties": {"name": "Location Name", "count": 5}')
    lines.append('}')
    lines.append("```\n")
    
    lines.append("**Constraints:**")
    lines.append("- Geo endpoint: max timespan = `7d`")
    lines.append("- Article list: max `250` records per call")
    lines.append("- `seendate` format: `20260214T181500Z`")
    lines.append("- `sourcecountry` = where the article was published, NOT where the outbreak is\n")
    
    lines.append("---\n")
    
    # disease.sh
    lines.append("## 4. disease.sh")
    lines.append("Base: `https://disease.sh/v3`")
    lines.append("Auth: None")
    lines.append("Update frequency: Varies (COVID data mostly frozen)\n")
    
    lines.append("**Country snapshot fields:**\n")
    lines.append("| Field | Type | Description |")
    lines.append("|-------|------|-------------|")
    lines.append("| `country` | str | Country name |")
    lines.append("| `countryInfo.iso2` | str | ISO2 code |")
    lines.append("| `countryInfo.iso3` | str | ISO3 code |")
    lines.append("| `countryInfo.lat` | float | Latitude |")
    lines.append("| `countryInfo.long` | float | Longitude |")
    lines.append("| `continent` | str | Continent name |")
    lines.append("| `population` | int | Country population |")
    lines.append("| `cases` | int | Total cumulative cases |")
    lines.append("| `deaths` | int | Total cumulative deaths |")
    lines.append("| `recovered` | int | Total recovered |")
    lines.append("| `active` | int | Currently active cases |")
    lines.append("| `critical` | int | Currently critical |")
    lines.append("| `casesPerOneMillion` | float | Cases normalized by pop |")
    lines.append("| `deathsPerOneMillion` | float | Deaths normalized by pop |")
    lines.append("| `tests` | int | Total tests administered |")
    lines.append("| `testsPerOneMillion` | float | Tests normalized by pop |")
    lines.append("")
    lines.append("**Historical fields:** `{date: cumulative_count}` dict")
    lines.append("- Dates formatted as `M/D/YY` (e.g., `2/8/23`)")
    lines.append("- Values are CUMULATIVE — subtract consecutive days for daily counts")
    lines.append("")
    lines.append("**Flu ILINet fields:**")
    lines.append("| Field | Type | Description |")
    lines.append("|-------|------|-------------|")
    lines.append("| `week` | str | `YYYY - WW/52` format |")
    lines.append("| `age 0-4` | int | ILI cases ages 0-4 |")
    lines.append("| `age 5-24` | int | ILI cases ages 5-24 |")
    lines.append("| `age 25-49` | int | ILI cases ages 25-49 |")
    lines.append("| `age 50-64` | int | ILI cases ages 50-64 |")
    lines.append("| `age 64+` | int | ILI cases ages 64+ |")
    lines.append("| `totalILI` | int | Total influenza-like illness cases |")
    lines.append("")
    
    lines.append("---\n")
    
    # Common country code mapping note
    lines.append("## Country Code Mapping")
    lines.append("")
    lines.append("APIs use different country identifiers:")
    lines.append("| API | Format | Example |")
    lines.append("|-----|--------|---------|")
    lines.append("| WHO GHO | ISO3 | `IND`, `USA`, `NGA` |")
    lines.append("| pytrends | ISO2 | `IN`, `US`, `NG` |")
    lines.append("| GDELT | Full name | `India`, `United States`, `Nigeria` |")
    lines.append("| disease.sh | Full name + ISO2/3 | `India` + `IN` + `IND` |")
    lines.append("")
    lines.append("**You'll need a mapping table to join data across sources.**")
    lines.append("Use `pycountry` library or a static CSV for this.\n")
    
    lines.append("---\n")
    
    lines.append("## Data Gaps & Gotchas\n")
    lines.append("- **WHO**: Yearly only. No real-time. Some indicators stop at 2022.")
    lines.append("- **pytrends**: Relative values (0-100), NOT absolute counts. Rate limited.")
    lines.append("- **GDELT**: `sourcecountry` ≠ outbreak location. Articles may be duplicates.")
    lines.append("- **disease.sh**: COVID `todayCases: 0` everywhere = data is frozen. Historical stops at 2023 for most countries.")
    lines.append("- **Date formats**: All different. Normalize early.")
    lines.append("- **Country codes**: All different. Normalize early.\n")
    
    # Write
    with open(OUTPUT_FILE, "w") as f:
        f.write("\n".join(lines))
    
    print(f"✅ Field reference saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    build_reference()
