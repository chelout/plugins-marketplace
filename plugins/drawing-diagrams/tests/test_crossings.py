import unittest

import support
from diagrams import flow, router


def card(i):
    return {"id": i, "title": i, "text": "Text"}


# a -> d and c -> b go corner to opposite corner up the one gutter between the columns: a -> d
# comes in from the left and leaves to the right, c -> b the other way round, so the two lines
# drawn side by side along the gutter swap sides there and cross once.
SWAP = {"kind": "flow", "nodes": [card(i) for i in "bdac"], "grid": ["b d", "a c"], "edges": ["a -> d", "c -> b"]}
SWAP_PATHS = [[(1, 3), (2, 3), (2, 1), (3, 1)], [(3, 3), (2, 3), (2, 1), (1, 1)]]
# a -> d and d -> a share the gutter between the rows: d -> a stays above a -> d from end to end.
NO_SWAP = {"kind": "flow", "nodes": [card(i) for i in "abcd"], "grid": ["a b .", ". c d"],
           "edges": ["a -> d", "d -> a"]}
NO_SWAP_PATHS = [[(1, 1), (1, 2), (5, 2), (5, 3)], [(5, 3), (6, 3), (6, 2), (2, 2), (2, 1), (1, 1)]]


class SharedStretch(unittest.TestCase):
    """router.crossings counts a stretch two lines share when they enter and leave it in swapped
    order, once per pair, and nothing when the order holds."""

    def test_swap_in_one_gutter(self):
        for mode in ("page", "widget"):
            with self.subTest(mode=mode):
                layout, _ = flow.plan(SWAP, mode)
                # the case exists only if both lines run up the gutter between the columns
                self.assertEqual(layout["paths"], SWAP_PATHS, "harness: the lines do not share the gutter")
                self.assertEqual(layout["crossings"], 1)

    def test_shared_row_gutter_without_swap(self):
        for mode in ("page", "widget"):
            with self.subTest(mode=mode):
                layout, _ = flow.plan(NO_SWAP, mode)
                # the case exists only if both lines run along the gutter between the rows
                self.assertEqual(layout["paths"], NO_SWAP_PATHS, "harness: the lines do not share the gutter")
                self.assertEqual(layout["crossings"], 0)

    def test_swap_counts_once_whichever_way_round(self):
        a, b = SWAP_PATHS
        for paths in ([a, b], [b, a], [a, b[::-1]], [a[::-1], b[::-1]]):
            with self.subTest(paths=paths):
                self.assertEqual(router.crossings(paths), 1)

    def test_same_side_at_both_ends(self):
        # each enters and leaves the gutter on its own side: no swap
        self.assertEqual(router.crossings([[(1, 1), (2, 1), (2, 5), (1, 5)], [(3, 1), (2, 1), (2, 5), (3, 5)]]), 0)

    def test_one_line_straight_through(self):
        straight = [(2, 0), (2, 6)]
        for other, want in (([(1, 2), (2, 2), (2, 4), (3, 4)], 1),   # joins from the left, leaves to the right
                            ([(1, 2), (2, 2), (2, 4), (1, 4)], 0)):  # joins and leaves on the left
            for paths in ([straight, other], [straight, other[::-1]], [straight[::-1], other]):
                with self.subTest(paths=paths):
                    self.assertEqual(router.crossings(paths), want)

    def test_two_swaps_between_one_pair(self):
        # the other line joins the straight one from the left and leaves to the right, then comes
        # back from the right and leaves to the left: two stretches, a crossing each
        straight = [(2, 0), (2, 10)]
        other = [(1, 2), (2, 2), (2, 4), (3, 4), (3, 6), (2, 6), (2, 8), (1, 8)]
        self.assertEqual(router.crossings([straight, other]), 2)

    def test_stretch_through_a_shared_corner(self):
        # both go up a gutter and turn along y=1 together, to the right or to the left; the line
        # that comes in from the side they turn to lies inside the corner, below the other one on
        # the second run. Turning left, "below" is on the other side of travel than "from the left".
        for outside, inside, end in (([(1, 5), (2, 5), (2, 1), (4, 1)], [(3, 5), (2, 5), (2, 1), (4, 1)], 4),
                                     ([(5, 5), (4, 5), (4, 1), (2, 1)], [(3, 5), (4, 5), (4, 1), (2, 1)], 2)):
            with self.subTest(turn="right" if end == 4 else "left"):
                # inside leaves downwards, outside upwards: the order holds
                self.assertEqual(router.crossings([outside + [(end, 0)], inside + [(end, 2)]]), 0)
                # inside leaves upwards, outside downwards: they swap, though neither run swaps alone
                self.assertEqual(router.crossings([outside + [(end, 2)], inside + [(end, 0)]]), 1)

    def test_one_route_between_the_same_nodes(self):
        route = [(5, 5), (4, 5), (4, 3), (1, 3)]
        self.assertEqual(router.crossings([route, route, route[::-1]]), 0)

    def test_shared_stretch_beside_a_crossing(self):
        # the swap in the gutter, and a third line straight across both lines there: three
        across = [(0, 2), (4, 2)]
        self.assertEqual(router.crossings(SWAP_PATHS + [across]), 3)


if __name__ == "__main__":
    unittest.main()
