"""A gutter has room, a group of lines closes up to fit it, and what does not fit is refused.

The unit is the group of `assign_offsets` — the runs on one lattice line that overlap or meet end
to end in a gutter — because a group of `w` runs is drawn `w` slots wide wherever it reaches. Its
outermost line lies (w - 1) * pitch / 2 from the lattice line, and the room is what `Geometry.room`
states on each side of that line, the clearances already taken off.

The room of the inner gutters and of the side margins follows from the mode tables; the room of the
top and bottom margins is measured in the browser (tests/test_browser_lines.py) and written into
diagrams/flow.py, and the table below is the hand-computed copy that a change of a mode table has
to move too.

The two halves of the capacity rule are below the room: the price `route` puts on a step along a
line that already carries as many lines as it holds (spec 4.3), which makes overflow rare, and the
layout error `flow.plan` writes when a group overflows anyway (spec 4.4), which is the guarantee.
"""
import json
import unittest

import support  # noqa: F401
import bench_routing
from diagrams import flow, router

# The five lines come into the column gutter X = 2 from five card rows on the left and leave it at
# the bottom row on the right: five runs on one line, overlapping, so one group five slots wide.
FIVE = [[(1, y), (2, y), (2, 11), (3, 11)] for y in (1, 3, 5, 7, 9)]
FIVE_NODES = frozenset({(1, y) for y in (1, 3, 5, 7, 9)} | {(3, 11)})

# Four lines that share no stretch at all: each runs down its own piece of the gutter X = 2 and
# hands over to the next at a gutter point. Spec 4.1 counts such a chain as wide as it is drawn.
CHAIN = [[(1, 1), (2, 1), (2, 3), (3, 3)],
         [(3, 3), (2, 3), (2, 5), (1, 5)],
         [(1, 5), (2, 5), (2, 7), (3, 7)],
         [(3, 7), (2, 7), (2, 9), (1, 9)]]
CHAIN_NODES = frozenset({(1, 1), (3, 3), (1, 5), (3, 7), (1, 9)})

# Five cards down column 1 of a two-column, five-row grid, column 0 empty: the lattice the price of
# a full gutter is measured on (FullGutterCost). A line from one of those cards to another cannot
# go straight down — the cells between them are cards — so it travels in the column gutter X = 2
# (cost 10), along the right margin X = 4 (15) or through the empty cells of column 0 (15).
COLUMN_FULL = {f"n{r}": (r, 1) for r in range(5)}
N1_N3 = (router.Lattice.point(1, 1), router.Lattice.point(3, 1))
GUTTER_ROUTE = [(3, 3), (2, 3), (2, 7), (3, 7)]    # n1 -> n3, down the column gutter X = 2
# n0 -> n4 down the whole of the gutter and of the margin: the traffic a second line meets. With
# both of them in place the gutter costs 24 and the margin 29, so the gutter is still where a line
# goes — and a step of it priced as full costs +20, which is what has to move it.
FULL_GUTTER = [(3, 1), (2, 1), (2, 9), (3, 9)]
FULL_MARGIN = [(3, 1), (4, 1), (4, 9), (3, 9)]

