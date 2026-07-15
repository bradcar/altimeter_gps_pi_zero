# rotary_menu_select.py
"""
Rotary Encoder Selector for Raspberry Pi Zero
Prints "Button Pressed" and the selected number upon switch press.

Hardware Configuration Pi Zero
    Encoder CLK: gpio 13 (Pin 33)
    Encoder DT:  gpio 19 (Pin 35)
    Encoder SW:  gpio 26 (Pin 37)
    3v3    - pin 17 of 2x20
    Ground - pin 39 of 2x20
"""
import time
from gpiozero import RotaryEncoder, Button

encoder = RotaryEncoder(a=13, b=19, bounce_time=0.005)
rotary_switch = Button(26, pull_up=True, bounce_time=0.05)

# Track the cumulative steps of the encoder
last_steps = encoder.steps


def button_pressed():
    # Retrieve the current raw step count from the encoder
    current_val = encoder.steps
    print("Button Pressed")
    print("Selected Number is :", current_val)


# Attach the button release/press event (non-blocking)
rotary_switch.when_pressed = button_pressed

print("Rotary encoder active. Rotate knob or press switch...")

try:
    while True:
        current_steps = encoder.steps

        if current_steps != last_steps:
            # Detect change in value and update tracking variable
            last_steps = current_steps
            print(f"value_new={current_steps}")

        # Small sleep to prevent eating 100% CPU on the Linux OS thread
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nExiting encoder script.")
