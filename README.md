# MIDI Captain MINI 6 ↔ Quad Cortex Bidirectional Firmware

I bought a Quad Cortex Mini and wanted an easier/quicker way to get to 
bank two of the presets in a live scenario. I had a MINI 6 laying around
so Claude and I got to work on coming-up with some programming to
integrate the two systems. Goal being, I can control bank 2 on the QC
without having to first move to bank 2 in order to control them with
switches. When time is of the essence live, this matters. Being the picky
guy I am, I wanted the LEDs on the MINI 6 to match the color of the
bank 2 scene, and so the QC sends a MIDI code to the MINI 6 to tell it
which color to use for the scene.

## Technical

Custom CircuitPython firmware for the PaintAudio **MIDI Captain MINI 6**
that provides true **bidirectional state sync** with a Neural DSP
**Quad Cortex (QC)** — the MINI 6's LEDs reflect what is *actually
happening on the QC* (scene changes, preset loads, scene colors), no
matter which device initiated the change. Stock "Super Mode" firmware can
only track its own local button presses; this replaces that with a
ground-truth MIDI echo loop, while keeping stock fully available via a
dual-boot selector.

Bench-validated on real hardware 2026-07-05 and in live use. Hardened
2026-07-21 (code review → burst-proof MIDI receive, guarded stock import,
boot settle delay, CircuitPython version pin) with the protocol logic
extracted to `qc_logic.py` and covered by desktop regression tests.

Extended 2026-08-26 for the QC's **Hybrid Modes**, where the footswitch
columns split between selecting scenes and toggling blocks. Each of the
MINI 6's four Gig View switches can now be told, per preset, whether it
is a **scene** switch (radio button — one bright at a time, as before) or
a **stomp** switch (latching and independent — bright while engaged, dim
while bypassed, unaffected by scene changes around it). Several LEDs can
be bright at once. See §5c.

---

## 1. Prerequisites

### Hardware

| Item | Notes |
|---|---|
| PaintAudio MIDI Captain MINI 6 | RP2040-based, running stock CircuitPython 7.3.1 (`raspberry_pi_pico` board ID). Pre-mid-2026 stock firmware (Super Mode era) is what this was built against. The firmware hard-checks for CircuitPython **7.x** at boot and refuses to run on anything else (CP 9 removed APIs it uses) |
| Neural DSP Quad Cortex | Any model with **Preset MIDI Out** support (per-footswitch and On Preset Load messages — see QC manual 4.0.0, pp. 88–94) |
| 2× MIDI cables | Bidirectional sync requires **both** directions cabled (see §3). Full-size QC: 5-pin DIN both ends. QC Mini: 5-pin DIN on the MINI 6 end, 1/8" (3.5mm) TRS on the QC end |
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
| `qc_logic.py` | Pure Gig View protocol/LED logic imported by the firmware — **required**, copy as-is to the device root |
| `boot.py` | **Stock, unmodified** — provides the hold-switch-"1" USB drive mode |
| `wallpaper/wp5.bmp` | Neural DSP logo (240×240, 4bpp indexed) shown in QC mode. Optional at runtime: if missing, an error prints to serial and the firmware runs on without a screen |
| `/lib/*` | Stock library set, untouched. Note: `lib/midicaptain6s.mpy` (the stock app) is **deliberately not in this repo** — it embeds the device's license key. It ships on every stock MINI 6; never delete it from the device |
| `license/` | Stock per-device vendor-key folder — also **not in this repo**; leave the device's own copy in place |
| `supersetup/` | Stock Super Mode config pages — still used by the stock boot path |

---

## 2. Installation / flashing

1. **Back up** the device's `supersetup/` folder, `boot.py`,
   `lib/midicaptain6s.mpy`, and `license/` if you haven't already. The
   last two are per-device vendor files this repo intentionally does not
   contain — the device's own copies are the only ones you have.
2. Hold switch **"1"** while powering on → the MINI 6 mounts as a USB
   drive (`CIRCUITPY`). Note: the firmware still boots and runs normally
   while the drive is mounted, which is handy for live editing.
