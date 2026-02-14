import requests
import pandas as pd
import os
from dotenv import load_dotenv

def Fire_API(lat,long):
    load_dotenv()
    MAP_KEY = os.getenv("MAP_KEY", "demo").strip()
    print(MAP_KEY)

    # Check transaction status
    status_url = f'https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}'
    status_resp = requests.get(status_url).json()
    print('Transactions used:', status_resp.get('current_transactions', 'Error'))

    # Fetch VIIRS NRT fires in California (bbox: minlon,minlat,maxlon,maxlat), last 1 day
    # US example: California ~ -125,32,-114,42
    area_url = f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/{lat},{long}/1'
    df = pd.read_csv(area_url)

    # Convert to JSON and save
    data_json = df.to_json(orient='records', lines=True, date_format='iso')
    with open('../Data/us_fires.json', 'w') as f:
        f.write(data_json)
    print(f'Saved {len(df)} fire detections to us_fires.json')

if __name__ == '__main__':
    lat,long = "-125,32","-114,42"
    Fire_API(lat,long)