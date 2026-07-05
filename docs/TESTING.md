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

- [x] Copy `code_draft.py` to the device root as `code.py` (per the
      standard PaintAudio USB-mode process: hold switch 1 at power-on,
      mount drive, replace `code.py`).
- [x] Power on **without** holding switch "A". Confirm the QC branch loads
      (this is now the default path). **Confirmed 2026-07-05.**
- [x] Power on **holding switch "A"**. Confirm stock Super Mode loads
      instead (QUAD page, LEDs/behavior unchanged). **Confirmed 2026-07-05
      — full checkout, all buttons still function as intended.**
- [x] Release "A" once the QC branch is up (i.e. after a non-held boot) —
      confirm the release itself does not fire a spurious CC 41 (Gig View
      C2 select), since "A" is reused for that during QC runtime.
      **Confirmed 2026-07-05, part of the full checkout above.**
- [x] Press each of the 6 switches one at a time. Confirm no crash/hang.
      **Confirmed 2026-07-05.**
- [x] If a switch does nothing and no error appears — check GPIO pin
      assignment for that switch first (see HARDWARE.md risk #1, GP24/GP25
      conflict). **Confirmed 2026-07-05: not an issue on this unit — all
      switches responded correctly out of the box on GP24/GP25.**

## 2. LED indexing

- [x] Confirm each switch's press lights the *correct* 3-pixel group (not
      a neighboring switch's LEDs) — proves GP7 NeoPixel wiring/order
      assumption and the `SWITCH_PIXELS` index map. **Confirmed 2026-07-05.**

## 3. Outgoing MIDI (MINI 6 → QC)

- [x] With a MIDI monitor between the MINI 6 and QC (or QC's own MIDI
      Thru + laptop), press switch "1". Confirm CC 39 value 127 arrives.
- [x] Repeat for switches 2/A/B (CC 40/41/42) and confirm the QC actually
      navigates to A2/B2/C2/D2 as expected.
- [x] Press switch "3" twice. Confirm CC 46 alternates 127 then 0, and
      that Gig View actually opens then closes on the QC screen.
- [x] Press switch "C" twice. Confirm CC 47 sends 2 then 1, and QC mode
      indicator (top-right of Grid/Gig View) shows Stomp then Scene.

## 4. Incoming MIDI (QC → MINI 6) — resolves the UART-vs-USB unknown

- [x] On the QC, configure all 8 Gig View footswitch identities in
      Cortex Control's Preset MIDI Out panel per the table in
      `PROTOCOL.md` (CC 100, values 1-8).
- [x] Without touching the MINI 6, press A2 on the QC's own touchscreen
      or onboard footswitch. Watch the MINI 6's switch "1" LED.
  - **If it lights up green:** UART path works, no changes needed.
  - **If nothing happens:** swap in the commented-out `usb_midi` block in
    `code_draft.py` in place of the `busio.UART` setup, reflash, retest.
  - **Confirmed 2026-07-05: UART path works out of the box — lights up
    green, no `usb_midi` fallback needed. Unknown #2 resolved.**
- [x] Repeat for B2/C2/D2 (switches "2"/"A"/"B" respectively).
- [x] Press A1/B1/C1/D1 on the QC. Confirm all four Gig View LEDs on the
      MINI 6 go dark.
- [x] Cross-test: press switch "1" on the MINI 6 itself (triggering CC 39
      out), then confirm the QC both navigates to A2 *and* echoes CC 100
      value 5 back, lighting the LED via the full round-trip rather than
      any local/optimistic logic (there isn't any in this design, so this
      just confirms the echo path works symmetrically regardless of which
      side initiated the change).
- [x] Preset-load clear: on each preset used live, add an On Preset Load
      message (CC 100, value 0, channel 1 — see `PROTOCOL.md`). With a
      Page II scene LED lit on the MINI 6, load a different preset on the
      QC and confirm all four Gig View LEDs clear.

## 5. Debounce / reliability

- [x] Rapid double-taps on each switch — confirm no double-fires, no
      missed presses. Current debounce window is 30ms
      (`DEBOUNCE_S = 0.03` in `code_draft.py`) — adjust if too twitchy or
      too sluggish underfoot. **Confirmed 2026-07-05: solid at 30ms, no
      adjustment needed.**

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

## 8. Display (known unknown #3 in `code_draft.py`)

- [x] With switch "C" held at power-on (QC branch), confirm the TFT shows
      the Neural DSP logo (`wp5.bmp`) instead of staying blank/garbage.
      Display init is non-fatal by design (wrapped in try/except, error
      printed to serial) — if the logo is missing but switches/MIDI still
      work, check the serial console for the printed exception rather
      than suspecting a full crash. **Confirmed 2026-07-05: logo shows,
      display init did not crash the firmware.**
- [x] If the screen stays dark: check the `reset=None` assumption first —
      the panel may need an actual reset pulse from a GPIO we haven't
      identified yet. **N/A — screen was not dark, `reset=None` is
      correct.**
- [x] If the image is shifted, cut off, or has a garbage band along one
      edge: try `rowstart=80` (common offset for 240x240 panels on a
      taller controller). **Confirmed 2026-07-05: this was the issue —
      first flash showed a garbage/blank band across the top with the
      logo shifted down and boxed in. `rowstart=80` applied in
      `code_draft.py`; reflash + reverify pending.**
- [x] If the image is upside-down or sideways: try `rotation=90/180/270`.
      **Confirmed 2026-07-05: logo now centered/correct with `rowstart=80`,
      `rotation=0` unchanged.**
