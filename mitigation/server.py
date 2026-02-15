"""
City Infrastructure Calamity Optimizer — Flask Server
=====================================================
Endpoints:
    POST /api/optimize
        Body: { "city_name": "Boston", "calamity_list": ["earthquake", "flood"] }
        Returns: { original_adj_list, optimized_adj_list, changes, reasoning }

    GET /api/health
        Health check

Requires:
    pip install flask flask-cors groq networkx numpy scipy

Environment:
    GROQ_API_KEY=gsk_...  (required)
    PORT=5000             (optional, default 5000)
"""

import os
import json
import copy
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

import networkx as nx
import numpy as np

# ── Import the city generator from our existing module ──
from city_infrastructure_network import (
    generate_city_infrastructure,
    export_to_json,
    INFRASTRUCTURE,
)

from groq import Groq

# ─────────────────────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


# ─────────────────────────────────────────────────────────────
# HELPERS: Build adjacency data from NetworkX graph
# ─────────────────────────────────────────────────────────────

def build_adjacency_list(G):
    """
    Build a clean adjacency list from the NetworkX graph.
    Only includes infrastructure nodes (skips intersections).
    Each entry: "Node Label" -> [ { "neighbor": "...", "edge_type": "...", "distance": ... } ]
    """
    adj = {}
    for nid in G.nodes():
        attrs = G.nodes[nid]
        if attrs.get("infra_type") == "intersection":
            continue
        label = attrs.get("label", str(nid))
        neighbors = []
        for neighbor_id in G.neighbors(nid):
            n_attrs = G.nodes[neighbor_id]
            if n_attrs.get("infra_type") == "intersection":
                continue
            edge_data = G.edges[nid, neighbor_id]
            neighbors.append({
                "neighbor": n_attrs.get("label", str(neighbor_id)),
                "edge_type": edge_data.get("edge_type", "road"),
                "distance": round(edge_data.get("weight", 0), 2),
            })
        neighbors.sort(key=lambda x: x["distance"])
        adj[label] = neighbors
    return adj


def build_compact_adjacency(adj_detailed):
    """Convert detailed adjacency to compact: label -> [neighbor_labels]"""
    return {k: [n["neighbor"] for n in v] for k, v in adj_detailed.items()}


def build_typed_adjacency(adj_detailed):
    """Build adjacency lists per edge type."""
    typed = {}
    for label, neighbors in adj_detailed.items():
        for n in neighbors:
            etype = n["edge_type"]
            if etype not in typed:
                typed[etype] = {}
            if label not in typed[etype]:
                typed[etype][label] = []
            typed[etype][label].append(n["neighbor"])
    return typed


def build_node_type_map(G):
    """Map label -> infra_type for all non-intersection nodes."""
    return {
        G.nodes[n].get("label"): G.nodes[n].get("infra_type")
        for n in G.nodes()
        if G.nodes[n].get("infra_type") != "intersection"
    }


def build_node_positions(G, pos):
    """Map label -> {x, y, type} for all non-intersection nodes.
    Scales coordinates to screen-friendly range (~hundreds of pixels)
    so that zoom=1 looks reasonable on canvas.
    """
    SCALE = 50  # 1 city unit ≈ 50 screen pixels
    result = {}
    for nid in G.nodes():
        attrs = G.nodes[nid]
        if attrs.get("infra_type") == "intersection":
            continue
        label = attrs.get("label", str(nid))
        result[label] = {
            "x": round(pos[nid][0] * SCALE, 2),
            "y": round(pos[nid][1] * SCALE, 2),
            "type": attrs.get("infra_type", "unknown"),
        }
    return result


# ─────────────────────────────────────────────────────────────
# GROQ PROMPT BUILDER
# ─────────────────────────────────────────────────────────────

