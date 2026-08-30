# gps_utils.py
"""

PMTK314 GPS Fields - we use 2, 4, 5 as shown in *'s
    GLL — Latitude, longitude, and fix time data.
    * RMC — Essential position, speed, and time data.
    VTG — Track vector, ground speed, and course over ground.
    * GGA — Essential fix data with altitude and satellite count.
    * GSA — Active satellites and dilution of precision metrics.
    GSV — Satellites in view, elevation, and signal strength.
    GRS — Range residuals used for GPS integrity monitoring.
    GST — Pseudorange noise statistics and error estimation.
    ZDA — Detailed UTC time, day, month, year, and timezone.
    MCHN — MTK proprietary GPS channel tracking status.
    DTM — Local geodetic datum reference transformations.
    GNS — Multi-constellation GNSS positioning fix data.
    VLW — Dual-distance traveled metrics (water and ground).
    GMP — MTK proprietary satellite power-saving data.
    PMTKCHN — Alternative field for channel assignment status.
    Reserved — Unused index for future MTK firmware expansion.
    Reserved — Unused index for future MTK firmware expansion.
    PMTK101 — MTK testing and diagnostic output message.
    PMTK102 — MTK auxiliary engineering calibration message.
"""
import functools
import operator
import os
import time
from datetime import datetime, timezone, timedelta

import adafruit_gps
import serial
from adafruit_gps import GPS


def initialize_gps():
    """
    Initializes GPS object with default values.
        RMC — Essential position, speed, and time data.
        GGA — Essential fix data with altitude and satellite count.
        GSA — Active satellites and dilution of precision metrics.

    :return:
    """
    print("\nInitializing GPS...")
    uart = serial.Serial("/dev/serial0", baudrate=9600, timeout=10)
    # Sometimes, passing permissions through symlinks inside Python virtual environments fails silently. Let's bypass the symlink entirely.
    # TODO Change from /dev/serial0 to the direct hardware node:
    # uart = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=10)


    # Turn on the basic GGA, RMC, GGA(Accuracy), update time 1sec, 1Hz (if change Hz, check UART timeout)

    # Time Injection, it uses uart because it is before driver attaches
    inject_system_time_to_gps_if_needed(uart)
    uart.flush()
    uart.reset_input_buffer()

    # Create GPS Instance, Turn on the basic RMC, GGA, GSA
    gps = adafruit_gps.GPS(uart, debug=False)
    gps.send_command(b"PMTK314,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")

    # update GPS metrics every sec, 1Hz
    gps.send_command(b"PMTK220,1000")

    print("GPS initialization Done.")
    return gps


def inject_system_time_to_gps_if_needed(uart_connection: serial.Serial):
    """
    Injects system time ($PMTK740) into MT3339 GPS and verifies PMTK001 acknowledgement.
    """
    if gps_has_valid_time(uart_connection):
        print(" * GPS RTC has valid time.")
        return True

    # Check if Pi system time is sane before using it
    now = time.gmtime()
    if now.tm_year < 2026:
        print(" * Pi system time is invalid (pre-2026) — Skipping Pi system time injection.")
        return False

    # Inject time if GPS has no time, but Pi has good time
    print(" * GPS missing valid time. Injecting Pi system time...")
    try:
        payload = f"PMTK740,{now.tm_year:04d},{now.tm_mon:02d},{now.tm_mday:02d},{now.tm_hour:02d},{now.tm_min:02d},{now.tm_sec:02d}"
        checksum = functools.reduce(operator.xor, (ord(c) for c in payload))
        command = f"${payload}*{checksum:02X}\r\n"

        uart_connection.reset_input_buffer()
        uart_connection.write(command.encode("ascii"))
        uart_connection.flush()
        print(f" * Sent Time Injection: {command.strip()}")
        return True
    except Exception as e:
        print(f" * Error during time injection: {e}")
        return False


def gps_has_valid_time(uart_connection: serial.Serial, check_timeout: float = 2.0) -> bool:
    """
    Reads incoming NMEA sentences to check if the GPS RTC already holds a valid year.
    Returns True if time is already known, False if GPS needs time injection.
    """
    start_time = time.time()
    while time.time() - start_time < check_timeout:
        if uart_connection.in_waiting:
            line = uart_connection.readline().decode("ascii", errors="ignore")

            # Look for RMC or ZDA sentences which contain date strings
            if "$GPRMC" in line or "$GNRMC" in line:
                parts = line.split(",")

                # RMC format: $GPRMC,hhmmss.ss,A,lat,N,lon,E,spd,cog,ddmmyy,...
                if len(parts) > 9 and len(parts[9]) == 6:
                    try:
                        year = int(parts[9][4:6]) + 2000
                        if year >= 2026:  # Valid modern date in GPS RTC
                            return True
                    except ValueError:
                        continue  # Skip corrupt string and keep checking next line
    return False


