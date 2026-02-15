# InnovAIte Cascade Prediction Engine

The AI brain of InnovAIte. Takes real-time threat signals from all lanes, retrieves historical context from the 176K-document ChromaDB, and uses Groq LLM to predict how disasters cascade across domains.

## Architecture

```
Active Threats (from lane APIs)
        │
        ▼
┌─────────────────┐     ┌──────────────────┐
│  retriever.py   │────▶│  ChromaDB        │
│  (semantic      │     │  threat_db/      │
│   search)       │◀────│  176K documents  │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ cascade_prompt   │────▶│  Groq LLM        │
│ (system prompt + │     │  llama-3.3-70b   │
│  active threats  │◀────│                  │
│  + hist context) │     └──────────────────┘
└────────┬────────┘
         │
         ▼
   Cascade Prediction JSON
   (risks, cascades, actions)
```

## Files

| File | What it does |
|------|-------------|
| `retriever.py` | Connects LangChain to existing ChromaDB, provides semantic search |
| `cascade_prompt.py` | System prompt + template for cascade analysis |
| `cascade_chain.py` | Main pipeline: retriever → prompt → Groq → structured JSON |
| `cascade_server.py` | Flask endpoints (standalone or register into existing server) |

## Quick Start

### 1. Install deps
```bash
pip install -r requirements.txt
```

### 2. Set your Groq key
```bash
export GROQ_API_KEY=gsk_your_key_here
```

### 3. Make sure threat_db/ is accessible
The ChromaDB folder (`threat_db/`) should be in the same directory, or update `CHROMA_PATH` in `retriever.py`.

### 4. Test the retriever
```bash
python retriever.py
```
Should print: `Collection 'threat_data' has 176,768 documents` and return search results.

### 5. Test the full chain
```bash
python cascade_chain.py
```
Runs with demo threats (earthquake + pandemic + flood in Boston). Should return a full cascade prediction JSON.

### 6. Run the server
```bash
python cascade_server.py
```
Then hit:
```bash
# Health check
curl http://localhost:5001/api/cascade/health

# Analyze from Context_Json.json (easiest for demo)
curl -X POST http://localhost:5001/api/cascade/from-context \
  -H "Content-Type: application/json" \
  -d '{"location": "Boston, MA"}'

# Analyze custom threats
curl -X POST http://localhost:5001/api/cascade \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Boston, MA",
    "threats": [
      {
        "threat_type": "earthquake",
        "severity": "high",
        "location": {"name": "Boston, MA"},
        "timestamp": "2026-02-15T15:00:00Z",
        "summary": "M4.2 earthquake detected near Boston",
        "data": {"magnitude": 4.2}
      }
    ]
  }'
```

## Integrating with Existing Server

In your `mitigation/server.py`, add:

```python
# At the top
from cascade_engine.cascade_server import cascade_bp

# After app = Flask(__name__)
app.register_blueprint(cascade_bp)
```

Now `/api/cascade` lives alongside `/api/optimize` on the same server.

## How It Works (for the presentation)

1. **Each lane** (earthquake, pandemic, flood, fire, volcano, solar) detects threats via real-time APIs
2. **Threats are standardized** into a common JSON format
3. **The cascade engine** takes ALL active threats simultaneously
4. **ChromaDB retrieval** finds the most relevant historical precedents across all 176K records
5. **The LLM analyzes** current threats + historical context together
6. **Output**: cascade predictions with timelines, probabilities, and specific recommended actions

**Key talking point**: "No human expert can monitor 6 threat domains simultaneously, identify cross-domain connections, and generate coordinated response plans in real-time. That's what our cascade engine does."
