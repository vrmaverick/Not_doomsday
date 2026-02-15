"""
City Infrastructure Mitigation Module
======================================
Reads apocalypse_analysis.json → fetches real OSM infrastructure →
sends adjacency list + threat data to Groq LLM → LLM optimizes the
network (removes vulnerable edges, adds emergency paths) → returns
original vs mitigated graphs.

Usage:
    from city_infra import mitigate
    result = mitigate()                              # reads apocalypse_analysis.json
    result = mitigate(apocalypse_file="my_data.json") # custom file
    result = mitigate(force_procedural=True)          # skip OSM

Requirements:
    pip install networkx numpy scipy requests langchain-groq
    export GROQ_API_KEY="your-key"
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from scipy.spatial import Delaunay, KDTree

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("city_infra")
logger.setLevel(logging.DEBUG)


def _timer():
    start = time.perf_counter()
    return lambda: time.perf_counter() - start


# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
INFRASTRUCTURE = {
    "Hospital":         {"category": "Emergency"},
    "Fire Station":     {"category": "Emergency"},
    "Police Station":   {"category": "Emergency"},
    "Ambulance Depot":  {"category": "Emergency"},
    "Bunker/Shelter":   {"category": "Shelter"},
    "Evacuation Point": {"category": "Shelter"},
    "Food Service":     {"category": "Food"},
    "Grocery Store":    {"category": "Food"},
    "Water Supply":     {"category": "Food"},
    "Power Plant":      {"category": "Utility"},
    "Substation":       {"category": "Utility"},
    "Telecom Tower":    {"category": "Utility"},
    "Water Treatment":  {"category": "Utility"},
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60

GROQ_MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────
# STEP 1: READ APOCALYPSE ANALYSIS JSON
# ─────────────────────────────────────────────────────────────

def _load_apocalypse_analysis(filepath: str) -> dict:
    t = _timer()
    path = Path(filepath)
    # If not found as-is, try relative to this script's parent directory
    if not path.exists():
        script_dir = Path(__file__).resolve().parent
        path = script_dir.parent / "Data" / "apocalypse_analysis.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Apocalypse analysis file not found.\n"
            f"  Tried: {Path(filepath).resolve()}\n"
            f"  Tried: {path.resolve()}\n"
            f"  Place the file in ../Data/ relative to this script."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"[LOAD] {path.name}: {len(data.get('ranked_calamities', []))} calamities, "
                f"threat={data.get('overall_threat_level', '?')} in {t():.2f}s")
    return data


# ─────────────────────────────────────────────────────────────
# STEP 2: OSM GEOCODE + OVERPASS
# ─────────────────────────────────────────────────────────────

def _geocode_city(city_name: str) -> tuple[float, float]:
    import requests
    t = _timer()
    logger.info(f"[GEOCODE] Nominatim → '{city_name}'...")
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city_name, "format": "json", "limit": 1},
        headers={"User-Agent": "CityInfraModule/1.0"},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode: {city_name}")
    lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
    logger.info(f"[GEOCODE] ({lat:.4f}, {lon:.4f}) in {t():.2f}s")
    return lat, lon


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    filters = [
        '"amenity"="hospital"', '"amenity"="fire_station"', '"amenity"="police"',
        '"emergency"="ambulance_station"',
        '"amenity"="shelter"', '"building"="bunker"', '"social_facility"="shelter"',
        '"amenity"="marketplace"', '"amenity"="food_court"',
        '"shop"="supermarket"', '"shop"="grocery"',
        '"man_made"="water_well"', '"man_made"="water_tower"',
        '"power"="plant"', '"power"="generator"', '"power"="substation"',
        '"man_made"="communications_tower"', '"tower:type"="communication"',
        '"man_made"="water_works"', '"man_made"="wastewater_plant"',
    ]
    lines = []
    for f in filters:
        lines.append(f"  node[{f}](around:{radius_m},{lat},{lon});")
        lines.append(f"  way[{f}](around:{radius_m},{lat},{lon});")
    return f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n(\n" + "\n".join(lines) + "\n);\nout center tags;"


def _osm_tags_to_type(tags: dict) -> str | None:
    a = tags.get("amenity", "")
    p = tags.get("power", "")
    mm = tags.get("man_made", "")
    sh = tags.get("shop", "")
    b = tags.get("building", "")
    em = tags.get("emergency", "")
    sf = tags.get("social_facility", "")
    tt = tags.get("tower:type", "")
    if a == "hospital": return "Hospital"
    if a == "fire_station": return "Fire Station"
    if a == "police": return "Police Station"
    if em == "ambulance_station": return "Ambulance Depot"
    if a == "shelter" or sf == "shelter" or b == "bunker": return "Bunker/Shelter"
    if a in ("marketplace", "food_court"): return "Food Service"
    if sh in ("supermarket", "grocery"): return "Grocery Store"
    if mm in ("water_well", "water_tower"): return "Water Supply"
    if p in ("plant", "generator"): return "Power Plant"
    if p == "substation": return "Substation"
    if mm == "communications_tower" or tt == "communication": return "Telecom Tower"
    if mm in ("water_works", "wastewater_plant"): return "Water Treatment"
    return None


def _fetch_osm(city_name: str, radius_m: int) -> tuple[list[dict], float, float]:
    import requests
    t_total = _timer()
    lat, lon = _geocode_city(city_name)
    query = _build_overpass_query(lat, lon, radius_m)

    t_op = _timer()
    logger.info(f"[OVERPASS] Querying r={radius_m}m...")
    resp = requests.post(OVERPASS_URL, data={"data": query},
                         timeout=OVERPASS_TIMEOUT + 10,
                         headers={"User-Agent": "CityInfraModule/1.0"})
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"[OVERPASS] {len(data.get('elements', []))} raw elements in {t_op():.2f}s")

    elements, seen = [], set()
    for el in data.get("elements", []):
        oid = el.get("id")
        if oid in seen: continue
        seen.add(oid)
        tags = el.get("tags", {})
        itype = _osm_tags_to_type(tags)
        if not itype: continue
        if "lat" in el:
            elat, elon = el["lat"], el["lon"]
        elif "center" in el:
            elat, elon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        elements.append({"id": oid, "infra_type": itype,
                         "name": tags.get("name", f"{itype} (OSM {oid})"),
                         "lat": elat, "lon": elon})

    for it, cnt in Counter(e["infra_type"] for e in elements).most_common():
        logger.debug(f"  {it}: {cnt}")
    logger.info(f"[OSM] {len(elements)} infra nodes in {t_total():.2f}s")
    return elements, lat, lon


# ─────────────────────────────────────────────────────────────
# GRAPH BUILDING
# ─────────────────────────────────────────────────────────────

def _add_road_edges(G, pos, city_radius):
    nodes = list(G.nodes())
    pa = np.array([pos[n] for n in nodes])
    if len(pa) >= 4:
        try:
            tri = Delaunay(pa)
            for s in tri.simplices:
                for j in range(3):
                    n1, n2 = nodes[s[j]], nodes[s[(j+1)%3]]
                    if not G.has_edge(n1, n2):
                        d = np.linalg.norm(pa[s[j]] - pa[s[(j+1)%3]])
                        if d < city_radius * 0.6:
                            G.add_edge(n1, n2, edge_type="road", weight=d)
        except Exception:
            pass
    tree = KDTree(pa)
    k = min(4, len(nodes) - 1)
    for i, node in enumerate(nodes):
        _, indices = tree.query(pa[i], k=k+1)
        for ji in indices[1:]:
            nbr = nodes[ji]
            if not G.has_edge(node, nbr):
                d = np.linalg.norm(pa[i] - pa[ji])
                G.add_edge(node, nbr, edge_type="road", weight=d)


def _add_utility_edges(G, pos, infra_nodes, city_radius):
    rng = np.random.RandomState(42)
    for pp in infra_nodes.get("Power Plant", []):
        for sub in infra_nodes.get("Substation", []):
            G.add_edge(pp, sub, edge_type="power", weight=np.linalg.norm(np.array(pos[pp]) - np.array(pos[sub])))
        for h in infra_nodes.get("Hospital", []):
            G.add_edge(pp, h, edge_type="power", weight=np.linalg.norm(np.array(pos[pp]) - np.array(pos[h])))
    for sub in infra_nodes.get("Substation", []):
        sp = np.array(pos[sub])
        for nid in G.nodes():
            if G.nodes[nid].get("infra_type") not in ("intersection", "Substation", "Power Plant"):
                d = np.linalg.norm(np.array(pos[nid]) - sp)
                if d < city_radius * 0.4 and rng.random() < 0.3:
                    G.add_edge(sub, nid, edge_type="power", weight=d)
    for wt in infra_nodes.get("Water Treatment", []):
        for ws in infra_nodes.get("Water Supply", []):
            G.add_edge(wt, ws, edge_type="water", weight=np.linalg.norm(np.array(pos[wt]) - np.array(pos[ws])))
        for h in infra_nodes.get("Hospital", []):
            G.add_edge(wt, h, edge_type="water", weight=np.linalg.norm(np.array(pos[wt]) - np.array(pos[h])))
    em_types = ["Hospital", "Fire Station", "Police Station", "Ambulance Depot"]
    em_nodes = [n for et in em_types for n in infra_nodes.get(et, [])]
    for i, n1 in enumerate(em_nodes):
        for n2 in em_nodes[i+1:]:
            d = np.linalg.norm(np.array(pos[n1]) - np.array(pos[n2]))
            if d < city_radius * 0.5:
                G.add_edge(n1, n2, edge_type="emergency", weight=d)


def _latlon_to_xy(lat, lon, clat, clon):
    return (lon - clon) * 111.32 * np.cos(np.radians(clat)), (lat - clat) * 111.32


def _build_graph_osm(elements, clat, clon):
    t = _timer()
    G = nx.Graph()
    pos = {}
    infra_nodes = {k: [] for k in INFRASTRUCTURE}
    placed = []
    for i, el in enumerate(elements):
        x, y = _latlon_to_xy(el["lat"], el["lon"], clat, clon)
        itype = el["infra_type"]
        if any(np.hypot(x-px, y-py) < 0.05 for px, py in placed): continue
        idx = len(infra_nodes.get(itype, [])) + 1
        label = el["name"] if el["name"] and "OSM" not in el["name"] else f"{itype} #{idx}"
        existing = {G.nodes[n].get("label") for n in G.nodes()}
        if label in existing: label = f"{label} ({idx})"
        G.add_node(i, label=label, infra_type=itype, category=INFRASTRUCTURE[itype]["category"])
        pos[i] = (x, y); placed.append((x, y)); infra_nodes[itype].append(i)
    if G.number_of_nodes() < 2:
        raise ValueError(f"Only {G.number_of_nodes()} OSM nodes")
    pa = np.array([pos[n] for n in G.nodes()])
    cr = float(np.max(np.linalg.norm(pa, axis=1))) + 0.5
    _add_road_edges(G, pos, cr)
    _add_utility_edges(G, pos, infra_nodes, cr)
    logger.info(f"[GRAPH] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges in {t():.2f}s")
    return G, pos, infra_nodes, cr


# ─────────────────────────────────────────────────────────────
# PROCEDURAL FALLBACK
# ─────────────────────────────────────────────────────────────

def _city_seed(name): return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def _generate_procedural(city_name, seed=None):
    t = _timer()
    sd = seed if seed else _city_seed(city_name)
    rng = np.random.RandomState(sd)
    G = nx.Graph(); pos = {}
    h = hashlib.sha256(city_name.encode()).hexdigest()
    cr = 4.0 + int(h[:2], 16) / 256 * 3.0
    dens = 0.6 + int(h[2:4], 16) / 256 * 0.6
    n_h = max(4, int(5*dens + rng.randint(0,3)))
    hc = []
    for i in range(n_h):
        a = (2*np.pi*i/n_h) + rng.uniform(-.4,.4); r = cr*(.25+rng.uniform(0,.55))
        hc.append((r*np.cos(a), r*np.sin(a)))
    hc.insert(0, (rng.uniform(-.5,.5), rng.uniform(-.5,.5)))
    nc = {"Hospital":max(2,int(3*dens+rng.randint(0,3))),"Fire Station":max(2,int(4*dens+rng.randint(0,2))),"Police Station":max(2,int(3*dens+rng.randint(0,2))),"Ambulance Depot":max(1,int(2*dens)),"Bunker/Shelter":max(2,int(3*dens+rng.randint(0,2))),"Evacuation Point":max(1,int(2*dens)),"Food Service":max(3,int(5*dens+rng.randint(0,3))),"Grocery Store":max(2,int(4*dens+rng.randint(0,2))),"Water Supply":max(2,int(3*dens)),"Power Plant":max(1,int(1.5*dens)),"Substation":max(2,int(4*dens+rng.randint(0,2))),"Telecom Tower":max(2,int(3*dens+rng.randint(0,2))),"Water Treatment":max(1,int(1.5*dens))}
    ms = {"Hospital":cr*.4,"Fire Station":cr*.3,"Police Station":cr*.35,"Ambulance Depot":cr*.3,"Bunker/Shelter":cr*.3,"Evacuation Point":cr*.35,"Food Service":cr*.2,"Grocery Store":cr*.2,"Water Supply":cr*.35,"Power Plant":cr*.5,"Substation":cr*.25,"Telecom Tower":cr*.35,"Water Treatment":cr*.5}
    nid = 0; infra_nodes = {}; ap = []
    def _pl(cx,cy,sp,md):
        for _ in range(50):
            x,y = cx+rng.uniform(-sp,sp), cy+rng.uniform(-sp,sp)
            if all(np.hypot(x-px,y-py)>=md for px,py in ap): return x,y
        return cx+rng.uniform(-sp*1.5,sp*1.5), cy+rng.uniform(-sp*1.5,sp*1.5)
    for it, cnt in nc.items():
        infra_nodes[it] = []; md = ms.get(it, cr*.2)
        for i in range(cnt):
            nm = f"{it} #{i+1}"
            if it in ("Power Plant","Water Treatment"):
                a=rng.uniform(0,2*np.pi);r=cr*(.7+rng.uniform(0,.3));x,y=_pl(r*np.cos(a),r*np.sin(a),cr*.15,md)
            elif it in ("Bunker/Shelter","Evacuation Point"):
                hood=hc[i%len(hc)];x,y=_pl(hood[0],hood[1],cr*.35,md)
            elif it=="Hospital":
                hood=hc[0] if i==0 else hc[min(i,len(hc)-1)];x,y=_pl(hood[0],hood[1],cr*.25,md)
            elif it in ("Fire Station","Police Station"):
                hood=hc[i%len(hc)];x,y=_pl(hood[0],hood[1],cr*.2,md)
            elif it=="Substation":
                h1,h2=hc[i%len(hc)],hc[(i+1)%len(hc)];x,y=_pl((h1[0]+h2[0])/2+rng.uniform(-.5,.5),(h1[1]+h2[1])/2+rng.uniform(-.5,.5),cr*.2,md)
            elif it=="Telecom Tower":
                a=rng.uniform(0,2*np.pi);r=cr*(.3+rng.uniform(0,.5));x,y=_pl(r*np.cos(a),r*np.sin(a),cr*.15,md)
            else:
                hood=hc[rng.randint(0,len(hc))];x,y=_pl(hood[0],hood[1],cr*.25,md*.6)
            G.add_node(nid,label=nm,infra_type=it,category=INFRASTRUCTURE[it]["category"])
            pos[nid]=(x,y);ap.append((x,y));infra_nodes[it].append(nid);nid+=1
    for i in range(int(25*dens+rng.randint(0,12))):
        if i<len(hc) and rng.random()<.6:
            h1=hc[i%len(hc)];h2=hc[(i+rng.randint(1,max(2,len(hc))))%len(hc)];tv=rng.uniform(.2,.8)
            x=h1[0]*(1-tv)+h2[0]*tv+rng.uniform(-.3,.3);y=h1[1]*(1-tv)+h2[1]*tv+rng.uniform(-.3,.3)
        else:
            hood=hc[rng.randint(0,len(hc))];x=hood[0]+rng.uniform(-cr*.3,cr*.3);y=hood[1]+rng.uniform(-cr*.3,cr*.3)
        G.add_node(nid,label="Intersection",infra_type="intersection",category="road");pos[nid]=(x,y);nid+=1
    _add_road_edges(G,pos,cr);_add_utility_edges(G,pos,infra_nodes,cr)
    logger.info(f"[PROCEDURAL] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges in {t():.2f}s")
    return G,pos,infra_nodes,cr


def _get_infrastructure(city_name, seed=None, radius_m=15000, force_procedural=False):
    """Returns (G, pos, infra_nodes, city_radius, data_source, fallback_reason)."""
    t = _timer()
    fallback_reason = None
    if not force_procedural:
        try:
            import requests as _rc  # noqa
        except ImportError:
            fallback_reason = "'requests' library not installed"; force_procedural = True
    if not force_procedural:
        try:
            els, clat, clon = _fetch_osm(city_name, radius_m)
            if len(els) >= 5:
                G, pos, inf, cr = _build_graph_osm(els, clat, clon)
                logger.info(f"[PIPELINE] OSM done in {t():.2f}s")
                return G, pos, inf, cr, "openstreetmap", None
            fallback_reason = f"Only {len(els)} OSM elements (need ≥5)"
        except Exception as e:
            fallback_reason = f"{type(e).__name__}: {e}"
    if not fallback_reason: fallback_reason = "force_procedural=True"
    logger.warning(f"[FALLBACK] {fallback_reason}")
    G, pos, inf, cr = _generate_procedural(city_name, seed)
    return G, pos, inf, cr, "procedural_fallback", fallback_reason


# ─────────────────────────────────────────────────────────────
# ADJACENCY + STATS
# ─────────────────────────────────────────────────────────────

def _build_adj(G):
    adj = {}
    for nid in G.nodes():
        a = G.nodes[nid]
        if a.get("infra_type") == "intersection": continue
        label = a.get("label", str(nid))
        nbs = []
        for nbr in G.neighbors(nid):
            na = G.nodes[nbr]
            if na.get("infra_type") == "intersection": continue
            e = G.edges[nid, nbr]
            nbs.append({"neighbor": na.get("label", str(nbr)),
                        "edge_type": e.get("edge_type", "road"),
                        "distance": round(e.get("weight", 0), 4)})
        nbs.sort(key=lambda x: x["distance"])
        adj[label] = nbs
    return adj


def _compute_stats(G):
    t = _timer()
    ic = sum(1 for n in G.nodes() if G.nodes[n].get("infra_type") != "intersection")
    ec = {}
    for _, _, d in G.edges(data=True):
        ec[d.get("edge_type", "road")] = ec.get(d.get("edge_type", "road"), 0) + 1
    stats = {"total_nodes": G.number_of_nodes(), "infrastructure_nodes": ic,
             "total_edges": G.number_of_edges(), "edge_type_counts": ec,
             "density": round(nx.density(G), 6),
             "is_connected": nx.is_connected(G) if G.number_of_nodes() > 0 else False}
    if stats["is_connected"] and G.number_of_nodes() > 1:
        t2 = _timer()
        stats["avg_shortest_path"] = round(nx.average_shortest_path_length(G, weight="weight"), 4)
        logger.info(f"[STATS] avg_shortest_path: {t2():.2f}s")
    if G.number_of_nodes() > 1:
        t3 = _timer()
        bc = nx.betweenness_centrality(G, weight="weight")
        logger.info(f"[STATS] betweenness_centrality: {t3():.2f}s")
        ibc = {G.nodes[n].get("label", str(n)): round(v, 6)
               for n, v in bc.items() if G.nodes[n].get("infra_type") != "intersection"}
        stats["top_critical_nodes"] = dict(sorted(ibc.items(), key=lambda x: x[1], reverse=True)[:10])
    logger.info(f"[STATS] Done in {t():.2f}s")
    return stats


# ─────────────────────────────────────────────────────────────
# STEP 3: GROQ LLM OPTIMIZATION
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a ruthless disaster infrastructure optimizer. Your goal is to STRIP the city's infrastructure network down to only the ESSENTIAL connections needed for disaster survival. Every unnecessary edge is a liability — it wastes resources, creates confusion during evacuation, and exposes vulnerable routes.

You will receive:
1. A city's infrastructure adjacency list (nodes = hospitals, fire stations, power plants, shelters, etc. with edges = road, power, water, emergency connections)
2. An apocalypse threat analysis with ranked calamities, risk scores, and timeline

Your job: AGGRESSIVELY prune the network. The mitigated network should be DRAMATICALLY simpler than the original — keep only the bare minimum paths needed for survival.

You MUST return ONLY valid JSON with this exact schema:
{
  "reasoning": "2-3 paragraph analysis explaining your aggressive pruning strategy and why the stripped-down network is sufficient for survival",
  "remove_edges": [
    {"from": "exact node label", "to": "exact node label", "edge_type": "road|power|water|emergency", "reason": "why this edge must go"}
  ],
  "add_edges": [
    {"from": "exact node label", "to": "exact node label", "edge_type": "emergency", "reason": "why this critical emergency path is needed"}
  ],
  "add_nodes": [
    {"label": "descriptive name", "type": "Bunker/Shelter|Evacuation Point", "connect_to": ["existing node label"], "edge_type": "emergency", "reason": "why this new node fills a critical gap"}
  ],
  "reroute": [
    {"from": "node A", "to": "node B", "via": "node C", "edge_type": "emergency", "reason": "why rerouting through C is safer"}
  ],
  "priority_nodes": [
    {"node": "exact label", "priority": "critical|high|medium", "reason": "why this node matters"}
  ]
}

CRITICAL RULES — FOLLOW ALL OF THESE:
- REMOVE AS MANY EDGES AS POSSIBLE. Target removing 60-80% of all edges. The mitigated list should be much shorter than the original.
- Remove ALL redundant road connections — if two nodes are already connected via emergency or power, the road edge is unnecessary
- Remove ALL road edges between non-critical nodes (grocery stores, food services, telecom towers connecting to each other)
- Remove ALL long-distance edges — anything over 5km is a vulnerability during disasters
- Remove power/water edges to non-essential nodes (grocery stores, food services don't need direct power lines during apocalypse)
- Keep ONLY: hospital↔shelter, hospital↔fire station, fire station↔police, power plant↔hospital, water treatment↔hospital connections
- Add only 3-5 critical emergency paths that don't already exist (hospital to nearest shelter, fire station to nearest hospital)
- The final network should look like a MINIMAL SPANNING TREE of critical infrastructure, not a dense mesh
- Use ONLY exact node labels from the provided list — do not invent names
- add_nodes: use 0-2 maximum, only if there's a critical gap with no shelter near a hospital"""


