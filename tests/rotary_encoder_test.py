# rotary_encoder_test.py
"""
Rotary Encoder Port for Raspberry Pi Zero

Adjusts new_alt_feet by +/- 1ft per detent, or by 25 ft if the push button is toggled.

Hardware Configuration Pi Zero
    Encoder CLK: gpio 21 (Pin 40)
    Encoder DT:  gpio 13 (Pin 33)
    Encoder SW:  gpio 19 (Pin 35)
    3v3    - 3v3
    Ground - pin 39 of 2x20
"""

import time
from gpiozero import RotaryEncoder, Button

# Rotary encoder setup (CLK=a, DT=b)
encoder = RotaryEncoder(a=21, b=13, bounce_time=0.005)
rotary_switch = Button(19, pull_up=True, bounce_time=0.05)

DEBUG = True
SWITCH_MULTIPLIER = 25
rotary_multiplier = 1  # Global variable will toggle between 1 and SWITCH_MULTIPLIER

# Track the cumulative steps of the encoder
last_steps = encoder.steps

def toggle_multiplier():
    global rotary_multiplier
    # Toggle global multiplier between 1 and SWITCH_MULTIPLIER
    rotary_multiplier = SWITCH_MULTIPLIER if rotary_multiplier == 1 else 1
    if DEBUG:
        print(f"--- Multiplier changed to: {rotary_multiplier}x ---")

rotary_switch.when_pressed = toggle_multiplier

print("Rotary encoder active. Rotate knob or press switch...")
new_alt_feet = 365

try:
    while True:
        current_steps = encoder.steps

        if current_steps != last_steps:
            # Track number steps we turned (and direction)
            delta = current_steps - last_steps

            # Apply scaling
            new_alt_feet += delta * rotary_multiplier
            last_steps = current_steps

            if DEBUG:
                print(f"new_alt_feet = {new_alt_feet}")

        time.sleep(0.02)

except KeyboardInterrupt:
    print("\nExiting encoder script.")