- [x] Confirm the logo stays static and doesn't interfere with switch
      responsiveness or MIDI timing (it's drawn once at boot, not in the
      main loop, so it shouldn't — but confirm). **Confirmed by user
      2026-07-05 — no meaningful performance impact observed.**
- [x] New 2026-07-05: with the `rowstart=80` fix in place, a white
      pixelated screen (leftover GRAM noise) was visible for a beat before
      the logo finished painting in, bottom-to-top. **Resolved 2026-07-05
      via a red-frame diagnostic build:** the working pattern is
      `display.auto_refresh = False` before any `show()`, then an explicit
      `display.refresh()` after each `show()` — with auto-refresh enabled,
      a background refresh can be "in progress" on the bus, making a
      manual `refresh()` silently return without painting. (An earlier
      test of this same pattern appeared to fail, but the diagnostic
      proved the pattern works — that flash most likely never took due to
      an un-flushed USB copy. Lesson: eject the CIRCUITPY drive cleanly
      before power-cycling.) `auto_refresh` stays off permanently since
      the display is static after boot. Residual: a brief flash of noise
      remains between power-on and the black frame — that's the
      CircuitPython boot/import window before our code can paint, with
      the backlight already on; can't be fully eliminated from `code.py`.
- [x] New 2026-07-05: to shrink that residual noise window, the QC branch
      was reordered — display init + black paint now happen first, before
      the heavy imports (`adafruit_midi` is source and slow to parse on
      the RP2040), which previously all ran inside the noise window.
      **Tested 2026-07-05: no meaningful change in the noise window** —
      the boot noise is dominated by CircuitPython's interpreter startup,
      not our import time. Sequence is otherwise correct (black frame,
      then logo). Accepted as-is for now; alternative paths for
      eliminating the noise are tracked in the TO-DO list in
      `docs/CLAUDE.md`. Since the reordering bought nothing, it was
      reverted 2026-07-05 to keep the code lean — display logic is back
      to a single block, keeping only the proven fixes (rowstart=80,
      auto_refresh off + explicit refresh(), black blank frame). The
      reverted structure passed its smoke test on hardware 2026-07-05.
- [ ] Power on holding "A" (stock branch, per the 2026-07-05 selector
      flip) and confirm the screen behaves exactly as it always has — this
      code path never touches the display, so stock's own screen usage
      should be completely unaffected.

## 9. Per-preset LED color override (CC 101-104, added 2026-07-05)

**Confirmed working on hardware 2026-07-05, first flash — tested across
multiple banks/presets with differing color assignments, operating as
designed. Palette colors look right; no tuning needed.**

- [x] On a test preset, add On Preset Load messages: CC 101 with some
      value 1-8 that is NOT green (say 3, red), channel 1, alongside the
      existing CC 100 value 0 clear. Load the preset, then select A2 (from
      either device) — switch "1" should light in the new color instead
      of the default green.
- [x] With that A2 LED still lit, send a different color on CC 101 (e.g.
      from a MIDI monitor/laptop, or by re-loading a preset configured
      differently) — the lit LED should repaint immediately, without
      needing another scene change.
- [x] Send CC 101 value 0 — switch "1" should go back to default green on
      the next A2 echo (and immediately if lit).
- [x] Send an out-of-range value (e.g. CC 101 value 20) — should be
      ignored, no color change, no crash.
- [x] Repeat the basic override check for CC 102/103/104 → switches
      "2"/"A"/"B".
- [x] Load a preset with NO color messages after one that set custom
      colors — confirm colors persist (this is by design; presets wanting
      defaults must send value 0s).
- [x] Compare each of the 8 palette values side by side with the QC's
      picker colors on its screen; tune the RGB values in
      `QC_COLOR_PALETTE` if any look wrong (pink and purple are the
      likeliest to need adjustment).

## 10. Three-state LEDs — dim/bright/unknown (added 2026-07-05)

**Bench-tested 2026-07-05: everything below confirmed working, including
the adjusted dim level (`DIM_DIVISOR = 8`). Section complete.**

Gig View LEDs are now never fully off: bright scene color = active, dim
scene color = inactive, white = color not learned (boot, or since the
last CC 100 value 0). Note the semantic changes from section 9's original
design: CC 100 value 0 now also FORGETS learned colors, and CC 101-104
value 0 now means "forget" (dim white), not "restore default" — the
static green/red/orange/yellow defaults are retired.

- [x] Boot the QC branch: all four Gig View switches should show dim
      white (not off) alongside the usual "3"/"C" defaults.
- [x] Load an opted-in preset (On Preset Load: CC 100 v0 + color CCs):
      all four should go dim in that preset's colors, no interaction
      needed.
- [x] Select a Page II scene: that switch bright in its color, the other
      three stay dim in theirs.
- [x] Select a Page I scene: no switch bright, all four dim in their
      learned colors (colors NOT forgotten).
- [x] Load a preset with only the CC 100 v0 clear and no color CCs: all
      four should drop to dim white (previous preset's colors forgotten).
- [x] Send CC 101 value 0 with switch "1" lit: should go bright white
      (active but unknown), then dim white after leaving the scene.
- [x] Dim level check: `DIM_DIVISOR = 6` confirmed slightly too bright on
      bench; bumped to 8 — **confirmed as desired on hardware 2026-07-05.**
- [x] Optional, QC-side: in Cortex Control's Preset MIDI Out panel, check
      whether one of the 8 scene entries (AI-DII — the same entries that
      send the CC 100 value 1-8 echoes) can hold MORE than one message.
      **Confirmed 2026-07-05: yes — each scene entry has multiple message
      slots (Cortex Control marks the footswitches "MULTIPLE"; e.g. AII
      configured with CC 100 v5 + CC 101 v8). The user has already set
      this up — color CCs now ride alongside the scene echoes, so
      "press to learn" works, and the firmware handles either message
      order within a press.**
