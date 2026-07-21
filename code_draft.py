"""
Dual-boot MINI 6 firmware -- loads either stock PaintAudio Super Mode or a
custom QC bidirectional Gig View LED tracker, chosen by a switch held at
power-on. This replaces `code.py` entirely (both the selector logic and the
custom firmware below live in this one file).

Bench-tested on real hardware 2026-07-05: switches, LEDs, outgoing and
incoming MIDI, dual-boot selector, and display all confirmed working. The
three original known unknowns below are all resolved.

Review fixes applied 2026-07-21 (bounded MIDI drain + 256B UART buffer,
guarded stock import, switch settle delay, preset-load reset of local
optimistic state) -- all bench-tested on real hardware 2026-07-21.

SELECTOR: QC firmware is the default at power-on (nothing held). Hold
switch "A" (GP9) during power-on instead to load stock `midicaptain6s`
for the unrelated DRKG laptop-effects rig. Flipped 2026-07-05 now that QC
is the primary use -- previously "C" held loaded QC and stock was the
default. Switch "1" (GP1) was not used for this choice because `boot.py` already
claims it (hold at power-on -> USB drive mode). Note (bench-discovered
2026-07-05): holding "1" does NOT stop this file from running -- boot.py
enables the USB drive and then code.py runs as normal, so a switch-1 boot
lands in the QC branch *with* the drive mounted, which is handy for
editing files while the QC firmware is live. It's still wrong as a
selector, though: firmware choice would then be entangled with USB mode.

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

KNOWN UNKNOWNS -- ALL RESOLVED ON BENCH, 2026-07-05:
  1. GP24/GP25 reserved-pin risk: not an issue on this unit -- switches
     "2" and "3" work as shipped on those pins.
  2. UART vs. USB MIDI: UART on GP16/17 works in both directions; the
     "no UART" reference did not apply here. (A usb_midi fallback block
     is still commented out near the MIDI setup, just in case.)
  3. Display driver: `reset=None` and `rotation=0` were correct;
     `rowstart=80` was required (rowstart=0 showed a garbage band across
     the top with the image shifted down). Painting requires auto_refresh
     off + explicit refresh() calls -- see the display setup comments.

Incoming protocol expected from the QC (set up in the QC's own "Preset MIDI
Out" -> per-footswitch panel, one CC/value pair assigned to each of the 8
Gig View footswitch identities, Channel 1):
  CC 100 value 1 = A1 pressed   CC 100 value 5 = A2 pressed -> light "1"
  CC 100 value 2 = B1 pressed   CC 100 value 6 = B2 pressed -> light "2"
  CC 100 value 3 = C1 pressed   CC 100 value 7 = C2 pressed -> light "A"
  CC 100 value 4 = D1 pressed   CC 100 value 8 = D2 pressed -> light "B"
  CC 100 value 0 = explicit "zero out", sent by each live-used preset's
                   On Preset Load config: no scene active, and all four
                   learned colors are forgotten (see below)

  CC 101/102/103/104 = scene color for switch "1"/"2"/"A"/"B": value 1-8
  picks from QC_COLOR_PALETTE (matches the QC's scene color picker),
  value 0 forgets. Sent as extra On Preset Load messages (or attached to
  footswitch echoes, or from anywhere else -- handled whenever received).

  Gig View LEDs are three-state (never fully off):
    bright scene color = active scene    dim scene color = inactive
    white (bright or dim) = color not learned since boot / last value 0
  So an opted-in preset shows four dim colored LEDs from the moment it
  loads; a preset that teaches nothing shows dim white, which is honest
  ("unknown") rather than stale. See docs/PROTOCOL.md.
"""

import board
import digitalio
import time

# ---------------------------------------------------------------------------
# Firmware selector -- read once at startup, then release the pin either way
# so whichever firmware loads next can claim it fresh. QC is the default
# (unheld) path; hold switch "A" to fall back to stock/DRKG instead.
# ---------------------------------------------------------------------------

_selector = digitalio.DigitalInOut(board.GP9)  # switch "A"
_selector.direction = digitalio.Direction.INPUT
_selector.pull = digitalio.Pull.UP
time.sleep(0.05)
_load_stock_firmware = not _selector.value  # active-low: pressed/held == True
_selector.deinit()