# Hand-computed room per kind and mode, in the order (inner column gutter, inner row gutter, left
# margin, right margin, top margin, bottom margin without footnotes, bottom margin with them), each
# pair (lower coordinate, higher coordinate). A gutter keeps LINE_CLEAR from the cards on both
# sides: gap / 2 - 4 across, row_gap / 2 - 4 down. A side margin keeps LINE_CLEAR towards the cards
# (margin - 4, margin being max(8, pad - 6)) and EDGE_CLEAR towards the grid box (pad - margin - 1).
# The outer row margins are the measured ones, less the same two clearances; below the grid box the
# measurement is of the first content after it, which is the .dg-foot list when the model has
# footnotes and the legend's text when it has none, so the bottom margin has two rooms.
ROOMS = {
    ("flow", "widget"): ((10, 10), (16, 16), (5, 8), (8, 5), (-5, 8), (8, 7), (8, 3)),
    ("flow", "page"): ((12, 12), (18, 18), (5, 14), (14, 5), (-11, 14), (14, 1), (14, -3)),
    ("state", "widget"): ((10, 10), (16, 16), (5, 8), (8, 5), (-5, 8), (8, 7), (8, 3)),
    ("state", "page"): ((12, 12), (18, 18), (5, 14), (14, 5), (-11, 14), (14, 1), (14, -3)),
    ("blocks", "widget"): ((10, 10), (16, 16), (5, 8), (8, 5), (-5, 8), (8, 7), (8, 3)),
    ("blocks", "page"): ((12, 12), (18, 18), (5, 14), (14, 5), (-11, 14), (14, 1), (14, -3)),
    ("swimlane", "widget"): ((5, 5), (16, 16), (5, 8), (8, 5), (27, 8), (8, 7), (8, 3)),
    ("swimlane", "page"): ((10, 10), (18, 18), (5, 14), (14, 5), (25, 14), (14, 1), (14, -3)),
}

# How many lines each of those bottom margins holds at the smallest pitch — the number task 9's
# message will print when a group does not fit there.
BOTTOM_CAPACITY = {("widget", False): 3, ("widget", True): 2, ("page", False): 1, ("page", True): 0}


def room_of(pair):
    """A room callable that gives every even lattice line the same pair, and, as `Geometry.room`
    does, no room at all for an odd one, which runs through the cards."""
    return lambda axis, line: None if line % 2 else pair


def spread(paths, offsets, axis, line):
    """The distinct offsets across `line` that the runs drawn on it take, sorted: the picture of
    how wide the group stands and at what pitch."""
    out = set()
    for p, off in zip(paths, offsets):
        for (x, y), (ox, oy) in zip(p, off):
            if axis == "v" and x == line:
                out.add(ox)
            elif axis == "h" and y == line:
                out.add(oy)
    return sorted(out)


def widest(pitch, room):
    """The most runs that fit on a line with this room at this pitch."""
    w = 0
    while router.fits(w + 1, pitch, room):
        w += 1
    return w


def only(axis, line, cap):
    """A capacity callable that states one lattice line's capacity and leaves every other unstated,
    as `Geometry.room` leaves the lines it knows nothing about."""
    return lambda a, l: cap if (a, l) == (axis, line) else None


def group_on(axis, line, count):
    """`count` paths that each run the same stretch of one lattice line and turn off it at both
    ends: one group `count` runs wide, whatever else stands on the lattice. The arm at each end
    points into the neighbouring cell, or, on the left or top margin, the only way there is."""
    side = line + 1 if line == 0 else line - 1
    if axis == "v":
        return [[(side, 1), (line, 1), (line, 5), (side, 5)] for _ in range(count)]
    return [[(1, side), (1, line), (5, line), (5, side)] for _ in range(count)]


class Fits(unittest.TestCase):
    """How many lines a room holds, per pitch."""

    def test_the_lines_that_fit_at_each_pitch(self):
        # (10, 10) is an inner column gutter at gap 28, (5, 5) one at gap 18, (8, 5) a widget side
        # margin — the three rooms the mode tables actually produce
        for room, want in (((10, 10), (3, 4, 5)), ((5, 5), (2, 2, 3)), ((8, 5), (2, 2, 3))):
            with self.subTest(room=room):
                self.assertEqual(tuple(widest(p, room) for p in router.PITCHES), want)

    def test_capacity_is_the_width_at_the_smallest_pitch(self):
        for room in ((10, 10), (5, 5), (8, 5), (12, 12), (16, 16), (25, 14), (8, 7), (8, 3), (14, 1), (0, 0)):
            with self.subTest(room=room):
                self.assertEqual(router.capacity(room), widest(router.PITCHES[-1], room))

    def test_a_line_already_past_its_bound_holds_nothing(self):
        # a flow's top margin, where the line itself is above the grid box and so under the title
        # or past the edge the section clips at, and its bottom margin in a page with footnotes,
        # where the line is already inside the .dg-foot list: not even one line fits
        for room in ((-5, 8), (-11, 14), (14, -3)):
            with self.subTest(room=room):
                self.assertEqual(router.capacity(room), 0)
                self.assertFalse(router.fits(1, router.PITCHES[-1], room))


