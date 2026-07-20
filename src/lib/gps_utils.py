import time

from adafruit_gps import GPS


def get_local_time(gps, time_zone_hours=0):
    # Convert the struct_time from the GPS to seconds since the epoch
    utc_seconds = time.mktime(gps.timestamp_utc)

    # local time in seconds (time_zone_hours * 60 minutes * 60 seconds)
    local_seconds = utc_seconds + time_zone_hours * 3600

    # Convert those seconds back for a clean struct_time
    return time.localtime(local_seconds)


def print_gps_dms(gps):
    """
    print GPS in degree,minute,sec format
    """
    lat_deg = int(gps.latitude_degrees)
    lat_min_float = gps.latitude_minutes
    lat_min = int(lat_min_float)
    lat_sec = (lat_min_float - lat_min) * 60.0
    lon_deg = int(gps.longitude_degrees)
    lon_min_float = gps.longitude_minutes
    lon_min = int(lon_min_float)
    lon_sec = (lon_min_float - lon_min) * 60.0
    print(f"Latitude  (DMS): {lat_deg}° {lat_min}' {lat_sec:.4f}\"")
    print(f"Longitude (DMS): {lon_deg}° {lon_min}' {lon_sec:.4f}\"")


def get_map_string(gps: GPS) -> str:
    """
    Create from the GPS coordinates a string format (ex:  "xxx.xxxxxxx N, xxx.xxxxxxx W").
    This format can be copy-paste into most maps (Apple, Google) to find location on map.
    :param gps:
    :return: string: "xxx.xxxxxxx N, xxx.xxxxxxx W"
    """
    lat_string = ""
    lon_string = ""
    if gps is None or gps.latitude is None or gps.longitude is None:
        return "GPS location: N/A"
    lat_dir = "N" if gps.latitude_degrees >= 0 else "S"
    lat_string = f"{abs(gps.latitude):.6f} {lat_dir}"
    lon_dir = "E" if gps.longitude_degrees >= 0 else "W"
    lon_string = f"{abs(gps.longitude):.6f} {lon_dir}"
    return f"{lat_string}, {lon_string}"

def get_lat_string(gps: GPS) -> str:
    """
    Create Latitude string from the GPS coordinates a sting format (ex:  "xxx.xxxxxxx N").
    """
    if gps is None or gps.latitude is None:
        return "Lat: N/A"
    direction = "N" if gps.latitude >= 0 else "S"
    return f"{abs(gps.latitude):.4f}° {direction}"

def get_lon_string(gps: GPS) -> str:
    """
    Create Longitude string from the GPS coordinates a sting format (ex:  "xxx.xxxxxxx W").
    """
    if gps is None or gps.longitude is None:
        return "Lon: N/A"
    direction = "E" if gps.longitude >= 0 else "W"
    return f"{abs(gps.longitude):.4f}° {direction}"
