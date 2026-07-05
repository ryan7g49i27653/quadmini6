# MIDI Captain MINI 6 ↔ Quad Cortex Bidirectional Firmware

Custom CircuitPython firmware for the PaintAudio **MIDI Captain MINI 6**
that provides true **bidirectional state sync** with a Neural DSP
**Quad Cortex (QC)** — the MINI 6's LEDs reflect what is *actually
happening on the QC* (scene changes, preset loads, scene colors), no
matter which device initiated the change. Stock "Super Mode" firmware can
only track its own local button presses; this replaces that with a
ground-truth MIDI echo loop, while keeping stock fully available via a
dual-boot selector.

Bench-validated on real hardware 2026-07-05 and in live use.

---

## 1. Prerequisites

### Hardware

| Item | Notes |
|---|---|
| PaintAudio MIDI Captain MINI 6 | RP2040-based, running stock CircuitPython 7.3.1 (`raspberry_pi_pico` board ID). Pre-mid-2026 stock firmware (Super Mode era) is what this was built against |
| Neural DSP Quad Cortex | Any model with **Preset MIDI Out** support (per-footswitch and On Preset Load messages — see QC manual 4.0.0, pp. 88–94) |
| 2× 5-pin DIN MIDI cables | Bidirectional sync requires **both** directions cabled (see §3) |
| USB-C/data cable + computer | Only needed for flashing and for Cortex Control configuration |

### Software / configuration tools

- **Cortex Control** (desktop app) — used once per preset to configure the
  QC's outgoing MIDI messages (§5). All QC-side config is per-preset.
- No computer is needed during normal operation.

### On-device libraries (already present on a stock MINI 6, in `/lib`)

The firmware only imports what stock already ships:
`adafruit_midi` (source), `neopixel.mpy`, `adafruit_st7789.mpy`,
`adafruit_imageload`, plus CircuitPython built-ins (`busio`, `displayio`,
`digitalio`). No library installation required.

### Files that must be on the device

| File | Purpose |
|---|---|
| `code.py` | This firmware (flash `code_draft.py` from this repo as `code.py`) |
| `boot.py` | **Stock, unmodified** — provides the hold-switch-"1" USB drive mode |
| `wallpaper/wp5.bmp` | Neural DSP logo (240×240, 4bpp indexed) shown in QC mode. Optional at runtime: if missing, an error prints to serial and the firmware runs on without a screen |
| `/lib/*` | Stock library set, untouched |
| `supersetup/` | Stock Super Mode config pages — still used by the stock boot path |

---

## 2. Installation / flashing

1. **Back up** the device's `supersetup/` folder and `boot.py` if you
   haven't already (known-working fallback).
2. Hold switch **"1"** while powering on → the MINI 6 mounts as a USB
   drive (`CIRCUITPY`). Note: the firmware still boots and runs normally
   while the drive is mounted, which is handy for live editing.
3. Copy `code_draft.py` from this repo to the device root as **`code.py`**
   (replacing the stock one-liner). Ensure `wallpaper/wp5.bmp` exists.
4. **Eject the drive cleanly before power-cycling.** An un-flushed copy
   silently leaves the old firmware in place — this bit us during
   development.
5. Power-cycle. Done — QC mode is the default boot.

