"""Desktop regression tests for the Gig View incoming-CC protocol.

Run from the repo root (no hardware, no dependencies):

    python3 tests/test_qc_logic.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qc_logic

# Mirrors the values in code_draft.py; the logic is palette-agnostic so the
# tests only care about identity, not the exact RGB numbers.
PALETTE = {
    1: (255, 255, 0),
    2: (255, 128, 0),
    3: (255, 0, 0),
    4: (255, 0, 128),
    5: (128, 0, 255),
    6: (0, 0, 255),
    7: (0, 255, 255),
    8: (0, 255, 0),
}
UNKNOWN = (255, 255, 255)
DIM = 8


def dim(color):
    return (color[0] // DIM, color[1] // DIM, color[2] // DIM)


def make_tracker():
    return qc_logic.GigViewTracker(PALETTE, UNKNOWN, DIM)


class InitialState(unittest.TestCase):
    def test_boot_shows_all_dim_white(self):
        t = make_tracker()
        self.assertEqual(
            t.all_led_updates(),
            [(name, dim(UNKNOWN)) for name in ("1", "2", "A", "B")],
        )

    def test_nothing_lit_at_boot(self):
        self.assertIsNone(make_tracker().lit_switch)


class ColorLearning(unittest.TestCase):
    def test_learn_color_paints_that_switch_dim(self):
        t = make_tracker()
        updates = t.handle_cc(101, 3)  # switch "1" -> red
        self.assertEqual(updates, [("1", dim(PALETTE[3]))])

    def test_learn_color_while_lit_paints_bright(self):
        t = make_tracker()
        t.handle_cc(100, 5)  # switch "1" active
        updates = t.handle_cc(101, 3)
        self.assertEqual(updates, [("1", PALETTE[3])])

    def test_value_zero_forgets_one_switch(self):
        t = make_tracker()
        t.handle_cc(102, 8)
        updates = t.handle_cc(102, 0)
        self.assertEqual(updates, [("2", dim(UNKNOWN))])
        self.assertIsNone(t.scene_colors["2"])

    def test_out_of_palette_value_is_ignored(self):
        t = make_tracker()
        t.handle_cc(103, 4)
        before = dict(t.scene_colors)
        self.assertEqual(t.handle_cc(103, 9), [])
        self.assertEqual(t.handle_cc(103, 127), [])
        self.assertEqual(t.scene_colors, before)

    def test_each_color_cc_maps_to_its_switch(self):
        t = make_tracker()
        for cc, name in ((101, "1"), (102, "2"), (103, "A"), (104, "B")):
            updates = t.handle_cc(cc, 6)
            self.assertEqual(updates, [(name, dim(PALETTE[6]))])


class SceneEchoes(unittest.TestCase):
    def test_page2_echo_lights_the_mapped_switch(self):
        t = make_tracker()
        t.handle_cc(103, 7)  # "A" learns cyan
        updates = dict(t.handle_cc(100, 7))  # A2 pressed -> "A" active
        self.assertEqual(t.lit_switch, "A")
        self.assertEqual(updates["A"], PALETTE[7])
        self.assertEqual(updates["1"], dim(UNKNOWN))

    def test_page1_echo_clears_the_lit_switch(self):
        t = make_tracker()
        t.handle_cc(102, 2)
        t.handle_cc(100, 6)  # "2" active
        updates = dict(t.handle_cc(100, 1))  # Page I scene: nothing bright
        self.assertIsNone(t.lit_switch)
        self.assertEqual(updates["2"], dim(PALETTE[2]))

    def test_switching_active_scene_moves_the_bright_led(self):
        t = make_tracker()
        t.handle_cc(100, 5)
        updates = dict(t.handle_cc(100, 8))  # "1" -> "B"
        self.assertEqual(t.lit_switch, "B")
        self.assertEqual(updates["1"], dim(UNKNOWN))
        self.assertEqual(updates["B"], UNKNOWN)

    def test_unknown_cc100_values_are_ignored(self):
        t = make_tracker()
        t.handle_cc(100, 5)
        for value in (9, 42, 127):
            self.assertEqual(t.handle_cc(100, value), [])
        self.assertEqual(t.lit_switch, "1")


class PresetLoad(unittest.TestCase):
    def _loaded_tracker(self):
        t = make_tracker()
        t.handle_cc(101, 1)
        t.handle_cc(102, 2)
        t.handle_cc(103, 3)
        t.handle_cc(104, 4)
        t.handle_cc(100, 6)  # "2" active
        return t

    def test_zero_out_forgets_everything(self):
        t = self._loaded_tracker()
        updates = t.handle_cc(100, 0)
        self.assertIsNone(t.lit_switch)
        self.assertEqual(t.scene_colors, {"1": None, "2": None, "A": None, "B": None})
        self.assertEqual(
            updates, [(name, dim(UNKNOWN)) for name in ("1", "2", "A", "B")]
        )

    def test_preset_can_reteach_after_zero_out(self):
        t = self._loaded_tracker()
        t.handle_cc(100, 0)
        updates = t.handle_cc(104, 5)
        self.assertEqual(updates, [("B", dim(PALETTE[5]))])


class StompRoles(unittest.TestCase):
    """Hybrid Scene/Stomp layouts, taught per preset via CC 105-108."""

    def _hybrid(self):
        # The user's layout: "1"/"2" scenes, "A"/"B" stomps -- "A"
        # starting bypassed, "B" starting engaged.
        t = make_tracker()
        t.handle_cc(105, 0)
        t.handle_cc(106, 0)
        t.handle_cc(107, 1)
        t.handle_cc(108, 2)
        return t

    def test_roles_default_to_scene(self):
        t = make_tracker()
        self.assertEqual(set(t.roles.values()), {qc_logic.ROLE_SCENE})

    def test_stomp_can_start_engaged_or_bypassed(self):
        t = make_tracker()
        t.handle_cc(103, 8)  # "A" learns green
        self.assertEqual(t.handle_cc(107, 1), [("A", dim(PALETTE[8]))])
        self.assertEqual(t.handle_cc(107, 2), [("A", PALETTE[8])])

    def test_echo_toggles_a_stomp_without_touching_anything_else(self):
        t = self._hybrid()
        t.handle_cc(100, 5)  # scene "1" active
        updates = t.handle_cc(100, 7)  # "A" (C2) pressed -> engage
        self.assertEqual(updates, [("A", UNKNOWN)])
        self.assertTrue(t.stomp_on["A"])
        self.assertEqual(t.lit_switch, "1")  # scene untouched
        self.assertTrue(t.stomp_on["B"])  # other stomp untouched

    def test_two_stomps_and_a_scene_are_bright_together(self):
        t = self._hybrid()
        t.handle_cc(100, 7)  # engage "A"
        t.handle_cc(100, 5)  # scene "1" active
        bright = [n for n in ("1", "2", "A", "B") if t.is_bright(n)]
        self.assertEqual(bright, ["1", "A", "B"])

    def test_scene_change_does_not_clear_stomps(self):
        t = self._hybrid()
        t.handle_cc(100, 5)  # scene "1"
        t.handle_cc(100, 6)  # scene "2"
        self.assertEqual(t.lit_switch, "2")
        self.assertTrue(t.stomp_on["B"])
        self.assertFalse(t.stomp_on["A"])

    def test_page1_scene_dims_scenes_and_leaves_stomps_bright(self):
        t = self._hybrid()
        t.handle_cc(100, 5)  # scene "1" active
        updates = dict(t.handle_cc(100, 1))  # A1: a Page I scene
        self.assertIsNone(t.lit_switch)
        self.assertEqual(updates["1"], dim(UNKNOWN))
        self.assertEqual(updates["B"], UNKNOWN)  # engaged stomp stays bright

    def test_page1_stomp_press_is_ignored(self):
        # C1 is a different block from C2 -- the MINI 6 shows only C2.
        t = self._hybrid()
        t.handle_cc(100, 5)
        for value in (3, 4):
            self.assertEqual(t.handle_cc(100, value), [])
        self.assertEqual(t.lit_switch, "1")
        self.assertFalse(t.stomp_on["A"])
        self.assertTrue(t.stomp_on["B"])

    def test_reversed_layout_swaps_which_page1_values_clear(self):
        # Stomp row on top: "1"/"2" stomps, "A"/"B" scenes.
        t = make_tracker()
        t.handle_cc(105, 1)
        t.handle_cc(106, 1)
        t.handle_cc(107, 0)
        t.handle_cc(108, 0)
        t.handle_cc(100, 7)  # scene "A" active
        self.assertEqual(t.handle_cc(100, 1), [])  # A1 is now a stomp
        self.assertEqual(t.lit_switch, "A")
        self.assertTrue(t.handle_cc(100, 3))  # C1 is now a Page I scene
        self.assertIsNone(t.lit_switch)

    def test_becoming_a_stomp_releases_the_lit_scene(self):
        t = make_tracker()
        t.handle_cc(100, 5)  # "1" is the active scene
        t.handle_cc(105, 1)  # ...now a bypassed stomp
        self.assertIsNone(t.lit_switch)
        self.assertFalse(t.is_bright("1"))

    def test_role_zero_returns_a_switch_to_scene_and_dims_it(self):
        t = self._hybrid()
        t.handle_cc(100, 8)  # "B" toggles off (started engaged)
        t.handle_cc(100, 8)  # ...back on
        self.assertEqual(t.handle_cc(108, 0), [("B", dim(UNKNOWN))])
        self.assertEqual(t.roles["B"], qc_logic.ROLE_SCENE)
        self.assertFalse(t.stomp_on["B"])

    def test_explicit_toggle_value(self):
        t = self._hybrid()
        self.assertEqual(t.handle_cc(107, 3), [("A", UNKNOWN)])
        self.assertTrue(t.stomp_on["A"])
        self.assertEqual(t.handle_cc(107, 3), [("A", dim(UNKNOWN))])
        self.assertFalse(t.stomp_on["A"])

    def test_toggle_adopts_stomp_role_carrying_current_brightness(self):
        t = make_tracker()
        t.handle_cc(100, 5)  # "1" bright as the active scene
        t.handle_cc(105, 3)  # toggle: adopt stomp role, then flip off
        self.assertEqual(t.roles["1"], qc_logic.ROLE_STOMP)
        self.assertFalse(t.stomp_on["1"])
        self.assertIsNone(t.lit_switch)

    def test_out_of_range_role_values_are_ignored(self):
        t = self._hybrid()
        for value in (4, 9, 127):
            self.assertEqual(t.handle_cc(107, value), [])
        self.assertEqual(t.roles["A"], qc_logic.ROLE_STOMP)
        self.assertFalse(t.stomp_on["A"])

    def test_preset_load_resets_the_layout(self):
        t = self._hybrid()
        t.handle_cc(100, 7)  # engage "A"
        t.handle_cc(100, 0)  # preset load
        self.assertEqual(set(t.roles.values()), {qc_logic.ROLE_SCENE})
        self.assertEqual(set(t.stomp_on.values()), {False})

    def test_a_scene_can_reteach_stomp_states_it_changed(self):
        # Scenes carry per-block bypass states on the QC, so a scene's
        # own message slots can re-assert them alongside its CC 100 echo.
        t = self._hybrid()
        t.handle_cc(100, 5)  # scene "1"
        t.handle_cc(107, 2)  # ...which engages "A"
        t.handle_cc(108, 1)  # ...and bypasses "B"
        self.assertTrue(t.stomp_on["A"])
        self.assertFalse(t.stomp_on["B"])
        self.assertEqual(t.lit_switch, "1")


class UnrelatedTraffic(unittest.TestCase):
    def test_other_ccs_do_nothing(self):
        t = make_tracker()
        before = dict(t.scene_colors)
        for cc in (0, 39, 46, 47, 99, 109, 127):
            self.assertEqual(t.handle_cc(cc, 127), [])
        self.assertEqual(t.scene_colors, before)
        self.assertIsNone(t.lit_switch)
        self.assertEqual(set(t.roles.values()), {qc_logic.ROLE_SCENE})


if __name__ == "__main__":
    unittest.main()