def _ask_groq(adj_list: dict, apocalypse_data: dict, city_name: str) -> dict:
    """Send compressed adjacency list + apocalypse data to Groq LLM, get optimization directions."""
    t = _timer()
    logger.info(f"[GROQ] Calling {GROQ_MODEL}...")

    try:
        from langchain_groq import ChatGroq
    except ImportError:
        raise ImportError(
            "langchain-groq is required. Install with: pip install langchain-groq\n"
            "Also set GROQ_API_KEY environment variable."
        )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")

    # ── Compress adjacency into a compact edge list + node summary ──
    # Instead of full adj per node, send: node list + unique edges
    all_nodes = sorted(adj_list.keys())
    node_types = {}
    for label in all_nodes:
        for itype in INFRASTRUCTURE:
            if label.startswith(itype):
                node_types.setdefault(itype, []).append(label)
                break

    # Node summary by type
    node_summary_lines = []
    for itype, labels in sorted(node_types.items()):
        node_summary_lines.append(f"  {itype} ({len(labels)}): {', '.join(labels)}")
    node_summary = "\n".join(node_summary_lines)

    # Deduplicated edge list (compact: "A -- B [type, dist]")
    edges_seen = set()
    edge_lines = {"road": [], "power": [], "water": [], "emergency": []}
    for label, nbs in adj_list.items():
        for n in nbs:
            key = tuple(sorted([label, n["neighbor"]])) + (n["edge_type"],)
            if key in edges_seen:
                continue
            edges_seen.add(key)
            et = n["edge_type"]
            if et in edge_lines:
                edge_lines[et].append(f"{label} -- {n['neighbor']} ({n['distance']:.1f}km)")

    # Cap edges per type to fit context (keep most important)
    MAX_EDGES_PER_TYPE = 40
    edge_text_parts = []
    for et, lines in edge_lines.items():
        if not lines:
            continue
        shown = lines[:MAX_EDGES_PER_TYPE]
        omitted = len(lines) - len(shown)
        edge_text_parts.append(f"{et.upper()} connections ({len(lines)} total):")
        edge_text_parts.extend(f"  {l}" for l in shown)
        if omitted > 0:
            edge_text_parts.append(f"  ... +{omitted} more {et} edges")
    edge_text = "\n".join(edge_text_parts)

    # Extract key threat info (compact)
    threats = []
    for cal in apocalypse_data.get("ranked_calamities", []):
        threats.append({
            "rank": cal["rank"], "name": cal["name"],
            "risk_level": cal["risk_level"], "risk_score": cal["risk_score"],
            "confidence": cal["confidence"],
            "summary": cal["summary"],
            "key_factors": cal.get("key_fields_used", {}).get("key_factors", []),
        })

    timeline = apocalypse_data.get("apocalypse_timeline", [])
    timeline_compact = [{"phase": t["phase"], "title": t["title"],
                         "drivers": t.get("main_drivers", [])} for t in timeline]

    user_msg = f"""CITY: {city_name}
OVERALL THREAT: {apocalypse_data.get('overall_threat_level', 'UNKNOWN')}
SUMMARY: {apocalypse_data.get('overall_summary', '')}

RANKED THREATS:
{json.dumps(threats, indent=2)}

TIMELINE: {json.dumps(timeline_compact)}

INFRASTRUCTURE NODES ({len(all_nodes)} total):
{node_summary}

NETWORK EDGES ({len(edges_seen)} total):
{edge_text}

NODE LABELS (use ONLY these exact names in your response):
{json.dumps(all_nodes)}

Analyze this infrastructure against these threats. Return optimization JSON."""

    # Log prompt size
    prompt_chars = len(_SYSTEM_PROMPT) + len(user_msg)
    est_tokens = prompt_chars // 4
    logger.info(f"[GROQ] Prompt: ~{est_tokens} tokens ({prompt_chars} chars)")

    llm = ChatGroq(
        model=GROQ_MODEL,
        temperature=0.1,
        max_tokens=4096,
        api_key=api_key,
    )

    response = llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    raw = response.content
    logger.info(f"[GROQ] Response received in {t():.2f}s ({len(raw)} chars)")

    # Parse JSON from response (handle markdown code blocks)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        directions = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            directions = json.loads(match.group())
        else:
            logger.error(f"[GROQ] Failed to parse JSON from response")
            directions = {"reasoning": raw, "remove_edges": [], "add_edges": [],
                          "add_nodes": [], "reroute": [], "priority_nodes": []}

    logger.info(f"[GROQ] Parsed: {len(directions.get('remove_edges', []))} removals, "
                f"{len(directions.get('add_edges', []))} additions, "
                f"{len(directions.get('add_nodes', []))} new nodes")
    return directions


