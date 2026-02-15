#!/usr/bin/env python3
from geopy.geocoders import Nominatim

def get_city_lat_lon(city, state):
    geolocator = Nominatim(user_agent="citycoord")
    loc = geolocator.geocode(f"{city}, {state}, US")
    if loc:
        return loc.latitude, loc.longitude
    return None, None

if __name__ == "__main__":
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--city", required=True)
    # parser.add_argument("--state", required=True)
    # args = parser.parse_args()
    city = "Boston"
    state = "MA"
    lat, lon = get_city_lat_lon(city, state)
    print(f"{lat},{lon}")
