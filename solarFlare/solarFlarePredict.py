"""
!(Not)Doomsday - Solar Flare Monitor
Fetches real-time solar flare data from NOAA SWPC and analyzes it
via Groq API (LangChain) for outage prediction.
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ──────────────────────────────────────────────────────────────
# 1. Pydantic schema for structured output
# ──────────────────────────────────────────────────────────────
class SolarFlareReport(BaseModel):
    outages: str = Field(description="'Yes' or 'No' — whether outages are expected")
    description: str = Field(description="Plain-english summary of current solar activity and potential impact")
    accuracy: int = Field(description="Confidence score 0-100 based on data quality and event severity")


# ──────────────────────────────────────────────────────────────
# 2. Fetch real-time data from NOAA SWPC public JSON endpoints
# ──────────────────────────────────────────────────────────────
NOAA_SWPC_ENDPOINTS = {
    "solar_flares": "https://services.swpc.noaa.gov/json/solar_flare/latest.json",
    "kp_index": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "geo_forecast": "https://services.swpc.noaa.gov/products/noaa-scales.json",
    "solar_wind_mag": "https://services.swpc.noaa.gov/products/solar-wind/mag-2-hour.json",
    "xray_flux": "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json",
}


def fetch_noaa_data() -> dict:
    """Fetch all NOAA SWPC endpoints and return a consolidated dict."""
    data = {}
    headers = {"User-Agent": "NotDoomsday/1.0 (solar-flare-monitor)"}

    for key, url in NOAA_SWPC_ENDPOINTS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            raw = resp.json()

            if isinstance(raw, list):
                raw = raw[-20:]

            data[key] = raw
            print(f"  ✓ {key}: {len(raw) if isinstance(raw, list) else 'obj'} records")
        except Exception as e:
            data[key] = f"FETCH_ERROR: {e}"
            print(f"  ✗ {key}: {e}")

    return data


# ──────────────────────────────────────────────────────────────
# 3. Build LangChain pipeline with Groq
# ──────────────────────────────────────────────────────────────
def build_chain():
    """Create a LangChain chain: Prompt → Groq LLM → JSON parser."""

    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        api_key=os.environ.get("GROQ_API_KEY"),
    )

    parser = JsonOutputParser(pydantic_object=SolarFlareReport)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a space-weather analyst for the !(Not)Doomsday early-warning system.
Your job is to evaluate real-time NOAA SWPC data and determine whether
solar-flare activity is likely to cause radio/GPS/power-grid outages.

ANALYSIS GUIDELINES:
- X-class flares (≥X1.0) with Kp ≥ 7  → High risk, outages = "Yes", accuracy 80-95
- M-class flares (≥M5.0) with Kp ≥ 5  → Moderate risk, outages = "Yes", accuracy 60-80
- M-class flares (<M5.0) with Kp < 5   → Low risk, outages = "No", accuracy 70-85
- C-class or below with Kp < 4         → Minimal risk, outages = "No", accuracy 85-95
- If data is missing or errored, lower accuracy accordingly.

{format_instructions}"""
        ),
        (
            "human",
            """Analyze the following real-time NOAA SWPC solar data
(fetched at {timestamp}) and produce your outage assessment.

--- SOLAR FLARE EVENTS (last 7 days) ---
{solar_flares}

--- PLANETARY K-INDEX ---
{kp_index}

--- GEOMAGNETIC FORECAST (NOAA Scales) ---
{geo_forecast}

--- SOLAR WIND MAGNETIC FIELD (2-hour) ---
{solar_wind_mag}

--- X-RAY FLARE ACTIVITY (7-day) ---
{xray_flux}
"""
        ),
    ])

    chain = prompt | llm | parser
    return chain


# ──────────────────────────────────────────────────────────────
# 4. Main execution
# ──────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  !(Not)Doomsday — Solar Flare Monitor")
    print("=" * 60)

    if not os.environ.get("GROQ_API_KEY"):
        print("\n⚠  GROQ_API_KEY not set.")
        print("   Get a free key at: https://console.groq.com/keys")
        print('   Then run:  export GROQ_API_KEY="gsk_..."')
        return

    # --- Step 1: Fetch real-time data ---
    print("\n[1/3] Fetching real-time data from NOAA SWPC...")
    noaa_data = fetch_noaa_data()

    # --- Step 2: Build chain ---
    print("\n[2/3] Sending to Groq (llama-3.3-70b-versatile) via LangChain...")
    chain = build_chain()

    parser = JsonOutputParser(pydantic_object=SolarFlareReport)

    result = chain.invoke({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "solar_flares": json.dumps(noaa_data.get("solar_flares", []), indent=2)[:3000],
        "kp_index": json.dumps(noaa_data.get("kp_index", []), indent=2)[:2000],
        "geo_forecast": json.dumps(noaa_data.get("geo_forecast", []), indent=2)[:2000],
        "solar_wind_mag": json.dumps(noaa_data.get("solar_wind_mag", []), indent=2)[:2000],
        "xray_flux": json.dumps(noaa_data.get("xray_flux", []), indent=2)[:3000],
        "format_instructions": parser.get_format_instructions(),
    })

    # --- Step 3: Output ---
    print("\n[3/3] Analysis complete.\n")
    print("─" * 40)
    print("  SOLAR FLARE OUTAGE REPORT")
    print("─" * 40)
    print(json.dumps(result, indent=2))
    print("─" * 40)

    # --- Save to shared context ---
    from context_manager import save_to_context
    save_to_context("solar_flare", {
        "type": "solar_flare",
        "location": "Global",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outages_expected": result.get("outages"),
        "description": result.get("description"),
        "accuracy": result.get("accuracy"),
        "risk_level": "HIGH" if result.get("outages") == "Yes" else "LOW",
    })

    return result


if __name__ == "__main__":
    main()