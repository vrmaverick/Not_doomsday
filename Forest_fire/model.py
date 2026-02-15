# #!/usr/bin/env python3
import json
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
import os


from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "Data"  # Forest_fire/.. / Data  == PROJECT_ROOT/Data


load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY_3"))

def summarize_groq_fire(json_file=None):
    if json_file is None:
        json_file = DATA_DIR / "fire_key.json"
    else:
        json_file = Path(json_file)

    # Load ANY JSON (array or JSONL)
    if str(json_file).endswith(".jsonl"):
        df = pd.read_json(json_file, lines=True)
    else:
        with open(json_file) as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    
    # Key fields only
    df_key = df[['latitude', 'longitude', 'bright_ti4', 'frp', 'confidence', 'acq_date']].round(4)
    fires_text = df_key.to_json(orient='records', lines=True)
    
    print(f"Loaded {len(df_key)} fire detections")



    SYSTEM_PROMPT = """You are a forest fire expert specializing in VIIRS FIRMS satellite data analysis. Analyze fire detections and provide structured risk assessments.

Respond ONLY in this exact JSON format, no extra text or markdown:
{
  "risk_level": "LOW" | "MODERATE" | "HIGH" | "CRITICAL",
  "risk_score": <1-10 integer>,
  "confidence": <0.0-1.0 float>,
  "summary": "<1-2 sentence plain English summary of fire threat>",
  "key_factors": ["<fire factor 1>", "<fire factor 2>", "<fire factor 3>"],
  "clusters_detected": "<description of spatial clusters or hotspots>",
  "spread_potential": "<1-2 sentence assessment of fire growth/spread risk>",
  "recommendation": "<1-2 sentence actionable recommendation for response>"
}

Assessment criteria (VIIRS FIRMS data):
- LOW (1-3): FRP<2MW, ti4<310K, isolated detections, nominal/low confidence
- MODERATE (4-5): FRP 2-5MW OR ti4 310-330K, small clusters (2-5 detections), stable pattern
- HIGH (6-8): FRP>5MW OR ti4>330K, large clusters (>5 detections/area), multiple high-confidence fires
- CRITICAL (9-10): FRP>10MW, saturated pixels, dense clusters across region, rapid increase in detections

Consider: FRP (fire power/intensity), bright_ti4 (thermal anomaly), confidence (h/n/l), spatial clustering by lat/lon, detection density."""

    
    prompt = f"""Forest fire expert: Analyze VIIRS FIRMS data:

{fires_text}

JSON response only:
{{
  "total_detections": num,
  "high_risk_count": num,
  "clusters": ["lat,lon: reason"],
  "threat_level": "Low/Medium/High",
  "predictions": [{{"lat": num, "lon": num, "risk": "High", "reason": "FRP 6MW intense fire"}}]
}}"""

    chat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    summary = chat.choices[0].message.content
    print("Groq Summary:")
    print(summary)
    
    with open(DATA_DIR / "fire_summary.json", "w") as f:
        json.dump({"data_count": len(df_key), "summary": summary}, f, indent=2)
    print("Saved fire_summary.json")


# def process_groq_to_map(groq_summary_file="../Data/fire_summary.json", fire_key_file="../Data/fire_key.json"):
#         # Load Groq summary
#         with open(groq_summary_file) as f:
#             groq_data = json.load(f)
#         groq_text = groq_data["summary"]  # Fixed: "summary" not "expert_summary"
        
#         # Parse JSON from markdown-wrapped text
#         start = groq_text.find('{')
#         end = groq_text.rfind('}') + 1
#         groq_json_str = groq_text[start:end]
        
#         summary_json = json.loads(groq_json_str)
#         predictions = summary_json.get("predictions", [])
        
#         # Build pred dict
#         pred_dict = {}
#         for p in predictions:
#             key = f"{p['lat']:.4f},{p['lon']:.4f}"
#             pred_dict[key] = p['risk']
        
#         # Load ALL fire coords (Low default)
#         with open(fire_key_file) as f:
#             fires = json.load(f)
#         df = pd.DataFrame(fires)
#         all_coords = {f"{row['latitude']:.4f},{row['longitude']:.4f}": "Low" 
#                     for _, row in df.iterrows()}
        
#         # Override with Groq predictions
#         all_coords.update(pred_dict)
        
#         # Save
#         with open("../Data/map_fire.json", "w") as f:
#             json.dump(all_coords, f, indent=2)
        
#         print("map.json:")
#         print(json.dumps(dict(list(all_coords.items())[:10]), indent=2))
#         print(f"Total: {len(all_coords)} coords, High: {sum(1 for v in all_coords.values() if v=='High')}")
        
#         return all_coords


def process_groq_to_map(
    groq_summary_file=None,
    fire_key_file=None,
):
    groq_summary_path = DATA_DIR / "fire_summary.json" if groq_summary_file is None else Path(groq_summary_file)
    fire_key_path     = DATA_DIR / "fire_key.json"     if fire_key_file is None else Path(fire_key_file)
    map_out_path      = DATA_DIR / "map_fire.json"

    with open(groq_summary_path) as f:
        groq_data = json.load(f)
    groq_text = groq_data["summary"]

    start = groq_text.find("{")
    end = groq_text.rfind("}") + 1
    groq_json_str = groq_text[start:end]

    summary_json = json.loads(groq_json_str)
    predictions = summary_json.get("predictions", [])

    pred_dict = {}
    for p in predictions:
        key = f"{p['lat']:.4f},{p['lon']:.4f}"
        pred_dict[key] = p["risk"]

    with open(fire_key_path) as f:
        fires = json.load(f)
    df = pd.DataFrame(fires)
    all_coords = {
        f"{row['latitude']:.4f},{row['longitude']:.4f}": "Low"
        for _, row in df.iterrows()
    }

    all_coords.update(pred_dict)

    with open(map_out_path, "w") as f:
        json.dump(all_coords, f, indent=2)

    print("map_fire.json path:", map_out_path)
    print(json.dumps(dict(list(all_coords.items())[:10]), indent=2))
    print(f"Total: {len(all_coords)} coords, High: {sum(1 for v in all_coords.values() if v=='High')}")

    return all_coords


    # # Load ALL fire coords
    # with open(fire_key_file) as f:
    #     fires = json.load(f)
    # df = pd.DataFrame(fires)
    # all_coords = {f"{row['latitude']:.4f},{row['longitude']:.4f}": "Low" for _, row in df.iterrows()}
    
    # # Merge: Groq High/Med → override Low
    # all_coords.update(pred_dict)
    
    # # Save map.json
    # with open("map.json", "w") as f:
    #     json.dump(all_coords, f, indent=2)
    
    # print("map.json created:")
    # print(json.dumps({k: v for k, v in list(all_coords.items())[:5]}, indent=2))
    # print(f"... {len(all_coords)} total coords")
    
    # return all_coords

# # Add to model.py after Groq call:
# if __name__ == "__main__":
#     summarize_groq_fire()


if __name__ == "__main__":
    # summarize_groq_fire()
    process_groq_to_map()  # Auto-process