class GeometryRoom(unittest.TestCase):
    """What `Geometry.room` states for every kind and mode the renderer has."""

    def test_the_table_covers_every_mode(self):
        self.assertEqual(set(ROOMS), {(kind, name) for kind, modes in flow.MODES.items() for name in modes})

    def test_every_mode_against_the_hand_computed_pairs(self):
        for (kind, name), (column, row, left, right, top, bare, footed) in sorted(ROOMS.items()):
            for footnotes, bottom in ((False, bare), (True, footed)):
                with self.subTest(kind=kind, mode=name, footnotes=footnotes):
                    mode = flow.mode_for(kind, name, None)
                    geo = flow.Geometry(mode, 100.0, 3, 2, *flow.margin_room(kind, name, footnotes))
                    self.assertEqual(geo.room("v", 2), column)
                    self.assertEqual(geo.room("h", 2), row)
                    self.assertEqual(geo.room("v", 0), left)
                    self.assertEqual(geo.room("v", 6), right)
                    self.assertEqual(geo.room("h", 0), top)
                    self.assertEqual(geo.room("h", 4), bottom)

    def test_the_bottom_margin_holds_what_the_room_leaves(self):
        # the numbers the capacity message of task 9 will print for a full bottom margin
        for (kind, name), rooms in sorted(ROOMS.items()):
            for footnotes, bottom in ((False, rooms[5]), (True, rooms[6])):
                with self.subTest(kind=kind, mode=name, footnotes=footnotes):
                    self.assertEqual(router.capacity(bottom), BOTTOM_CAPACITY[name, footnotes])

    def test_a_line_through_the_cards_states_no_room(self):
        # an odd line runs along a row or a column of cards, where template/js/flow.js places a
        # line against card heights this side knows nothing about
        geo = flow.Geometry(flow.mode_for("flow", "widget", None), 100.0, 3, 2,
                            *flow.margin_room("flow", "widget", False))
        self.assertIsNone(geo.room("v", 1))
        self.assertIsNone(geo.room("h", 3))

    def test_a_geometry_without_the_measurement_states_no_outer_room(self):
        geo = flow.Geometry(flow.mode_for("flow", "widget", None), 100.0, 3, 2)
        self.assertIsNone(geo.room("h", 0))
        self.assertIsNone(geo.room("h", 4))
        self.assertEqual(geo.room("h", 2), (16, 16))


