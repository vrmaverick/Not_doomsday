"""
City Infrastructure Network Visualizer
=======================================
Uses NetworkX to model and visualize city infrastructure including:
- Hospitals, Fire Stations, Police Stations
- Bunkers / Shelters, Food Services
- Power Plants, Water Treatment, Telecom Towers
- Road network connections between them

Usage:
    python city_infrastructure_network.py
    python city_infrastructure_network.py --city "New York"
    python city_infrastructure_network.py --city "Mumbai" --seed 42

When run WITH internet (osmnx installed):
    Fetches real OpenStreetMap data for the given city.

When run WITHOUT internet:
    Generates a realistic procedural city layout based on the city name.
"""

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np
import argparse
import hashlib
import json
import sys

# ─────────────────────────────────────────────────────────────
# CONFIGURATION: Infrastructure categories, colors, markers
# ─────────────────────────────────────────────────────────────

INFRASTRUCTURE = {
    # ── Emergency Services ──
    "Hospital":         {"color": "#E63946", "marker": "H", "shape": "s", "size": 320, "category": "Emergency"},
    "Fire Station":     {"color": "#FF6B35", "marker": "F", "shape": "^", "size": 280, "category": "Emergency"},
    "Police Station":   {"color": "#1D3557", "marker": "P", "shape": "D", "size": 260, "category": "Emergency"},
    "Ambulance Depot":  {"color": "#E07A5F", "marker": "A", "shape": "v", "size": 240, "category": "Emergency"},

    # ── Shelter & Safety ──
    "Bunker/Shelter":   {"color": "#6D6875", "marker": "B", "shape": "8", "size": 260, "category": "Shelter"},
    "Evacuation Point": {"color": "#B5838D", "marker": "E", "shape": "p", "size": 240, "category": "Shelter"},

    # ── Food & Supplies ──
    "Food Service":     {"color": "#2A9D8F", "marker": "FS", "shape": "o", "size": 220, "category": "Food"},
    "Grocery Store":    {"color": "#57CC99", "marker": "G", "shape": "o", "size": 200, "category": "Food"},
    "Water Supply":     {"color": "#48CAE4", "marker": "W", "shape": "h", "size": 240, "category": "Food"},

    # ── Power & Utilities (Sources) ──
    "Power Plant":      {"color": "#FFBE0B", "marker": "⚡", "shape": "*", "size": 400, "category": "Utility"},
    "Substation":       {"color": "#F4A261", "marker": "S", "shape": "d", "size": 240, "category": "Utility"},
    "Telecom Tower":    {"color": "#7209B7", "marker": "T", "shape": "^", "size": 260, "category": "Utility"},
    "Water Treatment":  {"color": "#0096C7", "marker": "WT", "shape": "H", "size": 300, "category": "Utility"},
}

CATEGORY_COLORS = {
    "Emergency": "#E63946",
    "Shelter":   "#6D6875",
    "Food":      "#2A9D8F",
    "Utility":   "#FFBE0B",
}

EDGE_STYLES = {
    "road":       {"color": "#AAAAAA", "width": 0.8, "style": "-",  "alpha": 0.3},
    "power":      {"color": "#FFBE0B", "width": 1.5, "style": "--", "alpha": 0.5},
    "water":      {"color": "#48CAE4", "width": 1.4, "style": "-.", "alpha": 0.5},
    "emergency":  {"color": "#E63946", "width": 1.2, "style": ":",  "alpha": 0.4},
}


# ─────────────────────────────────────────────────────────────
# CITY GENERATOR: Procedural layout from city name
# ─────────────────────────────────────────────────────────────

def city_seed(city_name: str) -> int:
    """Deterministic seed from city name so same city = same layout."""
    return int(hashlib.md5(city_name.encode()).hexdigest()[:8], 16)