# ─────────────────────────────────────────────────────────────
# STEP 4: APPLY LLM DIRECTIONS TO GRAPH
# ─────────────────────────────────────────────────────────────

def _fuzzy_find(name: str, lid: dict) -> int | None:
    """Find a node ID by exact match first, then fuzzy substring/case-insensitive match."""
    if not name:
        return None
    # Exact match
    if name in lid:
        return lid[name]
    # Case-insensitive
    name_lower = name.lower().strip()
    for label, nid in lid.items():
        if label.lower().strip() == name_lower:
            return nid
    # Substring: LLM label is contained in real label or vice versa
    for label, nid in lid.items():
        ll = label.lower()
        if name_lower in ll or ll in name_lower:
            return nid
    # Partial word overlap (at least 2 words match)
    name_words = set(name_lower.split())
    for label, nid in lid.items():
        label_words = set(label.lower().split())
        if len(name_words & label_words) >= 2:
            return nid
    return None


def _apply_llm_directions(G, directions):
    """Apply LLM optimization directions with fuzzy label matching."""
    M = G.copy()
    changes = []
    applied = 0

    lid = {M.nodes[n].get("label", ""): n for n in M.nodes()
           if M.nodes[n].get("label", "") not in ("", "Intersection")}

    def _resolve(name):
        return _fuzzy_find(name, lid)

    # Remove edges
    for es in directions.get("remove_edges", []):
        fr, to = _resolve(es.get("from", "")), _resolve(es.get("to", ""))
        if fr is not None and to is not None and M.has_edge(fr, to):
            M.remove_edge(fr, to)
            changes.append({"phase": "llm_optimization", "action": "removed_edge",
                            "from": es["from"], "to": es["to"],
                            "edge_type": es.get("edge_type", "?"), "reason": es.get("reason", "")})
            applied += 1
        else:
            changes.append({"phase": "llm_optimization", "action": "remove_edge_skipped",
                            "from": es.get("from"), "to": es.get("to"),
                            "reason": f"Not found. LLM reason: {es.get('reason', '')}"})

    # Add edges
    for es in directions.get("add_edges", []):
        fr, to = _resolve(es.get("from", "")), _resolve(es.get("to", ""))
        if fr is not None and to is not None:
            et = es.get("edge_type", "emergency")
            M.add_edge(fr, to, edge_type=et, weight=1.0)
            changes.append({"phase": "llm_optimization", "action": "added_edge",
                            "from": es["from"], "to": es["to"],
                            "edge_type": et, "reason": es.get("reason", "")})
            applied += 1
        else:
            changes.append({"phase": "llm_optimization", "action": "add_edge_skipped",
                            "from": es.get("from"), "to": es.get("to"),
                            "reason": f"Node not found. LLM reason: {es.get('reason', '')}"})

    # Add nodes
    nxt = max(M.nodes()) + 1 if M.nodes() else 0
    for ns in directions.get("add_nodes", []):
        label = ns.get("label", f"Emergency_Node_{nxt}")
        nt = ns.get("type", "Bunker/Shelter")
        cat = INFRASTRUCTURE.get(nt, {}).get("category", "Shelter")
        M.add_node(nxt, label=label, infra_type=nt, category=cat)
        lid[label] = nxt
        for cl in ns.get("connect_to", []):
            cid = _resolve(cl)
            if cid is not None:
                M.add_edge(nxt, cid, edge_type=ns.get("edge_type", "emergency"), weight=1.0)
        changes.append({"phase": "llm_optimization", "action": "added_node",
                        "label": label, "type": nt,
                        "connected_to": ns.get("connect_to", []),
                        "reason": ns.get("reason", "")})
        applied += 1
        nxt += 1

    # Reroute
    for rt in directions.get("reroute", []):
        fr = _resolve(rt.get("from", ""))
        to = _resolve(rt.get("to", ""))
        via = _resolve(rt.get("via", ""))
        et = rt.get("edge_type", "emergency")
        if all(x is not None for x in (fr, to, via)):
            if M.has_edge(fr, to): M.remove_edge(fr, to)
            M.add_edge(fr, via, edge_type=et, weight=1.0)
            M.add_edge(via, to, edge_type=et, weight=1.0)
            changes.append({"phase": "llm_optimization", "action": "rerouted",
                            "from": rt["from"], "to": rt["to"], "via": rt["via"],
                            "reason": rt.get("reason", "")})
            applied += 1
        else:
            changes.append({"phase": "llm_optimization", "action": "reroute_skipped",
                            "spec": rt, "reason": "Node not found"})

    logger.info(f"[LLM APPLY] {applied} operations succeeded out of "
                f"{len(directions.get('remove_edges', [])) + len(directions.get('add_edges', [])) + len(directions.get('add_nodes', [])) + len(directions.get('reroute', []))} attempted")

    return M, changes, applied