class AdaptivePitch(unittest.TestCase):
    """A group takes the widest pitch its line has room for, and `overfull` names the rest."""

    def test_five_runs_in_one_gutter_close_up_to_six(self):
        offs = router.assign_offsets(FIVE, nodes=FIVE_NODES, room=room_of((12, 12)))  # gap 32
        self.assertEqual(spread(FIVE, offs, "v", 2), [-12.0, -6.0, 0.0, 6.0, 12.0])

    def test_three_runs_keep_the_widest_pitch(self):
        three = FIVE[:3]
        offs = router.assign_offsets(three, nodes=FIVE_NODES, room=room_of((10, 10)))  # gap 28
        self.assertEqual(spread(three, offs, "v", 2), [-8.0, 0.0, 8.0])

    def test_five_runs_do_not_fit_a_narrow_gutter(self):
        self.assertEqual(router.overfull(FIVE, FIVE_NODES, room_of((5, 5))),  # gap 18
                         [("v", 2, [0, 1, 2, 3, 4], 3)])

    def test_a_chain_that_only_meets_end_to_end_is_one_group(self):
        self.assertEqual(router.overfull(CHAIN, CHAIN_NODES, room_of((5, 5))),
                         [("v", 2, [0, 1, 2, 3], 3)])

    def test_a_group_that_fits_is_not_overfull(self):
        self.assertEqual(router.overfull(FIVE, FIVE_NODES, room_of((12, 12))), [])
        self.assertEqual(router.overfull(FIVE[:3], FIVE_NODES, room_of((10, 10))), [])

    def test_the_width_priced_is_the_width_drawn(self):
        # the two read their groups from one place: a message naming more lines than the picture
        # shows, or fewer, would send the author after the wrong gutter
        for paths, nodes in ((FIVE, FIVE_NODES), (CHAIN, CHAIN_NODES)):
            with self.subTest(lines=len(paths)):
                (axis, line, idx, _), = router.overfull(paths, nodes, room_of((5, 5)))
                offs = router.assign_offsets(paths, nodes=nodes, room=room_of((5, 5)))
                self.assertEqual(len(set(spread(paths, offs, axis, line))), len(idx))

    def test_a_group_over_capacity_is_drawn_at_the_smallest_pitch(self):
        offs = router.assign_offsets(FIVE, nodes=FIVE_NODES, room=room_of((5, 5)))
        self.assertEqual(spread(FIVE, offs, "v", 2), [-10.0, -5.0, 0.0, 5.0, 10.0])

    def test_an_even_group_at_the_smallest_pitch_lands_on_half_pixels(self):
        offs = router.assign_offsets(CHAIN, nodes=CHAIN_NODES, room=room_of((5, 5)))
        self.assertEqual(spread(CHAIN, offs, "v", 2), [-7.5, -2.5, 2.5, 7.5])

    def test_without_room_the_offsets_are_todays(self):
        for paths, nodes in ((FIVE, FIVE_NODES), (CHAIN, CHAIN_NODES)):
            with self.subTest(lines=len(paths)):
                today = router.assign_offsets(paths, nodes=nodes)
                self.assertEqual(router.assign_offsets(paths, nodes=nodes, room=lambda a, l: None), today)
                self.assertEqual(spread(paths, today, "v", 2)[1] - spread(paths, today, "v", 2)[0], 8.0)

    def test_a_line_with_no_room_stated_holds_any_group(self):
        self.assertEqual(router.overfull(FIVE, FIVE_NODES, lambda axis, line: None), [])


class FullGutterCost(unittest.TestCase):
    """Spec 4.3, criterion B4: a step along a unit edge of an even line whose load is already that
    line's capacity costs +20, more than a crossing, so a line takes any cheaper detour instead.

    The detour here is the right margin: 5 dearer than the gutter whether the two channels are
    empty (10 against 15) or already hold a line each (24 against 29), a quarter of what one step
    on a full line costs. So the price, and nothing else in `route`, is what moves the line."""

    def lattice(self, capacity=None):
        return router.Lattice(2, 5, COLUMN_FULL, capacity=capacity)

    def loaded(self):
        """A traffic holding one line down the whole gutter and one down the whole margin: the
        state a second line meets when every channel beside the cards already carries a line."""
        traffic = router.Traffic()
        traffic.add(FULL_GUTTER)
        traffic.add(FULL_MARGIN)
        return traffic

    def assertOffTheGutter(self, path):
        self.assertNotIn(("v", 2), [(axis, line) for axis, line, _, _ in router.segments(path)],
                         f"the line still runs along the gutter: {path}")

    def test_the_gutter_is_the_cheapest_way_down(self):
        # the case exists only if an unpriced gutter is where the line goes
        self.assertEqual(router.route(self.lattice(), *N1_N3), GUTTER_ROUTE)

    def test_a_line_avoids_a_gutter_that_holds_nothing(self):
        # capacity 0 — a flow's top margin is one — prices every step along the line with no
        # traffic at all: the load is 0 and 0 is already the capacity
        self.assertOffTheGutter(router.route(self.lattice(only("v", 2, 0)), *N1_N3))

    def test_a_line_avoids_a_gutter_already_at_its_capacity(self):
        self.assertOffTheGutter(router.route(self.lattice(only("v", 2, 1)), *N1_N3, traffic=self.loaded()))

    def test_the_same_traffic_without_a_capacity_keeps_the_gutter(self):
        # what the line does with the load and without the price: the traffic alone leaves the
        # gutter the cheapest way down, so the test above measures the price and not the traffic
        self.assertEqual(router.route(self.lattice(), *N1_N3, traffic=self.loaded()), GUTTER_ROUTE)

    def test_a_gutter_below_its_capacity_is_not_priced(self):
        self.assertEqual(router.route(self.lattice(only("v", 2, 2)), *N1_N3, traffic=self.loaded()),
                         GUTTER_ROUTE)

    def test_a_lattice_built_without_a_capacity_routes_as_it_did(self):
        # tests/reference.py, tools/bench_routing.py and tests/test_traffic.py build one this way
        self.assertEqual(router.route(router.Lattice(2, 5, COLUMN_FULL), *N1_N3, traffic=self.loaded()),
                         GUTTER_ROUTE)


