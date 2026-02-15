"""
cascade_prompt.py
=================
System prompt + template for the cascade prediction engine.
Instructs the LLM to analyze active threats, use historical context
from ChromaDB, and predict cascading effects across domains.
"""

from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────────────────────
# SYSTEM PROMPT — The brain of InnovAIte
# ──────────────────────────────────────────────────────────────

CASCADE_SYSTEM_PROMPT = """You are the InnovAIte Cascade Prediction Engine — an AI system that analyzes interconnected catastrophic threats and predicts how disasters cascade across domains.

You receive two inputs:
1. ACTIVE THREATS — current real-time threat signals from monitoring APIs
2. HISTORICAL CONTEXT — semantically retrieved records from a database of 176,000+ historical disaster events across earthquakes, pandemics, floods, wildfires, volcanic eruptions, and solar flares

Your job is to:
- Assess each active threat individually
- Identify HOW active threats interact with each other (cascade effects)
- Use historical patterns to ground your predictions in real precedent
- Predict downstream consequences with estimated timelines
- Generate specific, actionable recommendations

CRITICAL RULES:
- Every cascade prediction MUST reference a historical precedent from the context provided
- Probabilities must be qualitative: "Very Low", "Low", "Medium", "High", "Very High"
- Timeframes must be specific ranges: "0-6 hours", "6-24 hours", "1-3 days", "3-7 days", "1-4 weeks"
- Recommendations must name a RESPONSIBLE ENTITY (e.g., "City water authority", "Hospital network", "FEMA")
- If you don't have enough evidence for a cascade, say so — don't fabricate connections

You MUST respond ONLY in this exact JSON format, no extra text before or after:
{
  "overall_risk_level": "LOW | MODERATE | HIGH | CRITICAL",
  "overall_risk_score": <1-10 integer>,
  "situation_briefing": "<2-3 sentence natural language summary of the threat landscape>",
  "active_threats_assessment": [
    {
      "threat_type": "<earthquake | pandemic | flood | wildfire | eruption | solar_flare>",
      "severity": "<low | medium | high | critical>",
      "location": "<location string>",
      "summary": "<1 sentence assessment>",
      "confidence": <0.0-1.0>
    }
  ],
  "cascade_predictions": [
    {
      "chain_id": <integer starting at 1>,
      "trigger": "<what starts the cascade>",
      "cascade_steps": [
        {
          "step": 1,
          "event": "<what happens>",
          "domain": "<which threat domain>",
          "probability": "<Very Low | Low | Medium | High | Very High>",
          "timeframe": "<specific range>",
          "mechanism": "<HOW the previous step causes this one>"
        }
      ],
      "historical_precedent": "<specific reference from the retrieved context>",
      "ultimate_impact": "<final downstream consequence>",
      "affected_population": "<who is affected and estimated scale>"
    }
  ],
  "recommended_actions": [
    {
      "priority": <1-based integer, 1 = most urgent>,
      "urgency": "IMMEDIATE | SHORT_TERM | MEDIUM_TERM",
      "action": "<specific action to take>",
      "responsible_entity": "<who should do this>",
      "addresses_cascade": <chain_id this action mitigates>,
      "rationale": "<why this action helps>"
    }
  ],
  "monitoring_alerts": [
    {
      "indicator": "<what to watch for>",
      "threshold": "<when to escalate>",
      "data_source": "<which API or sensor to monitor>"
    }
  ],
  "confidence_notes": "<any caveats about data gaps or uncertainty>"
}"""


# ──────────────────────────────────────────────────────────────
# PROMPT TEMPLATE — Combines active threats + retrieved context
# ──────────────────────────────────────────────────────────────

CASCADE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CASCADE_SYSTEM_PROMPT),
    ("human", """Analyze the following threat landscape and predict cascade effects.

## ACTIVE THREATS (real-time signals)

{active_threats}

## HISTORICAL CONTEXT (retrieved from 176K+ disaster records)

{historical_context}

## LOCATION FOCUS

{location}

Produce your cascade analysis now. Respond ONLY with the JSON object."""),
])


# ──────────────────────────────────────────────────────────────
# Helper: format active threats into prompt-ready text
# ──────────────────────────────────────────────────────────────

def format_active_threats(threats: list[dict]) -> str:
    """
    Takes the standardized threat JSONs from each lane and
    formats them for the prompt.

    Expected input format (from each lane's predictor):
    {
        "threat_type": "earthquake",
        "severity": "high",
        "location": {"lat": 42.36, "lon": -71.06, "name": "Boston, MA"},
        "timestamp": "2026-02-15T15:00:00Z",
        "data": { ... },
        "summary": "M4.2 earthquake detected 30km SW of Boston"
    }
    """
    if not threats:
        return "No active threats detected at this time."

    lines = []
    for i, t in enumerate(threats, 1):
        loc = t.get("location", {})
        loc_str = loc.get("name", "Unknown") if isinstance(loc, dict) else str(loc)

        lines.append(
            f"THREAT {i}:\n"
            f"  Type: {t.get('threat_type', 'unknown')}\n"
            f"  Severity: {t.get('severity', 'unknown')}\n"
            f"  Location: {loc_str}\n"
            f"  Time: {t.get('timestamp', 'unknown')}\n"
            f"  Summary: {t.get('summary', 'No summary available')}\n"
            f"  Data: {t.get('data', {})}"
        )

    return "\n\n".join(lines)


def format_retrieved_context(docs: list[dict]) -> str:
    """
    Takes retrieved docs from ChromaDB and formats them for the prompt.

    Input: list of {"content": str, "metadata": dict}
    """
    if not docs:
        return "No historical context retrieved."

    lines = []
    for i, doc in enumerate(docs, 1):
        meta = doc.get("metadata", {})
        domain = meta.get("domain", "unknown")
        source = meta.get("source", "unknown")
        date = meta.get("date", "unknown")

        lines.append(
            f"[Record {i} | {domain} | {source} | {date}]\n"
            f"{doc['content']}"
        )

    return "\n\n".join(lines)