if _load_stock_firmware:
    try:
        import midicaptain6s
    except Exception as _e:
        # A broken/missing stock module must not strand the pedal at the
        # REPL (no LEDs, no MIDI). Fall through to the QC firmware instead.
        # Best effort: if the stock module claimed pins before raising, the
        # QC setup below may still fail -- no worse than dying here.
        import sys
        sys.print_exception(_e)
        _load_stock_firmware = False

if not _load_stock_firmware:
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

    COLOR_UNKNOWN = (255, 255, 255) # white -- scene color not yet learned
    COLOR_GIGVIEW_ON = (255, 255, 255)
    COLOR_GIGVIEW_OFF = (40, 40, 40)
    COLOR_STOMP = (255, 0, 255)     # magenta
    COLOR_SCENE = (0, 0, 255)       # blue

    # Inactive Gig View switches show their scene color divided by this
    # (dim-but-visible; tune on bench -- higher = dimmer). 6 read slightly
    # too bright on bench 2026-07-05; 8 is the adjusted value.
    DIM_DIVISOR = 8

    # QC scene-color palette, selectable per switch via incoming CC 101-104
    # (see docs/PROTOCOL.md). Values 1-8 follow the QC's own scene color
    # picker left to right; RGB approximations, tune on bench against the
    # QC screen if they look off.
    QC_COLOR_PALETTE = {
        1: (255, 255, 0),    # yellow
        2: (255, 128, 0),    # orange
        3: (255, 0, 0),      # red
        4: (255, 0, 128),    # pink
        5: (128, 0, 255),    # purple
        6: (0, 0, 255),      # blue
        7: (0, 255, 255),    # cyan
        8: (0, 255, 0),      # green
    }

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

    # Static display: black frame first (hides the panel's power-on GRAM
    # noise while the bmp decodes), then the Neural DSP logo, once. No
    # PC/CC values, no battery status, no live updates. Bench-confirmed
    # 2026-07-05: reset=None and rotation=0 correct; rowstart=80 required
    # (0 shows a garbage band, image shifted down); auto_refresh must be
    # off, since a background refresh can be "in progress" on the bus,
    # making a manual refresh() silently no-op -- with it off, each
    # refresh() is a guaranteed synchronous paint. It stays off for good:
    # the display is static after boot.
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
            rowstart=80,
            rotation=0,
        )
        display.auto_refresh = False

        _blank_bitmap = displayio.Bitmap(DISPLAY_WIDTH, DISPLAY_HEIGHT, 1)
        _blank_palette = displayio.Palette(1)
        _blank_palette[0] = 0x000000
        _blank_group = displayio.Group()
        _blank_group.append(displayio.TileGrid(_blank_bitmap, pixel_shader=_blank_palette))
        display.show(_blank_group)
        display.refresh(target_frames_per_second=None, minimum_frames_per_second=0)

        _bitmap, _palette = adafruit_imageload.load(
            QC_MODE_IMAGE, bitmap=displayio.Bitmap, palette=displayio.Palette
        )
        _splash = displayio.Group()
        _splash.append(displayio.TileGrid(_bitmap, pixel_shader=_palette))
        display.show(_splash)
        display.refresh(target_frames_per_second=None, minimum_frames_per_second=0)
    except Exception as _e:
        # The logo is cosmetic; MIDI/LED sync is the mission. Never let a
        # display fault (missing wp5.bmp, etc.) take the whole firmware
        # down on stage.
        import sys
        sys.print_exception(_e)

    switches = {}
    for _name, _pin in SWITCH_PINS.items():
        _io = digitalio.DigitalInOut(_pin)
        _io.direction = digitalio.Direction.INPUT
        _io.pull = digitalio.Pull.UP
        switches[_name] = _io
    # Let the pull-ups settle before the last_state snapshot below -- the
    # selector pin gets the same 50ms. Without it the snapshot can capture
    # a floating read and fire a phantom press (a real CC to the QC) on
    # the first loop pass.
    time.sleep(0.05)

    # receiver_buffer_size: the default 64 bytes is only ~4ms of headroom at
    # 31250 baud. A preset load bursts 5 CCs (CC 100 + 101-104) back-to-back;
    # with Clock or Active Sensing interleaved the buffer can overrun and
    # drop CCs silently. 256 gives slack without meaningful RAM cost.
    uart = busio.UART(
        board.GP16, board.GP17, baudrate=31250, timeout=0.001,
        receiver_buffer_size=256,
    )
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

    # Per-switch Gig View scene colors, learned from incoming CC 101-104.
    # None = not learned (shown dim white). CC 100 value 0 (preset load)
    # forgets all four -- each preset re-teaches its own colors, or the
    # LEDs honestly say "unknown" instead of lying with stale colors.
    # lit_switch tracks which scene is active for the bright/dim split.
    scene_colors = {"1": None, "2": None, "A": None, "B": None}
    lit_switch = None

    last_state = {name: switches[name].value for name in switches}
    last_change = {name: 0.0 for name in switches}

    def set_pixel_group(name, color):
        a, b, c = SWITCH_PIXELS[name]
        pixels[a] = color
        pixels[b] = color
        pixels[c] = color

    def gigview_led_color(name):
        # Bright scene color when active; dim scene color when inactive;
        # white in either case if the color hasn't been learned yet.
        color = scene_colors[name] or COLOR_UNKNOWN
        if name == lit_switch:
            return color
        return (color[0] // DIM_DIVISOR, color[1] // DIM_DIVISOR, color[2] // DIM_DIVISOR)

    def repaint_gigview_leds():
        for name in ("1", "2", "A", "B"):
            set_pixel_group(name, gigview_led_color(name))

    # Initial LED state on boot
    repaint_gigview_leds()
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

    GIGVIEW_ECHO_MAP = {5: "1", 6: "2", 7: "A", 8: "B"}
    COLOR_CC_TO_SWITCH = {101: "1", 102: "2", 103: "A", 104: "B"}

    def handle_incoming_cc(cc_num, value):
        global lit_switch, gig_view_open, next_press_is_stomp

        if cc_num == 100:
            if value == 0:
                # Explicit "zero out" (each preset's On Preset Load config):
                # no scene active AND forget all learned colors -- the new
                # preset either re-teaches its own via CC 101-104 or the
                # LEDs show dim white ("unknown") rather than stale colors.
                lit_switch = None
                for _name in scene_colors:
                    scene_colors[_name] = None
                # Also reset the two locally-owned optimistic states to
                # their boot assumptions (Gig View closed, Scene mode) --
                # assumed QC behavior on preset change, bench-verify.
                # Without this the "3"/"C" LEDs lie until pressed twice.
                gig_view_open = False
                next_press_is_stomp = True
                set_pixel_group("3", COLOR_GIGVIEW_OFF)
                set_pixel_group("C", COLOR_SCENE)
                repaint_gigview_leds()
                pixels.show()
            elif value in (1, 2, 3, 4):
                # A Page I scene is active: nothing on Page II is, so no
                # switch is bright. Learned colors keep showing dim.
                lit_switch = None
                repaint_gigview_leds()
                pixels.show()
            elif value in GIGVIEW_ECHO_MAP:
                lit_switch = GIGVIEW_ECHO_MAP[value]
                repaint_gigview_leds()
                pixels.show()
        elif cc_num in COLOR_CC_TO_SWITCH:
            # Per-switch scene color: 1-8 picks from QC_COLOR_PALETTE,
            # 0 forgets (back to dim white), anything else is ignored.
            # Applies immediately, bright or dim as appropriate.
            name = COLOR_CC_TO_SWITCH[cc_num]
            if value == 0:
                scene_colors[name] = None
            elif value in QC_COLOR_PALETTE:
                scene_colors[name] = QC_COLOR_PALETTE[value]
            else:
                return
            set_pixel_group(name, gigview_led_color(name))
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

        # Drain the queue each pass, bounded so switches never starve. One
        # message per pass at a ~1-3ms loop period cannot keep up with a
        # preset load's 5-CC burst, and the buffer overruns if the QC ever
        # interleaves Clock or Active Sensing.
        for _ in range(8):
            msg = midi.receive()
            if msg is None:
                break
            if isinstance(msg, ControlChange):
                handle_incoming_cc(msg.control, msg.value)

        time.sleep(0.001)
