"""
Custom MINI 6 firmware -- QC bidirectional Gig View LED tracking.
Replaces stock PaintAudio Super Mode (midicaptain6s.mpy) entirely.

DRAFT v0.1 -- not yet bench-tested. Two known unknowns flagged inline below;
resolve those first before trusting this on stage.

Hardware (RP2040 / CircuitPython 7.3.1), confirmed via community
reverse-engineering (PySwitch project's pa_midicaptain_mini_6.py) plus our
own boot.py cross-check (GP1 = switch "1", matches independently):

  Switch "1" -> GP1  -> pixels 0,1,2    -> outgoing CC 39 v127 (Gig View A2)
  Switch "2" -> GP25 -> pixels 3,4,5    -> outgoing CC 40 v127 (Gig View B2)
  Switch "3" -> GP24 -> pixels 6,7,8    -> outgoing CC 46 toggle (Gig View open/close)
  Switch "A" -> GP9  -> pixels 9,10,11  -> outgoing CC 41 v127 (Gig View C2)
  Switch "B" -> GP10 -> pixels 12,13,14 -> outgoing CC 42 v127 (Gig View D2)
  Switch "C" -> GP11 -> pixels 15,16,17 -> outgoing CC 47 toggle (Stomp/Scene)

  NeoPixel data pin: GP7 (18 pixels total, 3 per switch, in series)
  MIDI UART: TX=GP16, RX=GP17 @ 31250 baud (5-pin DIN in/out)

KNOWN UNKNOWNS -- VERIFY ON FIRST FLASH:
  1. GP24/GP25 are reserved for VBUS_SENSE/onboard-LED on genuine Raspberry
     Pi Pico modules. PaintAudio's actual Mini 6 PCB reportedly works fine
     on these pins as shipped, but if switch "2" or "3" don't respond,
     this is the first thing to suspect.
  2. One reference claims PA MIDICaptain devices have "no UART" and need
     usb_midi instead, contradicting the GP16/17 uart_midi_tx/rx labels.
     If nothing arrives via the UART midi.receive() loop below, the
     device may need usb_midi.ports[0] instead -- see commented-out
     alternative near the MIDI setup.

Incoming protocol expected from the QC (set up in the QC's own "Preset MIDI
Out" -> per-footswitch panel, one CC/value pair assigned to each of the 8
Gig View footswitch identities, Channel 1):
  CC 100 value 1 = A1 pressed   CC 100 value 5 = A2 pressed -> light "1"
  CC 100 value 2 = B1 pressed   CC 100 value 6 = B2 pressed -> light "2"
  CC 100 value 3 = C1 pressed   CC 100 value 7 = C2 pressed -> light "A"
  CC 100 value 4 = D1 pressed   CC 100 value 8 = D2 pressed -> light "B"
  (values 1-4 => all four Gig View LEDs off, since none of A2-D2 is active)
"""

import time

import board
import busio
import digitalio
import neopixel

import adafruit_midi
from adafruit_midi.control_change import ControlChange

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIDI_CHANNEL = 1  # 1-16 as configured on the QC; adafruit_midi wants 0-15

NUM_PIXELS = 18
BRIGHTNESS = 0.3

COLOR_OFF = (0, 0, 0)
COLOR_A2 = (0, 255, 0)          # green
COLOR_B2 = (255, 0, 0)          # red
COLOR_C2 = (255, 128, 0)        # orange
COLOR_D2 = (255, 255, 0)        # yellow
COLOR_GIGVIEW_ON = (255, 255, 255)
COLOR_GIGVIEW_OFF = (40, 40, 40)
COLOR_STOMP = (255, 0, 255)     # magenta
COLOR_SCENE = (0, 0, 255)       # blue

SWITCH_PINS = {
    "1": board.GP1,
    "2": board.GP25,
    "3": board.GP24,
    "A": board.GP9,
    "B": board.GP10,
    "C": board.GP11,
}

SWITCH_PIXELS = {
    "1": (0, 1, 2),
    "2": (3, 4, 5),
    "3": (6, 7, 8),
    "A": (9, 10, 11),
    "B": (12, 13, 14),
    "C": (15, 16, 17),
}

DEBOUNCE_S = 0.03

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

pixels = neopixel.NeoPixel(
    board.GP7, NUM_PIXELS, brightness=BRIGHTNESS, auto_write=False
)

