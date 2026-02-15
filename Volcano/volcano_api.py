#!/usr/bin/env python3
"""
volcano_api.py — Reusable module for the team
==============================================
Import this in your Flask/FastAPI backend or notebooks.

Usage:
    from volcano_api import VolcanoClient

    client = VolcanoClient()
    client.refresh_data()                          # Pull fresh from USGS
    nearby = client.get_risk("Hawaii")             # Get risk assessment
    nearby = client.get_risk(19.4, -155.3)         # With coords
    answer = client.ask("Will Kilauea erupt?", 19.4, -155.3)  # LLM query
"""

import requests
import json
import math
import os
from datetime import datetime, timedelta


class VolcanoClient:
    HANS_BASE = "https://volcanoes.usgs.gov/hans-public/api/volcano"
    EQ_BASE = "https://earthquake.usgs.gov/fdsnws/event/1"

    THREAT_SCORES = {
        "Very High Threat": 5, "High Threat": 4, "Moderate Threat": 3,
        "Low Threat": 2, "Very Low Threat": 1, "Unassigned": 0,
    }
    ALERT_SCORES = {
        "WARNING": 4, "WATCH": 3, "ADVISORY": 2, "NORMAL": 1, None: 0,
    }
    COLOR_SCORES = {
        "RED": 4, "ORANGE": 3, "YELLOW": 2, "GREEN": 1, None: 0,
    }

    PRESETS = {
        "hawaii": (19.896, -155.582), "seattle": (47.606, -122.332),
        "portland": (45.505, -122.675), "anchorage": (61.217, -149.900),
        "manila": (14.599, 120.984), "tokyo": (35.682, 139.692),
        "naples": (40.852, 14.268), "mexico city": (19.432, -99.133),
        "san francisco": (37.774, -122.419), "los angeles": (34.052, -118.244),
    }

    def __init__(self, groq_api_key=None, cache_dir="volcano_data"):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.cache_dir = cache_dir
        self.data = []
        self._load_cache()

    def _load_cache(self):
        path = os.path.join(self.cache_dir, "volcanoes_enriched.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _save_cache(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        path = os.path.join(self.cache_dir, "volcanoes_enriched.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, default=str, ensure_ascii=False)

    # ---- Data pulling ----

    def refresh_data(self, with_seismicity=True):
        """Pull fresh data from all USGS APIs and rebuild the enriched dataset."""
        print("Pulling USGS data...")
        all_v = requests.get(f"{self.HANS_BASE}/getUSVolcanoes", timeout=30).json()
        monitored = requests.get(f"{self.HANS_BASE}/getMonitoredVolcanoes", timeout=30).json()
        elevated = requests.get(f"{self.HANS_BASE}/getElevatedVolcanoes", timeout=30).json()

        mon_set = {v.get("vnum", "") for v in monitored}
        elev_map = {v.get("vnum", ""): v for v in elevated}

        enriched = []
        for v in all_v:
            e = self._enrich(v, elev_map, mon_set)
            if with_seismicity and e["is_monitored"] and e["latitude"] and e["longitude"]:
                eqs = self._pull_earthquakes(e["latitude"], e["longitude"])
                e = self._add_seismicity(e, eqs)
            e = self._compute_risk(e)
            enriched.append(e)

        enriched.sort(key=lambda x: x["composite_risk_score"], reverse=True)
        self.data = enriched
        self._save_cache()
        print(f"Done. {len(enriched)} volcanoes cached.")
        return enriched

    def _pull_earthquakes(self, lat, lon, days=30, radius=50, min_mag=1.0):
        try:
            end = datetime.utcnow()
            start = end - timedelta(days=days)
            r = requests.get(f"{self.EQ_BASE}/query", params={
                "format": "geojson", "starttime": start.strftime("%Y-%m-%d"),
                "endtime": end.strftime("%Y-%m-%d"), "latitude": lat,
                "longitude": lon, "maxradiuskm": radius,
                "minmagnitude": min_mag, "limit": 500,
            }, timeout=20)
            return r.json().get("features", [])
        except Exception:
            return []

    def _enrich(self, v, elev_map, mon_set):
        vnum = v.get("vnum", "")
        e = {
            "vnum": vnum,
            "volcano_name": v.get("volcano_name", ""),
            "region": v.get("region", ""),
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "elevation_meters": v.get("elevation_meters"),
            "is_monitored": vnum in mon_set,
            "nvews_threat": v.get("nvews_threat", "Unassigned"),
            "threat_score": self.THREAT_SCORES.get(v.get("nvews_threat", ""), 0),
            "alert_level": None, "color_code": None,
            "alert_score": 0, "color_score": 0,
            "obs_abbr": v.get("obs_abbr", ""),
            "volcano_url": v.get("volcano_url", ""),
            "volcano_image_url": v.get("volcano_image_url", ""),
            "eq_count_30d": 0, "eq_max_mag_30d": 0.0,
            "eq_avg_mag_30d": 0.0, "eq_avg_depth_km": 0.0,
            "eq_shallow_count": 0, "composite_risk_score": 0.0,
        }
        if vnum in elev_map:
            el = elev_map[vnum]
            alert = el.get("alert_level") or el.get("alertLevel")
            color = el.get("color_code") or el.get("colorCode")
            e["alert_level"] = alert
            e["color_code"] = color
            e["alert_score"] = self.ALERT_SCORES.get(str(alert).upper() if alert else None, 0)
            e["color_score"] = self.COLOR_SCORES.get(str(color).upper() if color else None, 0)
        return e

    def _add_seismicity(self, e, eqs):
        mags, depths, shallow = [], [], 0
        for eq in eqs:
            p = eq.get("properties", {})
            c = eq.get("geometry", {}).get("coordinates", [0, 0, 0])
            if p.get("mag") is not None:
                mags.append(p["mag"])
            d = c[2] if len(c) > 2 else 0
            depths.append(d)
            if d < 5:
                shallow += 1
        e["eq_count_30d"] = len(eqs)
        e["eq_max_mag_30d"] = max(mags) if mags else 0.0
        e["eq_avg_mag_30d"] = round(sum(mags)/len(mags), 2) if mags else 0.0
        e["eq_avg_depth_km"] = round(sum(depths)/len(depths), 2) if depths else 0.0
        e["eq_shallow_count"] = shallow
        return e

    def _compute_risk(self, e):
        score = (
            (e["threat_score"] / 5.0) * 25 +
            (e["alert_score"] / 4.0) * 25 +
            (e["color_score"] / 4.0) * 15 +
            min(e["eq_count_30d"] / 200.0, 1.0) * 15 +
            min(e["eq_max_mag_30d"] / 6.0, 1.0) * 10 +
            min(e["eq_shallow_count"] / 50.0, 1.0) * 10
        )
        e["composite_risk_score"] = round(score, 1)
        return e

    # ---- Query methods ----

    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = (math.sin(dlat/2)**2 +
             math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*
             math.sin(dlon/2)**2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def nearby(self, lat, lon, radius_km=500, top_n=10):
        """Get nearby volcanoes sorted by distance."""
        results = []
        for v in self.data:
            if v["latitude"] and v["longitude"]:
                d = self.haversine(lat, lon, v["latitude"], v["longitude"])
                vc = dict(v)
                vc["distance_km"] = round(d, 1)
                results.append(vc)
        results.sort(key=lambda x: x["distance_km"])
        return [r for r in results if r["distance_km"] <= radius_km][:top_n]

    def get_risk(self, *args, radius_km=500):
        """
        Get risk data. Accepts:
            get_risk("Hawaii")
            get_risk(19.4, -155.3)
        """
        if len(args) == 1 and isinstance(args[0], str):
            key = args[0].lower().strip()
            if key not in self.PRESETS:
                return {"error": f"Unknown location. Use coords or: {list(self.PRESETS.keys())}"}
            lat, lon = self.PRESETS[key]
        elif len(args) == 2:
            lat, lon = float(args[0]), float(args[1])
        else:
            return {"error": "Usage: get_risk('Hawaii') or get_risk(19.4, -155.3)"}

        nb = self.nearby(lat, lon, radius_km=radius_km)
        return {
            "user_location": {"lat": lat, "lon": lon},
            "nearby_count": len(nb),
            "nearest_volcano": nb[0] if nb else None,
            "max_risk_score": max((v["composite_risk_score"] for v in nb), default=0),
            "elevated_volcanoes": [v for v in nb if v["alert_score"] >= 2],
            "all_nearby": nb,
        }

    def ask(self, question, lat=None, lon=None, location_name=None):
        """Ask the Groq LLM a question with volcano data context."""
        if not self.groq_api_key:
            return "Error: No GROQ_API_KEY set. Pass it to VolcanoClient() or set env var."

        # Resolve location
        if location_name:
            key = location_name.lower().strip()
            if key in self.PRESETS:
                lat, lon = self.PRESETS[key]
        if lat is None or lon is None:
            return "Error: Provide lat/lon or location_name."

        nb = self.nearby(lat, lon)
        context = self._build_context(nb, lat, lon)

        return self._query_groq(question, context)

    def _build_context(self, nearby, lat, lon):
        lines = [f"User location: ({lat}, {lon})", f"Nearby volcanoes:\n"]
        for v in nearby:
            lines.append(
                f"- {v['volcano_name']} ({v['region']}): "
                f"{v['distance_km']}km away, "
                f"Threat={v['nvews_threat']}, "
                f"Alert={v['alert_level'] or 'NORMAL'}, "
                f"Color={v['color_code'] or 'GREEN'}, "
                f"EQ(30d)={v['eq_count_30d']} "
                f"(max M{v['eq_max_mag_30d']}, shallow={v['eq_shallow_count']}), "
                f"Risk={v['composite_risk_score']}/100"
            )
        return "\n".join(lines)

    def _query_groq(self, question, context):
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.groq_api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": (
                        "You are a volcano hazard analyst AI. Use the real-time USGS data "
                        "provided to assess risk. Be specific with numbers. Note that "
                        "volcanic prediction is inherently uncertain."
                    )},
                    {"role": "user", "content": f"DATA:\n{context}\n\nQUESTION: {question}"},
                ],
                "temperature": 0.3, "max_tokens": 1024,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # ---- Export for frontend ----

    def export_for_globe(self, path="volcano_data/globe_data.json"):
        """Export minimal data optimized for Three.js globe visualization."""
        globe_data = []
        for v in self.data:
            if v["latitude"] and v["longitude"]:
                globe_data.append({
                    "name": v["volcano_name"],
                    "lat": v["latitude"],
                    "lon": v["longitude"],
                    "elevation": v["elevation_meters"],
                    "threat": v["nvews_threat"],
                    "threat_score": v["threat_score"],
                    "alert": v["alert_level"],
                    "alert_score": v["alert_score"],
                    "color_code": v["color_code"],
                    "risk": v["composite_risk_score"],
                    "eq_count": v["eq_count_30d"],
                    "monitored": v["is_monitored"],
                    "url": v["volcano_url"],
                    "image_url": v["volcano_image_url"],
                    "region": v["region"],
                })
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(globe_data, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(globe_data)} volcanoes for globe → {path}")
        return globe_data
