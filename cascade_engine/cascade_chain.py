"""
cascade_chain.py
================
The core cascade prediction engine for InnovAIte.
Ties together: ChromaDB retriever + cascade prompt + Groq LLM.

Usage:
    from cascade_chain import analyze_threats

    # Active threats from your lane predictors
    threats = [
        {
            "threat_type": "earthquake",
            "severity": "high",
            "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
            "timestamp": "2026-02-15T15:00:00Z",
            "data": {"magnitude": 4.2, "depth_km": 8.0},
            "summary": "M4.2 earthquake detected 30km SW of Boston"
        },
        {
            "threat_type": "pandemic",
            "severity": "medium",
            "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
            "timestamp": "2026-02-15T15:00:00Z",
            "data": {"disease": "influenza", "trend": "rising"},
            "summary": "Flu hospitalizations up 40% week-over-week in MA"
        }
    ]

    result = analyze_threats(threats, location="Boston, MA")
    print(result)

Requires:
    pip install langchain langchain-groq langchain-community chromadb sentence-transformers
    GROQ_API_KEY environment variable set
"""

import os
import json
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

# from retriever import multi_domain_query, query_threats
# from cascade_prompt import (
#     CASCADE_PROMPT,
#     JSON_SCHEMA,
#     format_active_threats,
#     format_retrieved_context,
# )

# from retriever import multi_domain_query, query_threats
from .retriever import multi_domain_query, query_threats
from .cascade_prompt import (
    CASCADE_PROMPT,
    JSON_SCHEMA,
    format_active_threats,
    format_retrieved_context,
)


load_dotenv()

# ──────────────────────────────────────────────────────────────
# LLM Setup — Groq (same model your team already uses)
# ──────────────────────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY_5", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def get_llm(temperature: float = 0.2):
    """
    Initialize the Groq LLM via LangChain.
    Low temperature for structured, consistent output.
    """
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        temperature=temperature,
        max_tokens=4096,
    )


# ──────────────────────────────────────────────────────────────
# Context retrieval — builds the historical context from ChromaDB
# ──────────────────────────────────────────────────────────────

def retrieve_context_for_threats(threats: list[dict], n_per_query: int = 5) -> list[dict]:
    """
    For each active threat, query ChromaDB for relevant historical context.
    Also does a cross-domain query to find cascade-relevant records.

    Strategy:
    1. Query each threat's summary against its OWN domain (specific)
    2. Query each threat's summary against ALL domains (cross-domain cascades)
    3. Query the combined threat picture for compound event patterns

    Deduplicates by document content.
    """
    all_docs = []
    seen_content = set()

    def add_unique(docs):
        for d in docs:
            content_key = d["content"][:200]  # first 200 chars as dedup key
            if content_key not in seen_content:
                seen_content.add(content_key)
                all_docs.append(d)

    for threat in threats:
        summary = threat.get("summary", "")
        domain = threat.get("threat_type", "")

        if not summary:
            continue

        # 1. Domain-specific retrieval
        domain_docs = query_threats(summary, n=n_per_query, domain=domain)
        add_unique(domain_docs)

        # 2. Cross-domain retrieval (finds cascade-relevant records)
        cross_docs = query_threats(summary, n=n_per_query, domain=None)
        add_unique(cross_docs)

    # 3. Compound query — combine all threat summaries
    if len(threats) > 1:
        combined_query = " AND ".join(
            t.get("summary", t.get("threat_type", "")) for t in threats
        )
        compound_docs = query_threats(combined_query, n=n_per_query)
        add_unique(compound_docs)

    return all_docs


# ──────────────────────────────────────────────────────────────
# The main analysis function
# ──────────────────────────────────────────────────────────────