switches = {}
for _name, _pin in SWITCH_PINS.items():
    _io = digitalio.DigitalInOut(_pin)
    _io.direction = digitalio.Direction.INPUT
    _io.pull = digitalio.Pull.UP
    switches[_name] = _io

uart = busio.UART(board.GP16, board.GP17, baudrate=31250, timeout=0.001)
midi = adafruit_midi.MIDI(
    midi_in=uart,
    midi_out=uart,
    in_channel=MIDI_CHANNEL - 1,
    out_channel=MIDI_CHANNEL - 1,
)

# If unknown #2 above turns out to be true, comment out the busio/adafruit_midi
# block above and use this instead:
#
# import usb_midi
# midi = adafruit_midi.MIDI(
#     midi_in=usb_midi.ports[0],
#     midi_out=usb_midi.ports[1],
#     in_channel=MIDI_CHANNEL - 1,
#     out_channel=MIDI_CHANNEL - 1,
# )

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

gig_view_open = False           # local optimistic state, switch "3"
next_press_is_stomp = True      # local optimistic state, switch "C"

last_state = {name: switches[name].value for name in switches}
last_change = {name: 0.0 for name in switches}


def set_pixel_group(name, color):
    a, b, c = SWITCH_PIXELS[name]
    pixels[a] = color
    pixels[b] = color
    pixels[c] = color


def clear_gigview_leds():
    for name in ("1", "2", "A", "B"):
        set_pixel_group(name, COLOR_OFF)


def light_gigview_led(name, color):
    clear_gigview_leds()
    set_pixel_group(name, color)


# Initial LED state on boot
clear_gigview_leds()
set_pixel_group("3", COLOR_GIGVIEW_OFF)
set_pixel_group("C", COLOR_SCENE)  # QC has no MIDI feedback for current Mode; Scene
                                    # is the assumed default since that's where the QC
                                    # spends nearly all its time. Wrong the rare times it
                                    # isn't, but self-corrects within 1-2 presses of "C".
pixels.show()

# ---------------------------------------------------------------------------
# Outgoing actions: button press -> MIDI out
# ---------------------------------------------------------------------------


def send_cc(cc_num, value):
    midi.send(ControlChange(cc_num, value))


def on_press(name):
    global gig_view_open, next_press_is_stomp

    if name == "1":
        send_cc(39, 127)
    elif name == "2":
        send_cc(40, 127)
    elif name == "3":
        gig_view_open = not gig_view_open
        send_cc(46, 127 if gig_view_open else 0)
        set_pixel_group("3", COLOR_GIGVIEW_ON if gig_view_open else COLOR_GIGVIEW_OFF)
        pixels.show()
    elif name == "A":
        send_cc(41, 127)
    elif name == "B":
        send_cc(42, 127)
    elif name == "C":
        if next_press_is_stomp:
            send_cc(47, 2)
            set_pixel_group("C", COLOR_STOMP)
        else:
            send_cc(47, 1)
            set_pixel_group("C", COLOR_SCENE)
        next_press_is_stomp = not next_press_is_stomp
        pixels.show()


# ---------------------------------------------------------------------------
# Incoming state sync: QC echo -> LEDs
# ---------------------------------------------------------------------------

GIGVIEW_ECHO_MAP = {
    5: ("1", COLOR_A2),
    6: ("2", COLOR_B2),
    7: ("A", COLOR_C2),
    8: ("B", COLOR_D2),
}


def handle_incoming_cc(cc_num, value):
    if cc_num != 100:
        return
    if value in (1, 2, 3, 4):
        clear_gigview_leds()
        pixels.show()
    elif value in GIGVIEW_ECHO_MAP:
        name, color = GIGVIEW_ECHO_MAP[value]
        light_gigview_led(name, color)
        pixels.show()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

while True:
    now = time.monotonic()

    for name, io in switches.items():
        current = io.value
        if current != last_state[name] and (now - last_change[name]) > DEBOUNCE_S:
            last_change[name] = now
            last_state[name] = current
            if current is False:  # active-low: False means pressed
                on_press(name)

    msg = midi.receive()
    if msg is not None and isinstance(msg, ControlChange):
        handle_incoming_cc(msg.control, msg.value)

    time.sleep(0.001)