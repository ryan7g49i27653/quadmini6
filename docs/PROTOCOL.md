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
- CC 46 is **value-range-gated**, not edge-triggered — the *value itself*
  determines open vs. closed, not just message presence. Sending a fixed
  127 on every press does NOT toggle; you must alternate 127/0.
  Re-proved 2026-07-21 by direct observation: a 127 sent while Gig View
  was already open was a no-op (it did not close), which a toggle
  interpretation would contradict. The 4.1 manual gives the exact
  thresholds: **0-63 closes, 64-127 opens.** Our 127/0 sits safely inside
  each range. CC 45 (Tuner) is documented with the identical shape.
- CC 47 selects a **Mode Slot, not a named Mode** — a distinction that
  matters and that this document previously got wrong. Per the 4.1
  manual: value 0 = Mode Slot 1 (PRESET *by default*), value 1 = Slot 2
  (SCENE by default), value 2 = Slot 3 (STOMP by default). The manual is
  explicit that "when Modes are reordered in the Modes Configuration
  menu, MIDI CC values do not change to reflect the new cycle
  arrangement", and that **"if a Mode slot is empty, MIDI messages will
  not recall any Mode."** So the value→mode mapping holds only for a
  default configuration; once slots are edited, CC 47 addresses whatever
  now occupies that slot, or nothing. We send 1 and 2, skipping Preset
  mode, since Preset-mode footswitch behavior isn't part of this pedal's
  role — see the switch "C" section below for what that means on a
  merged-mode configuration.
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

(As of 2026-07-21 this logic is implemented in `qc_logic.py`
(`GigViewTracker`), separate from the hardware code, and regression-
tested on desktop: `python3 tests/test_qc_logic.py`.)

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

The table above describes an all-scenes layout, which is the default and
what every preset gets until told otherwise. On a QC **Hybrid Mode**,
switches told they are stomps (CC 105-108) latch independently instead —
see "Hybrid Scene/Stomp layouts" below, which also changes what values
1-4 mean on a stomp column.

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

### Hybrid Scene/Stomp layouts: per-switch roles (CC 105-108, added 2026-08-26)

**Bench-tested on real hardware 2026-08-26 — all checks in
`docs/TESTING.md` §12 passed, first flash, no code changes needed.**

The QC supports **Hybrid Modes** (Cortex Control → Modes Configuration →
drag one Mode onto another), which split the four footswitch columns
between Scene and Stomp duty — e.g. the A/B row selecting scenes while
the C/D row toggles blocks. Both pages follow the column, so A1/A2/B1/B2
are scenes and C1/C2/D1/D2 are stomps.

This breaks the radio-button assumption underneath the LED logic above.
A stomp is **latching and independent**: it stays bright while engaged
even as scenes change around it, and it can start a preset either
engaged or bypassed. Under the original scheme only one of the four
switches could ever be bright, so no QC-side reassignment could have
produced this — it needed firmware.

**The row arrangement is user-arrangeable** (Scene above Stomp, or
swapped via the ↕ control on the hybrid tile), so which columns are
scenes is *not* fixed and cannot be hardcoded. Each MINI 6 switch is
therefore told its role, per preset:

| CC | Sets role for | (QC slot) |
|---|---|---|
| 105 | Switch "1" | A2 |
| 106 | Switch "2" | B2 |
| 107 | Switch "A" | C2 |
| 108 | Switch "B" | D2 |

| Value | Meaning |
|---|---|
| 0 | **Scene** role — radio button, the default and the pre-hybrid behavior |
| 1 | **Stomp** role, currently **bypassed** (dim) |
| 2 | **Stomp** role, currently **engaged** (bright) |
| 3 | **Stomp** role, **toggle** current state |

Any other value is ignored. Values 1 and 2 are what let a stomp start a
preset in either state.

#### What this changes about CC 100 values 1-4

Nothing needs re-assigning in the per-footswitch panel — **leave all
eight CC 100 echoes exactly as they are.** The firmware now interprets
values 1-4 against the role of the MINI 6 switch sharing that QC column
(v1→"1", v2→"2", v3→"A", v4→"B"):

| Column role | A Page I press means | LED result |
|---|---|---|
| Scene | A Page I scene went active, so no Page II scene is | Scene LEDs dim; **engaged stomps stay bright** |
| Stomp | The Page I *block* toggled — a different block from the Page II one this switch displays | Ignored entirely |

"Dim only the scenes, leave active stomps bright" needs no special case:
stomp brightness is driven by the switch's own latched state and never
consults the active-scene value, so clearing it dims scenes only.

Keeping all eight assigned is what makes the layout portable — flipping
Scene-above-Stomp to Stomp-above-Scene is four edited values in On
Preset Load and nothing else.

#### Example: scenes on top, stomps below

On Preset Load for a hybrid preset (9 of the 12 slots), with "A" starting
bypassed and "B" starting engaged:

