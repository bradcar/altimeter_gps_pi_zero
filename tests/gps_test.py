# gps_test.py
"""
Simple GPS module demonstration.
Waits for a fix and print a message every second with the current location and other details.

Initialize the GPS module by changing what data it sends and at what rate.
using PMTK_314_SET_NMEA_OUTPUT and PMTK_220_SET_NMEA_UPDATERATE:
    https://cdn-shop.adafruit.com/datasheets/PMTK_A11.pdf

Significant figures in Lat/Long
0	111 km (69 mi)	Country/large region
1	11.1 km (6.9 mi)	City
2	1.11 km (0.69 mi)	Neighborhood
3	111 m (364 ft)	Large building or city block
4	11.1 m (36.4 ft)	House, parking lot
5	1.11 m (3.6 ft)	Front door, trail
6	11.1 cm (4.4 in)	Survey-grade detail (more precision than most GPS receivers)

TODO can't feed altitude back to this GPS module, need u-blox modules
    need something like: https://www.sparkfun.com/sparkfun-gps-breakout-neo-m9n-u-fl-qwiic.html

Code based on Adafruit:
# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
"""

import serial
import time

import adafruit_gps
from gps_utils import get_local_time, get_map_string


def main():
    # GPS on Pi Zero uses UART with pyserial library
    uart = serial.Serial("/dev/serial0", baudrate=9600, timeout=10)
    gps = adafruit_gps.GPS(uart, debug=False)

    # Turn on the basic GGA, RMC, GGA(Accuracy), update time 1sec, 1Hz (check UART timeout)
    gps.send_command(b"PMTK314,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
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
            # print(
            #     "GMT     timestamp: {}/{}/{} {:02}:{:02}:{:02}".format(  # noqa: UP032
            #         gps.timestamp_utc.tm_mon,  # Grab parts of the time from the
            #         gps.timestamp_utc.tm_mday,  # struct_time object that holds
            #         gps.timestamp_utc.tm_year,  # the fix time.  Note you might
            #         gps.timestamp_utc.tm_hour,  # not get all data like year, day,
            #         gps.timestamp_utc.tm_min,  # month!
            #         gps.timestamp_utc.tm_sec,
            #     )
            # )
            map_string = get_map_string(gps)
            if gps.horizontal_dilution is not None:
                accuracy_string = f"+/- {gps.horizontal_dilution * 2.5:.1f}m"
            else:
                accuracy_string = "accuracy unknown"
            print(f"Map string: {map_string} ({accuracy_string})")
            # print(f"Latitude: {gps.latitude:.6f} degrees")
            # print(f"Longitude: {gps.longitude:.6f} degrees")

            if gps.altitude_m is not None:
                if gps.vdop is not None:
                    est_altitude_string = f"+/- {gps.vdop * 4:.1f}m"
                else:
                    est_altitude_string = "N/A (Waiting for data)"
                print(f"Altitude: {gps.altitude_m} meters ({est_altitude_string})")

            if gps.speed_knots is not None:
                print(f"Speed: {gps.speed_knots * 1.15078:.1f} mph")
            if gps.speed_kmh is not None:
                print(f"Speed: {gps.speed_kmh} km/h")

            if gps.satellites is not None:
                print(f"# satellites: {gps.satellites} (Fix quality: {gps.fix_quality})")

            if gps.track_angle_deg is not None:
                if gps.speed_knots < 2.0:
                    print("Heading: Unreliable (Speed too low)")
                elif gps.speed_knots < 5.0:
                    print(f"Heading: {gps.track_angle_deg}° (+/- 15°)")
                else:
                    print(f"Heading: {gps.track_angle_deg}° (+/- 2°)")

            # if gps.horizontal_dilution is not None:
            #     print(f"Horizontal dilution: {gps.horizontal_dilution}")
            # if gps.height_geoid is not None:
            #     print(f"Height geoid: {gps.height_geoid} meters")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGPS reader exit.")
