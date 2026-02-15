"""
validate_apocalypse.py
======================
Takes the apocalypse prediction JSON and validates it against
176K historical records in ChromaDB via the cascade engine.

Usage:
    python validate_apocalypse.py
    python validate_apocalypse.py --file path/to/apocalypse.json
"""

import os
import sys
import json
from dotenv import load_dotenv

from cascade_chain import analyze_threats
from retriever import query_threats, get_collection

load_dotenv()

# ── The apocalypse prediction to validate ──
APOCALYPSE_PREDICTION = {
    "location": "Boston, Massachusetts",
    "overall_threat_level": "CRITICAL",
    "ranked_calamities": [
        {
            "rank": 1,
            "name": "flood",
            "type": "flood",
            "risk_level": "CRITICAL",
            "risk_score": 10,
            "confidence": 0.95,
            "summary": "The region is at extreme risk of flooding due to significantly elevated forecast projections and multiple risk days ahead.",
            "key_fields_used": {
                "key_factors": [
                    "Elevated forecast projections",
                    "Multiple risk days",
                    "Rapid acceleration in discharge"
                ]
            }
        },
        {
            "rank": 2,
            "name": "earthquake",
            "type": "earthquake",
            "risk_level": "LOW",
            "risk_score": 1,
            "confidence": 0.9,
            "summary": "The region is experiencing normal background seismicity with a single minor event, indicating a low risk of significant earthquake activity.",
            "key_fields_used": {
                "key_factors": [
                    "Single minor event",
                    "Decelerating frequency trend",
                    "No significant clustering"
                ]
            }
        },
        {
            "rank": 3,
            "name": "pandemic",
            "type": "pandemic",
            "risk_level": "LOW",
            "risk_score": 0,
            "confidence": 0.7,
            "summary": "There is no immediate pandemic threat in the region, but there are rising concerns about diseases such as Nipah virus and measles.",
            "key_fields_used": {
                "key_factors": ["Rising concerns about diseases"]
            }
        },
        {
            "rank": 4,
            "name": "solar_flare",
            "type": "solar_flare",
            "risk_level": "LOW",
            "risk_score": 0,
            "confidence": 0.7,
            "summary": "Recent solar flare activity has been low to moderate, with no immediate threat to the region.",
            "key_fields_used": {
                "key_factors": ["Low to moderate solar flare activity"]
            }
        },
        {
            "rank": 5,
            "name": "volcano",
            "type": "volcano",
            "risk_level": "LOW",
            "risk_score": 0,
            "confidence": 0.7,
            "summary": "There are no nearby volcanoes, indicating a low risk of volcanic activity in the region.",
            "key_fields_used": {
                "key_factors": ["No nearby volcanoes"]
            }
        }
    ],
    "apocalypse_timeline": [
        {
            "phase": 1,
            "title": "Initial Flood Event",
            "description": "A severe flood event occurs in Boston, Massachusetts, causing widespread damage and disruption."
        },
        {
            "phase": 2,
            "title": "Secondary Disasters",
            "description": "The initial flood event triggers secondary disasters such as earthquakes and pandemics."
        },
        {
            "phase": 3,
            "title": "Long-term Consequences",
            "description": "Displacement of people, disruption of healthcare services, destruction of infrastructure."
        }
    ]
}


def convert_to_threats(prediction: dict) -> list[dict]:
    """Convert apocalypse prediction into standardized threat format."""
    threats = []
    for calamity in prediction.get("ranked_calamities", []):
        threats.append({
            "threat_type": calamity["type"],
            "severity": calamity["risk_level"].lower(),
            "location": {"name": prediction["location"]},
            "timestamp": "2026-02-15T00:00:00Z",
            "data": {
                "risk_score": calamity["risk_score"],
                "confidence": calamity["confidence"],
                "key_factors": calamity.get("key_fields_used", {}).get("key_factors", []),
            },
            "summary": calamity["summary"],
        })
    return threats