def build_groq_prompt(city_name, calamity_list, adj_detailed, node_type_map):
    """
    Build a structured prompt that sends the adjacency list and calamity
    info to the LLM and asks it to return JSON with edge removals,
    edge additions (emergency_path), and reasoning.
    """

    # Compact adjacency with edge types for the prompt
    adj_for_prompt = {}
    for label, neighbors in adj_detailed.items():
        adj_for_prompt[label] = [
            {"to": n["neighbor"], "via": n["edge_type"], "dist": n["distance"]}
            for n in neighbors
        ]

    # Node types summary
    type_summary = {}
    for label, itype in node_type_map.items():
        if itype not in type_summary:
            type_summary[itype] = []
        type_summary[itype].append(label)

    calamity_str = ", ".join(calamity_list)

    system_prompt = """You are an expert disaster response and urban infrastructure optimization AI.
You analyze city infrastructure networks and optimize them for specific calamity scenarios.

You must respond with ONLY valid JSON — no markdown, no explanation outside JSON, no backticks.
The JSON must strictly follow the schema provided."""

    user_prompt = f"""## TASK
The city "{city_name}" faces these calamities: [{calamity_str}]

Analyze the infrastructure network below and produce an optimized version:

1. **REMOVE edges** that are vulnerable, redundant, or dangerous during the given calamities.
   - e.g., during floods: remove low-lying road connections, vulnerable power lines
   - e.g., during earthquakes: remove connections through fault-prone areas, fragile bridges
   - Be strategic — don't remove critical lifelines. Only remove edges that are liabilities.

2. **ADD new "emergency_path" edges** to create critical emergency corridors:
   - Connect hospitals to the nearest shelters/bunkers
   - Connect fire stations to power plants (fire risk from damaged power infrastructure)
   - Connect food/water services to shelters (supply routes for displaced people)
   - Connect evacuation points to hospitals and police stations
   - Create redundant paths between critical nodes so the network stays connected
   - The emergency_path edges represent hastily established priority routes (cleared roads,
     helicopter corridors, temporary bridges, etc.)

3. **Reason about each change** — explain WHY each edge is removed or added in context of
   the specific calamities.

## INFRASTRUCTURE NODES BY TYPE
{json.dumps(type_summary, indent=2)}

## CURRENT ADJACENCY LIST (with edge types and distances)
{json.dumps(adj_for_prompt, indent=2)}

## REQUIRED JSON OUTPUT SCHEMA
Respond with ONLY this JSON (no other text):
{{
    "reasoning": "2-3 paragraph strategic overview of optimization approach for these calamities",
    "edges_to_remove": [
        {{
            "from": "Node Label A",
            "to": "Node Label B",
            "edge_type": "road|power|water|emergency",
            "reason": "why this edge should be removed"
        }}
    ],
    "edges_to_add": [
        {{
            "from": "Node Label A",
            "to": "Node Label B",
            "edge_type": "emergency_path",
            "reason": "why this emergency path is needed"
        }}
    ],
    "priority_nodes": [
        {{
            "node": "Node Label",
            "priority": "critical|high|medium",
            "reason": "why this node is priority during these calamities"
        }}
    ]
}}

IMPORTANT RULES:
- Use EXACT node labels from the adjacency list (e.g., "Hospital #1", "Fire Station #2")
- Only remove edges that actually exist in the adjacency list
- Add 8-15 emergency_path edges — enough to create robust emergency corridors
- Remove 5-12 edges — be surgical, not destructive
- Mark 5-10 priority nodes
- Every edge_to_add MUST have edge_type: "emergency_path"
- Respond with ONLY the JSON object, nothing else"""

    return system_prompt, user_prompt


# ─────────────────────────────────────────────────────────────
# GROQ API CALL
# ─────────────────────────────────────────────────────────────

