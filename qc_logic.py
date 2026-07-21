"""
Pure Gig View protocol/LED logic for the MINI 6 <-> Quad Cortex firmware.

No hardware imports: this module runs unchanged on the pedal
(CircuitPython 7.x) and on desktop CPython, so the incoming-CC protocol
can be regression-tested without hardware -- see tests/test_qc_logic.py
(`python3 tests/test_qc_logic.py`).

DEPLOY: must be copied to the device root alongside code.py; the QC
firmware imports it at boot.
"""

# Incoming CC 100 echo values 5-8 -> which switch's Page II scene went
# active. Values 1-4 are Page I scenes (no MINI 6 switch is bright).
GIGVIEW_ECHO_MAP = {5: "1", 6: "2", 7: "A", 8: "B"}

# Incoming per-switch scene-color CCs -> which switch they teach.
COLOR_CC_TO_SWITCH = {101: "1", 102: "2", 103: "A", 104: "B"}

GIGVIEW_SWITCHES = ("1", "2", "A", "B")


class GigViewTracker:
    """Scene colors + active scene, driven by incoming QC CCs.

    Owns no hardware: handle_cc() returns a list of (switch_name, rgb)
    LED updates to paint (empty = nothing changed); the caller owns the
    actual pixels. gig_view_open / next_press_is_stomp are *outgoing*
    optimistic state and deliberately not tracked here -- they persist
    across preset loads (bench 2026-07-21: the QC keeps Gig View open on
    preset change).
    """

    def __init__(self, palette, color_unknown, dim_divisor):
        self.palette = palette
        self.color_unknown = color_unknown
        self.dim_divisor = dim_divisor
        # None = not learned (shown dim white). CC 100 value 0 (preset
        # load) forgets all four -- each preset re-teaches its own
        # colors, or the LEDs honestly say "unknown" instead of lying
        # with stale colors.
        self.scene_colors = {"1": None, "2": None, "A": None, "B": None}
        self.lit_switch = None

    def led_color(self, name):
        # Bright scene color when active; dim scene color when inactive;
        # white in either case if the color hasn't been learned yet.
        color = self.scene_colors[name]
        if color is None:
            color = self.color_unknown
        if name == self.lit_switch:
            return color
        d = self.dim_divisor
        return (color[0] // d, color[1] // d, color[2] // d)

    def all_led_updates(self):
        return [(name, self.led_color(name)) for name in GIGVIEW_SWITCHES]

    def handle_cc(self, cc_num, value):
        if cc_num == 100:
            if value == 0:
                # Explicit "zero out" (each preset's On Preset Load
                # config): no scene active AND forget all learned colors.
                self.lit_switch = None
                for name in self.scene_colors:
                    self.scene_colors[name] = None
                return self.all_led_updates()
            elif value in (1, 2, 3, 4):
                # A Page I scene is active: nothing on Page II is, so no
                # switch is bright. Learned colors keep showing dim.
                self.lit_switch = None
                return self.all_led_updates()
            elif value in GIGVIEW_ECHO_MAP:
                self.lit_switch = GIGVIEW_ECHO_MAP[value]
                return self.all_led_updates()
            return []
        elif cc_num in COLOR_CC_TO_SWITCH:
            # Per-switch scene color: 1-8 picks from the palette, 0
            # forgets (back to dim white), anything else is ignored.
            # Applies immediately, bright or dim as appropriate.
            name = COLOR_CC_TO_SWITCH[cc_num]
            if value == 0:
                self.scene_colors[name] = None
            elif value in self.palette:
                self.scene_colors[name] = self.palette[value]
            else:
                return []
            return [(name, self.led_color(name))]
        return []