def validate_timeline_claims(prediction: dict) -> dict:
    """
    Specifically check the apocalypse timeline claims against historical data.
    The big question: does the timeline's cascade logic hold up?
    """
    col = get_collection()
    validation = []

    # Claim 1: Flood triggers earthquakes
    print("\n[VALIDATE] Checking: Can floods trigger earthquakes?")
    flood_eq_docs = query_threats("flood triggering earthquake seismic activity water", n=10)
    flood_eq_relevant = [d for d in flood_eq_docs if "earthquake" in d["content"].lower() or "seismic" in d["content"].lower()]
    validation.append({
        "claim": "Flood triggers earthquakes (Phase 2)",
        "historical_support": len(flood_eq_relevant),
        "total_searched": len(flood_eq_docs),
        "verdict": "SUPPORTED" if len(flood_eq_relevant) >= 3 else "WEAK" if len(flood_eq_relevant) >= 1 else "UNSUPPORTED",
        "evidence_samples": [d["content"][:150] for d in flood_eq_relevant[:3]],
    })

    # Claim 2: Flood triggers pandemic via displacement
    print("[VALIDATE] Checking: Can floods trigger pandemics via displacement?")
    flood_pan_docs = query_threats("flood displacement disease outbreak contaminated water health", n=10)
    flood_pan_relevant = [d for d in flood_pan_docs if any(kw in d["content"].lower() for kw in ["disease", "outbreak", "cholera", "health", "pandemic", "contamina"])]
    validation.append({
        "claim": "Flood triggers pandemic via displacement/healthcare disruption (Phase 2)",
        "historical_support": len(flood_pan_relevant),
        "total_searched": len(flood_pan_docs),
        "verdict": "SUPPORTED" if len(flood_pan_relevant) >= 3 else "WEAK" if len(flood_pan_relevant) >= 1 else "UNSUPPORTED",
        "evidence_samples": [d["content"][:150] for d in flood_pan_relevant[:3]],
    })

    # Claim 3: Flood risk is CRITICAL (score 10)
    print("[VALIDATE] Checking: Historical flood severity patterns in Boston/NE region")
    flood_hist_docs = query_threats("severe flooding Boston Massachusetts northeast discharge record", n=10)
    validation.append({
        "claim": "Flood risk CRITICAL (score 10/10) in Boston",
        "historical_support": len(flood_hist_docs),
        "total_searched": 10,
        "verdict": "CHECK_DATA",
        "evidence_samples": [d["content"][:150] for d in flood_hist_docs[:3]],
        "note": "Verify against current discharge data — score 10 implies historic levels",
    })

    # Claim 4: Earthquake risk is LOW
    print("[VALIDATE] Checking: Historical earthquake activity near Boston")
    eq_boston_docs = query_threats("earthquake Boston Massachusetts New England seismic", n=10)
    eq_significant = [d for d in eq_boston_docs if d.get("metadata", {}).get("magnitude", 0) > 3.0]
    validation.append({
        "claim": "Earthquake risk LOW in Boston (normal background seismicity)",
        "historical_support": len(eq_boston_docs) - len(eq_significant),
        "significant_events_found": len(eq_significant),
        "verdict": "SUPPORTED" if len(eq_significant) <= 2 else "QUESTIONABLE",
        "evidence_samples": [d["content"][:150] for d in eq_boston_docs[:3]],
    })

    # Claim 5: No immediate pandemic threat
    print("[VALIDATE] Checking: Current pandemic signals in historical context")
    pan_docs = query_threats("Nipah measles outbreak rising concern disease surveillance", n=10)
    pan_active = [d for d in pan_docs if any(kw in d["content"].lower() for kw in ["nipah", "measles", "rising", "outbreak", "surge"])]
    validation.append({
        "claim": "No immediate pandemic threat (LOW, score 0)",
        "historical_support": len(pan_docs) - len(pan_active),
        "active_signals_found": len(pan_active),
        "verdict": "SUPPORTED" if len(pan_active) <= 1 else "QUESTIONABLE — rising signals detected",
        "evidence_samples": [d["content"][:150] for d in pan_docs[:3]],
    })

    return validation


