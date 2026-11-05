import unittest

from emoji_picker.nav import Grid, Pointer


class GridTest(unittest.TestCase):
    def setUp(self):
        # sections of 5 and 2 items, 3 columns:
        # line0: 0 1 2 / line1: 3 4 / line2: 5 6
        self.g = Grid([5, 2], 3)

    def test_left_right_follow_reading_order(self):
        self.assertEqual(self.g.move(2, "right"), 3)
        self.assertEqual(self.g.move(0, "left"), 0)
        self.assertEqual(self.g.move(6, "right"), 6)

    def test_down_keeps_column_and_clamps(self):
        self.assertEqual(self.g.move(2, "down"), 4)   # line1 is shorter
        self.assertEqual(self.g.move(4, "down"), 6)
        self.assertEqual(self.g.move(6, "down"), 6)

    def test_up(self):
        self.assertEqual(self.g.move(5, "up"), 3)
        self.assertEqual(self.g.move(1, "up"), 1)

    def test_pages_and_ends(self):
        self.assertEqual(self.g.move(0, "page_down"), 5)
        self.assertEqual(self.g.move(6, "page_up"), 1)  # keeps the column
        self.assertEqual(self.g.move(3, "end"), 6)

    def test_empty(self):
        self.assertIsNone(Grid([], 3).move(None, "down"))



class PointerTest(unittest.TestCase):
    def test_still_pointer_is_not_a_move(self):
        p = Pointer()
        p.enter(100, 80)                      # window opened under the mouse
        self.assertFalse(p.motion(100, 80))   # chart rebuilt, GTK repeats the position
        self.assertFalse(p.motion(100.2, 80))
        self.assertTrue(p.motion(130, 80))    # the user moved the mouse

    def test_motion_without_enter_is_not_a_move(self):
        p = Pointer()
        self.assertFalse(p.motion(10, 10))
        self.assertTrue(p.motion(40, 10))

    def test_leave_forgets_the_position(self):
        p = Pointer()
        p.enter(0, 0)
        p.motion(50, 50)
        p.leave()
        self.assertFalse(p.moved)
        self.assertFalse(p.motion(50, 50))


if __name__ == "__main__":
    unittest.main()
