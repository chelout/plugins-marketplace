import unittest

import support
import bench_routing
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


# Defect A: path 1 has two runs on x = 7 with a detour between them. One slot per (line, path)
# gives both of them one offset, so they lie on the same line as path 0 and path 2 and the crossing
# that is counted is drawn as an overlap instead.
RUN_A_PATHS = [[(9, 1), (8, 1), (8, 4), (7, 4), (7, 5), (5, 5)],
               [(7, 3), (7, 5), (8, 5), (8, 8), (7, 8), (7, 9)],
               [(7, 3), (7, 5), (5, 5)]]
RUN_A_NODES = frozenset({(9, 1), (5, 5), (7, 3), (7, 9)})
# Defect C: the pair shares two stretches on x = 4, entering the first left of each other and the
# second right. One order per (line, pair) keeps only the second, so both runs of the first path
# take the side the second stretch asks for and the pair crosses twice where it is drawn.
RUN_C_PATHS = [[(3, 1), (4, 1), (4, 3), (2, 3), (2, 5), (6, 5), (6, 7), (4, 7), (4, 9), (5, 9)],
               [(5, 1), (4, 1), (4, 3), (6, 3), (6, 4), (0, 4), (0, 7), (4, 7), (4, 9), (3, 9)]]
RUN_C_NODES = frozenset({(3, 1), (5, 1), (3, 9), (5, 9)})


class RunKeys(unittest.TestCase):
    """A slot and a pair order belong to a run — a maximal straight piece of one path on one
    lattice line — and not to the whole path: a path with two runs on one line gets a slot for
    each, and a pair with two stretches on one line keeps the order of each."""

    def test_two_runs_of_one_path_on_one_line_get_a_slot_each(self):
        offs = router.assign_offsets(RUN_A_PATHS, nodes=RUN_A_NODES)
        # the case exists only if the count sees one crossing there
        self.assertEqual(router.crossings(RUN_A_PATHS), 1, "harness: nothing to draw")
        self.assertEqual(router.drawn_overlaps(RUN_A_PATHS, offs, RUN_A_NODES), 0)
        self.assertEqual(router.drawn_crossings(RUN_A_PATHS, offs, RUN_A_NODES), 1)

    def test_each_stretch_of_one_pair_keeps_its_own_order(self):
        offs = router.assign_offsets(RUN_C_PATHS, nodes=RUN_C_NODES)
        self.assertEqual(router.crossings(RUN_C_PATHS), 1, "harness: nothing to draw")
        self.assertEqual(router.drawn_crossings(RUN_C_PATHS, offs, RUN_C_NODES), 1)
        # x = 4 carries a run of each path twice: the first path enters the earlier stretch left of
        # the second and the later one right of it, so it lies left at y = 1 and right at y = 9
        self.assertLess(offs[0][1][0], offs[1][1][0])
        self.assertGreater(offs[0][8][0], offs[1][8][0])

    def test_collinear_points_are_one_run(self):
        # the middle point lies on the straight, so x = 1 carries one run and not two: alone on its
        # line it needs no offset, and both its segments keep the same one
        offs = router.assign_offsets([[(1, 1), (1, 3), (1, 5), (3, 5)]])
        self.assertEqual([ox for ox, _ in offs[0][:3]], [0.0, 0.0, 0.0])

    def test_a_zero_length_segment_is_a_run_of_its_own(self):
        # two equal consecutive points, which schema.plan produces: that segment is a run of its
        # own on the vertical line through it, and the collinear pieces on either side of it stay
        # one run, so a path alone on both its lines takes no offset anywhere
        path = [(1, 1005), (2, 1005), (2, 1005), (3, 1005)]
        runs, of_seg = router._runs(path)
        self.assertEqual([(d["axis"], d["line"], d["lo"], d["hi"]) for d in runs],
                         [("h", 1005, 1, 3), ("v", 2, 1005, 1005)])
        self.assertEqual(of_seg, [0, 1, 0])
        self.assertEqual(router.assign_offsets([path])[0], [(0.0, 0.0)] * 4)


# Defect B: on y = 4 two runs meet end to end at (2, 4) and two more at (4, 4), in a gutter and
# with their arms pointing opposite ways. Neither pair shares a stretch, so no order holds them
# apart, and each pair that takes the wrong slot crosses twice where nothing is counted.
END_TO_END_PATHS = [[(1, 3), (1, 4), (2, 4), (2, 6), (6, 6), (6, 9), (7, 9)],
                    [(7, 5), (4, 5), (4, 4), (2, 4), (2, 3), (1, 3)],
                    [(1, 7), (2, 7), (2, 3), (3, 3)],
                    [(5, 3), (4, 3), (4, 4), (0, 4), (0, 11), (1, 11)]]
END_TO_END_NODES = frozenset({(1, 3), (7, 9), (7, 5), (1, 7), (3, 3), (5, 3), (1, 11)})