def generate_city_infrastructure(city_name: str, custom_seed: int = None):
    """
    Generate a realistic city infrastructure network using NetworkX.
    Uses neighborhood-based placement with minimum spacing to avoid
    origin-clustering, producing layouts similar to real OSM data.
    Returns (G, pos, infra_nodes, city_radius).
    """
    seed = custom_seed if custom_seed else city_seed(city_name)
    rng = np.random.RandomState(seed)

    G = nx.Graph()
    pos = {}

    # City parameters derived from name hash
    h = hashlib.sha256(city_name.encode()).hexdigest()
    city_radius = 4.0 + int(h[:2], 16) / 256 * 3.0
    density = 0.6 + int(h[2:4], 16) / 256 * 0.6

    # ── Step 1: Create neighborhood centers ──
    # These act like districts (downtown, suburbs, industrial, etc.)
    n_neighborhoods = max(4, int(5 * density + rng.randint(0, 3)))
    hood_centers = []
    for i in range(n_neighborhoods):
        angle = (2 * np.pi * i / n_neighborhoods) + rng.uniform(-0.4, 0.4)
        r = city_radius * (0.25 + rng.uniform(0, 0.55))
        cx, cy = r * np.cos(angle), r * np.sin(angle)
        hood_centers.append((cx, cy))
    # Add a downtown center near (0,0) but slightly offset
    hood_centers.insert(0, (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)))

    # ── Step 2: Place infrastructure with minimum spacing ──
    node_counts = {
        "Hospital":         max(2, int(3 * density + rng.randint(0, 3))),
        "Fire Station":     max(2, int(4 * density + rng.randint(0, 2))),
        "Police Station":   max(2, int(3 * density + rng.randint(0, 2))),
        "Ambulance Depot":  max(1, int(2 * density)),
        "Bunker/Shelter":   max(2, int(3 * density + rng.randint(0, 2))),
        "Evacuation Point": max(1, int(2 * density)),
        "Food Service":     max(3, int(5 * density + rng.randint(0, 3))),
        "Grocery Store":    max(2, int(4 * density + rng.randint(0, 2))),
        "Water Supply":     max(2, int(3 * density)),
        "Power Plant":      max(1, int(1.5 * density)),
        "Substation":       max(2, int(4 * density + rng.randint(0, 2))),
        "Telecom Tower":    max(2, int(3 * density + rng.randint(0, 2))),
        "Water Treatment":  max(1, int(1.5 * density)),
    }

    # Minimum spacing per infrastructure type (prevents clumping)
    min_spacing = {
        "Hospital": city_radius * 0.4,
        "Fire Station": city_radius * 0.3,
        "Police Station": city_radius * 0.35,
        "Ambulance Depot": city_radius * 0.3,
        "Bunker/Shelter": city_radius * 0.3,
        "Evacuation Point": city_radius * 0.35,
        "Food Service": city_radius * 0.2,
        "Grocery Store": city_radius * 0.2,
        "Water Supply": city_radius * 0.35,
        "Power Plant": city_radius * 0.5,
        "Substation": city_radius * 0.25,
        "Telecom Tower": city_radius * 0.35,
        "Water Treatment": city_radius * 0.5,
    }

    node_id = 0
    infra_nodes = {}
    all_placed_positions = []  # track all positions for spacing

    def place_node_near(center_x, center_y, spread, min_dist, max_attempts=50):
        """Place a node near a center with minimum distance from existing nodes."""
        for _ in range(max_attempts):
            x = center_x + rng.uniform(-spread, spread)
            y = center_y + rng.uniform(-spread, spread)
            # Check minimum distance from all placed nodes
            too_close = False
            for px, py in all_placed_positions:
                if np.hypot(x - px, y - py) < min_dist:
                    too_close = True
                    break
            if not too_close:
                return x, y
        # Fallback: use the last attempt position with jitter
        return (center_x + rng.uniform(-spread * 1.5, spread * 1.5),
                center_y + rng.uniform(-spread * 1.5, spread * 1.5))

    # Place each infrastructure type with spatial rules
    for infra_type, count in node_counts.items():
        infra_nodes[infra_type] = []
        min_dist = min_spacing.get(infra_type, city_radius * 0.2)

        for i in range(count):
            name = f"{infra_type} #{i+1}"

            if infra_type in ("Power Plant", "Water Treatment"):
                # Industrial outskirts — place on the periphery
                angle = rng.uniform(0, 2 * np.pi)
                r = city_radius * (0.7 + rng.uniform(0, 0.3))
                cx, cy = r * np.cos(angle), r * np.sin(angle)
                x, y = place_node_near(cx, cy, city_radius * 0.15, min_dist)

            elif infra_type in ("Bunker/Shelter", "Evacuation Point"):
                # Spread across different neighborhoods
                hood = hood_centers[i % len(hood_centers)]
                x, y = place_node_near(hood[0], hood[1],
                                       city_radius * 0.35, min_dist)

            elif infra_type == "Hospital":
                # Hospitals spread across different areas of the city
                # First hospital near downtown, rest in different quadrants
                if i == 0:
                    hood = hood_centers[0]  # downtown
                else:
                    hood = hood_centers[min(i, len(hood_centers) - 1)]
                x, y = place_node_near(hood[0], hood[1],
                                       city_radius * 0.25, min_dist)

            elif infra_type in ("Fire Station", "Police Station"):
                # Distributed evenly — each in a different neighborhood
                hood = hood_centers[i % len(hood_centers)]
                x, y = place_node_near(hood[0], hood[1],
                                       city_radius * 0.2, min_dist)

            elif infra_type == "Substation":
                # Between neighborhoods, along "power corridors"
                h1 = hood_centers[i % len(hood_centers)]
                h2 = hood_centers[(i + 1) % len(hood_centers)]
                mid_x = (h1[0] + h2[0]) / 2 + rng.uniform(-0.5, 0.5)
                mid_y = (h1[1] + h2[1]) / 2 + rng.uniform(-0.5, 0.5)
                x, y = place_node_near(mid_x, mid_y,
                                       city_radius * 0.2, min_dist)

            elif infra_type == "Telecom Tower":
                # High ground / spread out for coverage
                angle = rng.uniform(0, 2 * np.pi)
                r = city_radius * (0.3 + rng.uniform(0, 0.5))
                x, y = place_node_near(r * np.cos(angle), r * np.sin(angle),
                                       city_radius * 0.15, min_dist)

            else:
                # Food Service, Grocery Store, Water Supply — neighborhood-based
                hood = hood_centers[rng.randint(0, len(hood_centers))]
                x, y = place_node_near(hood[0], hood[1],
                                       city_radius * 0.25,
                                       min_dist * 0.6)

            G.add_node(node_id, label=name, infra_type=infra_type,
                       category=INFRASTRUCTURE[infra_type]["category"])
            pos[node_id] = (x, y)
            all_placed_positions.append((x, y))
            infra_nodes[infra_type].append(node_id)
            node_id += 1

    # ── Step 3: Add road intersection nodes along grid-like streets ──
    # Create intersections along roads BETWEEN neighborhoods (not at origin)
    n_intersections = int(25 * density + rng.randint(0, 12))
    intersection_ids = []

    # Some intersections along corridors between neighborhoods
    for i in range(n_intersections):
        if i < len(hood_centers) and rng.random() < 0.6:
            # Place along a corridor between two neighborhoods
            h1 = hood_centers[i % len(hood_centers)]
            h2 = hood_centers[(i + rng.randint(1, max(2, len(hood_centers))))
                              % len(hood_centers)]
            t = rng.uniform(0.2, 0.8)
            x = h1[0] * (1 - t) + h2[0] * t + rng.uniform(-0.3, 0.3)
            y = h1[1] * (1 - t) + h2[1] * t + rng.uniform(-0.3, 0.3)
        else:
            # Place within a neighborhood
            hood = hood_centers[rng.randint(0, len(hood_centers))]
            x = hood[0] + rng.uniform(-city_radius * 0.3, city_radius * 0.3)
            y = hood[1] + rng.uniform(-city_radius * 0.3, city_radius * 0.3)

        G.add_node(node_id, label="Intersection", infra_type="intersection",
                   category="road")
        pos[node_id] = (x, y)
        intersection_ids.append(node_id)
        node_id += 1

    # ── Step 4: Build road network using Delaunay + KNN ──
    all_nodes = list(G.nodes())
    positions_array = np.array([pos[n] for n in all_nodes])

    from scipy.spatial import KDTree, Delaunay

    # Use Delaunay triangulation for natural road network
    if len(positions_array) >= 4:
        try:
            tri = Delaunay(positions_array)
            for simplex in tri.simplices:
                for j in range(3):
                    n1 = all_nodes[simplex[j]]
                    n2 = all_nodes[simplex[(j + 1) % 3]]
                    if not G.has_edge(n1, n2):
                        d = np.linalg.norm(positions_array[simplex[j]] -
                                           positions_array[simplex[(j + 1) % 3]])
                        # Only add if not too long (prevents unrealistic cross-city edges)
                        if d < city_radius * 0.7:
                            G.add_edge(n1, n2, edge_type="road", weight=d)
        except Exception:
            pass

    # Also add KNN for connectivity insurance
    tree = KDTree(positions_array)
    k = min(3, len(all_nodes) - 1)
    for i, node in enumerate(all_nodes):
        dists, indices = tree.query(positions_array[i], k=k+1)
        for j_idx, dist in zip(indices[1:], dists[1:]):
            neighbor = all_nodes[j_idx]
            if not G.has_edge(node, neighbor):
                G.add_edge(node, neighbor, edge_type="road", weight=dist)

    # ── Step 5: Add utility connections ──
    # Power lines: Power Plant -> Substations -> other facilities
    for pp in infra_nodes.get("Power Plant", []):
        for sub in infra_nodes.get("Substation", []):
            G.add_edge(pp, sub, edge_type="power",
                       weight=np.linalg.norm(np.array(pos[pp]) - np.array(pos[sub])))
        for hosp in infra_nodes.get("Hospital", []):
            G.add_edge(pp, hosp, edge_type="power",
                       weight=np.linalg.norm(np.array(pos[pp]) - np.array(pos[hosp])))

    # Substations -> nearby facilities
    for sub in infra_nodes.get("Substation", []):
        sub_pos = np.array(pos[sub])
        for nid in G.nodes():
            if G.nodes[nid].get("infra_type") not in ("intersection", "Substation", "Power Plant"):
                d = np.linalg.norm(np.array(pos[nid]) - sub_pos)
                if d < city_radius * 0.5:
                    if rng.random() < 0.35:
                        G.add_edge(sub, nid, edge_type="power", weight=d)

    # Water pipes: Water Treatment -> Water Supply -> Food Services
    for wt in infra_nodes.get("Water Treatment", []):
        for ws in infra_nodes.get("Water Supply", []):
            G.add_edge(wt, ws, edge_type="water",
                       weight=np.linalg.norm(np.array(pos[wt]) - np.array(pos[ws])))
        for hosp in infra_nodes.get("Hospital", []):
            G.add_edge(wt, hosp, edge_type="water",
                       weight=np.linalg.norm(np.array(pos[wt]) - np.array(pos[hosp])))

    # Emergency routes: Hospitals <-> Fire Stations <-> Police
    emergency_types = ["Hospital", "Fire Station", "Police Station", "Ambulance Depot"]
    emergency_nodes = []
    for et in emergency_types:
        emergency_nodes.extend(infra_nodes.get(et, []))

    for i, n1 in enumerate(emergency_nodes):
        for n2 in emergency_nodes[i+1:]:
            d = np.linalg.norm(np.array(pos[n1]) - np.array(pos[n2]))
            if d < city_radius * 0.7:
                G.add_edge(n1, n2, edge_type="emergency", weight=d)

    return G, pos, infra_nodes, city_radius