3. Copy `code_draft.py` from this repo to the device root as **`code.py`**
   (replacing the stock one-liner), and copy `qc_logic.py` to the device
   root as-is. Ensure `wallpaper/wp5.bmp` exists.
4. **Eject the drive cleanly before power-cycling.** An un-flushed copy
   silently leaves the old firmware in place — this bit us during
   development.
5. Power-cycle. Done — QC mode is the default boot.

Optional pre-flight check (no hardware needed): `python3
tests/test_qc_logic.py` runs the Gig View protocol regression tests
against the exact `qc_logic.py` you're about to copy.

Reverting to stock permanently: restore `code.py` to
`import midicaptain6s`. (Day to day you don't need this — see §4.)

---

## 3. Physical cabling

Both MIDI directions are required for bidirectional sync:

```
MINI 6  MIDI OUT  ──────────▶  MIDI IN   Quad Cortex
MINI 6  MIDI IN   ◀──────────  MIDI OUT  Quad Cortex
```

Connector types differ by QC model — the MINI 6 end is always 5-pin DIN:

| QC model | MINI 6 end | QC end |
|---|---|---|
| Quad Cortex (full size) | 5-pin DIN | 5-pin DIN |
| Quad Cortex Mini | 5-pin DIN | 1/8" (3.5mm) TRS |

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

### 5c. Hybrid Scene/Stomp presets — switch roles (optional)

Only needed on presets using a QC **Hybrid Mode**, where some footswitch
columns select scenes and others toggle blocks. Tell the MINI 6 which of
its switches is which, and what state each stomp starts in:

| CC | Sets role for | Values |
|---|---|---|
| 105 | Switch "1" (A2) | **0** = scene · **1** = stomp, bypassed · **2** = stomp, engaged |
| 106 | Switch "2" (B2) | (same) |
| 107 | Switch "A" (C2) | (same) |
| 108 | Switch "B" (D2) | (same) |

A **scene** switch is a radio button — one bright at a time. A **stomp**
switch latches independently: bright while engaged, dim while bypassed,
and unaffected by scene changes around it.

Roles are taught rather than hardcoded because the hybrid layout is
arrangeable on the QC (scene row above stomp row, or swapped via the ↕
control). Flipping the arrangement means changing these four values and
**nothing else** — §5a stays exactly as it is on every preset, hybrid or
not.

### 5d. On Preset Load messages

Sent automatically every time the preset loads (up to 12 slots). Order
matters: `CC 100 v0` must come **first**, since it resets colors and
roles.

| Slot | Message | Status |
|---|---|---|
| 1 | `CC 100, value 0` | **Required** — clears active-scene state, forgets colors, resets all four switches to scene role |
| 2–5 | `CC 101–104` | **Recommended** — this preset's colors, shown on load before any switch is pressed |
| 6–9 | `CC 105–108` | **Hybrid presets only** — see §5c |

A full hybrid preset uses 9 of the 12 slots.

### Why CC 100–108?

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
- CC 47 selects a **Mode Slot**, not a named Mode: value 0 = Slot 1
  (PRESET by default), 1 = Slot 2 (SCENE), 2 = Slot 3 (STOMP). Those
  names are only the defaults — editing Modes Configuration changes what
  each value recalls, and an empty slot recalls nothing (QC manual
  4.1.0). Preset mode is deliberately unused here.
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
  Preset Load messages re-teach them instantly (§5d), or cycling the four
  switches teaches them one press at a time (§5b).
- LED changes are driven by the QC's echo, not local button presses —
  expect the round-trip (press → QC navigates → echo → LED), which is
  imperceptible in practice.
- Dim level is `DIM_DIVISOR` in the firmware (8 = bench-confirmed).

### LEDs — stomp switches on hybrid presets (added 2026-08-26)

On a preset that assigns stomp roles (§5c), those switches drop the
radio-button behavior entirely:

| LED state | Meaning |
|---|---|
| **Bright** color | Block engaged |
| **Dim** color | Block bypassed |

- **Independent.** Several can be bright at once, alongside a bright
  scene switch. Selecting a scene never clears them.
- **Page I presses are filtered by role.** A Page I press on a *scene*
  column dims the scene LEDs as always; on a *stomp* column it toggled a
  different block than the one this switch displays, so it's ignored.
- **State is inferred, not read back.** The QC sends the same message
  whether a block was engaged or bypassed, so the firmware flips its own
  bit per echo. It stays accurate because it starts accurate (§5c values
  1/2) and because every change echoes — including changes made by
  **touching the QC's screen**, confirmed on hardware 2026-08-26.
- Only theoretical gap: a scene that itself changes a block's bypass
  state could desync that stomp. Not observed in practice; if it turns
  up, add the matching CC 105–108 message to that scene's own entry.

### LEDs — locally tracked (switches 3/C)

The QC has **no MIDI feedback** for Gig View open/closed or the current
Mode — these are global QC behaviors with no per-preset MIDI hooks. So
these two LEDs are optimistic local state, same ceiling stock always had:

| Switch | States | Boot default | Accuracy |
|---|---|---|---|
| 3 | White = Gig View open, dim gray = closed | Closed | Exact at boot (QC always boots closed). Stays correct across preset loads — the QC keeps Gig View open on preset change and the firmware deliberately preserves its state too (bench-confirmed 2026-07-21). Goes stale only if you open Gig View by swiping the QC's screen |
| C | Magenta = Stomp, blue = Scene | Scene | Best guess (QC remembers last mode); a wrong guess self-corrects within 1–2 presses since CC 47 is absolute, not a toggle. **Dormant while your mode rotation is a single Hybrid Mode** — the LED still alternates but the QC ignores the CC; works normally again once the rotation holds separate Scene/Stomp modes. See below |

**Switch "C" and Hybrid Modes (bench-confirmed 2026-08-26):** Modes
Configuration is a **global** QC setting, not per-preset or per-bank. If
your rotation contains only a Scene+Stomp Hybrid Mode and no Preset mode,
pressing "C" does nothing observable — and the reason isn't a MIDI
limitation, it's that **with one mode in the rotation there is nothing to
select.** CC 47 recalls a mode from a slot; it never reconfigures the
slots, and per the 4.1 manual an empty slot recalls nothing. Switching
between hybrid and non-hybrid is a Modes Configuration edit, which the
QC doesn't expose over MIDI at all.

**"C" is dormant, not dead.** Reconfigure the QC back to separate Scene
and Stomp modes and CC 47 addresses real slots again — the switch works
exactly as documented above, with no firmware change. It is deliberately
left alone for that reason. The only cost while a hybrid rotation is
active is cosmetic: its LED still alternates magenta/blue on each press,
showing a mode the QC isn't in.

### Display

Static Neural DSP logo, painted once at boot (black frame first, then
the bitmap). No live info by design — scene/preset state lives on the
LEDs and the QC's own screen.

---

## 7. Color / hex reference

### 7a. Fixed element colors

| Element | Color | Hex |
|---|---|---|
| Scene or stomp switch, color unknown | White | `0xFFFFFF` |
| Gig View open (switch "3") | White | `0xFFFFFF` |
| Gig View closed (switch "3") | Dim gray | `0x282828` |
| QC in Stomp *mode* (switch "C") | Magenta | `0xFF00FF` |
| QC in Scene *mode* (switch "C") | Blue | `0x0000FF` |

Note the name collision: switch "C" reports the QC's global **Mode**,
which is unrelated to a switch's **role** (§5c). A switch with a stomp
role shows its own learned scene color, never magenta.

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
| 46 | 127 / 0 | Gig View open / close (QC gates on range: 0–63 close, 64–127 open) |
| 47 | 2 / 1 | Mode Slot 3 / Slot 2 (STOMP / SCENE by default). No effect if those slots are empty — e.g. a single merged Hybrid Mode |

### QC → MINI 6 (incoming)

| CC | Values | Function |
|---|---|---|
| 100 | 0 | Preset loaded: no scene active, forget all colors, reset all roles to scene |
| 100 | 1–4 | Page I press (A1–D1). Scene column → no switch bright; stomp column → ignored |
| 100 | 5–8 | Page II press (A2–D2) on switch "1"/"2"/"A"/"B". Scene role → that switch bright, others dim; stomp role → that switch toggles, others untouched |
| 101 | 0–8 | Color for switch "1" (A2) |
| 102 | 0–8 | Color for switch "2" (B2) |
| 103 | 0–8 | Color for switch "A" (C2) |
| 104 | 0–8 | Color for switch "B" (D2) |
| 105 | 0 / 1 / 2 / 3 | Switch "1" (A2) role: scene / stomp bypassed / stomp engaged / stomp toggle |
| 106 | 0 / 1 / 2 / 3 | Switch "2" (B2) role — same values |
| 107 | 0 / 1 / 2 / 3 | Switch "A" (C2) role — same values |
| 108 | 0 / 1 / 2 / 3 | Switch "B" (D2) role — same values |

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Firmware change didn't take effect | USB copy wasn't flushed — always eject `CIRCUITPY` cleanly before power-cycling |
| LEDs never light from QC actions | QC → MINI 6 MIDI cable missing/dead, or the preset's Preset MIDI Out messages aren't configured (§5) |
| LEDs stuck on dim white | Colors were never taught: add the color CCs to the preset (§5b/§5d) |
| Stomp switches act like scenes — pressing one dims the others | The role messages aren't arriving. Check `CC 105–108` exist in On Preset Load, on channel 1 (§5c). Without them every switch defaults to scene role |
| A stomp LED is bright when the block is bypassed (or vice versa) | The `CC 105–108` value disagrees with what the preset actually saved. Values 1/2 are static claims, not readings — confirm the preset's real bypass state on the QC and fix the value (§5c) |
| Stomp LED went stale after a scene change | That scene changes the block's bypass state. Add the matching `CC 105–108` message to that scene's own Preset MIDI Out entry (§6) |
| Roles reset themselves on preset load | Working as designed — `CC 100 v0` clears roles along with colors, so each preset re-teaches its own. Make sure it is the **first** On Preset Load slot (§5d) |
| Switch "C" does nothing on the QC | Expected if your Modes Configuration is a single Hybrid Mode — there is no second mode to select. Works again once the rotation holds separate Scene/Stomp modes (§6) |
| LED colors wrong after editing a preset's scene colors on the QC | The static CC values in Preset MIDI Out went stale — update them to match (known tradeoff; the values are manual config) |
| No logo / blank screen, but switches and MIDI work | Display init is non-fatal by design; attach a serial console to read the printed exception. Check `wallpaper/wp5.bmp` exists |
| Brief screen noise at power-on | Known cosmetic limitation (pre-code boot window); see the parked TO-DO in `docs/CLAUDE.md` |
| Switch "3"/"C" LED doesn't match the QC | Expected: no MIDI feedback exists for Gig View/Mode state (§6); it self-corrects on the next press |
| Deployed a change and nothing happened | `qc_logic.py` must be copied to the device root **alongside** `code.py` — most protocol changes live there, so copying only `code.py` is a silent no-op |

---

## 10. Repository layout

| Path | Contents |
|---|---|
| `code_draft.py` | The firmware (flash as `code.py`) |
| `qc_logic.py` | Pure protocol/LED logic (device + desktop) |
| `tests/test_qc_logic.py` | Desktop protocol regression tests (`python3 tests/test_qc_logic.py`) |
| `code.py` | Stock one-liner, kept for reference |
| `boot.py`, `supersetup/`, `wallpaper/`, `lib/` | Device file mirrors (stock + assets) |
| `TODO.md` | 2026-07-20 code-review findings and their resolutions (all closed 2026-07-21) |
| `docs/CLAUDE.md` | Project status, decisions log, TO-DO |
| `docs/PROTOCOL.md` | Full MIDI protocol rationale and details |
| `docs/HARDWARE.md` | GPIO pinout, NeoPixel map, hardware notes |
| `docs/TESTING.md` | Bench-test checklist with results |
