# MIDI Protocol Reference

## Firmware selector (not MIDI, but affects everything below)

`code_draft.py` is a dual-boot script, not just the QC logic. At startup it
reads switch "A" (GP9) once: if held, it hands off to stock
`midicaptain6s` unmodified; otherwise (default, nothing held) it runs the
QC bidirectional logic described in this document. This lets the same
device serve both the QC rig and the unrelated `DRKG` laptop-effects rig
without re-flashing — power-cycle and hold "A" for stock, or don't for QC.
Flipped 2026-07-05 (previously: hold "C" for QC, default was stock) now
that QC is the primary use. Switch "1" was ruled out for this choice since
`boot.py` already claims it for USB drive mode. (Bench-discovered
2026-07-05: holding "1" doesn't actually stop `code.py` from running — it
boots the QC branch *and* mounts the USB drive simultaneously, useful for
live file editing — but that's exactly why it can't double as the
firmware selector: it's already spoken for.) See the module docstring in
`code_draft.py` for the exact implementation.

Everything below only applies when the QC branch is active.

MIDI channel throughout: **1** (adafruit_midi represents this as `0` — its
channel numbering is 0-indexed while the QC's UI and our config both use
1-indexed; the draft code handles this conversion, but it's worth
double-checking if messages seem to go to the wrong channel).

## Outgoing: MINI 6 → QC (button press actions)

These replicate the previously-validated Super Mode config exactly (see
"Prior working config" below for the original config-file version of this
same logic).

| Switch | Action | MIDI sent |
|---|---|---|
| 1 | Select Gig View A2 | CC 39, value 127 |
| 2 | Select Gig View B2 | CC 40, value 127 |
| 3 | Toggle Gig View open/close | CC 46, value 127 (open) / 0 (close), alternating each press |
| A | Select Gig View C2 | CC 41, value 127 |
| B | Select Gig View D2 | CC 42, value 127 |
| C | Cycle Stomp ↔ Scene mode | CC 47, value 2 (Stomp) then 1 (Scene), alternating each press — Stomp fires first |

Notes on the above, learned empirically on real hardware with the Super
Mode config (still true for custom firmware):
- CC 46 is **value-range-gated**, not edge-triggered — the QC treats it
  like its sibling CC 62 ("ignore duplicate PC"), where the *value itself*
  determines open vs. closed, not just message presence. Sending a fixed
  127 on every press does NOT toggle; you must alternate 127/0.
- CC 47 values 0/1/2 map to QC Modes Preset/Scene/Stomp respectively (per
  Neural DSP's own manual). We only use 1 and 2 (Scene/Stomp), skipping
  Preset mode entirely, since Preset-mode footswitch behavior isn't part
  of this pedal's role.
- Switches "3" and "C" are the two rightmost physical switches in each row.
  On stock Super Mode, these have a **hardwired long-press page+/page−**
  function baked into the firmware itself, independent of config. This
  hardwired behavior does NOT exist in custom CircuitPython firmware
  (there's no "page" concept at all in the draft code) — long-press
  behavior would need to be implemented from scratch if still wanted, and
  currently isn't.

## Incoming: QC → MINI 6 (state echo, for LED sync)

Configured on the **QC itself**, in Cortex Control's "Preset MIDI Out" →
per-footswitch panel (confirmed to exist and confirmed to fire on every
press, not just once on preset load — verified empirically by the user
before this protocol was finalized).

Each of the QC's 8 Gig View footswitch identities (AI/BI/CI/DI on Page I,
AII/BII/CII/DII on Page II) gets assigned one CC message in that QC UI:

| QC footswitch | CC | Value |
|---|---|---|
| A1 (AI) | 100 | 1 |
| B1 (BI) | 100 | 2 |
| C1 (CI) | 100 | 3 |
| D1 (DI) | 100 | 4 |
| A2 (AII) | 100 | 5 |
| B2 (BII) | 100 | 6 |
| C2 (CII) | 100 | 7 |
| D2 (DII) | 100 | 8 |

CC 100 was chosen because it's outside the QC's reserved incoming CC list
(which tops out at 62), so it's safe as an outgoing-only channel with no
collision risk against anything the QC itself listens for.

### MINI 6 LED response logic

The MINI 6's four Gig View switches (1/2/A/B) only ever target Page II
(A2-D2) — they have no reason to distinguish *which* Page I patch is
active, only that a Page I patch (any of them) is now active, meaning none
of the Page II patches are.

**Three-state LEDs (decided 2026-07-05):** Gig View LEDs are never fully
off. Each switch shows its scene color **bright** when its scene is
active, **dim** when inactive, and **white** (bright or dim per the same
rule) when its color hasn't been learned — i.e. no CC 101-104 received
for it since boot or since the last CC 100 value 0. Dim white is an
honest "I don't know this preset's colors" state, as opposed to showing
stale colors from a previous preset. Scene colors come from CC 101-104
(next section); dim level is `DIM_DIVISOR` in the firmware (tune on
bench).

| Incoming CC 100 value | LED result |
|---|---|
| 0 (explicit "zero out" — preset load) | No switch bright; all four colors **forgotten** → all dim white until re-taught |
| 1, 2, 3, or 4 (any Page I patch) | No switch bright; learned colors keep showing dim |
| 5 (A2) | Switch "1" bright, others dim |
| 6 (B2) | Switch "2" bright, others dim |
| 7 (C2) | Switch "A" bright, others dim |
| 8 (D2) | Switch "B" bright, others dim |

This is **ground truth**, not optimistic/local — confirmed acceptable
given the user watches the QC's own screen live and doesn't need
sub-100ms LED feedback on the MINI 6 itself. No "light immediately on
press, correct later" logic needed.

### Preset changes: On Preset Load messages (QC-side config, decided 2026-07-04)

The CC 100 echo above only fires on *footswitch identity* presses. Loading
a different **preset** on the QC fires nothing — the new preset comes up
on whatever scene it was saved with, and the MINI 6's LEDs keep showing
the last scene of the *previous* preset (stale).

The QC's fix is per-preset: each preset supports up to 12 "On Preset Load"
MIDI messages (Preset MIDI Out → ON PRESET LOAD MESSAGES, QC manual
p. 90), sent every time that preset loads.

**Decided approach: every preset used live gets one On Preset Load
message — CC 100, value 0, channel 1.** Value 0 is a dedicated "zero out"
semantic (decided 2026-07-04): reserved exclusively for explicit
clear-LED-state events rather than footswitch echoes, keeping MIDI
monitor logs unambiguous (a value 0 can only mean a preset loaded, never
"someone pressed A1"). Since the three-state LED scheme (2026-07-05),
value 0 does slightly more than values 1-4: both mean "no scene bright,"
but value 0 additionally **forgets all four learned scene colors** —
each preset re-teaches its own via CC 101-104 in the same preset-load
batch, or the LEDs drop to dim white ("unknown") rather than carrying a
previous preset's colors forward. The user mostly runs one preset all
night, so this only matters at song-boundary preset switches.

Optional refinement, deliberately NOT the default: since the message is
configured per preset, a preset saved with a Page II scene active could
instead send the matching value 5-8 to light the correct LED on load.
This works, but it's a static value — if the preset is ever re-saved on a
different scene, the message silently goes stale and lies. Value 0
(clear) is maintenance-free and errs dark rather than wrong; use the
refinement only for presets that firmly live on a Page II scene.

### Optional: per-preset LED color override (CC 101-104, decided 2026-07-05)

The QC lets each scene in a preset be assigned a color from a fixed
picker, and those colors vary preset to preset — while the MINI 6's LED
colors were originally static. This feature lets a preset *elect* to tell
the MINI 6 what colors to use, so the LEDs can match that preset's actual
scene colors.

The QC has no MIDI feedback for scene colors (nothing dynamic exists to
echo), so this works the same way as the CC 100 value-0 clear: static,
user-configured **On Preset Load messages** on each preset that opts in
(up to 12 slots per preset; the value-0 clear plus four colors uses 5).

One CC per MINI 6 switch, so ordering within the preset-load batch never
matters:

| CC | Sets LED color for | (QC scene) |
|---|---|---|
| 101 | Switch "1" | A2 |
| 102 | Switch "2" | B2 |
| 103 | Switch "A" | C2 |
| 104 | Switch "B" | D2 |

Values follow the QC's scene color picker, left to right:

| Value | Color |
|---|---|
| 0 | Forget this switch's color (back to dim white / "unknown") |
| 1 | Yellow |
| 2 | Orange |
| 3 | Red |
| 4 | Pink |
| 5 | Purple |
| 6 | Blue |
| 7 | Cyan |
| 8 | Green |

Any other value is ignored. Behavior notes:

- **Colors persist until overwritten or forgotten.** Learned colors
  survive scene changes and Page I trips, but CC 100 value 0 (preset
  load) forgets all four — so each opted-in preset re-teaches its colors
  in the same On Preset Load batch, and a preset that teaches nothing
  shows dim white ("unknown") rather than inheriting the previous
  preset's colors.
- Color CCs are handled whenever they arrive, not just on preset load,
  and repaint the LED immediately (bright or dim as appropriate). This
  enables the "press to learn" pattern — **confirmed possible and in use
  2026-07-05**: each scene entry (AI-DII) in the Preset MIDI Out panel
  holds multiple message slots (Cortex Control marks them "MULTIPLE"),
  so a color CC rides alongside that scene's CC 100 echo (e.g. AII
  sending CC 100 v5 + CC 101 v8). Cycling through the four switches
  teaches the colors even on presets without On Preset Load color
  messages. Message order within a press doesn't matter — the firmware
  stores colors independently of the echo.
- **Same staleness caveat as the value 5-8 preset-load refinement:** the
  values are static config. If a preset's scene colors are ever changed
  on the QC without updating its On Preset Load messages, the LEDs will
  confidently lie. Elective, per preset — the maintenance burden is
  opt-in.
- CC 101-104 sit right above CC 100, comfortably outside the QC's
  reserved incoming CC list (tops out at 62), same collision-safety
  argument as CC 100.

### No feedback available for switch "3" (Gig View) or "C" (Mode)

Confirmed via the Quad Cortex mini manual (`docs/Quad Cortex Mini User
Manual 4.0.0.pdf`, pp. 88-94): Preset MIDI Out only sends a message when
one of the 8 Gig View scene footswitches is pressed. There is no outgoing
MIDI message for Gig View open/closed state or for the currently active
Mode (Preset/Scene/Stomp) — those are only settable via incoming CC (CC 46
and CC 47 respectively), never echoed back out. So switches "3" and "C"
cannot be ground-truth synced the way 1/2/A/B are; they stay
locally-tracked/optimistic in `code_draft.py`, same limitation stock Super
Mode's `ledmode = [select]` always had. Not a regression, just a ceiling
on what the QC exposes over MIDI.

Two boot-state defaults follow from this, decided 2026-07-04:

- **Switch "3" (Gig View) defaults to closed/off at boot.** This isn't a
  guess — the QC always boots with Gig View closed (confirmed: it always
  requires a swipe-up or switch press to open), so the default is exactly
  correct, not just a best-effort assumption.
- **Switch "C" (Mode) defaults to Scene at boot.** Unlike Gig View, Mode
  is *not* fixed at boot — the QC remembers whatever mode was active when
  it was last powered off, and there's no way to query it. In practice the
  QC spends nearly all its time in Scene mode (Stomp is used occasionally
  but the user returns to Scene afterward), so Scene is the better default
  guess. When the guess is wrong, pressing "C" sends an absolute
  set-mode command (not a relative toggle), so the QC always ends up in
  the intended mode — it just may take an extra press to get there, and
  the LED can show a stale color until then. Confirmed acceptable by the
  user as a rare, livable edge case.

## Colors reference (for consistency if extending)

| Element | Color | Hex |
|---|---|---|
| Gig View switch, color unknown | White (bright/dim) | `0xffffff` |
| Gig View switch, color learned | Learned color (bright when active, dim otherwise) | via CC 101-104 |
| Gig View open (switch "3") | White | `0xffffff` |
| Gig View closed (switch "3") | Dim gray | `0x282828` |
| Stomp mode (switch "C") | Magenta | `0xff00ff` |
| Scene mode (switch "C") | Blue | `0x0000ff` |

(The original static per-switch defaults — green/red/orange/yellow —
were retired 2026-07-05 with the three-state scheme: white now means
"not taught yet" and learned colors come exclusively from CC 101-104.)

The palette those CCs select from (`QC_COLOR_PALETTE` in the firmware —
RGB approximations of the QC's picker, tune on bench if they look off
next to the QC screen):

| CC value | Color | RGB |
|---|---|---|
| 1 | Yellow | `(255, 255, 0)` |
| 2 | Orange | `(255, 128, 0)` |
| 3 | Red | `(255, 0, 0)` |
| 4 | Pink | `(255, 0, 128)` |
| 5 | Purple | `(128, 0, 255)` |
| 6 | Blue | `(0, 0, 255)` |
| 7 | Cyan | `(0, 255, 255)` |
| 8 | Green | `(0, 255, 0)` |

## Prior working config (reference / fallback)

Before this bidirectional project, the MINI 6 ran stock Super Mode with a
config file (`supersetup/page0.txt`, page name `QUAD`) implementing the
exact same six-switch outgoing logic above, using `ledmode = [select]`
(local-only, last-pressed-wins) for LED state on switches 1/2/A/B instead
of true QC state sync.

The MINI 6 also has a second real page, `supersetup/page1.txt` (page name
`DRKG`), for an unrelated laptop-based multi-effects rig — six momentary
CC toggles (Distortion/Octaver/Delay/Tap Tempo/Bypass plus one unlabeled,
CC 80-85), used at different times than the QC, never simultaneously.

Both are known-working stock config, and both stay fully available as a
fallback via the dual-boot selector in `code_draft.py`: power on holding
switch "A" and stock `midicaptain6s` loads unmodified, giving access to
`QUAD`, `DRKG`, and any other supersetup page exactly as they work
today — no restore-from-backup or re-flash needed to fall back.
