# Hardware Reference — MIDI Captain MINI 6

## Source of truth

Pin assignments below come from the **PySwitch** project
(`pa_midicaptain_mini_6.py` device definition, part of
github.com/Tunetown/PySwitch and forks), an actively maintained open-source
CircuitPython firmware for this exact device family, cross-referenced
against forum-reported full GPIO tables for the wider MIDI Captain product
line. Switch "1" = GP1 was independently confirmed from this device's own
stock `boot.py` (used as the "hold at boot to enter USB mode" pin), which
matches the PySwitch data exactly — good independent cross-check.

**Not yet independently verified on this specific physical unit** — verify
via the bench test in `TESTING.md` before relying on any of this in a
performance context.

## Switch GPIO + NeoPixel pixel index map

| Physical switch | GPIO  | LED pixel indices (3 per switch, in series) |
|---|---|---|
| 1 | GP1  | 0, 1, 2 |
| 2 | GP25 | 3, 4, 5 |
| 3 | GP24 | 6, 7, 8 |
| A | GP9  | 9, 10, 11 |
| B | GP10 | 12, 13, 14 |
| C | GP11 | 15, 16, 17 |

Total 18 NeoPixels, single data line.

**Switch "A" (GP9) is dual-purpose in `code_draft.py`:** read once at
power-on as the QC-vs-stock firmware selector (hold = load stock; default,
nothing held, loads QC), then — only within the QC branch — reused for its
normal runtime function (select Gig View C2, CC 41). Flipped from switch
"C" to switch "A" 2026-07-05 now that QC is the default boot path; switch
"C" is back to being solely the runtime Stomp/Scene toggle. See
`docs/PROTOCOL.md`.

## Other confirmed pins

| Function | GPIO |
|---|---|
| NeoPixel data | GP7 |
| MIDI UART TX | GP16 |
| MIDI UART RX | GP17 |
| TFT DC | GP12 |
| TFT CS | GP13 |
| TFT SPI CLK | GP14 |
| TFT SPI MOSI | GP15 |
| Expression pedal 1 | GP27 |
| Expression pedal 2 | GP28 |

MIDI UART baud rate: 31250 (MIDI standard).

Display driver in `/lib`: `adafruit_st7789.mpy`. Used minimally in
`code_draft.py`'s QC branch as of 2026-07-04 — shows `wallpaper/wp5.bmp`
(Neural DSP logo, confirmed 240x240, 4bpp indexed) once at boot as a
static "you're in QC mode" indicator, no live updates, no PC/CC values, no
battery status. Bench-tested 2026-07-05: `reset=None` and `rotation=0`
were correct; `rowstart=0` was not (needed `rowstart=80` to fix a garbage
band across the top of the panel) — see known unknown #3 in
`code_draft.py`'s docstring. Also bench-observed 2026-07-05: the panel
shows leftover GRAM noise (a white pixelated screen) for a beat before the
logo finishes painting in; fixed by painting a solid black frame
immediately after display init, before decoding/loading the bitmap.

## Known risks / unknowns to verify

### 1. GP24 / GP25 reserved-pin conflict (possible, unconfirmed on this unit)

On genuine Raspberry Pi Pico modules, GP23/24/25 are internally used for
SMPS mode select, VBUS sense, and the onboard LED respectively. A separate
DIY builder (using bare Pico modules + their own switches/NeoPixels, NOT a
purchased PaintAudio unit) had to remap switch 2 off GP25 (to GP19) and
suggested GP20 as an alternative for switch 3 instead of GP24.

However: PaintAudio's actual Mini 6 PCB is reported by multiple real users
of the PySwitch firmware to work "out of the box" on GP24/GP25 without
modification — this device's `boot_out.txt` identifies as
`raspberry_pi_pico`, but the actual PCB likely doesn't use the same
onboard regulator/LED circuitry that reserves those pins on a genuine Pico
dev board.

**If switch "2" or "3" don't register presses reliably, this is the first
thing to suspect.** Fallback: remap those two switches to spare GPIOs
(GP19/GP20 have precedent as substitutes from the DIY builder's report).

### 2. UART vs. USB MIDI (unresolved, contradictory evidence)

The pinout table explicitly labels GP16/17 as `uart_midi_tx`/`uart_midi_rx`.
However, one code comment from the PySwitch project states: *"USB Midi
in/out for PA MIDICaptain devices. No UART, so ports have to be adafruit
MIDI ports from the usb_midi module."*

This device does have physical 5-pin DIN MIDI IN/OUT jacks (confirmed —
it's how it currently talks to the QC via cable), which strongly implies a
real UART path exists in hardware. The contradictory comment may refer to
a different device/config path, or may indicate the UART needs different
setup than a simple `busio.UART()` call.

**Resolution:** the draft `code.py` uses UART as primary, with a
commented-out `usb_midi.ports[]` fallback ready to swap in if UART proves
silent on first test.

## Library inventory available on-device (`/lib`)

- `adafruit_midi` — **source, not compiled**. Real API is directly
  readable/inspectable on-device if behavior is unclear.
- `neopixel.mpy` — standard Adafruit NeoPixel driver, compiled but
  publicly documented (not proprietary).
- `adafruit_st7789.mpy` — TFT display driver, compiled, publicly
  documented. Used for the static QC-mode logo (see above).
- `adafruit_imageload` — used to load `wp5.bmp` for the same purpose.
- `adafruit_hid` — keyboard/mouse HID emulation, unused for this project.
- `adafruit_bitmap_font`, `adafruit_display_shapes`, `adafruit_display_text`,
  `adafruit_progressbar` — display/UI helpers, still unused (no PC/CC/text
  rendering planned — the QC branch only ever shows the static logo).
- `asyncio` — available if an async event loop structure is preferred over
  the draft's simple polling `while True` loop.
- `midicaptain6s.mpy` — **stock application, do not import.** This is what
  we're replacing.