# On y = 4 the stretch path 0 shares with path 1 and the one path 1 shares with path 2 order the
# three runs 0, 1, 2 from the top. The runs of path 2 and path 0 meet end to end at (3, 4), where
# path 2's arm points up and path 0's down, so the end-to-end rule asks for path 2 above path 0 and
# closes a cycle with the two stretches. Being the weakest, it is the order that gives way.
CYCLE_PATHS = [[(5, 1), (4, 1), (4, 4), (3, 4), (3, 5)],
               [(1, 7), (2, 7), (2, 4), (4, 4), (4, 3), (5, 3)],
               [(3, 7), (2, 7), (2, 4), (3, 4), (3, 3)]]
CYCLE_NODES = frozenset({(5, 1), (3, 5), (1, 7), (5, 3), (3, 7), (3, 3)})


class EndToEnd(unittest.TestCase):
    """Two runs of one group that meet end to end at a gutter point with their arms pointing to
    opposite sides take the slots their arms point to: the weakest of the three strengths of
    order, recorded only where a shared stretch has said nothing, and dropped where it closes a
    cycle with the orders of the stretches."""

    def test_the_four_paths_draw_the_crossings_they_count(self):
        offs = router.assign_offsets(END_TO_END_PATHS, nodes=END_TO_END_NODES)
        # the case exists only if the count sees five crossings there
        self.assertEqual(router.crossings(END_TO_END_PATHS), 5, "harness: nothing to draw")
        self.assertEqual(router.drawn_crossings(END_TO_END_PATHS, offs, END_TO_END_NODES), 5)
        self.assertEqual(router.drawn_overlaps(END_TO_END_PATHS, offs, END_TO_END_NODES), 0)

    def test_it_gives_way_to_the_orders_it_closes_a_cycle_with(self):
        # the case exists only if both orders on y = 4 come from a stretch with a swap — the
        # weakest is dropped for them, not for a firmer kind — and the pair whose runs meet end to
        # end shares no stretch, so nothing but the end-to-end rule speaks about it
        for i, j in ((0, 1), (1, 2)):
            with self.subTest(pair=(i, j)):
                self.assertEqual(router.shared_swaps(CYCLE_PATHS[i], CYCLE_PATHS[j]), 1,
                                 "harness: the pair shares no stretch with a swap")
        self.assertEqual(list(router.stretches(CYCLE_PATHS[0], CYCLE_PATHS[2])), [],
                         "harness: the ends of the cycle share a stretch")
        offs = router.assign_offsets(CYCLE_PATHS, nodes=CYCLE_NODES)
        # the run on y = 4 is the third segment of each path, so its oy sits on points 2 and 3
        for m in (2, 3):
            with self.subTest(point=m):
                self.assertLess(offs[0][m][1], offs[1][m][1])
                self.assertLess(offs[1][m][1], offs[2][m][1])


def plan_with_drawn_crossings(model, mode, n):
    """What flow.plan takes from router.drawn_crossings, per call: the counter is swapped for a spy
    that returns `n`, so the layout and the warning are read from this seam alone and not from a
    count taken again behind it."""
    seen = []
    real = router.drawn_crossings

    def spy(paths, offsets, nodes):
        seen.append((paths, offsets, nodes))
        return n

    router.drawn_crossings = spy
    try:
        layout, warnings = flow.plan(model, mode)
    finally:
        router.drawn_crossings = real
    return layout, warnings, seen


class PlanReportsWhatIsDrawn(unittest.TestCase):
    """What flow.plan counts is what the reader sees: the crossings of the lines with the offsets
    the edges carry into the script, not of the lattice paths behind them."""

    def test_the_count_and_the_warning_come_from_drawn_crossings(self):
        # a number no count of these two lines could reach, and above the threshold of the warning
        layout, warnings, seen = plan_with_drawn_crossings(SWAP, "page", 97)
        self.assertEqual(len(seen), 1, "flow.plan counts a layout once")
        self.assertEqual(seen[0][0], layout["paths"])
        self.assertEqual(seen[0][2], frozenset(layout["lattice"].blocked))
        self.assertEqual(layout["crossings"], 97)
        self.assertIn("пересечений линий: 97", " ".join(warnings))

    def test_every_flow_like_example_reports_the_crossings_it_draws(self):
        found = bench_routing.examples()
        self.assertEqual({m["kind"] for _, m in found}, set(flow.MODES), "harness: a kind lost its example")
        for path, model in found:
            for mode in bench_routing.MODES:
                with self.subTest(example=path.name, mode=mode):
                    layout, _ = flow.plan(model, mode)
                    offs = [[(ox, oy) for _, _, ox, oy in e["path"]] for e in layout["edges"]]
                    nodes = frozenset(layout["lattice"].blocked)
                    self.assertEqual(layout["crossings"],
                                     router.drawn_crossings(layout["paths"], offs, nodes))


if __name__ == "__main__":
    unittest.main()
