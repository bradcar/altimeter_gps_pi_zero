#!/usr/bin/env python3
"""
gps_utils.py

Library Module Methods:

Methods:
    initialize_gps - Initializes the UART connection, synchronizes system time, and configures the GPS module sentence output and refresh rate.
    sync_system_time_and_gps - Cross-synchronizes clocks by setting the Pi system time from valid GPS RTC data, or injecting Pi system time into the GPS if its RTC time is missing/invalid.
    gps_has_valid_time - Parses incoming NMEA RMC sentences to check if the GPS RTC holds a valid UTC date and time (year >= 2026), returning a datetime object or None.
    get_time_from_gps - Converts the GPS UTC timestamp to a local time struct_time using a specified timezone offset.
    set_pi_system_time_from_gps - Updates the Raspberry Pi system clock in UTC using the date command and the current GPS UTC timestamp.
    print_gps_dms - Formats and prints the current GPS latitude and longitude coordinates in degrees, minutes, and seconds (DMS).
    get_map_string - Formats current GPS coordinates into a standard, copy-pasteable map location string (Apple Maps).
    get_lat_string - Formats the GPS latitude into a formatted decimal degree string with N/S orientation.
    get_lon_string - Formats the GPS longitude into a formatted decimal degree string with E/W orientation.

PMTK314 GPS Fields - typical use 2, 4, 5 as shown with *'s
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

    # Turn on the basic GGA, RMC, GGA(Accuracy), update time 1sec, 1Hz (if change Hz, check UART timeout)

    # Time Injection, it uses uart because it is before driver attaches
    sync_system_time_and_gps(uart)
    uart.flush()
    uart.reset_input_buffer()

    # Create GPS Instance, Turn on the basic RMC, GGA, GSA
    gps = adafruit_gps.GPS(uart, debug=False)
    gps.send_command(b"PMTK314,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")

    # update GPS metrics every sec, 1Hz
    gps.send_command(b"PMTK220,1000")

    print("GPS initialization Done.")
    return gps


def sync_system_time_and_gps(uart_connection: serial.Serial):
    """
    GPS time is more accurate than system time, if it is valid. If GPX
    RTC (real time clock) is not valid, inject Pi system time ($PMTK740) into MT3339 GPS
    and verifies PMTK001 acknowledgement.

    Checks GPS RTC time. If missing, injects Pi system time ($PMTK740).
    If GPS time is already valid, synchronizes the Pi system clock directly.
    """
    gps_time = gps_has_valid_time(uart_connection)
    pi_time = time.gmtime()

    if gps_time is not None:
        print(f" * GPS RTC has accurate valid time from RTC:  {gps_time.isoformat()}")
        print(f"   Used GPS to update Pi system (Pi Time was: {pi_time.tm_year:04d}-{pi_time.tm_mon:02d}-{pi_time.tm_mday:02d}T{pi_time.tm_hour:02d}:{pi_time.tm_min:02d}:{pi_time.tm_sec:02d}")
        # Sync Pi system clock directly if Pi clock hasn't been set yet
        utc_str = gps_time.strftime("%Y-%m-%d %H:%M:%S")
        os.system(f'sudo date -u -s "{utc_str}" > /dev/null 2>&1')
        return True

    # Check if Pi system time is sane before injecting into GPS
    # RTC defaults to its firmware release epoch (often 1980, 2000, or 2019).

    if pi_time.tm_year < 2026:
        print(" * Pi system time is invalid (pre-2026) — Skipping using Pi system time to update GPS.")
        return False

    # Inject time to GPS if GPS lacks valid time but Pi system clock is correct
    print(" * GPS missing valid time")
    print("   Used Pi system clock to update GPS clock")
    try:
        payload = f"PMTK740,{pi_time.tm_year:04d},{pi_time.tm_mon:02d},{pi_time.tm_mday:02d},{pi_time.tm_hour:02d},{pi_time.tm_min:02d},{pi_time.tm_sec:02d}"
        checksum = functools.reduce(operator.xor, (ord(c) for c in payload))
        command = f"${payload}*{checksum:02X}\r\n"

        uart_connection.reset_input_buffer()
        uart_connection.write(command.encode("ascii"))
        uart_connection.flush()
        print(f"   Sent Time Injection to GPS: {command.strip()}")
        return True
    except Exception as e:
        print(f" * Error doing time injection into GPS: {e}")
        return False


def gps_has_valid_time(uart_connection: serial.Serial, check_timeout: float = 2.0):
    """
    Reads incoming NMEA sentences to check if the GPS RTC already holds a valid year.

    Since the project operates in 2026, any year prior to 2026 confirms the RTC lacks a
    valid system time and requires time injection or a satellite lock.
    RTC defaults to its firmware release epoch (often 1980, 2000, or 2019).

    :param uart_connection: Active PySerial connection instance.
    :param check_timeout: Seconds to listen for a valid NMEA sentence.
    :return: UTC datetime object if valid (year >= 2026), otherwise None.
    """
    start_time = time.time()
    while time.time() - start_time < check_timeout:
        if uart_connection.in_waiting:
            line = uart_connection.readline().decode("ascii", errors="ignore")

            # Match RMC sentence: $GPRMC,hhmmss.ss,A,lat,N,lon,E,spd,cog,ddmmyy,...
            if "$GPRMC" in line or "$GNRMC" in line:
                parts = line.split(",")

                if len(parts) > 9 and len(parts[1]) >= 6 and len(parts[9]) == 6:
                    try:
                        time_str = parts[1]  # hhmmss.ss
                        date_str = parts[9]  # ddmmyy

                        day = int(date_str[0:2])
                        month = int(date_str[2:4])
                        year = int(date_str[4:6]) + 2000

                        hour = int(time_str[0:2])
                        minute = int(time_str[2:4])
                        second = int(time_str[4:6])

                        if year >= 2026:
                            return datetime(year, month, day, hour, minute, second)
                    except (ValueError, IndexError):
                        continue  # Skip corrupted sentences and keep listening

    return None


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