# ─────────────────────────────────────────────────────────────
# VISUALIZATION
# ─────────────────────────────────────────────────────────────

def plot_city_network(G, pos, infra_nodes, city_name, city_radius, save_path=None):
    """Create a beautiful matplotlib visualization of the city infrastructure."""

    fig, ax = plt.subplots(1, 1, figsize=(18, 16), facecolor="#0D1117")
    ax.set_facecolor("#0D1117")

    # ── Draw city boundary ──
    circle = plt.Circle((0, 0), city_radius * 1.1, fill=False,
                         edgecolor="#21262D", linewidth=2, linestyle="--", alpha=0.5)
    ax.add_patch(circle)
    # Inner zones
    for r_frac, alpha in [(0.33, 0.15), (0.66, 0.1)]:
        zone = plt.Circle((0, 0), city_radius * r_frac, fill=True,
                           facecolor="#161B22", edgecolor="#21262D",
                           linewidth=1, alpha=alpha)
        ax.add_patch(zone)

    # ── Draw edges by type ──
    for u, v, data in G.edges(data=True):
        etype = data.get("edge_type", "road")
        style = EDGE_STYLES.get(etype, EDGE_STYLES["road"])
        x = [pos[u][0], pos[v][0]]
        y = [pos[u][1], pos[v][1]]
        ax.plot(x, y, color=style["color"], linewidth=style["width"],
                linestyle=style["style"], alpha=style["alpha"], zorder=1)

    # ── Draw intersection nodes (tiny dots) ──
    int_nodes = [n for n in G.nodes() if G.nodes[n].get("infra_type") == "intersection"]
    if int_nodes:
        int_x = [pos[n][0] for n in int_nodes]
        int_y = [pos[n][1] for n in int_nodes]
        ax.scatter(int_x, int_y, c="#21262D", s=8, zorder=2, alpha=0.4)

    # ── Draw infrastructure nodes ──
    for infra_type, nodes in infra_nodes.items():
        if not nodes:
            continue
        cfg = INFRASTRUCTURE[infra_type]
        x = [pos[n][0] for n in nodes]
        y = [pos[n][1] for n in nodes]

        # Glow effect
        ax.scatter(x, y, c=cfg["color"], s=cfg["size"] * 3, alpha=0.08,
                   marker="o", zorder=3)
        ax.scatter(x, y, c=cfg["color"], s=cfg["size"] * 1.6, alpha=0.15,
                   marker="o", zorder=3)

        # Main node
        ax.scatter(x, y, c=cfg["color"], s=cfg["size"],
                   marker=cfg["shape"], edgecolors="white",
                   linewidths=0.5, zorder=5, label=infra_type)

        # Labels
        for n in nodes:
            ax.annotate(G.nodes[n]["label"], pos[n],
                        textcoords="offset points", xytext=(6, 6),
                        fontsize=5.5, color=cfg["color"], alpha=0.7,
                        fontfamily="monospace", fontweight="bold")

    # ── Legend ──
    legend_elements = []
    for infra_type, cfg in INFRASTRUCTURE.items():
        legend_elements.append(
            Line2D([0], [0], marker=cfg["shape"], color="none",
                   markerfacecolor=cfg["color"], markeredgecolor="white",
                   markersize=8, label=f"  {infra_type}")
        )
    # Edge types
    legend_elements.append(Line2D([0], [0], color="none", label=""))  # spacer
    legend_elements.append(Line2D([0], [0], color="none", label="── Connections ──"))
    for etype, style in EDGE_STYLES.items():
        legend_elements.append(
            Line2D([0], [0], color=style["color"], linewidth=style["width"]*1.5,
                   linestyle=style["style"], alpha=0.8,
                   label=f"  {etype.title()} Network")
        )

    legend = ax.legend(handles=legend_elements, loc="upper left",
                       fontsize=7, facecolor="#161B22", edgecolor="#30363D",
                       labelcolor="#C9D1D9", framealpha=0.95,
                       borderpad=1.2, handletextpad=0.8)
    legend.get_frame().set_linewidth(1.5)

    # ── Stats box ──
    n_infra = sum(1 for n in G.nodes() if G.nodes[n].get("infra_type") != "intersection")
    n_roads = sum(1 for _, _, d in G.edges(data=True) if d.get("edge_type") == "road")
    n_power = sum(1 for _, _, d in G.edges(data=True) if d.get("edge_type") == "power")
    n_water = sum(1 for _, _, d in G.edges(data=True) if d.get("edge_type") == "water")
    n_emerg = sum(1 for _, _, d in G.edges(data=True) if d.get("edge_type") == "emergency")

    stats_text = (
        f"Infrastructure Nodes: {n_infra}\n"
        f"Road Connections: {n_roads}\n"
        f"Power Lines: {n_power}\n"
        f"Water Pipes: {n_water}\n"
        f"Emergency Routes: {n_emerg}\n"
        f"Total Edges: {G.number_of_edges()}"
    )
    props = dict(boxstyle="round,pad=0.8", facecolor="#161B22",
                 edgecolor="#30363D", alpha=0.95)
    ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
            fontsize=7, color="#8B949E", fontfamily="monospace",
            verticalalignment="bottom", horizontalalignment="right",
            bbox=props)

    # ── Title ──
    ax.set_title(f"🏙  {city_name.upper()}  —  Infrastructure Network",
                 fontsize=22, color="#F0F6FC", fontweight="bold",
                 fontfamily="monospace", pad=20)
    ax.text(0.5, 1.01, "Hospitals • Fire Stations • Power Plants • Shelters • Food Services • Utilities",
            transform=ax.transAxes, fontsize=9, color="#484F58",
            ha="center", fontfamily="monospace")

    # ── Styling ──
    ax.set_aspect("equal")
    margin = city_radius * 1.3
    ax.set_xlim(-margin, margin)
    ax.set_ylim(-margin, margin)
    ax.grid(True, alpha=0.05, color="#30363D")
    ax.tick_params(colors="#30363D", labelsize=6)
    for spine in ax.spines.values():
        spine.set_color("#21262D")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=200, bbox_inches="tight",
                    facecolor="#0D1117", edgecolor="none")
        print(f"✅ Saved to: {save_path}")

    return fig


