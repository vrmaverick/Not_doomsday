"""
cascade_server.py
=================
Flask endpoint for the cascade prediction engine.

Option A: Run standalone on a different port
    python cascade_server.py  →  runs on port 5001

Option B: Import into your existing mitigation/server.py
    from cascade_engine.cascade_server import cascade_bp
    app.register_blueprint(cascade_bp)

Endpoints:
    POST /api/cascade
        Body: {
            "threats": [ ...standardized threat dicts... ],
            "location": "Boston, MA"    (optional, defaults to Boston)
        }
        Returns: Full cascade prediction JSON

    POST /api/cascade/from-context
        Body: {
            "context_path": "./Data/Context_Json.json",  (optional)
            "location": "Boston, MA"                      (optional)
        }
        Returns: Cascade prediction from existing Context_Json.json

    GET /api/cascade/health
        Returns: { "status": "ok", "chromadb_docs": 176768, "model": "..." }
"""

import os
import json
import traceback
from flask import Flask, Blueprint, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from cascade_chain import analyze_threats, analyze_from_context_json, GROQ_MODEL
from retriever import get_vectorstore

load_dotenv()

# ── Blueprint (for importing into existing server) ──
cascade_bp = Blueprint("cascade", __name__)


@cascade_bp.route("/api/cascade", methods=["POST"])
def cascade_analyze():
    """
    Main endpoint — takes active threats, returns cascade predictions.
    """
    try:
        body = request.get_json(force=True)
        threats = body.get("threats", [])
        location = body.get("location", "Boston, MA")

        if not threats:
            return jsonify({"error": "No threats provided. Send 'threats' array in body."}), 400

        result = analyze_threats(threats, location=location)

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@cascade_bp.route("/api/cascade/from-context", methods=["POST"])
def cascade_from_context():
    """
    Convenience endpoint — reads Context_Json.json directly.
    Good for demo: just hit this endpoint and it analyzes whatever
    your lane predictors have already saved.
    """
    try:
        body = request.get_json(force=True) if request.data else {}
        context_path = body.get("context_path", "./Data/Context_Json.json")
        location = body.get("location", "Boston, MA")

        result = analyze_from_context_json(context_path, location=location)

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@cascade_bp.route("/api/cascade/health", methods=["GET"])
def cascade_health():
    """Health check — verifies ChromaDB and Groq are accessible."""
    try:
        vs = get_vectorstore()
        doc_count = vs._collection.count()

        return jsonify({
            "status": "ok",
            "chromadb_docs": doc_count,
            "model": GROQ_MODEL,
            "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ── Standalone mode ──
if __name__ == "__main__":
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(cascade_bp)

    port = int(os.environ.get("CASCADE_PORT", 5001))
    print(f"\n{'='*50}")
    print(f"  InnovAIte Cascade Engine — port {port}")
    print(f"  POST /api/cascade")
    print(f"  POST /api/cascade/from-context")
    print(f"  GET  /api/cascade/health")
    print(f"{'='*50}\n")

    app.run(host="0.0.0.0", port=port, debug=True)