def analyze_threats(
    threats: list[dict],
    location: str = "Boston, MA",
    n_context: int = 5,
    temperature: float = 0.2,
) -> dict:
    """
    THE CORE FUNCTION — call this from your Flask server.

    Takes active threats from all lanes, retrieves historical context,
    sends everything to the LLM, returns structured cascade prediction.

    Args:
        threats: List of standardized threat dicts from each lane
        location: Focus location for the analysis
        n_context: Number of historical docs to retrieve per query
        temperature: LLM temperature (lower = more consistent)

    Returns:
        Parsed JSON dict with cascade predictions, or error dict
    """
    # Step 1: Retrieve historical context from ChromaDB
    print(f"[CASCADE] Retrieving historical context for {len(threats)} active threats...")
    historical_docs = retrieve_context_for_threats(threats, n_per_query=n_context)
    print(f"[CASCADE] Retrieved {len(historical_docs)} unique historical records")

    # Step 2: Format inputs for the prompt
    threats_text = format_active_threats(threats)
    context_text = format_retrieved_context(historical_docs)

    # Step 3: Build and invoke the chain
    llm = get_llm(temperature=temperature)

    chain = CASCADE_PROMPT | llm | StrOutputParser()

    print(f"[CASCADE] Sending to {GROQ_MODEL}...")
    raw_response = chain.invoke({
        "json_schema": JSON_SCHEMA,
        "active_threats": threats_text,
        "historical_context": context_text,
        "location": location,
    })

    # Step 4: Parse the JSON response
    try:
        # Strip markdown fences if the LLM wraps in ```json
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]  # remove first line
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)
        result["_meta"] = {
            "model": GROQ_MODEL,
            "threats_analyzed": len(threats),
            "historical_docs_used": len(historical_docs),
            "location": location,
        }

        # Auto-save to JSON + TXT
        _save_result(result, location)

        return result

    except json.JSONDecodeError as e:
        return {
            "error": "Failed to parse LLM response as JSON",
            "parse_error": str(e),
            "raw_response": raw_response,
            "model": GROQ_MODEL,
        }


# def _save_result(result: dict, location: str):
#     """Save cascade result as both JSON and human-readable TXT."""
#     from datetime import datetime

#     # Determine output directory — cascade_engine/output/ or Data/
#     script_dir = os.path.dirname(os.path.abspath(__file__))
#     out_dir = os.path.join(script_dir, "..", "Data")
#     if not os.path.isdir(out_dir):
#         out_dir = os.path.join(script_dir, "output")
#     os.makedirs(out_dir, exist_ok=True)

#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     base_name = f"cascade_result_{timestamp}"

#     # ── JSON ──
#     json_path = os.path.join(out_dir, f"{base_name}.json")
#     with open(json_path, "w") as f:
#         json.dump(result, f, indent=2)

#     # ── TXT (human-readable report) ──
#     txt_path = os.path.join(out_dir, f"{base_name}.txt")
#     lines = []
#     lines.append("=" * 70)
#     lines.append("  InnovAIte CASCADE PREDICTION REPORT")
#     lines.append(f"  Location: {location}")
#     lines.append(f"  Generated: {datetime.now().isoformat()}")
#     lines.append(f"  Model: {result.get('_meta', {}).get('model', 'N/A')}")
#     lines.append("=" * 70)

#     lines.append(f"\nOVERALL RISK: {result.get('overall_risk_level', 'N/A')} ({result.get('overall_risk_score', '?')}/10)")
#     lines.append(f"\nBRIEFING:\n  {result.get('situation_briefing', 'N/A')}")

#     # Active threats
#     threats_list = result.get("active_threats_assessment", [])
#     if threats_list:
#         lines.append(f"\n{'─'*70}")
#         lines.append(f"ACTIVE THREATS ({len(threats_list)})")
#         lines.append(f"{'─'*70}")
#         for t in threats_list:
#             lines.append(f"  [{t.get('severity', '?').upper()}] {t.get('threat_type', '?')} — {t.get('summary', '')}")

#     # Cascade chains
#     cascades = result.get("cascade_predictions", [])
#     if cascades:
#         lines.append(f"\n{'─'*70}")
#         lines.append(f"CASCADE PREDICTIONS ({len(cascades)} chains)")
#         lines.append(f"{'─'*70}")
#         for c in cascades:
#             lines.append(f"\n  Chain {c.get('chain_id', '?')}: {c.get('trigger', '')}")
#             for step in c.get("cascade_steps", []):
#                 lines.append(f"    → Step {step.get('step')}: {step.get('event')}")
#                 lines.append(f"      Domain: {step.get('domain')} | Probability: {step.get('probability')} | Timeframe: {step.get('timeframe')}")
#                 lines.append(f"      Mechanism: {step.get('mechanism')}")
#             lines.append(f"    Historical precedent: {c.get('historical_precedent', 'None cited')}")
#             lines.append(f"    Ultimate impact: {c.get('ultimate_impact', 'N/A')}")
#             lines.append(f"    Affected: {c.get('affected_population', 'N/A')}")