def call_groq(system_prompt, user_prompt):
    """Call Groq API and parse JSON response. Returns (result, error_msg)."""

    client = Groq(api_key=GROQ_API_KEY)

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=GROQ_MODEL,
            temperature=0.3,
            max_tokens=4096,
            top_p=0.9,
            response_format={"type": "json_object"},
        )

        raw = chat_completion.choices[0].message.content.strip()

        # Clean up response — strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        return json.loads(raw), None

    except Exception as e:
        error_str = str(e)
        # Extract a cleaner message for known error patterns
        if "rate_limit" in error_str.lower() or "429" in error_str:
            # Try to extract the retry-after time
            import re
            retry_match = re.search(r'try again in ([^.]+\.?\d*s?)', error_str, re.IGNORECASE)
            retry_info = retry_match.group(1) if retry_match else "a while"
            msg = f"Groq rate limit reached. Try again in {retry_info}. Showing original network unchanged."
        elif "401" in error_str or "auth" in error_str.lower():
            msg = "Groq API authentication failed. Check your GROQ_API_KEY."
        elif "timeout" in error_str.lower():
            msg = "Groq API request timed out. Try again."
        else:
            msg = f"Groq API error: {error_str[:200]}"

        print(f"  ⚠️  Groq call failed: {msg}")
        return None, msg


# ─────────────────────────────────────────────────────────────
# GRAPH MUTATOR: Apply Groq's changes to NetworkX graph
# ─────────────────────────────────────────────────────────────

def apply_optimizations(G, pos, groq_response, node_type_map):
    """
    Apply the Groq-suggested changes to a copy of the graph.
    Returns (G_optimized, changes_applied).
    """
    G_opt = G.copy()

    # Build reverse lookup: label -> node_id
    label_to_id = {}
    for nid in G.nodes():
        label = G.nodes[nid].get("label", "")
        if label:
            label_to_id[label] = nid

    changes = {
        "edges_removed": [],
        "edges_added": [],
        "removal_failures": [],
        "addition_failures": [],
    }

    # ── REMOVE EDGES ──
    for edge_rm in groq_response.get("edges_to_remove", []):
        from_label = edge_rm.get("from", "")
        to_label = edge_rm.get("to", "")
        from_id = label_to_id.get(from_label)
        to_id = label_to_id.get(to_label)

        if from_id is not None and to_id is not None and G_opt.has_edge(from_id, to_id):
            old_data = dict(G_opt.edges[from_id, to_id])
            G_opt.remove_edge(from_id, to_id)
            changes["edges_removed"].append({
                "from": from_label,
                "to": to_label,
                "edge_type": old_data.get("edge_type", "unknown"),
                "reason": edge_rm.get("reason", ""),
            })
        else:
            changes["removal_failures"].append({
                "from": from_label,
                "to": to_label,
                "reason": f"Edge not found in graph",
            })

    # ── ADD EMERGENCY_PATH EDGES ──
    for edge_add in groq_response.get("edges_to_add", []):
        from_label = edge_add.get("from", "")
        to_label = edge_add.get("to", "")
        from_id = label_to_id.get(from_label)
        to_id = label_to_id.get(to_label)

        if from_id is not None and to_id is not None:
            # Calculate distance from positions
            d = np.linalg.norm(np.array(pos[from_id]) - np.array(pos[to_id]))
            # Add or overwrite as emergency_path
            G_opt.add_edge(from_id, to_id, edge_type="emergency_path", weight=d)
            changes["edges_added"].append({
                "from": from_label,
                "to": to_label,
                "edge_type": "emergency_path",
                "distance": round(d, 2),
                "reason": edge_add.get("reason", ""),
            })
        else:
            missing = []
            if from_id is None:
                missing.append(from_label)
            if to_id is None:
                missing.append(to_label)
            changes["addition_failures"].append({
                "from": from_label,
                "to": to_label,
                "reason": f"Node(s) not found: {', '.join(missing)}",
            })

    # ── Ensure graph stays connected — if removing edges disconnected it, ──
    # ── add back the minimum edges needed via emergency_path              ──
    if not nx.is_connected(G_opt):
        components = list(nx.connected_components(G_opt))
        for i in range(len(components) - 1):
            # Find closest pair between component i and i+1
            best_pair = None
            best_dist = float("inf")
            for n1 in components[i]:
                for n2 in components[i + 1]:
                    d = np.linalg.norm(np.array(pos[n1]) - np.array(pos[n2]))
                    if d < best_dist:
                        best_dist = d
                        best_pair = (n1, n2)
            if best_pair:
                n1, n2 = best_pair
                G_opt.add_edge(n1, n2, edge_type="emergency_path", weight=best_dist)
                changes["edges_added"].append({
                    "from": G.nodes[n1].get("label", str(n1)),
                    "to": G.nodes[n2].get("label", str(n2)),
                    "edge_type": "emergency_path",
                    "distance": round(best_dist, 2),
                    "reason": "Auto-added to maintain network connectivity after removals",
                })

    return G_opt, changes