| Slot | Message | Meaning |
|---|---|---|
| 1 | CC 100 v0 | Zero out (must come first — it resets colors and roles) |
| 2-5 | CC 101-104 v1-8 | Scene/stomp colors |
| 6 | CC 105 v0 | "1" is a scene |
| 7 | CC 106 v0 | "2" is a scene |
| 8 | CC 107 v1 | "A" is a stomp, starting bypassed |
| 9 | CC 108 v2 | "B" is a stomp, starting engaged |

#### Accuracy limits (much narrower than expected — bench 2026-08-26)

The QC sends the **same** Preset MIDI Out message whether a stomp was
engaged or bypassed — there is no state-conditional messaging — so the
firmware flips its own bit on each press echo rather than reading state
back. It is therefore accurate only as long as it *starts* accurate, and
only as long as every state change produces an echo.

**The main predicted drift source turned out not to exist.** The design
assumed that engaging or bypassing a block by tapping it on the QC's
**touchscreen** would fire no footswitch echo, leaving the LED lying
until the next preset load. Bench-disproved 2026-08-26: touching the QC
screen sends the codes too, so screen-driven changes keep the MINI 6 in
sync exactly as footswitch-driven ones do. Stomp tracking is
substantially closer to ground truth in practice than the inference
model suggests on paper.

One theoretical drift source remains, unobserved so far:

- **Scenes carry per-block bypass states on the QC**, so selecting a
  scene can in principle flip a stomp without that stomp's own entry
  firing. If it shows up, the fix reuses the same "MULTIPLE" message
  slots the colors already ride in: give that scene's own footswitch
  entry a CC 105-108 message asserting the states it implies — e.g. A2
  sends CC 100 v5 + CC 101 v8 + CC 107 v2 + CC 108 v1. Static config
  with the same staleness caveat as the colors, and opt-in per scene.

Value 3 (toggle) is not needed for normal operation — the CC 100 v5-8
echo already toggles. It exists for the case where some *other* QC
footswitch changes the same block the MINI 6 is displaying (e.g. the
same block assigned to both pages of a column), and that switch's entry
needs to keep this LED honest.

#### Interaction with switch "C" (CC 47)

**Unchanged, and staying that way** (user decision 2026-08-26).

**Modes Configuration is a global device setting, not per-preset or
per-bank** (user-confirmed 2026-08-26). With a rotation holding a single
Scene+Stomp Hybrid Mode and no Preset mode, pressing "C" does nothing
observable on the QC — bench-confirmed the same day. An earlier draft of
this document claimed non-hybrid *banks* kept "C" useful; that was wrong
and rested on a per-bank misreading of a global setting.

But global does not mean permanent, and this is the part to get right:
**the configuration is user-editable, so "C" is inert only while a merged
hybrid is the whole rotation.** Reconfigure back to separate Scene and
Stomp modes and CC 47 addresses occupied slots again, and "C" works
exactly as it always has. The user does exactly this and wants that
behavior kept, so the switch stays as-is — it has a real fallback role,
just a configuration-level one rather than a per-bank one. Do not
"reclaim" it on the grounds that it is dead weight; it is dormant, not
dead.

The 4.1 manual explains the dead switch better than our own guess did.
CC 47 addresses **slots**, and *"if a Mode slot is empty, MIDI messages
will not recall any Mode."* Removing PRESET and merging SCENE+STOMP
leaves at most one occupied slot, so the values we send (1 and 2) are
very likely pointing at empty ones.

**Careful with the strength of that claim, though.** "Nothing happens" is
not proof the CC was rejected: with only one mode in the rotation,
successfully recalling it is *also* invisible. Without a MIDI monitor the
two are indistinguishable. An earlier draft asserted the hybrid is
"reachable as neither value 1 nor value 2" — that overstates the
evidence. If it matters, the cheap test is CC 47 **value 0** (Slot 1),
which the hybrid may well have shifted into once PRESET was removed.

Either way the switch is useless *for mode selection*, and not because of
a MIDI limitation: **with one mode in the rotation there is nothing to
select.** Hybrid-vs-default is a Modes Configuration edit — which modes
exist and how they are merged — and CC 47 only recalls from slots, it
never reconfigures them. No CC edits device configuration; that surface
isn't exposed over MIDI. User's own reading, 2026-08-26, and the manual
supports it.

The residual cost, accepted 2026-08-26: while the hybrid rotation is
active, "C" alternates its own LED magenta/blue on every press, showing
a mode the QC isn't in. Purely cosmetic — the switch sends its CC and
the QC ignores it. Repurposing "C" for something unrelated (CC 45 Tuner,
CC 44 Tap Tempo) was considered and **declined**: the user already runs
an outboard tuner live, and needs "C" to keep behaving normally whenever
the QC is configured out of hybrid mode.

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
- **Local state persists across preset loads (bench-settled 2026-07-21).**
  The QC keeps Gig View open when a preset changes, so `gig_view_open`
  and `next_press_is_stomp` deliberately survive the CC 100 value 0
  preset-load clear (which only touches scene state and colors). A fix
  that reset them on preset load was tried and reverted the same day:
  with Gig View open, it dimmed switch "3" and made the first press a
  no-op (re-sending "open" to an already-open QC) before falling back in
  sync.
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
