import json
import pandas as pd
# from collections import defaultdict
# import io
import re  # For LLM output parsing
from model import *
def Predict_forest_fires():
    df = pd.read_json('../Data/us_fires.json', lines=True)

    # 1. Key fields JSON
    key_data = df[['latitude', 'longitude', 'bright_ti4', 'frp', 'confidence', 'acq_date']].round(4).to_dict('records')
    with open('../Data/fire_key.json', 'w') as f:
        json.dump(key_data, f, indent=2)

    # 2. map.json: lat,lon -> prediction (default low; update with LLM)
    coords = df[['latitude', 'longitude']].round(4).drop_duplicates()
    map_data = {f"{row.latitude},{row.longitude}": "Low" for _, row in coords.iterrows()}


if __name__ == '__main__':
    Predict_forest_fires()