# ─────────────────────────────────────────────────────────────
# COMPARISON STATS
# ─────────────────────────────────────────────────────────────

def compute_graph_stats(G):
    """Compute summary stats for a graph."""
    edge_counts = {}
    for _, _, data in G.edges(data=True):
        et = data.get("edge_type", "unknown")
        edge_counts[et] = edge_counts.get(et, 0) + 1

    infra_count = sum(
        1 for n in G.nodes()
        if G.nodes[n].get("infra_type") != "intersection"
    )

    stats = {
        "total_nodes": G.number_of_nodes(),
        "infrastructure_nodes": infra_count,
        "total_edges": G.number_of_edges(),
        "edge_type_counts": edge_counts,
        "density": round(nx.density(G), 6),
        "is_connected": nx.is_connected(G),
    }

    if nx.is_connected(G):
        stats["avg_shortest_path"] = round(
            nx.average_shortest_path_length(G, weight="weight"), 4
        )

    return stats


# ─────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "groq_configured": bool(GROQ_API_KEY),
        "model": GROQ_MODEL,
    })


@app.route("/api/optimize", methods=["POST"])
def optimize():
    """
    Main endpoint.
    Input:  { "city_name": "Boston", "calamity_list": ["earthquake", "flood"] }
    Output: { original_adj_list, optimized_adj_list, changes, groq_response, stats }
    """
    try:
        data = request.get_json(force=True)
        city_name = data.get("city_name", "").strip()
        calamity_list = data.get("calamity_list", [])

        # ── Validate ──
        if not city_name:
            return jsonify({"error": "city_name is required"}), 400
        if not calamity_list or not isinstance(calamity_list, list):
            return jsonify({"error": "calamity_list must be a non-empty array of strings"}), 400
        if not GROQ_API_KEY:
            return jsonify({"error": "GROQ_API_KEY environment variable not set"}), 500

        calamity_list = [str(c).strip() for c in calamity_list if str(c).strip()]

        # ── Step 1: Generate city infrastructure ──
        print(f"\n{'='*60}")
        print(f"  OPTIMIZE REQUEST: {city_name}")
        print(f"  Calamities: {calamity_list}")
        print(f"{'='*60}")

        G, pos, infra_nodes, city_radius = generate_city_infrastructure(city_name)

        # ── Step 2: Build original adjacency list ──
        original_adj_detailed = build_adjacency_list(G)
        original_adj_compact = build_compact_adjacency(original_adj_detailed)
        original_typed = build_typed_adjacency(original_adj_detailed)
        node_type_map = build_node_type_map(G)

        original_stats = compute_graph_stats(G)

        print(f"  Original graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        # ── Step 3: Call Groq for optimization ──
        groq_failed = False
        groq_warning = None

        print(f"  Calling Groq ({GROQ_MODEL})...")
        system_prompt, user_prompt = build_groq_prompt(
            city_name, calamity_list, original_adj_detailed, node_type_map
        )
        groq_response, groq_error = call_groq(system_prompt, user_prompt)

        if groq_response is None:
            # Groq failed (rate limit, auth, timeout, etc.)
            # Return original == optimized with a warning
            groq_failed = True
            groq_warning = groq_error
            groq_response = {
                "reasoning": "",
                "edges_to_remove": [],
                "edges_to_add": [],
                "priority_nodes": [],
            }
            print(f"  ⚠️  Groq failed, returning original network unchanged")
        else:
            print(f"  Groq response received:")
            print(f"    - Edges to remove: {len(groq_response.get('edges_to_remove', []))}")
            print(f"    - Edges to add:    {len(groq_response.get('edges_to_add', []))}")
            print(f"    - Priority nodes:  {len(groq_response.get('priority_nodes', []))}")

        # ── Step 4: Apply optimizations to graph ──
        G_opt, changes = apply_optimizations(G, pos, groq_response, node_type_map)

        # ── Step 5: Build optimized adjacency list ──
        optimized_adj_detailed = build_adjacency_list(G_opt)
        optimized_adj_compact = build_compact_adjacency(optimized_adj_detailed)
        optimized_typed = build_typed_adjacency(optimized_adj_detailed)

        optimized_stats = compute_graph_stats(G_opt)

        print(f"  Optimized graph: {G_opt.number_of_nodes()} nodes, {G_opt.number_of_edges()} edges")
        print(f"  Changes: -{len(changes['edges_removed'])} edges, +{len(changes['edges_added'])} edges")
        print(f"{'='*60}\n")

        # ── Step 6: Build response ──
        node_positions = build_node_positions(G, pos)
        SCALE = 50  # must match build_node_positions

        response = {
            "city_name": city_name,
            "calamity_list": calamity_list,
            "node_positions": node_positions,
            "city_radius": round(city_radius * SCALE, 2),
            "groq_failed": groq_failed,
            "warning": groq_warning,

            "original": {
                "adjacency_list": original_adj_compact,
                "typed_adjacency_lists": original_typed,
                "detailed_adjacency": original_adj_detailed,
                "stats": original_stats,
            },

            "optimized": {
                "adjacency_list": optimized_adj_compact,
                "typed_adjacency_lists": optimized_typed,
                "detailed_adjacency": optimized_adj_detailed,
                "stats": optimized_stats,
            },

            "changes": {
                "edges_removed": changes["edges_removed"],
                "edges_added": changes["edges_added"],
                "removal_failures": changes["removal_failures"],
                "addition_failures": changes["addition_failures"],
                "summary": {
                    "total_removed": len(changes["edges_removed"]),
                    "total_added": len(changes["edges_added"]),
                    "net_edge_change": len(changes["edges_added"]) - len(changes["edges_removed"]),
                    "failed_removals": len(changes["removal_failures"]),
                    "failed_additions": len(changes["addition_failures"]),
                },
            },

            "groq_analysis": {
                "reasoning": groq_response.get("reasoning", ""),
                "priority_nodes": groq_response.get("priority_nodes", []),
                "model_used": GROQ_MODEL,
            },

            "comparison": {
                "original_edges": original_stats["total_edges"],
                "optimized_edges": optimized_stats["total_edges"],
                "original_density": original_stats["density"],
                "optimized_density": optimized_stats["density"],
                "original_connected": original_stats["is_connected"],
                "optimized_connected": optimized_stats["is_connected"],
                "emergency_paths_created": sum(
                    1 for e in changes["edges_added"]
                    if e["edge_type"] == "emergency_path"
                ),
            },
        }

        return jsonify(response), 200

    except json.JSONDecodeError as e:
        return jsonify({
            "error": "Failed to parse Groq response as JSON",
            "details": str(e),
        }), 502

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "type": type(e).__name__,
        }), 500


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    if not GROQ_API_KEY:
        print("⚠️  WARNING: GROQ_API_KEY not set!")
        print("   Set it with: export GROQ_API_KEY=gsk_your_key_here")
        print("   The /api/optimize endpoint will fail without it.\n")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     City Infrastructure Calamity Optimizer Server       ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  POST /api/optimize                                      ║
║    Body: {{                                               ║
║      "city_name": "Boston",                              ║
║      "calamity_list": ["earthquake", "flood"]            ║
║    }}                                                     ║
║                                                          ║
║  GET  /api/health                                        ║
║                                                          ║
║  Groq Model: {GROQ_MODEL:<42} ║
║  Port:       {port:<42} ║
╚══════════════════════════════════════════════════════════╝
    """)

    app.run(host="0.0.0.0", port=port, debug=True)