class CapacityMessage(unittest.TestCase):
    """Spec 4.4, criterion B2: the layout error a group over its line's capacity becomes. It names
    the line the way the rest of the renderer names a column or a row, how many lines are drawn
    there against how many fit, the edges the author can move, and what to do."""

    def error(self, axis, line, count, cols=3, rows=3, room=(5, 5)):
        paths = group_on(axis, line, count)
        edges = [{"a": f"n{k}", "b": f"m{k}"} for k in range(count)]
        (group,) = router.overfull(paths, frozenset(), room_of(room))
        return flow.overfull_error(group, edges, cols, rows)

    def test_a_column_gutter(self):
        self.assertEqual(self.error("v", 2, 5),
                         "между столбцами 0 и 1 линий 5, помещается 3: n0 -> m0, n1 -> m1, n2 -> m2, "
                         "n3 -> m3, …; освободите ячейку рядом или переставьте узлы")

    def test_a_row_gutter(self):
        self.assertEqual(self.error("h", 2, 4),
                         "между рядами 0 и 1 линий 4, помещается 3: n0 -> m0, n1 -> m1, n2 -> m2, "
                         "n3 -> m3; освободите ячейку рядом или переставьте узлы")

    def test_the_left_margin(self):
        self.assertEqual(self.error("v", 0, 4),
                         "по левому полю линий 4, помещается 3: n0 -> m0, n1 -> m1, n2 -> m2, "
                         "n3 -> m3; освободите ячейку рядом или переставьте узлы")

    def test_the_right_margin(self):
        self.assertEqual(self.error("v", 6, 4),
                         "по правому полю линий 4, помещается 3: n0 -> m0, n1 -> m1, n2 -> m2, "
                         "n3 -> m3; освободите ячейку рядом или переставьте узлы")

    def test_the_top_margin_of_a_flow_holds_no_line_at_all(self):
        # room (-5, 8) is a flow's top margin in a widget: the lattice line itself lies past the
        # bound, so freeing a cell beside it would not help and the advice says something else
        self.assertEqual(self.error("h", 0, 1, room=(-5, 8)),
                         "по верхнему полю линий 1, помещается 0: n0 -> m0; линии здесь не проходят, "
                         "переставьте узлы так, чтобы связи шли ниже или между рядами")

    def test_the_bottom_margin_of_a_page_with_footnotes_holds_no_line_at_all(self):
        # room (14, -3): the footnote list stands where the line would be drawn
        self.assertEqual(self.error("h", 6, 1, room=(14, -3)),
                         "по нижнему полю линий 1, помещается 0: n0 -> m0; линии здесь не проходят, "
                         "переставьте узлы так, чтобы связи шли выше или между рядами")

    def test_a_side_margin_that_holds_no_line_at_all(self):
        # no mode table gives a side margin as little room as that, and the message has to make
        # sense if one ever does: there is no row to send the lines to, only a column gutter
        self.assertEqual(self.error("v", 0, 1, room=(-5, 8)),
                         "по левому полю линий 1, помещается 0: n0 -> m0; линии здесь не проходят, "
                         "переставьте узлы так, чтобы связи шли между столбцами")

    def test_at_most_four_edges_are_named(self):
        self.assertIn("n0 -> m0, n1 -> m1, n2 -> m2, n3 -> m3, …;", self.error("v", 2, 7))

    def test_an_edge_with_two_runs_in_the_group_is_named_once(self):
        # the count is the width of the group — what has to fit — and the list is who to move, so
        # a line that comes into the gutter twice is two of the lines and one of the names
        paths = [[(1, 1), (2, 1), (2, 3), (3, 3), (3, 5), (2, 5), (2, 7), (1, 7)],
                 [(1, 1), (2, 1), (2, 7), (1, 7)]]
        (group,) = router.overfull(paths, frozenset(), room_of((2, 2)))
        self.assertEqual(flow.overfull_error(group, [{"a": "a", "b": "b"}, {"a": "c", "b": "d"}], 3, 3),
                         "между столбцами 0 и 1 линий 3, помещается 1: a -> b, c -> d; "
                         "освободите ячейку рядом или переставьте узлы")

    def test_the_shape_the_plan_matches(self):
        self.assertRegex(self.error("v", 2, 5), r"между столбцами \d+ и \d+ линий \d+, помещается \d+")

    def test_columns_and_rows_are_numbered_as_the_grid_errors_number_them(self):
        # `grid, ряд 0` and `grid: узел a стоит в двух ячейках [0, 1] ...` count from zero, and so
        # does the gutter between the first two columns
        self.assertTrue(self.error("v", 2, 4).startswith("между столбцами 0 и 1 "))
        self.assertTrue(self.error("h", 4, 4, rows=3).startswith("между рядами 1 и 2 "))


