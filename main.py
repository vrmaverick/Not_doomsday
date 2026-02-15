"""
main.py
=======
Master pipeline for Not_Doomsday.

Flow:
    1. receive() takes a city/location input
    2. Resolves coordinates via latlong/convert.py
    3. Runs all threat modules via run_all_modules.run_all()
    4. Reads completed Context_Json.json
    5. Sends to Groq LLM for apocalypse scenario analysis
    6. Passes LLM response to validator

Usage:
    python3 main.py "Houston"
    python3 main.py "San Francisco"
    python3 main.py "Boston"
"""

import os
import sys
import json
from prompt import *

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "latlong"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from groq import Groq
from run_all_modules import run_all

# CONTEXT_FILE = os.path.join(PROJECT_ROOT, "Data", "Context_Json.json")
CONTEXT_FILE = os.path.join(PROJECT_ROOT, "Data", "temp.json")

client = Groq(api_key=os.environ.get("GROQ_API_KEY_5"))

SYSTEM_PROMPT = get_system_prompt_main()

def analyze_context() -> dict:
    """Read Context_Json.json and send to Groq for apocalypse analysis."""
    with open(CONTEXT_FILE, "r") as f:
        context_data = json.load(f)

    user_message = f"""
Here is context_json for ONE location:

{json.dumps(context_data, indent=2)}

Prioritize and build the apocalypse scenario as instructed.
"""

    print("\n🤖 Sending to Groq for apocalypse scenario analysis...")

    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    raw_text = resp.choices[0].message.content.strip()

    # Parse JSON — handle markdown wrapping
    try:
        cleaned = raw_text
        if "```" in cleaned:
            cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
            if not cleaned:
                cleaned = raw_text.split("```")[-2].strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        print(f"  ⚠️  Failed to parse LLM response, returning raw text")
        result = {"raw_response": raw_text, "error": "Failed to parse JSON"}

    # Save analysis result
    analysis_path = os.path.join(PROJECT_ROOT, "Data", "apocalypse_analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"💾 Analysis saved → {analysis_path}")

    return result


def validate(analysis: dict) -> dict:
    """
    Dummy validator — takes the LLM apocalypse analysis and validates it.
    Replace this with real validation logic (e.g. ChromaDB lookup, historical comparison).

    Args:
        analysis: The parsed LLM response dict.

    Returns:
        Validation result dict.
    """
    print("\n🔍 Running validation...")

    validation = {
        "status": "passed",
        "checks": [],
    }

    # Check 1: Has required fields
    required = ["location", "overall_threat_level", "ranked_calamities", "apocalypse_timeline"]
    for field in required:
        present = field in analysis
        validation["checks"].append({
            "check": f"has_{field}",
            "passed": present,
        })
        if not present:
            validation["status"] = "failed"

    # Check 2: Threat level is valid
    valid_levels = {"LOW", "MODERATE", "HIGH", "CRITICAL"}
    level = analysis.get("overall_threat_level", "")
    level_valid = level in valid_levels
    validation["checks"].append({
        "check": "valid_threat_level",
        "passed": level_valid,
        "value": level,
    })
    if not level_valid:
        validation["status"] = "failed"

    # Check 3: Has at least one ranked calamity
    ranked = analysis.get("ranked_calamities", [])
    has_ranked = len(ranked) > 0
    validation["checks"].append({
        "check": "has_ranked_calamities",
        "passed": has_ranked,
        "count": len(ranked),
    })

    # Check 4: Timeline has phases
    timeline = analysis.get("apocalypse_timeline", [])
    has_timeline = len(timeline) >= 2
    validation["checks"].append({
        "check": "has_timeline_phases",
        "passed": has_timeline,
        "count": len(timeline),
    })

    # Save validation result
    val_path = os.path.join(PROJECT_ROOT, "Data", "validation_result.json")
    with open(val_path, "w") as f:
        json.dump(validation, f, indent=2)
    print(f"💾 Validation saved → {val_path}")

    if validation["status"] == "passed":
        print("  ✅ Validation passed")
    else:
        print("  ❌ Validation failed")
        for check in validation["checks"]:
            if not check["passed"]:
                print(f"     — {check['check']}")

    return validation


def receive(city: str):
    """
    Main entry point. Takes a city name, runs everything.

    Flow:
        city → resolve coords → run all modules → analyze context → validate
    """
    print("=" * 60)
    print(f"  🚨 Not_Doomsday — Full Pipeline")
    print(f"  📍 Input: {city}")
    print("=" * 60)

    # Step 1: Resolve coordinates
    print(f"\n🔍 Resolving '{city}'...")
    try:
        from latlong.convert import get_city_lat_lon, get_state_country

        city_name, state, country = get_state_country(city)
        if not city_name:
            print(f"  ❌ Could not resolve '{city}'")
            return
        lat, lng = get_city_lat_lon(city_name, state, country or "US")
        if lat is None:
            print(f"  ❌ Could not get coordinates for '{city_name}'")
            return
        name = f"{city_name}, {state}" if state else city_name
        print(f"  📍 {name} ({lat}, {lng})")

    except Exception as e:
        print(f"  ❌ Geocoding failed: {e}")
        print("  Falling back — please provide lat/lng manually")
        return

    # Step 2: Run all threat modules
    print("\n" + "=" * 60)
    print("  ⚡ Running all threat modules...")
    print("=" * 60)
    run_all(lat=lat, lng=lng, name=name)

    # Step 3: Analyze context with LLM
    print("\n" + "=" * 60)
    print("  🧠 Apocalypse Scenario Analysis")
    print("=" * 60)
    analysis = analyze_context()

    # Step 4: Validate
    validation = validate(analysis)

    # Final summary
    print("\n" + "=" * 60)
    print("  📋 FINAL RESULT")
    print("=" * 60)
    if "error" not in analysis:
        print(f"  📍 Location: {analysis.get('location', 'Unknown')}")
        print(f"  ⚠️  Threat Level: {analysis.get('overall_threat_level', 'Unknown')}")
        print(f"  📝 {analysis.get('overall_summary', '')}")

        ranked = analysis.get("ranked_calamities", [])
        if ranked:
            print(f"\n  Threats (ranked):")
            for r in ranked:
                print(f"    #{r['rank']} {r.get('name', '')} — {r.get('risk_level', '')} (score: {r.get('risk_score', '?')})")

        timeline = analysis.get("apocalypse_timeline", [])
        if timeline:
            print(f"\n  Scenario Timeline:")
            for phase in timeline:
                print(f"    Phase {phase['phase']}: {phase['title']}")
                print(f"      {phase['description'][:100]}...")

    print(f"\n  ✅ Validation: {validation['status']}")
    print("=" * 60)

    return analysis


if __name__ == "__main__":
    # if len(sys.argv) >= 2:
    #     city = " ".join(sys.argv[1:])
    # else:
    #     city = "Houston"
    # city = "Boston"
    # receive(city)

    analyze_context()