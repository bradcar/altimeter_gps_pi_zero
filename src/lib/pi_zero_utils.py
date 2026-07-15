# pi_zero_utils.py
"""
General purpose Pi Zero functions

Temperature:
    pico_temperature(): get temperature of internal on-chip temperature.

Time-out:
    time_out(): wrapper to timeout number of seconds.
"""
import signal
from contextlib import contextmanager


def pico_temperature() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            # Read milli-celsius string ("43500")
            raw_temp = f.read().strip()
            return float(raw_temp) / 1000.0
    except (FileNotFoundError, ValueError, IOError):
        return 0.0


@contextmanager
def timeout(seconds, error_message="Timed out"):
    def signal_handler(signum, frame):
        raise TimeoutError(f"{error_message}")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