class ShippedExamples(unittest.TestCase):
    """Spec 4.2: every group of the shipped examples fits at the widest pitch, which is why the
    room reaching `assign_offsets` leaves their offsets, and so their rendered HTML, where they
    were."""

    def test_no_group_of_an_example_needs_a_narrower_pitch(self):
        found = bench_routing.examples()
        self.assertEqual({m["kind"] for _, m in found}, set(flow.MODES), "harness: a kind lost its example")
        for path, model in found:
            for mode in bench_routing.MODES:
                with self.subTest(example=path.name, mode=mode):
                    layout, _ = flow.plan(json.loads(json.dumps(model)), mode)
                    geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"],
                                        layout["grid_rows"],
                                        *flow.margin_room(layout["kind"], mode, layout["footnotes"]))
                    nodes = frozenset(layout["lattice"].blocked)
                    self.assertEqual(router.overfull(layout["paths"], nodes, geo.room), [])
                    self.assertEqual(router.assign_offsets(layout["paths"], nodes=nodes, room=geo.room),
                                     router.assign_offsets(layout["paths"], nodes=nodes))


class StressModels(unittest.TestCase):
    """The two models under tests/models/ that the owner reviews the line pitch on: real models
    inside their mode's limits that render without an error and hold a group at each of the two
    narrow pitches, which the shipped examples never reach."""

    MODELS = {"dense-widget-flow.json": "widget", "dense-page-swimlane.json": "page"}

    def steps_of(self, name, mode):
        """The px between neighbouring lines on each even lattice line of a rendered model, read
        back from the offsets the edge JSON carries — the pitch as the script will draw it."""
        model = json.loads((support.ROOT / "tests" / "models" / name).read_text())
        layout, _ = flow.plan(model, mode)
        lines = {}
        for e in layout["edges"]:
            for x, y, ox, oy in e["path"]:
                if x % 2 == 0:
                    lines.setdefault(("v", x), set()).add(ox)
                if y % 2 == 0:
                    lines.setdefault(("h", y), set()).add(oy)
        return {key: sorted(offs) for key, offs in lines.items()}

    def test_each_model_reaches_the_six_and_the_five(self):
        for name, mode in sorted(self.MODELS.items()):
            with self.subTest(model=name):
                steps = self.steps_of(name, mode)
                found = {round(b - a, 1) for offs in steps.values() for a, b in zip(offs, offs[1:])}
                self.assertLessEqual({6.0, 5.0}, found,
                                     f"{name} no longer holds a group at each narrow pitch: {steps}. "
                                     f"It is kept for that; pick another model rather than drop the check.")


if __name__ == "__main__":
    unittest.main()
