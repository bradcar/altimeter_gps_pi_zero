#!/usr/bin/env python3
"""
button_rotary_utils.py

GPIO buttons and rotary encoder setup, debounce, state, and button flags.

Currently, 3 Physical buttons defined and rotary encoder with switch
Touch panel can set state for 4 buttons
"""

import time
from gpiozero import Button, RotaryEncoder

# Module State
_button_1 = None
_button_2 = None
_button_3 = None
encoder = None  # Exposed for direct step readings
rotary_switch = None  # Exposed for is_pressed state check

_button_1_pushed = False
_button_2_pushed = False
_button_3_pushed = False
_button_4_pushed = False

_debounce_1_time = 0
_debounce_2_time = 0
_debounce_3_time = 0


def _ticks_ms():
    return int(time.monotonic() * 1000)


# Internal Handlers
def _button_1_handler():
    global _button_1_pushed, _debounce_1_time
    if (_ticks_ms() - _debounce_1_time) > 250:
        _button_1_pushed = True
        _debounce_1_time = _ticks_ms()


def _button_2_handler():
    global _button_2_pushed, _debounce_2_time
    if (_ticks_ms() - _debounce_2_time) > 250:
        _button_2_pushed = True
        _debounce_2_time = _ticks_ms()


def _button_3_handler():
    global _button_3_pushed, _debounce_3_time
    if (_ticks_ms() - _debounce_3_time) > 250:
        _button_3_pushed = True
        _debounce_3_time = _ticks_ms()


# Default Pin initialization
def init_controls(
        pin_button_1=6,
        pin_button_2=5,
        pin_button_3=16,
        pin_rotary_a=21,
        pin_rotary_b=13,
        pin_rotary_sw=19,
        bounce_time=0.05,
):
    global _button_1, _button_2, _button_3, encoder, rotary_switch

    _button_1 = Button(pin_button_1, pull_up=True, bounce_time=bounce_time)
    _button_2 = Button(pin_button_2, pull_up=True, bounce_time=bounce_time)
    _button_3 = Button(pin_button_3, pull_up=True, bounce_time=bounce_time)
    # NOTICE no physical #4 Button

    # Rotary encoder: a = clk, b = DT, max_steps is be default +/-16 steps, 0 means unlimited
    encoder = RotaryEncoder(a=pin_rotary_a, b=pin_rotary_b, bounce_time=0.005)
    rotary_switch = Button(pin_rotary_sw, pull_up=True, bounce_time=bounce_time)

    _button_1.when_pressed = _button_1_handler
    _button_2.when_pressed = _button_2_handler
    _button_3.when_pressed = _button_3_handler


# Event Setters used by Touch Handlers
def trigger_button_1():
    global _button_1_pushed
    _button_1_pushed = True


def trigger_button_2():
    global _button_2_pushed
    _button_2_pushed = True


def trigger_button_3():
    global _button_3_pushed
    _button_3_pushed = True


def trigger_button_4():
    global _button_4_pushed
    _button_4_pushed = True


# Public Check/Consume Functions
def check_button_1():
    global _button_1_pushed
    if _button_1_pushed:
        _button_1_pushed = False
        print("* Button 1 Pushed")
        return True
    return False


def check_button_2():
    global _button_2_pushed
    if _button_2_pushed:
        _button_2_pushed = False
        print("* Button 2 Pushed")
        return True
    return False


def check_button_3():
    global _button_3_pushed
    if _button_3_pushed:
        _button_3_pushed = False
        print("* Button 3 Pushed")
        return True
    return False


def check_button_4():
    global _button_4_pushed
    if _button_4_pushed:
        _button_4_pushed = False
        print("* Button 4 Pushed")
        return True
    return False
