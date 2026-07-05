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
- Firmware written as `code_draft.py` and **fully bench-validated on real
  hardware 2026-07-05** — flashed to the device as `code.py` and in live
  use. All three original known unknowns (GP24/GP25 pin reservation,
  UART-vs-USB-MIDI, display driver assumptions) are resolved; see the
  dated bullets below and `docs/TESTING.md` for the checklist results.
- Design reviewed against the live `supersetup/page0.txt` config and the
  Quad Cortex mini manual (`docs/Quad Cortex Mini User Manual 4.0.0.pdf`,
  gitignored, kept locally for reference):
  - Forward direction (MINI 6 → QC) confirmed to replicate `page0.txt`'s
    CC mapping exactly, switch by switch.
  - Backward direction (QC → MINI 6) confirmed to match the intended
    behavior: any Page I scene selected on the QC (from any source) means
    no Page II scene is active on the MINI 6; any Page II scene marks the
    matching switch active. See `docs/PROTOCOL.md` for the full mapping.
    (What the LEDs *show* for active/inactive has since evolved — see the
    2026-07-05 scene-color/three-state bullet below; the CC 100 value
    mapping itself is unchanged.)
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
- Preset-load LED staleness addressed, decided 2026-07-04: loading a
  different preset on the QC fires no CC 100 echo, so the MINI 6's LEDs
  would go stale at song-boundary preset switches. Fix: each live-used
  preset gets an On Preset Load message (CC 100, value 0) that clears the
  Gig View LEDs. Value 0 is a dedicated "zero out" semantic, kept distinct
  from the footswitch echoes (1-8) for unambiguous MIDI logs and future
  clear-state needs. (Since the 2026-07-05 three-state LED scheme, value 0
  does slightly more than 1-4: it also forgets the learned scene colors —
  see `docs/PROTOCOL.md`.)
- Static display added, decided 2026-07-04: QC branch now shows
  `wallpaper/wp5.bmp` (Neural DSP logo, 240x240) once at boot via
  `adafruit_st7789`/`adafruit_imageload`, purely so the screen doesn't look
  frozen/broken next to stock's live display when switching between modes.
  No PC/CC values, battery status, or other stock display info — user
  confirmed those aren't needed in QC mode. Bench-validated 2026-07-05
  after two fixes (rowstart=80, black-frame-first painting) — see the
  display bullets below.
- Bench-tested on real hardware, 2026-07-05: dual-boot selector, all six
  switches, LED indexing, outgoing MIDI (CC 39/40/41/42/46/47), incoming
  MIDI state echo (CC 100 round-trip both directions), preset-load clear,
  and 30ms debounce all confirmed working correctly, no code changes
  needed. This resolves known unknowns #1 (GP24/GP25 pin conflict — not an
  issue on this unit) and #2 (UART vs. USB MIDI — UART works as primary,
  no `usb_midi` fallback needed) from `code_draft.py`. Known unknown #3
  (display) was **not** clean on first flash: the logo showed but with a
  garbage band across the top and the image shifted down/boxed in — the
  classic symptom of a 240x240 panel needing a row offset. Fixed by
  setting `rowstart=80`; `reset=None` and `rotation=0` were both correct
  as guessed.