Reverting to stock permanently: restore `code.py` to
`import midicaptain6s`. (Day to day you don't need this — see §4.)

---

## 3. Physical cabling

Both MIDI directions are required for bidirectional sync:

```
MINI 6  MIDI OUT  ──5-pin DIN──▶  MIDI IN   Quad Cortex
MINI 6  MIDI IN   ◀──5-pin DIN──  MIDI OUT  Quad Cortex
```

- **MINI 6 → QC** carries the switch commands (scene selects, Gig View,
  mode changes).
- **QC → MINI 6** carries the state echoes (which scene is active, scene
  colors, preset-load clears). Without this cable the LEDs have nothing
  to sync to and will stay in their "unknown" state.
- All traffic is on **MIDI channel 1**.
- The MINI 6 side uses its hardware UART MIDI (DIN jacks), confirmed
  working in both directions on real hardware.

---

## 4. Boot modes (dual-boot selector)

The firmware reads one switch at power-on and picks a personality:

| Held at power-on | Result |
|---|---|
| *(nothing)* | **QC mode** (this firmware) — the default |
| Switch **"A"** | **Stock Super Mode** (`midicaptain6s`), completely unmodified — all supersetup pages (QUAD, DRKG, …) work exactly as stock |
| Switch **"1"** | USB drive mode (stock `boot.py` behavior) *and* QC mode simultaneously — edit files while the firmware runs |

How to recognize which mode you're in:

- **QC mode:** screen shows the static Neural DSP logo; the four scene
  switches show dim LEDs (see §6).
- **Stock mode:** the familiar stock live display and page behavior.
- Note: in QC mode there is a brief flash of display noise between
  power-on and the logo — this is the CircuitPython boot window before
  any code can paint, with the backlight hardwired on. Cosmetic, known,
  accepted (see TO-DO in `docs/CLAUDE.md`).

Switch "A" is dual-purpose: read once at boot as the selector, then it's
a normal scene switch in QC mode. Releasing it after boot does not fire
a spurious MIDI message.

---

## 5. QC-side configuration (per preset, in Cortex Control)

All of this lives in **Preset MIDI Out Settings** and must be configured
on each preset used live. Everything is channel 1.

### 5a. Scene footswitch echoes (the core sync)

Each of the 8 Gig View scene footswitch identities gets a CC message.
Entries support **multiple messages** — add the color message (§5b) to
the same entry.

| QC scene entry | Message |
|---|---|
| A1 (AI) | CC 100, value 1 |
| B1 (BI) | CC 100, value 2 |
| C1 (CI) | CC 100, value 3 |
| D1 (DI) | CC 100, value 4 |
| A2 (AII) | CC 100, value 5 |
| B2 (BII) | CC 100, value 6 |
| C2 (CII) | CC 100, value 7 |
| D2 (DII) | CC 100, value 8 |

### 5b. Scene colors ("press to learn")

On each Page II scene entry, add a second message teaching the MINI 6
that scene's color (values in §7b). Example: A2 entry sends
`CC 100 v5` **and** `CC 101 v8` (green).

| Scene | Color CC |
|---|---|
| A2 → MINI 6 switch "1" | CC 101 |
| B2 → MINI 6 switch "2" | CC 102 |
| C2 → MINI 6 switch "A" | CC 103 |
| D2 → MINI 6 switch "B" | CC 104 |

### 5c. On Preset Load messages

Sent automatically every time the preset loads (up to 12 slots):

- **Required:** `CC 100, value 0` — clears the active-scene state and
  forgets learned colors, so LEDs never carry a previous preset's state.
- **Recommended:** the four color messages (CC 101–104) so the LEDs show
  this preset's colors immediately on load, before any switch is pressed.

### Why CC 100–104?

The QC's own reserved incoming CC list tops out at 62, so CCs 100+ can
never collide with anything the QC itself reacts to.

---

## 6. Behavior expectations

### Outgoing — what each MINI 6 switch does (MINI 6 → QC)

| Switch | Function | MIDI sent |
|---|---|---|
| 1 | Select Gig View scene A2 | CC 39, value 127 |
| 2 | Select Gig View scene B2 | CC 40, value 127 |
| 3 | Toggle Gig View open/close | CC 46, value 127 (open) / 0 (close), alternating |
| A | Select Gig View scene C2 | CC 41, value 127 |
| B | Select Gig View scene D2 | CC 42, value 127 |
| C | Cycle Stomp ↔ Scene mode | CC 47, value 2 (Stomp) then 1 (Scene), alternating; Stomp first |

Notes learned on real hardware:

- CC 46 is value-gated on the QC, not edge-triggered — the value itself
  (127/0) determines open/closed, hence the alternation.
- CC 47 values 0/1/2 = Preset/Scene/Stomp modes; Preset mode is
  deliberately unused.
- Debounce is 30 ms (`DEBOUNCE_S`) — confirmed solid, no double-fires.

### LEDs — three-state scene indicators (switches 1/2/A/B)

Scene LEDs are **never fully off**:

| LED state | Meaning |
|---|---|
| **Bright** scene color | This scene is active on the QC right now (ground truth via echo) |
| **Dim** scene color | Scene inactive; color known — visual confirmation you're color-matched to the QC |
| **White** (bright or dim) | Color not learned yet — nothing received since boot or since the last preset load |

- Colors come **only** from the QC (CC 101–104). Dim white means "the QC
  hasn't told me" — it errs honest rather than stale.
- Selecting any Page I scene (CC 100 v1–4): no switch bright, learned
  colors stay dim.
- Preset load (CC 100 v0): all colors forgotten; the new preset's On
  Preset Load messages re-teach them instantly (§5c), or cycling the four
  switches teaches them one press at a time (§5b).
- LED changes are driven by the QC's echo, not local button presses —
  expect the round-trip (press → QC navigates → echo → LED), which is
  imperceptible in practice.
- Dim level is `DIM_DIVISOR` in the firmware (8 = bench-confirmed).

### LEDs — locally tracked (switches 3/C)

The QC has **no MIDI feedback** for Gig View open/closed or the current
Mode — these are global QC behaviors with no per-preset MIDI hooks. So
these two LEDs are optimistic local state, same ceiling stock always had:

| Switch | States | Boot default | Accuracy |
|---|---|---|---|
| 3 | White = Gig View open, dim gray = closed | Closed | Exact at boot (QC always boots closed). Goes stale only if you open Gig View by swiping the QC's screen |
| C | Magenta = Stomp, blue = Scene | Scene | Best guess (QC remembers last mode); a wrong guess self-corrects within 1–2 presses since CC 47 is absolute, not a toggle |

### Display

Static Neural DSP logo, painted once at boot (black frame first, then
the bitmap). No live info by design — scene/preset state lives on the
LEDs and the QC's own screen.

---

## 7. Color / hex reference

### 7a. Fixed element colors

| Element | Color | Hex |
|---|---|---|
| Scene switch, color unknown | White | `0xFFFFFF` |
| Gig View open (switch "3") | White | `0xFFFFFF` |
| Gig View closed (switch "3") | Dim gray | `0x282828` |
| Stomp mode (switch "C") | Magenta | `0xFF00FF` |
| Scene mode (switch "C") | Blue | `0x0000FF` |

### 7b. Scene color palette (CC 101–104 values)

Values follow the QC's scene color picker, left to right. RGB values are
NeoPixel approximations of the QC's on-screen colors (bench-confirmed to
read correctly).