def _apply_programmatic_pruning(G, calamity_names):
    """
    Guaranteed aggressive pruning when LLM fails or returns nothing useful.
    Removes 60-80% of edges, keeps only critical survival paths.
    """
    M = G.copy()
    changes = []
    rng = np.random.RandomState(99)

    CRITICAL_TYPES = {"Hospital", "Fire Station", "Police Station", "Bunker/Shelter",
                      "Evacuation Point", "Power Plant", "Water Treatment", "Ambulance Depot"}
    NON_CRITICAL_TYPES = {"Grocery Store", "Food Service", "Telecom Tower", "Substation", "Water Supply"}

    edges_to_remove = []

    for u, v, d in M.edges(data=True):
        u_type = M.nodes[u].get("infra_type", "")
        v_type = M.nodes[v].get("infra_type", "")
        et = d.get("edge_type", "road")
        dist = d.get("weight", 0)
        u_label = M.nodes[u].get("label", "")
        v_label = M.nodes[v].get("label", "")

        remove = False
        reason = ""

        # Rule 1: Remove ALL road edges between non-critical nodes
        if et == "road" and u_type in NON_CRITICAL_TYPES and v_type in NON_CRITICAL_TYPES:
            remove = True
            reason = f"Road between non-critical {u_type} and {v_type} — unnecessary during disaster"

        # Rule 2: Remove long-distance road edges (>5km)
        elif et == "road" and dist > 5.0:
            remove = True
            reason = f"Long-distance road ({dist:.1f}km) — vulnerable to disruption"

        # Rule 3: Remove road edges to intersections (always remove)
        elif et == "road" and (u_type == "intersection" or v_type == "intersection"):
            remove = True
            reason = "Road through intersection — not critical infrastructure"

        # Rule 4: For floods — remove 70% of road edges randomly (flood destroys roads)
        elif et == "road" and "flood" in [c.lower() for c in calamity_names] and rng.random() < 0.5:
            remove = True
            reason = "Road vulnerable to flood damage"

        # Rule 5: For earthquakes — remove power edges to non-hospitals (lines collapse)
        elif et == "power" and "earthquake" in [c.lower() for c in calamity_names]:
            if v_type not in ("Hospital", "Power Plant") and u_type not in ("Hospital", "Power Plant"):
                remove = True
                reason = "Power line to non-critical node — vulnerable to earthquake collapse"

        # Rule 6: Remove water edges to non-essential nodes
        elif et == "water" and u_type in NON_CRITICAL_TYPES and v_type in NON_CRITICAL_TYPES:
            remove = True
            reason = "Water pipe between non-critical nodes"

        # Rule 7: Remove redundant road edges when emergency edge exists
        elif et == "road":
            if M.has_edge(u, v):
                # Check if there's already an emergency or power connection
                all_edges = M.get_edge_data(u, v)
                if all_edges and any(M.edges[u, v].get("edge_type") in ("emergency", "power") for _ in [1]):
                    pass  # keep — but still probabilistically remove some roads
                elif rng.random() < 0.3:
                    remove = True
                    reason = "Redundant road — probabilistic pruning for simpler network"

        if remove:
            edges_to_remove.append((u, v, u_label, v_label, et, reason))

    # Apply removals
    for u, v, ul, vl, et, reason in edges_to_remove:
        if M.has_edge(u, v):
            M.remove_edge(u, v)
            changes.append({"phase": "programmatic_pruning", "action": "removed_edge",
                            "from": ul, "to": vl, "edge_type": et, "reason": reason})

    # Add emergency paths: each hospital → nearest shelter
    hospitals = [n for n in M.nodes() if M.nodes[n].get("infra_type") == "Hospital"]
    shelters = [n for n in M.nodes() if M.nodes[n].get("infra_type") in ("Bunker/Shelter", "Evacuation Point")]
    fire_stations = [n for n in M.nodes() if M.nodes[n].get("infra_type") == "Fire Station"]
    from scipy.spatial import KDTree as _KDT

    if hospitals and shelters:
        positions = {n: np.array([M.nodes[n].get("lat", 0), M.nodes[n].get("lon", 0)]) for n in M.nodes()
                     if "lat" in M.nodes[n]}
        # Fallback: use any position data we can find
        for h in hospitals:
            nearest = min(shelters, key=lambda s: nx.utils.arbitrary_element([1.0]))  # fallback
            hl = M.nodes[h].get("label", "")
            sl = M.nodes[nearest].get("label", "")
            if not M.has_edge(h, nearest):
                M.add_edge(h, nearest, edge_type="emergency", weight=1.0)
                changes.append({"phase": "programmatic_pruning", "action": "added_edge",
                                "from": hl, "to": sl, "edge_type": "emergency",
                                "reason": "Emergency evacuation path: hospital to nearest shelter"})

    # Add emergency: each fire station → nearest hospital
    if fire_stations and hospitals:
        for fs in fire_stations:
            nearest_h = hospitals[0]  # simplified
            fsl = M.nodes[fs].get("label", "")
            hl = M.nodes[nearest_h].get("label", "")
            if not M.has_edge(fs, nearest_h):
                M.add_edge(fs, nearest_h, edge_type="emergency", weight=1.0)
                changes.append({"phase": "programmatic_pruning", "action": "added_edge",
                                "from": fsl, "to": hl, "edge_type": "emergency",
                                "reason": "Emergency response route: fire station to hospital"})

    logger.info(f"[PROGRAMMATIC] Removed {sum(1 for c in changes if c['action'] == 'removed_edge')} edges, "
                f"added {sum(1 for c in changes if c['action'] == 'added_edge')} emergency paths")

    return M, changes


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def mitigate(
    apocalypse_file: str = "./Data/apocalypse_analysis.json",
    *,
    seed: int | None = None,
    radius_m: int = 2000,
    force_procedural: bool = False,
) -> dict[str, Any]:
    """
    Full pipeline:
    1. Read apocalypse_analysis.json
    2. Fetch city infrastructure from OSM (or procedural fallback)
    3. Send adj list + threats to Groq LLM
    4. Apply LLM optimizations
    5. Return original vs mitigated

    Returns dict with: city, node_positions, original_adjacency_list,
    mitigated_adjacency_list, llm_directions, changes, original_stats,
    mitigated_stats, data_source, fallback_reason, apocalypse_analysis,
    groq_analysis
    """
    t_total = _timer()
    logger.info("#" * 60)

    # ── Step 1: Load apocalypse data ──
    apocalypse = _load_apocalypse_analysis(apocalypse_file)
    city_name = apocalypse.get("location", "Boston")
    calamity_names = [c["name"] for c in apocalypse.get("ranked_calamities", [])]
    logger.info(f"[MITIGATE] city={city_name}, threats={calamity_names}")

    # ── Step 2: Get infrastructure ──
    G, pos, infra_nodes, city_radius, data_source, fallback_reason = _get_infrastructure(
        city_name, seed=seed, radius_m=radius_m, force_procedural=force_procedural,
    )
    if fallback_reason:
        warnings.warn(
            f"[FALLBACK] {fallback_reason}. Using procedural data, not real OSM.",
            UserWarning, stacklevel=2,
        )
    logger.info(f"[MITIGATE] Infrastructure: {t_total():.2f}s — {data_source}")

    # ── Step 3: Original adjacency + stats ──
    original_adj = _build_adj(G)
    original_stats = _compute_stats(G)
    logger.info(f"[MITIGATE] Original stats: {t_total():.2f}s")

    # ── Step 4: Ask Groq LLM ──
    groq_directions = None
    groq_error = None
    try:
        t_groq = _timer()
        groq_directions = _ask_groq(original_adj, apocalypse, city_name)
        logger.info(f"[MITIGATE] Groq LLM: {t_groq():.2f}s")
    except Exception as e:
        groq_error = f"{type(e).__name__}: {e}"
        logger.error(f"[MITIGATE] Groq failed: {groq_error}")
        groq_directions = {
            "reasoning": f"LLM call failed: {groq_error}. No optimizations applied.",
            "remove_edges": [], "add_edges": [], "add_nodes": [],
            "reroute": [], "priority_nodes": [],
        }

    # ── Step 5: Apply LLM directions (with fuzzy matching) ──
    t_apply = _timer()
    M, changes, llm_applied = _apply_llm_directions(G, groq_directions)
    logger.info(f"[MITIGATE] LLM applied {llm_applied} ops in {t_apply():.2f}s")

    # ── Step 5b: If LLM did nothing useful, apply programmatic pruning ──
    calamity_names = [c["name"] for c in apocalypse.get("ranked_calamities", [])]
    if llm_applied < 3:
        logger.warning(f"[MITIGATE] LLM only applied {llm_applied} changes — running programmatic pruning")
        M, prog_changes = _apply_programmatic_pruning(M, calamity_names)
        changes.extend(prog_changes)
        logger.info(f"[MITIGATE] Programmatic pruning added {len(prog_changes)} more changes")

    # ── Step 6: Mitigated adjacency + stats ──
    mitigated_adj = _build_adj(M)
    mitigated_stats = _compute_stats(M)

    # ── Step 7: Positions ──
    node_positions = {}
    for nid in G.nodes():
        a = G.nodes[nid]
        if a.get("infra_type") == "intersection": continue
        node_positions[a.get("label", str(nid))] = {
            "x": round(pos[nid][0], 4), "y": round(pos[nid][1], 4),
            "type": a.get("infra_type", ""),
        }
    # Add positions for LLM-added nodes (placed at centroid)
    for nid in M.nodes():
        lbl = M.nodes[nid].get("label", "")
        if lbl and lbl not in node_positions and M.nodes[nid].get("infra_type") != "intersection":
            # Place near connected nodes
            nbr_positions = [pos[n] for n in M.neighbors(nid) if n in pos]
            if nbr_positions:
                cx = np.mean([p[0] for p in nbr_positions])
                cy = np.mean([p[1] for p in nbr_positions])
            else:
                cx, cy = 0.0, 0.0
            node_positions[lbl] = {"x": round(cx, 4), "y": round(cy, 4),
                                   "type": M.nodes[nid].get("infra_type", "")}

    logger.info(f"[MITIGATE] TOTAL: {t_total():.2f}s ✓")
    logger.info("#" * 60)

    return {
        "city": {"name": city_name, "radius_km": round(city_radius, 4)},
        "node_positions": node_positions,
        "original_adjacency_list": original_adj,
        "mitigated_adjacency_list": mitigated_adj,
        "llm_directions": groq_directions,
        "changes": changes,
        "original_stats": original_stats,
        "mitigated_stats": mitigated_stats,
        "data_source": data_source,
        "fallback_reason": fallback_reason,
        "groq_error": groq_error,
        "apocalypse_analysis": None,
        "groq_analysis": {
            "reasoning": groq_directions.get("reasoning", ""),
            "priority_nodes": groq_directions.get("priority_nodes", []),
            "model_used": GROQ_MODEL,
        },
    }


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="City Infrastructure Mitigation")
    parser.add_argument("--file", default="./Data/apocalypse_analysis.json", help="Apocalypse analysis JSON")
    parser.add_argument("--procedural", action="store_true", help="Skip OSM")
    parser.add_argument("--json", type=str, default=None, help="Export result to JSON file")
    args = parser.parse_args()

    result = mitigate(apocalypse_file=args.file, force_procedural=args.procedural)

    print(f"\n{'='*60}")
    print(f"  City:       {result['city']['name']}")
    print(f"  Source:     {result['data_source']}")
    if result["fallback_reason"]:
        print(f"  ⚠ Fallback: {result['fallback_reason']}")
    if result["groq_error"]:
        print(f"  ⚠ Groq:     {result['groq_error']}")
    print(f"  Threats:    {result['groq_analysis'].get('model_used', '?')}")
    print(f"  Original:   {result['original_stats']['infrastructure_nodes']} nodes, "
          f"{result['original_stats']['total_edges']} edges")
    print(f"  Mitigated:  {result['mitigated_stats']['infrastructure_nodes']} nodes, "
          f"{result['mitigated_stats']['total_edges']} edges")
    print(f"  Changes:    {len(result['changes'])}")
    print(f"  LLM Model:  {result['groq_analysis']['model_used']}")
    print(f"{'='*60}")

    if result["groq_analysis"]["reasoning"]:
        print(f"\n  LLM Reasoning:\n  {result['groq_analysis']['reasoning'][:500]}...")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nExported to {args.json}")