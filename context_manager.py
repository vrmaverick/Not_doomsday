import os
import json
from datetime import datetime, timezone

CONTEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data", "Context_Json.json")

def save_to_context(name: str, data):
    """
    Save data to Context_Json.json.

    Args:
        name: Entry name (e.g. "earthquake", "flood", "solar_flare")
        data: Either a dict (used directly) or a file path string (read from file)
    """
    # Accept both dict and file path
    if isinstance(data, str):
        with open(data, 'r') as f:
            contents = json.load(f)
    elif isinstance(data, dict):
        contents = data
    else:
        raise ValueError("data must be a dict or a file path string")

    entry = {
        "name": name,
        "contents": contents,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, 'r') as f:
            context = json.load(f)
    else:
        context = {"entries": []}

    # Dedupe by name
    context["entries"] = [e for e in context["entries"] if e["name"] != name]
    context["entries"].append(entry)
    context["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(CONTEXT_FILE, 'w') as f:
        json.dump(context, f, indent=2)

    print(f"Saved '{name}' → {CONTEXT_FILE}")