| CC value | Color | Hex |
|---|---|---|
| 0 | *Forget → dim white ("unknown")* | — |
| 1 | Yellow | `0xFFFF00` |
| 2 | Orange | `0xFF8000` |
| 3 | Red | `0xFF0000` |
| 4 | Pink | `0xFF0080` |
| 5 | Purple | `0x8000FF` |
| 6 | Blue | `0x0000FF` |
| 7 | Cyan | `0x00FFFF` |
| 8 | Green | `0x00FF00` |

Any other value is ignored. Global LED brightness is 0.3
(`BRIGHTNESS`); inactive scenes show their color divided by
`DIM_DIVISOR` (8).

---

## 8. Complete MIDI map (channel 1 throughout)

### MINI 6 → QC (outgoing)

| CC | Values | Function |
|---|---|---|
| 39 | 127 | Select scene A2 |
| 40 | 127 | Select scene B2 |
| 41 | 127 | Select scene C2 |
| 42 | 127 | Select scene D2 |
| 46 | 127 / 0 | Gig View open / close |
| 47 | 2 / 1 | Mode: Stomp / Scene |

### QC → MINI 6 (incoming)

| CC | Values | Function |
|---|---|---|
| 100 | 0 | Preset loaded: no scene active + forget all learned colors |
| 100 | 1–4 | Page I scene active (A1–D1): no switch bright |
| 100 | 5–8 | Page II scene active (A2–D2): switch "1"/"2"/"A"/"B" bright |
| 101 | 0–8 | Scene color for switch "1" (A2) |
| 102 | 0–8 | Scene color for switch "2" (B2) |
| 103 | 0–8 | Scene color for switch "A" (C2) |
| 104 | 0–8 | Scene color for switch "B" (D2) |

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Firmware change didn't take effect | USB copy wasn't flushed — always eject `CIRCUITPY` cleanly before power-cycling |
| LEDs never light from QC actions | QC → MINI 6 MIDI cable missing/dead, or the preset's Preset MIDI Out messages aren't configured (§5) |
| LEDs stuck on dim white | Colors were never taught: add the color CCs to the preset (§5b/5c) |
| LED colors wrong after editing a preset's scene colors on the QC | The static CC values in Preset MIDI Out went stale — update them to match (known tradeoff; the values are manual config) |
| No logo / blank screen, but switches and MIDI work | Display init is non-fatal by design; attach a serial console to read the printed exception. Check `wallpaper/wp5.bmp` exists |
| Brief screen noise at power-on | Known cosmetic limitation (pre-code boot window); see the parked TO-DO in `docs/CLAUDE.md` |
| Switch "3"/"C" LED doesn't match the QC | Expected: no MIDI feedback exists for Gig View/Mode state (§6); it self-corrects on the next press |

---

## 10. Repository layout

| Path | Contents |
|---|---|
| `code_draft.py` | The firmware (flash as `code.py`) |
| `code.py` | Stock one-liner, kept for reference |
| `boot.py`, `supersetup/`, `wallpaper/`, `lib/` | Device file mirrors (stock + assets) |
| `docs/CLAUDE.md` | Project status, decisions log, TO-DO |
| `docs/PROTOCOL.md` | Full MIDI protocol rationale and details |
| `docs/HARDWARE.md` | GPIO pinout, NeoPixel map, hardware notes |
| `docs/TESTING.md` | Bench-test checklist with results |
