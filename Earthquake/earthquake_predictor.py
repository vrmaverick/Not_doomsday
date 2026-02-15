"""
earthquake_predictor.py
=======================
Takes preprocessed earthquake data and sends it to Groq's LLM
for seismic risk assessment and prediction.

Requires: GROQ_API_KEY environment variable.
Get your free key at: https://console.groq.com/keys

Usage:
    from earthquake_api import get_earthquakes
    from earthquake_preprocessor import preprocess
    from earthquake_predictor import predict_risk

    raw = get_earthquakes(lat=37.77, lng=-122.42, radius_km=500)
    processed = preprocess(raw, location_name="San Francisco, CA")
    prediction = predict_risk(processed)
    print(prediction)
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a seismology risk assessment AI. You analyze earthquake activity data and provide structured risk assessments.

Given seismic activity data for a region, you MUST respond ONLY in this exact JSON format, no extra text:
{
  "risk_level": "LOW" | "MODERATE" | "HIGH" | "CRITICAL",
  "risk_score": <1-10 integer>,
  "confidence": <0.0-1.0 float>,
  "summary": "<1-2 sentence plain English summary of the risk>",
  "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "pattern_detected": "<description of any notable seismic pattern>",
  "recommendation": "<1-2 sentence actionable recommendation>"
}

Assessment criteria:
- LOW (1-3): Normal background seismicity, no concerning patterns
- MODERATE (4-5): Slightly elevated activity, minor clustering or frequency uptick
- HIGH (6-8): Significant swarm activity, accelerating frequency, or moderate-large events
- CRITICAL (9-10): Major foreshock patterns, rapid acceleration, large magnitude events

Consider: frequency trends, magnitude distribution, depth profiles, geographic clustering, and temporal acceleration when making your assessment."""


def predict_risk(processed: dict, model: str = DEFAULT_MODEL) -> dict:
    """
    Send preprocessed earthquake data to Groq LLM for risk assessment.

    Args:
        processed: Output from earthquake_preprocessor.preprocess().
        model:     Groq model to use (default: llama-3.3-70b-versatile).

    Returns:
        Dict with keys:
            risk_level       (str)   : LOW / MODERATE / HIGH / CRITICAL
            risk_score       (int)   : 1-10
            confidence       (float) : 0.0-1.0
            summary          (str)   : Plain English risk summary
            key_factors      (list)  : Contributing factors
            pattern_detected (str)   : Notable seismic patterns
            recommendation   (str)   : Actionable recommendation
            raw_response     (str)   : Raw LLM output (for debugging)
            model            (str)   : Model used
            error            (str|None) : Error message if something failed

    Raises:
        ValueError: If GROQ_API_KEY is not set.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Get your free key at https://console.groq.com/keys\n"
            "Then run: export GROQ_API_KEY='your-key-here'"
        )

    prompt = processed.get("llm_prompt", "")
    if not prompt:
        return {"error": "No LLM prompt found in processed data.", "risk_level": "UNKNOWN"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": f"Groq API request failed: {e}", "risk_level": "UNKNOWN"}

    raw_text = data["choices"][0]["message"]["content"].strip()

    # Parse JSON from LLM response
    try:
        cleaned = raw_text
        if "```" in cleaned:
            cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
            if not cleaned:
                cleaned = raw_text.split("```")[-2].strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        return {
            "error": "Failed to parse LLM response as JSON",
            "risk_level": "UNKNOWN",
            "raw_response": raw_text,
            "model": model,
        }

    result["raw_response"] = raw_text
    result["model"] = model
    result["error"] = None
    return result


def predict_risk_full(
    lat: float,
    lng: float,
    location_name: str = "Unknown",
    radius_km: int = 250,
    min_mag: float = 2.5,
    days_back: int = 30,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Convenience function: fetch → preprocess → predict in one call.

    Args:
        lat, lng:       Location coordinates.
        location_name:  Human-readable name.
        radius_km:      Search radius in km.
        min_mag:        Minimum magnitude.
        days_back:      Days of history.
        model:          Groq model to use.

    Returns:
        Dict with prediction results + summary data.
    """
    from earthquake_api import get_earthquakes
    from earthquake_preprocessor import preprocess

    raw = get_earthquakes(lat=lat, lng=lng, radius_km=radius_km, min_mag=min_mag, days_back=days_back)
    processed = preprocess(raw, location_name=location_name)
    prediction = predict_risk(processed, model=model)

    return {
        "location": location_name,
        "events_analyzed": processed["summary"].get("total_events", 0),
        "prediction": prediction,
        "data_summary": processed["summary"],
    }


# --------------- Self Test ---------------
if __name__ == "__main__":
    print("=== Earthquake Risk Predictor — Self Test ===\n")

    result = predict_risk_full(
        lat=37.77,
        lng=-122.42,
        location_name="San Francisco, CA",
        radius_km=500,
        min_mag=3.0,
    )

    print(f"Location: {result['location']}")
    print(f"Events analyzed: {result['events_analyzed']}")
    print()

    p = result["prediction"]
    if p.get("error"):
        print(f"Error: {p['error']}")
        if p.get("raw_response"):
            print(f"Raw response: {p['raw_response']}")
    else:
        print(f"Risk Level : {p['risk_level']}")
        print(f"Risk Score : {p['risk_score']}/10")
        print(f"Confidence : {p['confidence']}")
        print(f"Summary    : {p['summary']}")
        print(f"Pattern    : {p['pattern_detected']}")
        print(f"Recommend  : {p['recommendation']}")
        print(f"Key Factors:")
        for f in p.get("key_factors", []):
            print(f"  - {f}")
        print(f"\nModel used: {p['model']}")

    # Save to shared context file
    from context_manager import save_to_context
    save_to_context("earthquake", {
        "location": result["location"],
        "events_analyzed": result["events_analyzed"],
        "prediction": result["prediction"],
        "data_summary": result["data_summary"],
    })

    print("\n=== Test complete ===")