def print_network_analysis(G, infra_nodes, city_name):
    """Print graph analysis stats."""
    print(f"\n{'='*60}")
    print(f"  NETWORK ANALYSIS: {city_name.upper()}")
    print(f"{'='*60}")

    print(f"\n  Total Nodes:  {G.number_of_nodes()}")
    print(f"  Total Edges:  {G.number_of_edges()}")
    print(f"  Density:      {nx.density(G):.4f}")

    # Connected?
    if nx.is_connected(G):
        print(f"  Connected:    ✅ Yes")
        print(f"  Avg Path Len: {nx.average_shortest_path_length(G, weight='weight'):.2f}")
    else:
        comps = list(nx.connected_components(G))
        print(f"  Connected:    ❌ No ({len(comps)} components)")

    print(f"\n  {'Type':<22} {'Count':>6}  {'Avg Degree':>10}")
    print(f"  {'─'*22} {'─'*6}  {'─'*10}")
    for infra_type, nodes in infra_nodes.items():
        if nodes:
            avg_deg = np.mean([G.degree(n) for n in nodes])
            print(f"  {infra_type:<22} {len(nodes):>6}  {avg_deg:>10.1f}")

    # Most connected nodes
    print(f"\n  🔗 Top 5 Most Connected Nodes:")
    degree_sorted = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    for node, deg in degree_sorted[:5]:
        label = G.nodes[node].get("label", "?")
        itype = G.nodes[node].get("infra_type", "?")
        if itype != "intersection":
            print(f"     {label} ({itype}) — {deg} connections")

    # Betweenness centrality for infrastructure nodes
    print(f"\n  🎯 Top 5 Critical Nodes (Betweenness Centrality):")
    bc = nx.betweenness_centrality(G, weight="weight")
    infra_bc = {n: v for n, v in bc.items()
                if G.nodes[n].get("infra_type") != "intersection"}
    for node, cent in sorted(infra_bc.items(), key=lambda x: x[1], reverse=True)[:5]:
        label = G.nodes[node].get("label", "?")
        print(f"     {label} — centrality: {cent:.4f}")

    print(f"\n{'='*60}\n")