def main():
    # Load from file if provided
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            prediction = json.load(f)
    else:
        prediction = APOCALYPSE_PREDICTION

    location = prediction.get("location", "Boston, Massachusetts")

    print("=" * 70)
    print("  APOCALYPSE PREDICTION VALIDATOR")
    print(f"  Location: {location}")
    print(f"  Overall Threat Level: {prediction.get('overall_threat_level', 'N/A')}")
    print("=" * 70)

    # ── Part 1: Validate individual timeline claims ──
    print("\n" + "─" * 70)
    print("  PART 1: HISTORICAL VALIDATION OF TIMELINE CLAIMS")
    print("─" * 70)

    timeline_validation = validate_timeline_claims(prediction)

    for v in timeline_validation:
        emoji = "✅" if "SUPPORTED" in v["verdict"] else "⚠️" if "WEAK" in v["verdict"] or "QUESTIONABLE" in v["verdict"] else "❌" if "UNSUPPORTED" in v["verdict"] else "🔍"
        print(f"\n{emoji} {v['claim']}")
        print(f"   Verdict: {v['verdict']}")
        print(f"   Historical evidence: {v.get('historical_support', 'N/A')} records")
        if v.get("evidence_samples"):
            for sample in v["evidence_samples"][:2]:
                print(f"   → {sample}...")

    # ── Part 2: Full cascade analysis via LLM ──
    print("\n" + "─" * 70)
    print("  PART 2: LLM CASCADE ANALYSIS (with priorities)")
    print("─" * 70)

    threats = convert_to_threats(prediction)
    print(f"\nSending {len(threats)} threats to cascade engine...")

    result = analyze_threats(threats, location=location, n_context=8)

    if "error" in result:
        print(f"\n❌ Error: {result['error']}")
        if "raw_response" in result:
            print(f"Raw response:\n{result['raw_response'][:500]}")
        return

    # Print key results
    print(f"\n{'='*70}")
    print(f"  CASCADE ENGINE RESULT")
    print(f"{'='*70}")
    print(f"  Overall Risk: {result.get('overall_risk_level', 'N/A')} ({result.get('overall_risk_score', 'N/A')}/10)")
    print(f"  Briefing: {result.get('situation_briefing', 'N/A')}")

    # Cascade predictions
    cascades = result.get("cascade_predictions", [])
    if cascades:
        print(f"\n  CASCADE CHAINS ({len(cascades)} predicted):")
        for c in cascades:
            print(f"\n  Chain {c.get('chain_id', '?')}: {c.get('trigger', 'N/A')}")
            for step in c.get("cascade_steps", []):
                print(f"    Step {step.get('step')}: {step.get('event')} [{step.get('domain')}]")
                print(f"           Probability: {step.get('probability')} | Timeframe: {step.get('timeframe')}")
                print(f"           Mechanism: {step.get('mechanism')}")
            print(f"    Historical precedent: {c.get('historical_precedent', 'None cited')}")
            print(f"    Ultimate impact: {c.get('ultimate_impact', 'N/A')}")

    # Priority actions
    actions = result.get("recommended_actions", [])
    if actions:
        print(f"\n  PRIORITY ACTIONS ({len(actions)}):")
        for a in actions:
            urgency_emoji = "🔴" if a.get("urgency") == "IMMEDIATE" else "🟡" if a.get("urgency") == "SHORT_TERM" else "🟢"
            print(f"    {urgency_emoji} P{a.get('priority', '?')}: {a.get('action')}")
            print(f"       Responsible: {a.get('responsible_entity', 'N/A')}")
            print(f"       Rationale: {a.get('rationale', 'N/A')}")

    # Monitoring alerts
    alerts = result.get("monitoring_alerts", [])
    if alerts:
        print(f"\n  MONITORING ALERTS ({len(alerts)}):")
        for alert in alerts:
            print(f"    📡 {alert.get('indicator')}")
            print(f"       Threshold: {alert.get('threshold')}")
            print(f"       Source: {alert.get('data_source')}")

    # Confidence notes
    if result.get("confidence_notes"):
        print(f"\n  ⚠️  CAVEATS: {result['confidence_notes']}")

    # Save full result
    out_path = "../Data/validation_result.json"
    with open(out_path, "w") as f:
        json.dump({
            "input_prediction": prediction,
            "timeline_validation": timeline_validation,
            "cascade_analysis": result,
        }, f, indent=2)
    print(f"\n  Full result saved to {out_path}")


if __name__ == "__main__":
    main()