- Two follow-up changes after the `rowstart=80` reflash, decided 2026-07-05:
  1. **Boot selector flipped, confirmed working on hardware 2026-07-05:**
     QC is now the default firmware at power-on (nothing held); hold
     switch "A" (GP9) instead to load stock `midicaptain6s` for the DRKG
     rig. Previously it was the other way around (hold "C" for QC, default
     stock). This makes switch "A" the dual-purpose switch (selector once
     at boot, then its normal Gig View C2 / CC 41 press during QC
     runtime) — switch "C" is back to being solely the runtime Stomp/Scene
     toggle. Full button checkout passed on both boot paths. See
     `docs/HARDWARE.md` and `docs/PROTOCOL.md`.
  2. **Display noise-before-logo fix, RESOLVED 2026-07-05:** bench-observed
     a white pixelated screen (leftover GRAM noise) visible before the
     logo painted in. Working pattern, proven via a red-frame diagnostic
     build: `display.auto_refresh = False` immediately after display
     init, then an explicit `display.refresh()` after each `show()` —
     with auto-refresh enabled, a background refresh can be "in progress"
     on the bus, making a manual `refresh()` silently return without
     painting. `show()` alone never writes to the panel at all (the SPI
     write normally happens on displayio's background refresh timer).
     `auto_refresh` stays off permanently; the display is static after
     boot. Note: an earlier bench test of this exact pattern appeared to
     fail — the diagnostic proved that flash never took (un-flushed USB
     copy is the prime suspect). **Flashing lesson: eject the CIRCUITPY
     drive cleanly before power-cycling.** Residual, accepted for now
     (user decision 2026-07-05): a noise flash between power-on and the
     black frame remains — the backlight is on from power-up and nothing
     can paint until code runs. Reordering the QC branch so display init +
     black paint happen before the heavy imports was tried and bench-
     tested: **no meaningful improvement**, the window is dominated by
     CircuitPython's interpreter startup, not our import time. The
     reordering was reverted 2026-07-05 (user preference: keep the code
     lean) — display logic is back to a single block, retaining only the
     proven fixes: rowstart=80, auto_refresh off + explicit refresh(),
     black blank frame before the bitmap. Alternative paths are in the
     TO-DO list below.
- LED scheme evolved 2026-07-05, both features designed, implemented, and
  bench-confirmed the same day:
  1. **Per-preset scene colors (CC 101-104):** the QC teaches the MINI 6
     each switch's scene color — via On Preset Load messages and/or color
     CCs riding alongside the CC 100 scene echoes (Preset MIDI Out scene
     entries hold multiple message slots, confirmed in Cortex Control and
     configured on the live presets). Value 1-8 = QC picker palette,
     value 0 = forget.
  2. **Three-state LEDs:** Gig View LEDs are never fully off — bright
     scene color = active, dim scene color = inactive (`DIM_DIVISOR`,
     bumped 6 → 8 after bench review), white = color not learned since
     boot or the last CC 100 value 0 (which now also forgets colors; the
     original static green/red/orange/yellow defaults are retired).
  See `docs/PROTOCOL.md` for the full scheme.
- Dual-boot selector added 2026-07-04, flipped 2026-07-05 (see the
  follow-up bullet above): originally stock loaded by default with "C"
  held for QC; **current behavior is QC by default, hold switch "A"
  (GP9) at power-on for stock** `midicaptain6s`, unmodified, with full
  access to every existing supersetup page including DRKG. Switch "1" was
  ruled out for this since `boot.py` already claims it for USB drive mode.
  The selector switch is dual-purpose: read once at power-on for firmware
  selection, then (only in the QC branch) reused for its normal runtime
  function (Gig View C2 / CC 41).
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
  `adafruit_ticks.mpy`, `asyncio`, `midicaptain6s.mpy` (stock app — never
  import it except via the dual-boot selector's stock branch),
  `neopixel.mpy`, `adafruit_st7789.mpy` (display driver, used by the QC
  branch for the static boot logo).
- **`boot.py`** on device uses `board.GP1` as the "hold at power-on to enter
  USB mode" switch — this is switch "1", confirmed independently and
  matches the community-sourced pinout below. Bench-discovered 2026-07-05:
  holding "1" enables the USB drive but does NOT prevent `code.py` from
  running — the device boots into the QC branch (the default) with the
  drive mounted at the same time, so files can be edited while the custom
  firmware is live. Earlier docs claimed holding "1" "never reaches
  code.py"; that was wrong and has been corrected.

## File inventory

- `code.py` — in the repo this is still the stock one-liner (`import
  midicaptain6s`); on the device it has been replaced by `code_draft.py`'s
  contents since the 2026-07-05 bench testing.
- `code_draft.py` — the custom firmware, bench-validated on hardware
  2026-07-05. Dual-boot: reads switch "A" once at startup — held loads
  stock `midicaptain6s` unmodified, otherwise (default) runs the custom
  QC bidirectional logic. Flashed to the device as `code.py`.
- `wallpaper/wp5.bmp` — Neural DSP logo (240x240, 4bpp indexed) shown by
  the QC branch at boot. A runtime dependency of `code_draft.py` on the
  device; display init is wrapped in try/except, so if it's missing or
  the driver assumptions are wrong, the error prints to serial and the
  firmware carries on without a screen.
- `docs/HARDWARE.md` — GPIO pinout, NeoPixel/UART pins, known risks
- `docs/PROTOCOL.md` — full MIDI CC scheme, both outgoing (MINI6→QC) and
  incoming (QC→MINI6 state echo)
- `docs/TESTING.md` — bench-test checklist to run before/during development
- `docs/*.pdf` — reference manuals (PaintAudio MINI 6, Neural DSP Quad
  Cortex mini, Super Mode) kept locally for lookup, gitignored (not
  committed — size and copyright)

## TO-DO

Active:

1. Three-state Gig View LEDs (dim/bright/unknown) — **bench-tested
   2026-07-05, working**: inactive switches show their learned scene
   color dim instead of off; white = color not learned. CC 100 value 0
   now also forgets learned colors; CC 101-104 value 0 now means "forget"
   (the static green/red/orange/yellow defaults are retired). QC-side
   "press to learn" confirmed and configured (Preset MIDI Out scene
   entries hold multiple messages, so color CCs ride with the CC 100
   echoes). One loose end: `DIM_DIVISOR` bumped 6 → 8 (dim read slightly
   too bright) — reconfirm on next flash, then move this to Done.
2. Further featureset ideas from the user (raised 2026-07-05).

Parked — boot-time display noise (revisit later, user decision
2026-07-05). The white pixelated flash between power-on and the black
frame is accepted for now; `code.py`-side fixes are exhausted (the window
is dominated by CircuitPython interpreter startup). Alternative paths not
yet tried:

- **`boot.py` early blank:** displays initialized in `boot.py` persist
  into `code.py`, and `boot.py` runs much earlier in the boot sequence —
  painting black there could cut the visible noise substantially. Risk:
  `boot.py` is shared with the stock path. Stock almost certainly calls
  `release_displays()` (it survives soft reloads), but it's a closed
  blob — needs a `boot.py` backup first and a careful stock-branch retest
  after. `boot.py` is present in the repo.
- **Backlight pin hunt:** the noise is only visible because the backlight
  is hardwired on from power-up. If the TFT backlight turns out to be on
  a controllable GPIO (not identified in the PySwitch pinout so far —
  see `docs/HARDWARE.md`), holding it off until the black frame is
  painted would eliminate the visible noise completely, including the
  interpreter-boot portion `boot.py` can't touch. Would need to confirm
  stock still manages its own backlight on the stock path.

Done (kept for context): supersetup backup (2026-07-04); flash + full
`docs/TESTING.md` checklist (2026-07-05); all three known unknowns
resolved (2026-07-05); debounce confirmed good at 30ms (2026-07-05);
per-preset LED color override via CC 101-104 designed, implemented, and
bench-confirmed across multiple banks/presets, first flash, palette
needing no tuning (2026-07-05) — see `docs/PROTOCOL.md` for the scheme.