# ─────────────────────────────────────────────────────────────
# JSON EXPORT: Adjacency list + full graph data
# ─────────────────────────────────────────────────────────────

def export_to_json(G, pos, infra_nodes, city_name, city_radius, json_path):
    """
    Export the full city infrastructure network as JSON including:
    - City metadata
    - All nodes with attributes
    - Adjacency list (per node: list of neighbors with edge type & weight)
    - Flat edge list
    - Network statistics
    """

    # ── Build node data ──
    nodes_data = {}
    for nid in G.nodes():
        attrs = G.nodes[nid]
        infra_type = attrs.get("infra_type", "unknown")
        if infra_type == "intersection":
            continue  # skip road intersections for cleaner JSON

        neighbors = []
        for neighbor in G.neighbors(nid):
            n_attrs = G.nodes[neighbor]
            if n_attrs.get("infra_type") == "intersection":
                continue
            edge_data = G.edges[nid, neighbor]
            neighbors.append({
                "node_id":    neighbor,
                "label":      n_attrs.get("label", ""),
                "type":       n_attrs.get("infra_type", ""),
                "edge_type":  edge_data.get("edge_type", "road"),
                "distance":   round(edge_data.get("weight", 0), 4),
            })

        # Sort neighbors by distance
        neighbors.sort(key=lambda x: x["distance"])

        nodes_data[str(nid)] = {
            "id":         nid,
            "label":      attrs.get("label", ""),
            "type":       infra_type,
            "category":   attrs.get("category", ""),
            "position":   {"x": round(pos[nid][0], 4), "y": round(pos[nid][1], 4)},
            "degree":     G.degree(nid),
            "neighbors":  neighbors,
        }

    # ── Adjacency list (compact: node_label -> [neighbor_labels]) ──
    adjacency_list = {}
    for nid_str, ndata in nodes_data.items():
        key = ndata["label"]
        adjacency_list[key] = [
            n["label"] for n in ndata["neighbors"]
        ]

    # ── Typed adjacency lists (per connection type) ──
    typed_adjacency = {etype: {} for etype in ["road", "power", "water", "emergency"]}
    for nid_str, ndata in nodes_data.items():
        label = ndata["label"]
        for n in ndata["neighbors"]:
            etype = n["edge_type"]
            if etype in typed_adjacency:
                if label not in typed_adjacency[etype]:
                    typed_adjacency[etype][label] = []
                typed_adjacency[etype][label].append(n["label"])

    # ── Flat edge list ──
    edge_list = []
    seen_edges = set()
    for u, v, data in G.edges(data=True):
        u_type = G.nodes[u].get("infra_type", "")
        v_type = G.nodes[v].get("infra_type", "")
        if u_type == "intersection" or v_type == "intersection":
            continue
        key = (min(u, v), max(u, v))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edge_list.append({
            "from_id":    u,
            "from_label": G.nodes[u].get("label", ""),
            "to_id":      v,
            "to_label":   G.nodes[v].get("label", ""),
            "edge_type":  data.get("edge_type", "road"),
            "distance":   round(data.get("weight", 0), 4),
        })

    # ── Summary counts ──
    infra_summary = {}
    for infra_type, nids in infra_nodes.items():
        infra_summary[infra_type] = {
            "count": len(nids),
            "category": INFRASTRUCTURE[infra_type]["category"],
            "node_ids": nids,
        }

    edge_type_counts = {}
    for e in edge_list:
        et = e["edge_type"]
        edge_type_counts[et] = edge_type_counts.get(et, 0) + 1

    # ── Centrality metrics ──
    bc = nx.betweenness_centrality(G, weight="weight")
    infra_bc = {
        G.nodes[n].get("label", str(n)): round(v, 6)
        for n, v in bc.items()
        if G.nodes[n].get("infra_type") != "intersection"
    }
    top_central = dict(sorted(infra_bc.items(), key=lambda x: x[1], reverse=True)[:10])

    # ── Assemble final JSON ──
    output = {
        "city": {
            "name":   city_name,
            "radius": round(city_radius, 4),
        },
        "summary": {
            "total_infrastructure_nodes": len(nodes_data),
            "total_edges": len(edge_list),
            "edge_type_counts": edge_type_counts,
            "infrastructure_counts": {k: v["count"] for k, v in infra_summary.items()},
            "is_connected": nx.is_connected(G),
            "graph_density": round(nx.density(G), 6),
        },
        "top_critical_nodes": top_central,
        "adjacency_list": adjacency_list,
        "typed_adjacency_lists": typed_adjacency,
        "nodes": nodes_data,
        "edges": edge_list,
    }

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ JSON exported to: {json_path}")
    print(f"   Nodes: {len(nodes_data)} | Edges: {len(edge_list)}")
    print(f"   Adjacency entries: {len(adjacency_list)}")

    return output


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="City Infrastructure Network Visualizer")
    parser.add_argument("--city", type=str, default="Boston",
                        help="City name (default: Boston)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed (default: derived from city name)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output image path (default: <city>_infrastructure.png)")
    parser.add_argument("--json", type=str, default=None,
                        help="Output JSON path (default: <city>_infrastructure.json)")
    parser.add_argument("--no-plot", action="store_true",
                        help="Skip plot generation, only export JSON")
    args = parser.parse_args()

    city_name = args.city
    city_slug = city_name.lower().replace(' ', '_')
    output_path = args.output or f"{city_slug}_infrastructure.png"
    json_path = args.json or f"{city_slug}_infrastructure.json"

    print(f"🏙  Generating infrastructure network for: {city_name}")

    G, pos, infra_nodes, city_radius = generate_city_infrastructure(
        city_name, custom_seed=args.seed
    )

    print_network_analysis(G, infra_nodes, city_name)

    # Always export JSON
    export_to_json(G, pos, infra_nodes, city_name, city_radius, json_path)

    if not args.no_plot:
        fig = plot_city_network(G, pos, infra_nodes, city_name, city_radius,
                                save_path=output_path)
        plt.close(fig)

    print("Done!")


if __name__ == "__main__":
    main()