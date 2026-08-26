"""
Pure Gig View protocol/LED logic for the MINI 6 <-> Quad Cortex firmware.

No hardware imports: this module runs unchanged on the pedal
(CircuitPython 7.x) and on desktop CPython, so the incoming-CC protocol
can be regression-tested without hardware -- see tests/test_qc_logic.py
(`python3 tests/test_qc_logic.py`).

DEPLOY: must be copied to the device root alongside code.py; the QC
firmware imports it at boot.
"""

# Incoming CC 100 echo values 5-8 -> which switch's Page II slot was
# pressed (a scene or a stomp, depending on that switch's role).
GIGVIEW_ECHO_MAP = {5: "1", 6: "2", 7: "A", 8: "B"}

# Incoming CC 100 echo values 1-4 -> the MINI 6 switch sharing that QC
# column. The MINI 6 never displays Page I, but it needs the column's
# role to know what a Page I press means: on a scene column it means a
# Page I scene is now active (so no Page II scene is), while on a stomp
# column it toggled the Page I *block* -- a different block from the
# Page II one the MINI 6 shows, so it is ignored entirely.
PAGE1_COLUMN_MAP = {1: "1", 2: "2", 3: "A", 4: "B"}

# Incoming per-switch scene-color CCs -> which switch they teach.
COLOR_CC_TO_SWITCH = {101: "1", 102: "2", 103: "A", 104: "B"}

# Incoming per-switch role/state CCs -> which switch they configure.
# Values: 0 = scene role, 1 = stomp role off, 2 = stomp role on,
# 3 = stomp role toggle. See docs/PROTOCOL.md.
ROLE_CC_TO_SWITCH = {105: "1", 106: "2", 107: "A", 108: "B"}

GIGVIEW_SWITCHES = ("1", "2", "A", "B")

ROLE_SCENE = "scene"  # radio button: exactly one scene switch is bright
ROLE_STOMP = "stomp"  # latching, independent of every other switch


class GigViewTracker:
    """Scene colors, active scene, and stomp states, driven by QC CCs.

    Owns no hardware: handle_cc() returns a list of (switch_name, rgb)
    LED updates to paint (empty = nothing changed); the caller owns the
    actual pixels. gig_view_open / next_press_is_stomp are *outgoing*
    optimistic state and deliberately not tracked here -- they persist
    across preset loads (bench 2026-07-21: the QC keeps Gig View open on
    preset change).

    Each of the four switches has a role, taught per preset via CC
    105-108, because the QC's Hybrid Mode layout is user-arrangeable
    (scene row on top of stomp row, or the reverse) and so cannot be
    hardcoded:

      scene -- radio button. Exactly one scene switch is bright, the one
               whose Page II scene the QC last reported active.
      stomp -- latching and independent. Bright while engaged, dim while
               bypassed, unaffected by scene changes on other switches.

    Stomp state is inferred from the press echo, not read back: the QC
    sends the same message whether a block was engaged or bypassed, so
    the firmware flips its own bit each time. Accurate as long as it
    starts accurate -- presets teach the true state at load (CC 105-108
    values 1/2), and any scene that changes a block's bypass state can
    re-teach it from that scene's own message slots.
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
        # Roles and stomp states get the same treatment as colors: a
        # preset load resets them to the plain all-scenes layout, and a
        # hybrid preset re-teaches its own in the same batch. A stale
        # role would be worse than a stale color -- it would stop a
        # switch behaving like a scene indicator at all.
        self.roles = {name: ROLE_SCENE for name in GIGVIEW_SWITCHES}
        self.stomp_on = {name: False for name in GIGVIEW_SWITCHES}

    def is_bright(self, name):
        if self.roles[name] == ROLE_STOMP:
            return self.stomp_on[name]
        return name == self.lit_switch

    def led_color(self, name):
        # Bright color when active (scene selected / stomp engaged); dim
        # when inactive; white in either case if the color hasn't been
        # learned yet.
        color = self.scene_colors[name]
        if color is None:
            color = self.color_unknown
        if self.is_bright(name):
            return color
        d = self.dim_divisor
        return (color[0] // d, color[1] // d, color[2] // d)

    def all_led_updates(self):
        return [(name, self.led_color(name)) for name in GIGVIEW_SWITCHES]

    def handle_cc(self, cc_num, value):
        if cc_num == 100:
            if value == 0:
                # Explicit "zero out" (each preset's On Preset Load
                # config): no scene active, forget all learned colors,
                # and drop back to the plain all-scenes layout.
                self.lit_switch = None
                for name in GIGVIEW_SWITCHES:
                    self.scene_colors[name] = None
                    self.roles[name] = ROLE_SCENE
                    self.stomp_on[name] = False
                return self.all_led_updates()
            elif value in PAGE1_COLUMN_MAP:
                if self.roles[PAGE1_COLUMN_MAP[value]] == ROLE_STOMP:
                    # Page I stomp: a different block from the Page II
                    # one this switch shows. Nothing here to reflect.
                    return []
                # A Page I scene is active, so nothing on Page II is: no
                # scene switch is bright. Engaged stomps stay bright --
                # is_bright() never consults lit_switch for them.
                self.lit_switch = None
                return self.all_led_updates()
            elif value in GIGVIEW_ECHO_MAP:
                name = GIGVIEW_ECHO_MAP[value]
                if self.roles[name] == ROLE_STOMP:
                    # No ground truth available (the QC sends the same
                    # message on engage and bypass), so the press itself
                    # is the signal. Only this switch changes.
                    self.stomp_on[name] = not self.stomp_on[name]
                    return [(name, self.led_color(name))]
                self.lit_switch = name
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
        elif cc_num in ROLE_CC_TO_SWITCH:
            # Per-switch role + stomp state. Anything else is ignored.
            name = ROLE_CC_TO_SWITCH[cc_num]
            if value == 0:
                self.roles[name] = ROLE_SCENE
                self.stomp_on[name] = False
            elif value == 1 or value == 2:
                self.roles[name] = ROLE_STOMP
                self.stomp_on[name] = value == 2
                if self.lit_switch == name:
                    # It can't be the active scene any more; leaving it
                    # would light it spuriously if it ever goes back to
                    # a scene role.
                    self.lit_switch = None
            elif value == 3:
                # Toggle. Rarely needed -- the CC 100 v5-8 echo already
                # toggles -- but it lets any other QC footswitch keep
                # this LED honest, e.g. a Page I switch assigned to the
                # same block as the Page II one shown here.
                if self.roles[name] == ROLE_SCENE:
                    self.roles[name] = ROLE_STOMP
                    self.stomp_on[name] = self.lit_switch == name
                    if self.lit_switch == name:
                        self.lit_switch = None
                self.stomp_on[name] = not self.stomp_on[name]
            else:
                return []
            return [(name, self.led_color(name))]
        return []
