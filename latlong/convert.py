# # #!/usr/bin/env python3
# # from geopy.geocoders import Nominatim

# # def get_city_lat_lon(city, state):
# #     geolocator = Nominatim(user_agent="citycoord")
# #     loc = geolocator.geocode(f"{city}, {state}, US")
# #     if loc:
# #         return loc.latitude, loc.longitude
# #     return None, None

# # def get_state_country(city_name: str):
# #     """
# #     Given a city name, return (city, state, country).
# #     Example: get_state_country("Boston") -> ("Boston", "Massachusetts", "United States")
# #     """
# #     geolocator = Nominatim(user_agent="city_to_state_country")

# #     loc = geolocator.geocode(city_name)
# #     if not loc:
# #         return None, None, None

# #     addr = loc.raw.get("address", {})
# #     city = (
# #         addr.get("city")
# #         or addr.get("town")
# #         or addr.get("village")
# #         or addr.get("hamlet")
# #         or city_name
# #     )
# #     state = addr.get("state")
# #     country = addr.get("country")
# #     return city, state, country

# # if __name__ == "__main__":
# #     # parser = argparse.ArgumentParser()
# #     # parser.add_argument("--city", required=True)
# #     # parser.add_argument("--state", required=True)
# #     # args = parser.parse_args()
# #     city = "Boston"
# #     # state = "MA"
# #     state = get_state_country("Boston")
# #     lat, lon = get_city_lat_lon(city, state)
# #     print(f"{lat},{lon}")
# #     print(state)
# # # if __name__ == "__main__":
# #     print(get_state_country("Boston"))
# #     print(get_state_country("San Francisco"))


# #!/usr/bin/env python3
from geopy.geocoders import Nominatim

# # Reuse one geolocator instance

def get_city_lat_lon(city, state=None, country="US"):
    """Return (lat, lon) for city, optional state, and country."""
    geolocator = Nominatim(user_agent="city_utils")
    if state:
        query = f"{city}, {state}, {country}"
    else:
        query = f"{city}, {country}"
    loc = geolocator.geocode(query)
    if loc:
        return loc.latitude, loc.longitude
    return None, None

# def get_state_country(city_name: str):
#     """
#     Given a city name, return (city, state, country).
#     Example: get_state_country("Boston") -> ("Boston", "Massachusetts", "United States")
#     """
#     loc = geolocator.geocode(city_name)
#     if not loc:
#         return None, None, None

#     addr = loc.raw.get("address", {})
#     city = (
#         addr.get("city")
#         or addr.get("town")
#         or addr.get("village")
#         or addr.get("hamlet")
#         or city_name
#     )
#     state = addr.get("state")
#     country = addr.get("country")
#     return city, state, country

# if __name__ == "__main__":
#     city = "Boston"

#     city_name, state_name, country_name = get_state_country(city)
#     print("Meta:", city_name, state_name, country_name)

#     lat, lon = get_city_lat_lon(city_name, state_name, country_name or "US")
#     print("Coords:", lat, lon)

#     print(get_state_country("Boston"))
#     print(get_state_country("San Francisco"))


# from geopy.geocoders import Nominatim


def get_state_country(city_name: str):
    """
    Given a US city name, return (city, state, country).
    Example: get_state_country("Boston") -> ("Boston", "Massachusetts", "United States")
    """
    geolocator = Nominatim(user_agent="city_to_state_country")
    loc = geolocator.geocode(
        city_name,
        country_codes="us",      # force US results
        addressdetails=True      # include detailed address dict
    )
    if not loc:
        return None, None, None

    addr = loc.raw.get("address", {})

    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("hamlet")
        or addr.get("municipality")
        or city_name
    )
    state = (
        addr.get("state")
        or addr.get("region")
        or addr.get("state_district")
    )
    country = addr.get("country") or "United States"

    return city, state, country

if __name__ == "__main__":
    city = "Boston"

    city_name, state_name, country_name = get_state_country(city)
    print("Meta:", city_name, state_name, country_name)
    
    lat, lon = get_city_lat_lon(city_name, state_name, country_name or "US")
    print("Coords:", lat, lon)
    print(get_state_country("Boston"))          # ("Boston", "Massachusetts", "United States")
    print(get_state_country("San Francisco"))   # ("San Francisco", "California", "United States")


