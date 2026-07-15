# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

# Simple GPS module demonstration.
# Waits for a fix and print a message every second with the current location and other details.

# todo can't feed altitude back to this GPS module, need u-blox modules
#   need something like: https://www.sparkfun.com/sparkfun-gps-breakout-neo-m9n-u-fl-qwiic.html

import serial
import time

import adafruit_gps
from adafruit_gps import GPS


def get_local_time(gps, time_zone_hours=0):
    # Convert the struct_time from the GPS to seconds since the epoch
    utc_seconds = time.mktime(gps.timestamp_utc)

    # Subtract 7 hours in seconds (- 7 hours * 60 minutes * 60 seconds = 25200 seconds)
    local_seconds = utc_seconds + time_zone_hours * 3600

    # Convert those seconds back into a clean time structure
    return time.localtime(local_seconds)


def print_dms(gps):
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
    if gps.latitude_degrees is not None:
        lat_dir = "N" if gps.latitude_degrees >= 0 else "S"
    if gps.longitude_degrees is not None:
        lon_dir = "E" if gps.longitude_degrees >= 0 else "W"
    map_string = f"{gps.latitude:.5f} {lat_dir}, {gps.longitude:.5f} {lon_dir}"
    return map_string


def main():
    # On Pi Zero , use the pyserial library for uart access
    uart = serial.Serial("/dev/serial0", baudrate=9600, timeout=10)
    gps = adafruit_gps.GPS(uart, debug=False)

    # Initialize the GPS module by changing what data it sends and at what rate.
    # using PMTK_314_SET_NMEA_OUTPUT and PMTK_220_SET_NMEA_UPDATERATE:
    #   https://cdn-shop.adafruit.com/datasheets/PMTK_A11.pdf

    # Turn on the basic GGA, RMC, GGA(Accuracy)
    gps.send_command(b"PMTK314,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")

    # Set update rate to one second (1hz), if increase, then must update UART timeout above!
    gps.send_command(b"PMTK220,1000")

    last_print = time.monotonic()

    while True:
        has_new_gps = gps.update()

        # Every second print out current location details if there's a fix.
        current = time.monotonic()
        if current - last_print >= 1.0:
            last_print = current
            if not gps.has_fix:
                # Try again if we don't have a fix yet.
                print("Waiting for fix...")
                continue

            print()
            print("=" * 40)  # Print a separator line.

            # PDX DST -7 hours
            time_zone_hours = -7
            time_zone_string = "PDX"
            day_light_savings_string = "DST"
            local_time = get_local_time(gps, time_zone_hours)

            print(
                "PDX DST timestamp: {}/{}/{} {:02}:{:02}:{:02}".format(  # noqa: UP032
                    local_time.tm_mon,
                    local_time.tm_mday,
                    local_time.tm_year,
                    local_time.tm_hour,
                    local_time.tm_min,
                    local_time.tm_sec,
                )
            )
            print(
                "GMT Act timestamp: {}/{}/{} {:02}:{:02}:{:02}".format(  # noqa: UP032
                    gps.timestamp_utc.tm_mon,  # Grab parts of the time from the
                    gps.timestamp_utc.tm_mday,  # struct_time object that holds
                    gps.timestamp_utc.tm_year,  # the fix time.  Note you might
                    gps.timestamp_utc.tm_hour,  # not get all data like year, day,
                    gps.timestamp_utc.tm_min,  # month!
                    gps.timestamp_utc.tm_sec,
                )
            )
            map_string = get_map_string(gps)
            print(f"Map string: {map_string}  (+/- {gps.horizontal_dilution * 2.5:.1f}m)")
            print(f"Latitude: {gps.latitude:.6f} degrees")
            print(f"Longitude: {gps.longitude:.6f} degrees")
            if gps.altitude_m is not None:
                if gps.vdop is not None:
                    est_altitude_string = f"+/- {gps.vdop * 4:.1f}m"
                else:
                    est_altitude_string = "N/A (Waiting for data)"
                print(f"Altitude: {gps.altitude_m} meters ({est_altitude_string})")

            if gps.speed_knots is not None:
                print(f"Speed: {gps.speed_knots * 1.15078:.1f} mph, {gps.speed_knots} knots")
            if gps.speed_kmh is not None:
                print(f"Speed: {gps.speed_kmh} km/h")

            if gps.satellites is not None:
                print(f"# satellites: {gps.satellites}")
            print(f"Fix quality: {gps.fix_quality}")

            if gps.track_angle_deg is not None:
                if gps.speed_knots < 2.0:
                    print("Heading: Unreliable (Speed too low)")
                elif gps.speed_knots < 5.0:
                    print(f"Heading: {gps.track_angle_deg}° (Estimated Accuracy: ±15°)")
                else:
                    print(f"Heading: {gps.track_angle_deg}° (Estimated Accuracy: ±2°)")
                print(f"Track angle: {gps.track_angle_deg} degrees")

            if gps.horizontal_dilution is not None:
                print(f"Horizontal dilution: {gps.horizontal_dilution}")
            if gps.height_geoid is not None:
                print(f"Height geoid: {gps.height_geoid} meters")


if __name__ == "__main__":
    main()