#     # Priority actions
#     actions = result.get("recommended_actions", [])
#     if actions:
#         lines.append(f"\n{'─'*70}")
#         lines.append(f"RECOMMENDED ACTIONS ({len(actions)})")
#         lines.append(f"{'─'*70}")
#         for a in actions:
#             urgency = a.get('urgency', '?')
#             lines.append(f"  P{a.get('priority', '?')} [{urgency}]: {a.get('action')}")
#             lines.append(f"    Responsible: {a.get('responsible_entity', 'N/A')}")
#             lines.append(f"    Rationale: {a.get('rationale', 'N/A')}")

#     # Monitoring
#     alerts = result.get("monitoring_alerts", [])
#     if alerts:
#         lines.append(f"\n{'─'*70}")
#         lines.append(f"MONITORING ALERTS ({len(alerts)})")
#         lines.append(f"{'─'*70}")
#         for alert in alerts:
#             lines.append(f"  {alert.get('indicator')}")
#             lines.append(f"    Threshold: {alert.get('threshold')} | Source: {alert.get('data_source')}")

#     # Caveats
#     if result.get("confidence_notes"):
#         lines.append(f"\n{'─'*70}")
#         lines.append(f"CAVEATS:\n  {result['confidence_notes']}")

#     lines.append(f"\n{'='*70}")

#     with open(txt_path, "w") as f:
#         f.write("\n".join(lines))

#     print(f"[CASCADE] Saved → {json_path}")
#     print(f"[CASCADE] Saved → {txt_path}")


def _save_result(result: dict, location: str):
    """Save cascade result as both JSON and human-readable TXT."""
    from datetime import datetime
    import json
    import os

    # Determine output directory — cascade_engine/output/ or Data/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "..", "Data")
    if not os.path.isdir(out_dir):
        out_dir = os.path.join(script_dir, "output")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"cascade_result_{timestamp}"

    # ── JSON ──
    json_path = os.path.join(out_dir, f"{base_name}.json")
    # ensure_ascii=False to keep Unicode, encoding="utf-8" to avoid cp1252 issues
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # ── TXT (human-readable report) ──
    txt_path = os.path.join(out_dir, f"{base_name}.txt")
    lines = []
    lines.append("=" * 70)
    lines.append("  InnovAIte CASCADE PREDICTION REPORT")
    lines.append(f"  Location: {location}")
    lines.append(f"  Generated: {datetime.now().isoformat()}")
    lines.append(f"  Model: {result.get('_meta', {}).get('model', 'N/A')}")
    lines.append("=" * 70)

    lines.append(
        f"\nOVERALL RISK: {result.get('overall_risk_level', 'N/A')} "
        f"({result.get('overall_risk_score', '?')}/10)"
    )
    lines.append(f"\nBRIEFING:\n  {result.get('situation_briefing', 'N/A')}")

    # Active threats
    threats_list = result.get("active_threats_assessment", [])
    if threats_list:
        lines.append(f"\n{'─'*70}")
        lines.append(f"ACTIVE THREATS ({len(threats_list)})")
        lines.append(f"{'─'*70}")
        for t in threats_list:
            lines.append(
                f"  [{t.get('severity', '?').upper()}] "
                f"{t.get('threat_type', '?')} — {t.get('summary', '')}"
            )

    # Cascade chains
    cascades = result.get("cascade_predictions", [])
    if cascades:
        lines.append(f"\n{'─'*70}")
        lines.append(f"CASCADE PREDICTIONS ({len(cascades)} chains)")
        lines.append(f"{'─'*70}")
        for c in cascades:
            lines.append(f"\n  Chain {c.get('chain_id', '?')}: {c.get('trigger', '')}")
            for step in c.get("cascade_steps", []):
                lines.append(f"    → Step {step.get('step')}: {step.get('event')}")
                lines.append(
                    "      Domain: {d} | Probability: {p} | Timeframe: {t}".format(
                        d=step.get("domain"),
                        p=step.get("probability"),
                        t=step.get("timeframe"),
                    )
                )
                lines.append(f"      Mechanism: {step.get('mechanism')}")
            lines.append(
                f"    Historical precedent: {c.get('historical_precedent', 'None cited')}"
            )
            lines.append(f"    Ultimate impact: {c.get('ultimate_impact', 'N/A')}")
            lines.append(f"    Affected: {c.get('affected_population', 'N/A')}")

    # Priority actions
    actions = result.get("recommended_actions", [])
    if actions:
        lines.append(f"\n{'─'*70}")
        lines.append(f"RECOMMENDED ACTIONS ({len(actions)})")
        lines.append(f"{'─'*70}")
        for a in actions:
            urgency = a.get("urgency", "?")
            lines.append(f"  P{a.get('priority', '?')} [{urgency}]: {a.get('action')}")
            lines.append(
                f"    Responsible: {a.get('responsible_entity', 'N/A')}"
            )
            lines.append(f"    Rationale: {a.get('rationale', 'N/A')}")

    # Monitoring
    alerts = result.get("monitoring_alerts", [])
    if alerts:
        lines.append(f"\n{'─'*70}")
        lines.append(f"MONITORING ALERTS ({len(alerts)})")
        lines.append(f"{'─'*70}")
        for alert in alerts:
            lines.append(f"  {alert.get('indicator')}")
            lines.append(
                f"    Threshold: {alert.get('threshold')} | "
                f"Source: {alert.get('data_source')}"
            )

    # Caveats
    if result.get("confidence_notes"):
        lines.append(f"\n{'─'*70}")
        lines.append(f"CAVEATS:\n  {result['confidence_notes']}")

    lines.append(f"\n{'='*70}")

    # FIX: write TXT with UTF-8 encoding
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[CASCADE] Saved → {json_path}")
    print(f"[CASCADE] Saved → {txt_path}")


