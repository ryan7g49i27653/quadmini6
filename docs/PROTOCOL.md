# MIDI Protocol Reference

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
of the Page II patches are:

| Incoming CC 100 value | LED result |
|---|---|
| 1, 2, 3, or 4 (any Page I patch) | All four Gig View LEDs off |
| 5 (A2) | Switch "1" lit (green), others off |
| 6 (B2) | Switch "2" lit (red), others off |
| 7 (C2) | Switch "A" lit (orange), others off |
| 8 (D2) | Switch "B" lit (yellow), others off |

This is **ground truth**, not optimistic/local — confirmed acceptable
given the user watches the QC's own screen live and doesn't need
sub-100ms LED feedback on the MINI 6 itself. No "light immediately on
press, correct later" logic needed.

## Colors reference (for consistency if extending)

| Element | Color | Hex |
|---|---|---|
| A2 / switch "1" | Green | `0x00ff00` |
| B2 / switch "2" | Red | `0xff0000` |
| C2 / switch "A" | Orange | `0xff8000` |
| D2 / switch "B" | Yellow | `0xffff00` |
| Gig View open | White | `0xffffff` |
| Gig View closed | Dim gray | `0x282828` |
| Stomp mode | Magenta | `0xff00ff` |
| Scene mode | Blue | `0x0000ff` |

## Prior working config (reference / fallback)

Before this bidirectional project, the MINI 6 ran stock Super Mode with a
config file (`page1.txt`, page name `QCMN`) implementing the exact same
six-switch outgoing logic above, using `ledmode = [select]` (local-only,
last-pressed-wins) for LED state on switches 1/2/A/B instead of true QC
state sync. That config is a known-working fallback if this custom
firmware project is paused or abandoned — restore from backup and the
pedal returns to full (locally-tracked, non-bidirectional) functionality
immediately.
