import time

from adafruit_gps import GPS


def get_local_time(gps, time_zone_hours=0):
    # Convert the struct_time from the GPS to seconds since the epoch
    utc_seconds = time.mktime(gps.timestamp_utc)

    # local time in seconds (time_zone_hours * 60 minutes * 60 seconds)
    local_seconds = utc_seconds + time_zone_hours * 3600

    # Convert those seconds back for a clean truct_time
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
    Create from the GPS coordinates a sting format (ex:  "xxx.xxxxxxx N, xxx.xxxxxxx W").
    This format can be copy-paste into most maps (Apple, Google) to find location on map.
    :param gps:
    :return:
    """
    if gps.latitude_degrees is not None:
        lat_dir = "N" if gps.latitude_degrees >= 0 else "S"
    if gps.longitude_degrees is not None:
        lon_dir = "E" if gps.longitude_degrees >= 0 else "W"
    map_string = f"{gps.latitude:.6f} {lat_dir}, {gps.longitude:.6f} {lon_dir}"
    return map_string