# ──────────────────────────────────────────────────────────────
# Convenience: analyze from Context_Json.json directly
# ──────────────────────────────────────────────────────────────

def analyze_from_context_json(context_path: str = "../Data/Context_Json.json", location: str = "Boston, MA") -> dict:
    """
    Reads the existing Context_Json.json (which has predictions from
    all lanes) and converts them into the standardized threat format
    for cascade analysis.

    This is handy for the demo — you already have lane predictions
    saved in Context_Json.json from the individual predictors.
    """
    with open(context_path, "r") as f:
        context = json.load(f)

    threats = []
    for entry in context.get("entries", []):
        name = entry.get("name", "")
        contents = entry.get("contents", {})
        prediction = contents.get("prediction", {})

        if not prediction:
            continue

        # Map the lane name to threat_type
        threat_type_map = {
            "earthquake": "earthquake",
            "flood": "flood",
            "forest_fire": "wildfire",
            "fire": "wildfire",
            "pandemic": "pandemic",
            "volcano": "eruption",
            "solar": "solar_flare",
            "solarFlare": "solar_flare",
        }

        threat_type = threat_type_map.get(name, name)
        loc_name = contents.get("location", location)

        threats.append({
            "threat_type": threat_type,
            "severity": prediction.get("risk_level", "unknown").lower(),
            "location": {"name": loc_name},
            "timestamp": "current",
            "data": contents.get("data_summary", {}),
            "summary": prediction.get("summary", f"{name} threat detected"),
        })

    if not threats:
        return {"error": "No threat data found in Context_Json.json"}

    return analyze_threats(threats, location=location)


# ──────────────────────────────────────────────────────────────
# CLI test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Demo threats for testing
    demo_threats = [
        {
            "threat_type": "earthquake",
            "severity": "high",
            "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
            "timestamp": "2026-02-15T15:00:00Z",
            "data": {"magnitude": 4.2, "depth_km": 8.0, "significance": 312},
            "summary": "M4.2 earthquake detected 30km southwest of Boston at 8km depth, significance score 312",
        },
        {
            "threat_type": "pandemic",
            "severity": "medium",
            "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
            "timestamp": "2026-02-15T15:00:00Z",
            "data": {"disease": "influenza", "weekly_change": "+40%", "hospitalization_rate": "elevated"},
            "summary": "Influenza hospitalizations up 40% week-over-week in Massachusetts, Google Trends showing rising searches for 'flu symptoms boston'",
        },
        {
            "threat_type": "flood",
            "severity": "moderate",
            "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
            "timestamp": "2026-02-15T15:00:00Z",
            "data": {"discharge_trend": "rising", "forecast_peak_ratio": 1.2},
            "summary": "Charles River discharge levels rising, forecast projects 120% of seasonal peak within 5 days",
        },
    ]

    # Check if user wants to use Context_Json.json
    if len(sys.argv) > 1 and sys.argv[1] == "--from-context":
        path = sys.argv[2] if len(sys.argv) > 2 else ".../Data/Context_Json.json"
        print(f"[CASCADE] Loading threats from {path}...")
        result = analyze_from_context_json(path)
    else:
        print("[CASCADE] Running with demo threats...")
        result = analyze_threats(demo_threats, location="Boston, MA")

    print("\n" + "=" * 60)
    print("  CASCADE PREDICTION RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2))
