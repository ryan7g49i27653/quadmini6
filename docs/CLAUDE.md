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

The MINI 6 is also used for a second, unrelated rig (a laptop-based
multi-effects setup — see `supersetup/page1.txt`, page name `DRKG`) at
different times, never simultaneously with the QC. Since a custom
firmware has to fully replace stock `code.py` (see "Environment facts"
below), we can't keep both stock's multi-page support and the new QC
bidirectional behavior running side by side in the same firmware without
reimplementing every stock page in Python. Instead, `code_draft.py` is
designed as a **dual-boot selector**: it checks one switch at power-on and
either hands off to unmodified stock `midicaptain6s` (all pages, DRKG
included, exactly as they work today) or runs the new QC-only logic — no
re-flashing required to switch between the two rigs. See "SELECTOR" note
at the top of `code_draft.py` and `docs/PROTOCOL.md` for details.

## Current status

- Hardware pinout confirmed (see `docs/HARDWARE.md`).
- Protocol designed (see `docs/PROTOCOL.md`).
- Draft firmware written as `code_draft.py` (kept separate from the live
  `code.py` on purpose until bench-tested — see "File inventory" below) —
  **untested on real hardware**. Has two known unknowns flagged inline
  (GP24/GP25 pin reservation risk, UART-vs-USB-MIDI ambiguity). See
  `docs/TESTING.md` for the bench-test plan to resolve these before
  trusting it on stage.
- Design reviewed against the live `supersetup/page0.txt` config and the
  Quad Cortex mini manual (`docs/Quad Cortex Mini User Manual 4.0.0.pdf`,
  gitignored, kept locally for reference):
  - Forward direction (MINI 6 → QC) confirmed to replicate `page0.txt`'s
    CC mapping exactly, switch by switch.
  - Backward direction (QC → MINI 6) confirmed to match the intended
    behavior: any Page I scene selected on the QC (from any source) clears
    all four Gig View LEDs on the MINI 6; any Page II scene lights the
    matching LED. See `docs/PROTOCOL.md` for the full mapping.
  - Confirmed via the manual that the QC has **no MIDI feedback for
    current Mode (Stomp/Scene/Preset) or Gig View open/closed state** —
    Preset MIDI Out only echoes the 8 Gig View scene footswitches. Switch
    "3" (Gig View) and switch "C" (Mode) remain locally-tracked/optimistic,
    same limitation stock Super Mode always had (not a regression).
  - Boot-state defaults decided: switch "3" LED defaults to closed, which
    matches the QC's actual boot behavior (Gig View is always closed on
    power-up). Switch "C" LED defaults to Scene, since the QC remembers
    its last-used mode across power cycles and is in Scene mode the vast
    majority of the time in practice; wrong in the rare case, self-corrects
    within 1-2 presses of "C". See `docs/PROTOCOL.md` for details.
- Dual-boot selector added, decided 2026-07-04: hold switch "C" (GP11) at
  power-on to load the custom QC firmware; otherwise (default, nothing
  held) stock `midicaptain6s` loads as normal, unmodified, with full
  access to every existing supersetup page including DRKG. Switch "1" was
  ruled out for this since `boot.py` already claims it for USB drive mode.
  This makes switch "C" dual-purpose: read once at power-on for firmware
  selection, then (only in the QC branch) reused for its normal Stomp/Scene
  toggle function during runtime.
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

- `code.py` — stock firmware, still live on the device (`import
  midicaptain6s`). Left untouched until the draft is bench-tested.
- `code_draft.py` — draft replacement firmware (untested on hardware).
  Dual-boot: reads switch "C" once at startup, then either hands off to
  stock `midicaptain6s` unmodified or runs the custom QC bidirectional
  logic. Deliberately kept as a separate file rather than overwriting
  `code.py` until validated per `docs/TESTING.md`.
- `docs/HARDWARE.md` — GPIO pinout, NeoPixel/UART pins, known risks
- `docs/PROTOCOL.md` — full MIDI CC scheme, both outgoing (MINI6→QC) and
  incoming (QC→MINI6 state echo)
- `docs/TESTING.md` — bench-test checklist to run before/during development
- `docs/*.pdf` — reference manuals (PaintAudio MINI 6, Neural DSP Quad
  Cortex mini, Super Mode) kept locally for lookup, gitignored (not
  committed — size and copyright)

## Immediate next steps

1. `supersetup` config folder is already backed up (confirmed by user,
   2026-07-04) — the known-working Super Mode fallback is safe.
2. Flash `code_draft.py` to the device as `code.py` (standard PaintAudio
   USB-mode process: hold switch 1 at power-on, mount drive, replace
   `code.py`) and work through the `docs/TESTING.md` checklist.
3. Resolve the two flagged unknowns (pin reservation, UART vs USB MIDI).
4. Iterate on debounce timing, long-press support (not yet implemented —
   stock Super Mode's page+/page− long-press behavior on switches "3"/"C"
   is NOT replicated in the draft code and would need to be added if
   still wanted).
