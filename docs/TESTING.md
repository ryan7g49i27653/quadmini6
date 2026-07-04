# Bench Test Checklist

Work through in order — each step either confirms an assumption the draft
code depends on, or reveals which fallback to swap in. Don't skip ahead;
later steps are hard to debug if an earlier assumption was wrong.

## 0. Before touching anything

- [x] Back up the entire `supersetup` folder from the MINI 6's USB drive to
      a local folder. This is the known-working Super Mode config (both
      the QC page and a separate laptop-effects-rig page) — the fallback
      if this project stalls or the device needs to go back to normal
      before a gig. **Done — confirmed by user, 2026-07-04.**

## 1. Flash and basic switch response

- [ ] Copy `code_draft.py` to the device root as `code.py` (per the
      standard PaintAudio USB-mode process: hold switch 1 at power-on,
      mount drive, replace `code.py`).
- [ ] Power on **without** holding switch "C". Confirm stock Super Mode
      loads exactly as before (QUAD page, LEDs/behavior unchanged). This
      is the dual-boot selector's default path — if this regresses, stock
      usage for both rigs breaks, not just the new QC feature.
- [ ] Power on **holding switch "C"**. Confirm the device does NOT run
      stock Super Mode — this is the QC branch. Attach a serial console if
      possible (helps see tracebacks, including non-fatal display errors,
      which print but don't halt). Continue the rest of this checklist
      with "C" held at every subsequent power-on.
- [ ] Release "C" once the QC branch is up — confirm the release itself
      does not fire a spurious CC 47 (mode change). By design, press
      events only fire on a new press, but verify on hardware.
- [ ] Press each of the 6 switches one at a time. Confirm no crash/hang.
- [ ] If a switch does nothing and no error appears — check GPIO pin
      assignment for that switch first (see HARDWARE.md risk #1, GP24/GP25
      conflict).

## 2. LED indexing

- [ ] Confirm each switch's press lights the *correct* 3-pixel group (not
      a neighboring switch's LEDs) — proves GP7 NeoPixel wiring/order
      assumption and the `SWITCH_PIXELS` index map.

## 3. Outgoing MIDI (MINI 6 → QC)

- [ ] With a MIDI monitor between the MINI 6 and QC (or QC's own MIDI
      Thru + laptop), press switch "1". Confirm CC 39 value 127 arrives.
- [ ] Repeat for switches 2/A/B (CC 40/41/42) and confirm the QC actually
      navigates to A2/B2/C2/D2 as expected.
- [ ] Press switch "3" twice. Confirm CC 46 alternates 127 then 0, and
      that Gig View actually opens then closes on the QC screen.
- [ ] Press switch "C" twice. Confirm CC 47 sends 2 then 1, and QC mode
      indicator (top-right of Grid/Gig View) shows Stomp then Scene.

## 4. Incoming MIDI (QC → MINI 6) — resolves the UART-vs-USB unknown

- [ ] On the QC, configure all 8 Gig View footswitch identities in
      Cortex Control's Preset MIDI Out panel per the table in
      `PROTOCOL.md` (CC 100, values 1-8).
- [ ] Without touching the MINI 6, press A2 on the QC's own touchscreen
      or onboard footswitch. Watch the MINI 6's switch "1" LED.
  - **If it lights up green:** UART path works, no changes needed.
  - **If nothing happens:** swap in the commented-out `usb_midi` block in
    `code_draft.py` in place of the `busio.UART` setup, reflash, retest.
- [ ] Repeat for B2/C2/D2 (switches "2"/"A"/"B" respectively).
- [ ] Press A1/B1/C1/D1 on the QC. Confirm all four Gig View LEDs on the
      MINI 6 go dark.
- [ ] Cross-test: press switch "1" on the MINI 6 itself (triggering CC 39
      out), then confirm the QC both navigates to A2 *and* echoes CC 100
      value 5 back, lighting the LED via the full round-trip rather than
      any local/optimistic logic (there isn't any in this design, so this
      just confirms the echo path works symmetrically regardless of which
      side initiated the change).
- [ ] Preset-load clear: on each preset used live, add an On Preset Load
      message (CC 100, value 1, channel 1 — see `PROTOCOL.md`). With a
      Page II scene LED lit on the MINI 6, load a different preset on the
      QC and confirm all four Gig View LEDs clear.

## 5. Debounce / reliability

- [ ] Rapid double-taps on each switch — confirm no double-fires, no
      missed presses. Current debounce window is 30ms
      (`DEBOUNCE_S = 0.03` in `code_draft.py`) — adjust if too twitchy or
      too sluggish underfoot.

## 6. Known gaps not yet addressed (decide if needed before relying on this live)

- [x] Long-press page+/page− behavior on switches "3"/"C" — resolved by
      the dual-boot design, 2026-07-04: multi-page switching (QUAD, DRKG,
      etc.) stays fully available by booting stock (the default path),
      where the hardwired long-press behavior is untouched. The QC branch
      has no page concept by design, so long-press has no job there.
      Nothing to implement unless a new use for long-press comes up.
- [x] No screen/display support beyond a static logo — resolved 2026-07-04
      by showing `wallpaper/wp5.bmp` once at boot in the QC branch (see
      section 8 below for the actual verification steps). Still no PC/CC
      values, battery status, or any other stock display info — confirmed
      not needed for this mode.

## 7. Known gaps already decided (verify behavior matches the decision)

- [x] Switch "3" (Gig View) LED defaults to closed at boot — matches the
      QC's actual boot state, so this needs no correction logic. Confirm
      during testing that it's actually correct on first power-up.
- [x] Switch "C" (Mode) LED defaults to Scene at boot — a best-guess, not
      ground truth, since the QC has no MIDI feedback for current Mode and
      remembers its last-used mode across power cycles. Decided acceptable
      since the QC is in Scene mode the vast majority of the time; wrong
      guesses self-correct within 1-2 presses of "C" (see `PROTOCOL.md`).
      Confirm during testing that a wrong guess still reaches the intended
      mode within 2 presses, not more.

## 8. Display (new, untested — known unknown #3 in `code_draft.py`)

- [ ] With switch "C" held at power-on (QC branch), confirm the TFT shows
      the Neural DSP logo (`wp5.bmp`) instead of staying blank/garbage.
      Display init is non-fatal by design (wrapped in try/except, error
      printed to serial) — if the logo is missing but switches/MIDI still
      work, check the serial console for the printed exception rather
      than suspecting a full crash.
- [ ] If the screen stays dark: check the `reset=None` assumption first —
      the panel may need an actual reset pulse from a GPIO we haven't
      identified yet.
- [ ] If the image is shifted, cut off, or has a garbage band along one
      edge: try `rowstart=80` (common offset for 240x240 panels on a
      taller controller).
- [ ] If the image is upside-down or sideways: try `rotation=90/180/270`.
- [ ] Confirm the logo stays static and doesn't interfere with switch
      responsiveness or MIDI timing (it's drawn once at boot, not in the
      main loop, so it shouldn't — but confirm).
- [ ] Power on **without** holding "C" (stock branch) and confirm the
      screen behaves exactly as it always has — this code path never
      touches the display, so stock's own screen usage should be
      completely unaffected.