def get_time_from_gps(gps: GPS, time_zone_hours: float = -7.0) -> time.struct_time | None:
    """
    Convert GPS UTC timestamp to local struct_time using explicit offset.
    For timezone:
        EDT (Daylight Saving, March-Nov) = -4.0
        EST (Standard Time, Nov-March)  = -5.0
        PDT (Daylight Saving, March-Nov) = -7.0
        PST (Standard Time, Nov-March)  = -8.0
    """
    if gps is None or gps.timestamp_utc is None:
        return None

    try:
        t = gps.timestamp_utc
        dt_utc = datetime(
            t.tm_year, t.tm_mon, t.tm_mday,
            t.tm_hour, t.tm_min, t.tm_sec,
            tzinfo=timezone.utc
        )
        dt_local = dt_utc + timedelta(hours=time_zone_hours)
        return dt_local.timetuple()
    except Exception as e:
        print(f"Failed to calculate local time: {e}")
        return None


def set_pi_system_time_from_gps(gps: GPS) -> bool:
    """Sets the Pi Zero system clock (in UTC) using GPS UTC timestamp."""
    if gps is None or gps.timestamp_utc is None or gps.timestamp_utc.tm_year < 2026:
        return False

    try:
        t = gps.timestamp_utc
        utc_str = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

        res = os.system(f'sudo date -u -s "{utc_str}" > /dev/null 2>&1')
        if res == 0:
            print(f"--> System clock synced to GPS UTC: {utc_str}")
            return True
        return False
    except Exception as e:
        print(f"Failed to set system time: {e}")
        return False


def print_gps_dms(gps: GPS) -> None:
    """Print GPS coordinates in Degree, Minute, Second (DMS) format."""
    if gps is None or gps.latitude is None or gps.longitude is None:
        print("DMS Coordinates: No GPS Fix")
        return

    lat_deg = int(abs(gps.latitude))
    lat_min_float = (abs(gps.latitude) - lat_deg) * 60.0
    lat_min = int(lat_min_float)
    lat_sec = (lat_min_float - lat_min) * 60.0
    lat_dir = "N" if gps.latitude >= 0 else "S"

    lon_deg = int(abs(gps.longitude))
    lon_min_float = (abs(gps.longitude) - lon_deg) * 60.0
    lon_min = int(lon_min_float)
    lon_sec = (lon_min_float - lon_min) * 60.0
    lon_dir = "E" if gps.longitude >= 0 else "W"

    print(f"Latitude  (DMS): {lat_deg}° {lat_min}' {lat_sec:.2f}\" {lat_dir}")
    print(f"Longitude (DMS): {lon_deg}° {lon_min}' {lon_sec:.2f}\" {lon_dir}")


def get_map_string(gps: GPS) -> str:
    """
    Create from the GPS coordinates a string format (ex: "37.774900 N, 122.419400 W").
    This format can be copy-pasted into standard map apps.
    """
    if gps is None or gps.latitude is None or gps.longitude is None:
        return "GPS location: N/A"

    lat_dir = "N" if gps.latitude >= 0 else "S"
    lon_dir = "E" if gps.longitude >= 0 else "W"
    return f"{abs(gps.latitude):.6f} {lat_dir}, {abs(gps.longitude):.6f} {lon_dir}"


def get_lat_string(gps: GPS) -> str:
    """Create Latitude string from GPS coordinates (ex: "37.7749° N")."""
    if gps is None or gps.latitude is None:
        return "N/A"
    direction = "N" if gps.latitude >= 0 else "S"
    return f"{abs(gps.latitude):.4f}° {direction}"


def get_lon_string(gps: GPS) -> str:
    """Create Longitude string from GPS coordinates (ex: "122.4194° W")."""
    if gps is None or gps.longitude is None:
        return "N/A"
    direction = "E" if gps.longitude >= 0 else "W"
    return f"{abs(gps.longitude):.4f}° {direction}"
