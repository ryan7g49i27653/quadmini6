# MIDI Captain MINI 6 — Custom QC Bidirectional Firmware

## Goal

Replace PaintAudio's stock "Super Mode" firmware (`midicaptain6s.mpy`, a
closed compiled blob) on a MIDI Captain MINI 6 with hand-rolled CircuitPython
that adds **bidirectional** state sync with a Neural DSP Quad Cortex (QC)
Mini — something Super Mode cannot do natively (its `ledmode = [select]`
only tracks local button presses, never actual device state).

Specifically: the MINI 6 has 4 footswitches ("1", "2", "A", "B") mapped to
QC Gig View Page II patches (A2/B2/C2/D2). We want their LEDs to reflect
whichever Page II patch is *actually active on the QC* — including when
changed from the QC's own touchscreen or onboard footswitches, not just
from the MINI 6. This requires the QC to echo state back over MIDI, which
we've confirmed it can do via its "Preset MIDI Out" per-footswitch config.

## Current status

- Hardware pinout confirmed (see `docs/HARDWARE.md`).
- Protocol designed (see `docs/PROTOCOL.md`).
- Draft `code.py` written (see `code.py` in this directory) — **untested on
  real hardware**. Has two known unknowns flagged inline (GP24/GP25 pin
  reservation risk, UART-vs-USB-MIDI ambiguity). See `docs/TESTING.md` for
  the bench-test plan to resolve these before trusting it on stage.
- User has NOT yet updated PaintAudio firmware and does not plan to for
  this project — device is running whatever shipped with a MIDI Captain
  MINI 6 purchased before mid-2026 (Super Mode era, `key0`-`key5` config
  syntax, NOT the FW5.0 `key1/key2/key3/keyA/keyB/keyC` syntax). Firmware
  version specifics are not confirmable from the device itself (no
  documented on-screen version display was found).

## Environment facts (don't re-derive these)

- **Board:** Raspberry Pi Pico, RP2040. CircuitPython 7.3.1
  (`Adafruit CircuitPython 7.3.1 on 2022-06-22`, Board ID `raspberry_pi_pico`).
- **Stock `code.py`:** just `import midicaptain6s` — all stock logic is a
  single closed `.mpy`, not readable/hookable/extendable. A custom firmware
  must be a full replacement, not an extension.
- **`/lib` contents on device:** `adafruit_bitmap_font`,
  `adafruit_display_shapes`, `adafruit_display_text`, `adafruit_hid`,
  `adafruit_imageload`, `adafruit_midi` (source, readable), `adafruit_progressbar`,
  `adafruit_ticks.mpy`, `asyncio`, `midicaptain6s.mpy` (stock app, do not
  import), `neopixel.mpy`, `adafruit_st7789.mpy` (display driver, unused so
  far — no screen support in the draft code).
- **`boot.py`** on device uses `board.GP1` as the "hold at power-on to enter
  USB mode" switch — this is switch "1", confirmed independently and
  matches the community-sourced pinout below.

## File inventory

- `code.py` — draft replacement firmware (untested)
- `docs/HARDWARE.md` — GPIO pinout, NeoPixel/UART pins, known risks
- `docs/PROTOCOL.md` — full MIDI CC scheme, both outgoing (MINI6→QC) and
  incoming (QC→MINI6 state echo)
- `docs/TESTING.md` — bench-test checklist to run before/during development

## Immediate next steps

1. Flash `code.py` to device (back up existing `supersetup` config folder
   first — it has a working, validated Super Mode config for both this QC
   setup and a separate laptop-effects rig, in case this project needs to
   be abandoned or paused).
2. Work through `docs/TESTING.md` checklist.
3. Resolve the two flagged unknowns (pin reservation, UART vs USB MIDI).
4. Iterate on debounce timing, long-press support (not yet implemented —
   stock Super Mode's page+/page− long-press behavior on switches "3"/"C"
   is NOT replicated in the draft code and would need to be added if
   still wanted).
