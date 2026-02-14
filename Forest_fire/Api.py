import requests
import json
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
MAP_KEY = os.getenv("SECRET_KEY")

# # Check transaction status
status_url = f'https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}'
status_resp = requests.get(status_url).json()
print('Transactions used:', status_resp.get('current_transactions', 'Error'))

# # Fetch VIIRS NRT fires in California (bbox: minlon,minlat,maxlon,maxlat), last 1 day
# # US example: California ~ -125,32,-114,42
area_url = f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-125,32,-114,42/1'
df = pd.read_csv(area_url)

# Convert to JSON and save
data_json = df.to_json(orient='records', lines=True, date_format='iso')
with open('us_fires.json', 'w') as f:
    f.write(data_json)
print(f'Saved {len(df)} fire detections to us_fires.json')
