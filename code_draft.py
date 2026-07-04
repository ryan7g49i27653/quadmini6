"""
Dual-boot MINI 6 firmware -- loads either stock PaintAudio Super Mode or a
custom QC bidirectional Gig View LED tracker, chosen by a switch held at
power-on. This replaces `code.py` entirely (both the selector logic and the
custom firmware below live in this one file).

DRAFT v0.1 -- not yet bench-tested. Three known unknowns flagged inline
below; resolve those first before trusting this on stage.

SELECTOR: hold switch "C" (GP11) during power-on to load the custom QC
firmware. If nothing is held, stock `midicaptain6s` loads as normal --
this is the safe default, since it's the field-proven path and gives
access to every existing supersetup page (QUAD, DRKG, etc.), not just the
QC-only behavior below. Switch "1" (GP1) was not used for this choice
because `boot.py` already claims it (hold at power-on -> USB drive mode);
holding it never reaches this file at all.

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
  3. The ST7789 TFT driver is untouched in stock's own usage so far, so its
     `reset`/`rowstart`/`rotation` values below are unverified guesses, not
     confirmed facts like the rest of this pinout. See inline notes at the
     display setup for what to try if the logo doesn't show correctly.

Incoming protocol expected from the QC (set up in the QC's own "Preset MIDI
Out" -> per-footswitch panel, one CC/value pair assigned to each of the 8
Gig View footswitch identities, Channel 1):
  CC 100 value 1 = A1 pressed   CC 100 value 5 = A2 pressed -> light "1"
  CC 100 value 2 = B1 pressed   CC 100 value 6 = B2 pressed -> light "2"
  CC 100 value 3 = C1 pressed   CC 100 value 7 = C2 pressed -> light "A"
  CC 100 value 4 = D1 pressed   CC 100 value 8 = D2 pressed -> light "B"
  (values 1-4 => all four Gig View LEDs off, since none of A2-D2 is active)
"""

import board
import digitalio
import time

# ---------------------------------------------------------------------------
# Firmware selector -- read once at startup, then release the pin either way
# so whichever firmware loads next can claim it fresh.
# ---------------------------------------------------------------------------

_selector = digitalio.DigitalInOut(board.GP11)  # switch "C"
_selector.direction = digitalio.Direction.INPUT
_selector.pull = digitalio.Pull.UP
time.sleep(0.05)
_load_qc_firmware = not _selector.value  # active-low: pressed/held == True
_selector.deinit()

if not _load_qc_firmware:
    import midicaptain6s
else:
    import busio
    import neopixel
    import displayio

    import adafruit_st7789
    import adafruit_imageload
    import adafruit_midi
    from adafruit_midi.control_change import ControlChange

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

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

    DISPLAY_WIDTH = 240
    DISPLAY_HEIGHT = 240
    QC_MODE_IMAGE = "/wallpaper/wp5.bmp"  # Neural DSP logo -- static, shown once

    # -----------------------------------------------------------------------
    # Hardware setup
    # -----------------------------------------------------------------------

    pixels = neopixel.NeoPixel(
        board.GP7, NUM_PIXELS, brightness=BRIGHTNESS, auto_write=False
    )

    # Static display: just enough to make QC mode visually unmistakable from
    # stock/DRKG mode. No PC/CC values, no battery status, no live updates --
    # none of that is needed or implemented, just the logo, once, on boot.
    #
    # UNVERIFIED (this driver is untouched in stock's own usage so far):
    #   - `reset=None` assumes the panel's reset line isn't microcontroller-
    #     controlled. If the screen never lights up, this is the first thing
    #     to check.
    #   - `rowstart`/`colstart` default to 0. Many 240x240 ST7789 panels use
    #     a controller with more physical rows than the visible panel and
    #     need an offset (commonly 80) -- if the image appears shifted or
    #     has garbage bands, try `rowstart=80`.
    #   - `rotation=0` assumes the panel is mounted "as manufactured". If the
    #     logo appears upside-down or sideways, try 90/180/270.
    try:
        displayio.release_displays()
        _spi = busio.SPI(clock=board.GP14, MOSI=board.GP15)
        _display_bus = displayio.FourWire(
            _spi, command=board.GP12, chip_select=board.GP13, reset=None
        )
        display = adafruit_st7789.ST7789(
            _display_bus,
            width=DISPLAY_WIDTH,
            height=DISPLAY_HEIGHT,
            rowstart=0,
            rotation=0,
        )
        _bitmap, _palette = adafruit_imageload.load(
            QC_MODE_IMAGE, bitmap=displayio.Bitmap, palette=displayio.Palette
        )
        _splash = displayio.Group()
        _splash.append(displayio.TileGrid(_bitmap, pixel_shader=_palette))
        display.show(_splash)
    except Exception as _e:
        # The logo is cosmetic; MIDI/LED sync is the mission. Never let a
        # display fault (wrong reset assumption, missing wp5.bmp, etc.)
        # take the whole firmware down on stage.
        import sys
        sys.print_exception(_e)

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

    # -----------------------------------------------------------------------
    # State
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Outgoing actions: button press -> MIDI out
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Incoming state sync: QC echo -> LEDs
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------

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
