"""
flood_predictor.py
==================
Takes preprocessed flood data and sends it to Groq's LLM
for flood risk assessment and prediction.

Requires: GROQ_API_KEY in .env file.

Usage:
    from flood_predictor import predict_flood_risk_full

    result = predict_flood_risk_full(lat=29.76, lng=-95.36, location_name="Houston, TX")
    print(result["prediction"])
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

SYSTEM_PROMPT = """You are a hydrology and flood risk assessment AI. You analyze river discharge data and provide structured flood risk assessments.

Given river discharge data for a region, you MUST respond ONLY in this exact JSON format, no extra text:
{
  "risk_level": "LOW" | "MODERATE" | "HIGH" | "CRITICAL",
  "risk_score": <1-10 integer>,
  "confidence": <0.0-1.0 float>,
  "summary": "<1-2 sentence plain English summary of flood risk>",
  "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "pattern_detected": "<description of any notable hydrological pattern>",
  "forecast_outlook": "<1-2 sentence outlook for the coming days/weeks>",
  "recommendation": "<1-2 sentence actionable recommendation>"
}

Assessment criteria:
- LOW (1-3): Normal discharge levels, stable or falling trend, no spikes
- MODERATE (4-5): Slightly elevated discharge, minor rising trend, or small spikes
- HIGH (6-8): Significantly elevated discharge, fast rising trend, forecast projections exceeding historical peaks
- CRITICAL (9-10): Extreme discharge levels, rapid acceleration, forecast max far exceeding historical peaks, multiple risk days

Consider: current discharge vs historical baseline, 7-day trend direction and speed, forecast max projections, spike frequency, and risk days when making your assessment."""


def predict_flood_risk(processed: dict, model: str = DEFAULT_MODEL) -> dict:
    """
    Send preprocessed flood data to Groq LLM for risk assessment.

    Args:
        processed: Output from flood_preprocessor.preprocess().
        model:     Groq model to use.

    Returns:
        Dict with risk_level, risk_score, confidence, summary,
        key_factors, pattern_detected, forecast_outlook, recommendation,
        raw_response, model, error.
    """
    api_key = os.environ.get("GROQ_API_KEY_4")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Get your free key at https://console.groq.com/keys\n"
            "Then add to .env: GROQ_API_KEY=your-key-here"
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


def predict_flood_risk_full(
    lat: float,
    lng: float,
    location_name: str = "Unknown",
    past_days: int = 30,
    forecast_days: int = 30,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Convenience function: fetch → preprocess → predict in one call.

    Args:
        lat, lng:       Location coordinates.
        location_name:  Human-readable name.
        past_days:      Days of historical data.
        forecast_days:  Days of forecast data.
        model:          Groq model to use.

    Returns:
        Dict with prediction results + summary data.
    """
    from flood_api import get_flood_data
    from flood_preprocessor import preprocess

    raw = get_flood_data(lat=lat, lng=lng, past_days=past_days, forecast_days=forecast_days)
    processed = preprocess(raw, location_name=location_name)
    prediction = predict_flood_risk(processed, model=model)

    return {
        "location": location_name,
        "days_analyzed": processed["summary"].get("total_days", 0),
        "prediction": prediction,
        "data_summary": processed["summary"],
    }


# --------------- Self Test ---------------
if __name__ == "__main__":
    print("=== Flood Risk Predictor — Self Test ===\n")

    result = predict_flood_risk_full(
        lat=29.76,
        lng=-95.36,
        location_name="Houston, TX",
    )

    print(f"Location: {result['location']}")
    print(f"Days analyzed: {result['days_analyzed']}")
    print()

    p = result["prediction"]
    if p.get("error"):
        print(f"Error: {p['error']}")
        if p.get("raw_response"):
            print(f"Raw response: {p['raw_response']}")
    else:
        print(f"Risk Level  : {p['risk_level']}")
        print(f"Risk Score  : {p['risk_score']}/10")
        print(f"Confidence  : {p['confidence']}")
        print(f"Summary     : {p['summary']}")
        print(f"Pattern     : {p['pattern_detected']}")
        print(f"Outlook     : {p['forecast_outlook']}")
        print(f"Recommend   : {p['recommendation']}")
        print(f"Key Factors :")
        for f in p.get("key_factors", []):
            print(f"  - {f}")
        print(f"\nModel used: {p['model']}")

    # Save to shared context file
    from context_manager import save_to_context
    save_to_context("flood", {
        "location": result["location"],
        "days_analyzed": result["days_analyzed"],
        "prediction": result["prediction"],
        "data_summary": result["data_summary"],
    })

    print("\n=== Test complete ===")