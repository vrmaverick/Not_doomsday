"""
context_manager.py
==================
Shared utility for all calamity modules to save LLM predictions
into a unified apocalypse_context.json file.

Place this file in the project root (Not_doomsday/).
Any module can import and use it.

Usage:
    from context_manager import save_threat

    # After getting prediction from any module's LLM call:
    save_threat(
        threat_type="earthquake",            # e.g. earthquake, flood, wildfire, pandemic
        location="San Francisco, CA",
        prediction={                         # the parsed LLM response dict
            "risk_level": "MODERATE",
            "risk_score": 4,
            "confidence": 0.7,
            "summary": "Slightly elevated seismic activity...",
            "key_factors": ["stable trend", "moderate magnitudes"],
            "pattern_detected": "Minor cluster near San Ramon",
            "recommendation": "Continue monitoring...",
            # any extra fields your module returns — they'll all be saved
        },
        extra={                              # optional: any module-specific metadata
            "events_analyzed": 39,
            "data_summary": { ... },
        }
    )
"""

import os
import json
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(PROJECT_ROOT, "Data", "apocalypse_context.json")


def save_threat(
    threat_type: str,
    location: str,
    prediction: dict,
    extra: dict = None,
) -> None:
    """
    Save a threat prediction to apocalypse_context.json.

    Deduplicates by (threat_type, location) — running the same
    combination again replaces the old entry.

    Args:
        threat_type: Kind of threat (e.g. "earthquake", "flood", "wildfire",
                     "pandemic", "cyclone", "drought", "volcano").
        location:    Human-readable location name.
        prediction:  The parsed LLM prediction dict. Expected keys:
                       risk_level, risk_score, confidence, summary,
                       key_factors, recommendation
                     Any extra keys your module adds will be kept.
        extra:       Optional dict of module-specific metadata
                     (e.g. events_analyzed, data_summary, days_analyzed).
    """
    with open(CONTEXT_FILE, "r") as f:
        context = json.load(f)

    # Remove old entry with same type + location
    context["threats"] = [
        t for t in context["threats"]
        if not (t["type"] == threat_type and t["location"] == location)
    ]

    # Build entry — standard fields first, then everything else from prediction
    entry = {
        "type": threat_type,
        "location": location,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "risk_level": prediction.get("risk_level"),
        "risk_score": prediction.get("risk_score"),
        "confidence": prediction.get("confidence"),
        "summary": prediction.get("summary"),
        "key_factors": prediction.get("key_factors"),
        "pattern_detected": prediction.get("pattern_detected"),
        "recommendation": prediction.get("recommendation"),
    }

    # Add any extra prediction fields (forecast_outlook, etc.)
    skip = {"risk_level", "risk_score", "confidence", "summary",
            "key_factors", "pattern_detected", "recommendation",
            "raw_response", "model", "error"}
    for k, v in prediction.items():
        if k not in skip:
            entry[k] = v

    # Add module-specific metadata
    if extra:
        entry["metadata"] = extra

    context["threats"].append(entry)
    context["generated_at"] = datetime.now(timezone.utc).isoformat()

    with open(CONTEXT_FILE, "w") as f:
        json.dump(context, f, indent=2)

    print(f"[context_manager] Saved {threat_type} @ {location} → {CONTEXT_FILE}")


def get_all_threats() -> list:
    """Read and return all current threats from the context file."""
    with open(CONTEXT_FILE, "r") as f:
        context = json.load(f)
    return context.get("threats", [])


def get_threats_by_type(threat_type: str) -> list:
    """Get all threats of a specific type."""
    return [t for t in get_all_threats() if t["type"] == threat_type]


def clear_threats() -> None:
    """Reset the context file to empty."""
    context = {"generated_at": datetime.now(timezone.utc).isoformat(), "threats": []}
    with open(CONTEXT_FILE, "w") as f:
        json.dump(context, f, indent=2)
    print(f"[context_manager] Cleared all threats from {CONTEXT_FILE}")