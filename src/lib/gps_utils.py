import os
import time

from adafruit_gps import GPS


def get_local_time(gps, time_zone_hours=0):
    """Convert GPS time and adjust by time_zone_hours to create local time."""
    # Convert GPS struct_time to seconds since the epoch, (time_zone_hours * 60 min * 60 sec)
    utc_seconds = time.mktime(gps.timestamp_utc)
    local_seconds = utc_seconds + time_zone_hours * 3600

    # Convert those seconds back to struct_time
    return time.localtime(local_seconds)


def set_system_time_from_gps(gps):
    """Sets the Pi ero system clock (in UTC) using GPS UTC timestamp."""
    if gps.timestamp_utc is None or gps.timestamp_utc.tm_year < 2024:
        return False

    try:
        t = gps.timestamp_utc
        utc_str = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

        # -u flag says it is UTC time
        os.system(f'sudo date -u -s "{utc_str}" > /dev/null 2>&1')
        print(f"--> System clock synced to GPS UTC: {utc_str}")
        return True
    except Exception as e:
        print(f"Failed to set system time: {e}")
        return False


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
