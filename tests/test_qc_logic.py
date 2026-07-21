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


class UnrelatedTraffic(unittest.TestCase):
    def test_other_ccs_do_nothing(self):
        t = make_tracker()
        before = dict(t.scene_colors)
        for cc in (0, 39, 46, 47, 99, 105, 127):
            self.assertEqual(t.handle_cc(cc, 127), [])
        self.assertEqual(t.scene_colors, before)
        self.assertIsNone(t.lit_switch)


if __name__ == "__main__":
    unittest.main()
