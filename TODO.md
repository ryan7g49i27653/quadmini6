# TODO — MINI 6 dual-boot firmware

From code review of `code_draft.py`, 2026-07-20.

## Must fix before next gig

- [x] **Drain all pending MIDI messages per loop pass** (`code_draft.py:378-380`)
  *(implemented and bench-tested 2026-07-21)*

  Only one message is drained per iteration. Loop period is ~1-3ms (sleep +
  UART timeout + up to ~0.85ms blocking `pixels.show()`), but a preset load
  sends a 5-message burst (CC 100 + CC 101-104) back-to-back at 31250 baud.
  If the QC ever emits Clock (0xF8) or Active Sensing (0xFE), the default
  64-byte `busio.UART` buffer overruns and CCs are silently dropped — LEDs
  show stale or wrong scene colors mid-set.

  ```python
  for _ in range(8):                      # bounded drain, never starves switches
      msg = midi.receive()
      if msg is None:
          break
      if isinstance(msg, ControlChange):
          handle_incoming_cc(msg.control, msg.value)
  ```

  Pair with a bigger hardware buffer:

  ```python
  uart = busio.UART(board.GP16, board.GP17, baudrate=31250,
                    timeout=0.001, receiver_buffer_size=256)
  ```

- [x] **Guard `import midicaptain6s`** (`code_draft.py:89-90`)
  *(implemented and bench-tested 2026-07-21)*

  Unguarded. If the stock module is missing or raises, CircuitPython drops to
  the REPL and the pedal is dead — no LEDs, no MIDI. The display path already
  has this protection; the mission-critical path does not.

  ```python
  if _load_stock_firmware:
      try:
          import midicaptain6s
      except Exception as _e:
          import sys
          sys.print_exception(_e)
          # fall through to QC firmware rather than dying at the REPL
          _load_stock_firmware = False
  ```

## Should fix

- [x] **Settle delay before snapshotting switch state** (`code_draft.py:214-219, 255`)
  *(implemented and bench-tested 2026-07-21)*

  The selector pin gets `time.sleep(0.05)` after enabling its pull-up; the six
  runtime switches get none. `last_state` may capture a floating read,
  producing a phantom press on the first loop pass that sends a real CC to the
  QC at boot. Add a 50ms sleep after configuring switches, before the snapshot.

- [x] **Reset `gig_view_open` and `next_press_is_stomp` on CC 100 value 0** (`code_draft.py:328-338`)
  *(implemented and bench-tested 2026-07-21)*

  Preset load clears `lit_switch` and `scene_colors` but leaves these two
  stale. If the QC closes Gig View on preset change, the switch "3" LED lies
  until pressed twice.

- [ ] **Re-verify CC 46 semantics on bench** (`code_draft.py:301`)

  Docstring calls CC 46 a *toggle*, but the code sends `127`/`0` as if it were
  a state set. If the QC toggles on any value, the `0` still toggles and local
  state drifts. If confirmed a toggle, send `127` unconditionally.

## Nice to have

- [ ] **Switch to `time.monotonic_ns()`** (`code_draft.py:368`)

  `time.monotonic()` returns a float that loses resolution as uptime grows
  (~0.006s spacing at ~1 day, ~0.03s at ~6 days) — eventually degenerate
  against `DEBOUNCE_S = 0.03`. Irrelevant for a gig, relevant for an
  always-on rig. Use integer nanosecond comparisons.

- [ ] **Replace tuple-truthiness check with `is None`** (`code_draft.py:267`)

  `scene_colors[name] or COLOR_UNKNOWN` is correct today (`(0,0,0)` is
  truthy) but fragile if colors ever become lists or ints.

- [ ] **Pin the CircuitPython version loudly** (`code_draft.py:180, 195-205`)

  `display.show()` and `displayio.FourWire` were removed in CircuitPython 9
  (`display.root_group = group`, `fourwire.FourWire`). Correct for the pinned
  7.3.1 — add a version assertion or comment so a future UF2 upgrade fails
  loudly instead of at load.

- [ ] **Extract pure logic for desktop testing**

  Zero automated coverage; "bench-tested" is the only verification.
  `gigview_led_color`, `handle_incoming_cc`, and the debounce predicate are
  pure logic. Extracting them into a module importable on desktop with a fake
  `pixels` object would allow regression-testing the protocol without hardware.

## Confirmed good — do not regress

- Incoming CC handling validates strictly via dict membership and explicit
  value tuples, with a bare `return` on unknown values.
- `pixels.show()` is deliberately called only for locally-owned LEDs
  ("3", "C") and not for echo-driven ones. Correct separation of optimistic
  vs. confirmed state.
- Display init wrapped in try/except — the logo is cosmetic, MIDI/LED sync is
  the mission.
- Selector pin is deinit'd before either firmware loads, so the next claim is
  clean.
- "Dim white = honestly unknown, rather than stale color" is documented and
  implemented consistently.
