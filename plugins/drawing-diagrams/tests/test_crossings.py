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


def sides_along(p, q, off_p, off_q):
    """Per unit step of p that q takes too (either way), the side of q's drawn line against p's,
    relative to p's direction of travel: 1 or -1, 0 where their offsets are equal."""
    def steps(path, off):
        out = {}
        for k, (a, b) in enumerate(zip(path, path[1:])):
            dx, dy = router._sign(b[0] - a[0]), router._sign(b[1] - a[1])
            pt = a
            while pt != b:
                nxt = (pt[0] + dx, pt[1] + dy)
                out[pt, nxt] = off[k]
                pt = nxt
        return out
    sp, sq = steps(p, off_p), steps(q, off_q)
    sides = []
    for (a, b), (ox, oy) in sp.items():
        other = sq.get((a, b), sq.get((b, a)))
        if other is None:
            continue
        tx, ty = b[0] - a[0], b[1] - a[1]
        sides.append(router._sign(tx * (other[1] - oy)) if ty == 0 else router._sign(-ty * (other[0] - ox)))
    return sides


CORNER_NODES = frozenset({(1, 1), (3, 1), (1, 3), (3, 3)})
# grid ["a b", "c d"], d -> a and a -> d: they share (1,1)-(2,1)-(2,2) and turn together at (2,1)
CORNER_PATHS = [[(3, 3), (2, 3), (2, 1), (1, 1)], [(1, 1), (2, 1), (2, 2), (3, 2), (3, 3)]]


class CornerOrder(unittest.TestCase):
    """assign_offsets keeps two lines in one order along all of a stretch they share, through the
    corners they turn together: the line inside a shared corner on one lattice line stays inside on
    the next."""

    def assert_one_order(self, paths, nodes=frozenset()):
        offs = router.assign_offsets(paths, nodes=nodes)
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                with self.subTest(pair=(i, j)):
                    sides = sides_along(paths[i], paths[j], offs[i], offs[j])
                    # the case exists only if the two lines share a stretch
                    self.assertTrue(sides, "harness: the lines share no step")
                    self.assertEqual(len(set(sides)), 1, f"{paths[i]} and {paths[j]} change order: {sides}")
                    self.assertNotIn(0, sides)
        return offs

    def test_two_lines_through_one_corner(self):
        offs = self.assert_one_order(CORNER_PATHS, CORNER_NODES)
        # they part at (2,2): a -> d turns right there, d -> a goes on down, so a -> d lies to the
        # right on the gutter between the columns, and outside the corner, above, along y=1
        self.assertGreater(offs[1][2][0], offs[0][2][0])
        self.assertLess(offs[1][1][1], offs[0][3][1])

    def test_one_route_between_the_same_nodes(self):
        # nothing parts them: any order, as long as it holds around both corners
        route = [(5, 5), (4, 5), (4, 3), (1, 3)]
        self.assert_one_order([route, route, route[::-1]], frozenset({(5, 5), (1, 3)}))

    def test_order_from_the_far_end_of_two_corners(self):
        # both come out of (1,1) to the right, turn down at (4,1), right again at (4,5) and part at
        # (6,5): the one going on to the right keeps the outer side of the first corner
        p = [(1, 1), (4, 1), (4, 5), (7, 5)]
        q = [(1, 1), (4, 1), (4, 5), (6, 5), (6, 7)]
        self.assert_one_order([p, q], frozenset({(1, 1), (7, 5)}))
        self.assert_one_order([q, p], frozenset({(1, 1), (7, 5)}))

    def test_swap_through_a_corner_keeps_the_order_it_enters_in(self):
        # up a gutter and along y=1 together, entering and leaving in swapped order: one crossing,
        # where they leave, so one order along both lattice lines
        outside = [(1, 5), (2, 5), (2, 1), (4, 1), (4, 2)]
        inside = [(3, 5), (2, 5), (2, 1), (4, 1), (4, 0)]
        self.assertEqual(router.crossings([outside, inside]), 1, "harness: the stretch has no swap")
        self.assert_one_order([outside, inside])

    def test_a_swap_gives_way_to_an_order_without_one(self):
        # grid ["e b", ". c", "d a"] as routed: along the gutter x=2 the swaps of a -> e with the
        # others, taken as orders, would close a cycle with the orders of b -> d and d -> c
        paths = [[(3, 1), (1, 1)], [(3, 1), (2, 1), (2, 4), (1, 4), (1, 5)], [(1, 5), (2, 5), (2, 3), (3, 3)],
                 [(1, 5), (1, 6), (4, 6), (4, 3), (3, 3)], [(1, 5), (2, 5), (2, 4), (3, 4), (3, 3)],
                 [(3, 5), (2, 5), (2, 3), (0, 3), (0, 1), (1, 1)], [(3, 1), (2, 1), (2, 5), (1, 5)],
                 [(3, 1), (4, 1), (4, 5), (3, 5)], [(3, 5), (2, 5), (2, 2), (1, 2), (1, 1)]]
        offs = router.assign_offsets(paths, nodes=frozenset({(1, 1), (3, 1), (3, 3), (1, 5), (3, 5)}))
        checked = 0
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                sides = sides_along(paths[i], paths[j], offs[i], offs[j])
                if not sides or router.shared_swaps(paths[i], paths[j]):
                    continue
                checked += 1
                with self.subTest(pair=(i, j)):
                    self.assertEqual(len(set(sides)), 1, f"{paths[i]} and {paths[j]} change order: {sides}")
        # the case exists only if pairs without a swap share the gutter with the swapping ones
        self.assertGreaterEqual(checked, 5, "harness: too few pairs share a stretch without a swap")


if __name__ == "__main__":
    unittest.main()
