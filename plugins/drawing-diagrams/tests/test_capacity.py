"""A gutter has room, a group of lines closes up to fit it, and what does not fit is refused.

The unit is the group of `assign_offsets` — the runs on one lattice line that overlap or meet end
to end in a gutter — because a group of `w` runs is drawn `w` slots wide wherever it reaches. Its
outermost line lies (w - 1) * pitch / 2 from the lattice line, and the room is what `Geometry.room`
states on each side of that line, the clearances already taken off.

The room of the inner gutters and of the side margins follows from the mode tables; the room of the
top and bottom margins is measured in the browser (tests/test_browser_lines.py) and written into
diagrams/flow.py, and the table below is the hand-computed copy that a change of a mode table has
to move too.

An empty row of the drawn extent has no cards for a gutter beside it to keep clear of, and the lines
of the band around it do not stand a row gap apart: `tracks()` of template/js/head.js invents a
track for such a row, and `by()` places the lines from it. Where those lines land is measured in the
browser too (case 17 there), and EMPTY_BAND below is the hand-computed copy.

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

# The band around a run of empty rows, hand-computed from the browser measurement (case 17 of
# tests/test_browser_lines.py). `tracks()` of template/js/head.js invents one track per empty row of
# the drawn extent and fills them in ascending order, so each sees the tracks already invented above
# it: the first row of a leading run lands flow.TRACK_LEAD px above the first cards and every row
# after it halves what is left, and a run between two occupied rows halves the span between their
# card edges the same way. That span is (k + 1) row gaps for k empty rows, because an empty implicit
# grid row is 0 px high and both of its row gaps stay. `by()` of template/js/flow.js then puts a
# gutter halfway between two tracks and the top margin `Geometry.margin` px above the first one.
#
# Per shape: (rows of the drawn extent, the empty ones among them, {mode: {lattice row line: room}}),
# each room the pair (towards the lower coordinate, towards the higher). Towards a card edge the room
# is the distance to it less LINE_CLEAR, towards another lattice line half the distance to it — two
# groups share the space between their lines — and the away-from-the-cards side of the top margin
# stays the measured TOP_ROOM of the kind (TOPWARD below), which a leading empty row only pushes the
# line further from.
TOPWARD = "TOP_ROOM"
EMPTY_BAND = {
    "one leading": (2, (0,), {
        "widget": {0: (TOPWARD, 6.0), 1: (6.0, 5.0), 2: (5.0, 6.0)},
        "page": {0: (TOPWARD, 9.0), 1: (9.0, 5.0), 2: (5.0, 6.0)}}),
    "two leading": (3, (0, 1), {
        "widget": {0: (TOPWARD, 6.0), 1: (6.0, 2.5), 2: (2.5, 2.5), 3: (2.5, 2.5), 4: (2.5, 1.0)},
        "page": {0: (TOPWARD, 9.0), 1: (9.0, 2.5), 2: (2.5, 2.5), 3: (2.5, 2.5), 4: (2.5, 1.0)}}),
    "three leading": (4, (0, 1, 2), {
        "widget": {0: (TOPWARD, 6.0), 1: (6.0, 2.5), 2: (2.5, 2.5), 3: (2.5, 1.25),
                   4: (1.25, 1.25), 5: (1.25, 1.25), 6: (1.25, -1.5)},
        "page": {0: (TOPWARD, 9.0), 1: (9.0, 2.5), 2: (2.5, 2.5), 3: (2.5, 1.25),
                 4: (1.25, 1.25), 5: (1.25, 1.25), 6: (1.25, -1.5)}}),
    "one interior": (3, (1,), {
        "widget": {2: (16.0, 10.0), 3: (10.0, 10.0), 4: (10.0, 16.0)},
        "page": {2: (18.0, 11.0), 3: (11.0, 11.0), 4: (11.0, 18.0)}}),
    "two interior": (4, (1, 2), {
        "widget": {2: (26.0, 15.0), 3: (15.0, 7.5), 4: (7.5, 7.5), 5: (7.5, 7.5), 6: (7.5, 11.0)},
        "page": {2: (29.0, 16.5), 3: (16.5, 8.25), 4: (8.25, 8.25), 5: (8.25, 8.25),
                 6: (8.25, 12.5)}}),
}

# The model the branch gate reported, and the px the browser showed between the gutter above the
# first cards and their top edge when the row above them is empty: the leading row's track lies
# flow.TRACK_LEAD px over the cards and by() puts the gutter halfway between, so that gutter is
# nowhere near row_gap / 2 from them.
GATE = {"kind": "flow", "nodes": [{"id": i, "title": i.upper()} for i in "abc"],
        "grid": [". . .", "a b c"], "edges": ["a -> c"] * 6}
OVER_THE_CARDS = 10.0

# Three cards in the second row of a two-row grid, the first row empty: a line from the first card to
# the last can run along the gutter above them (lattice row line Y = 2), along the cells of the empty
# row (Y = 1) or under the bottom margin (Y = 4). The gutter is the cheapest and the empty row the
# dearest — its cells cost a line +1 each — so the empty row is where a line goes only once the
# other two are full, which is what the price on an odd line has to be measured against.
EMPTY_ROW_CELLS = {"a": (1, 0), "b": (1, 1), "c": (1, 2)}
A_TO_C = (router.Lattice.point(1, 0), router.Lattice.point(1, 2))


def room_of(pair):
    """A room callable that gives every even lattice line the same pair, and, as `Geometry.room`
    does, no room at all for an odd one, which runs through the cards."""
    return lambda axis, line: None if line % 2 else pair


def room_at(axis, line, pair):
    """A room callable that states one lattice line's room and leaves every other unstated, so that
    an odd line can be given one too — as `Geometry.room` gives the row line of an empty row."""
    return lambda a, l: pair if (a, l) == (axis, line) else None


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


def stated(caps):
    """A capacity callable that states the capacity of the lines of `caps`, a {(axis, line): count}
    map, and leaves every other line unstated, as `Geometry.room` leaves the lines it knows nothing
    about."""
    return lambda axis, line: caps.get((axis, line))


def only(axis, line, cap):
    """A capacity callable that states one lattice line's capacity and leaves every other unstated."""
    return stated({(axis, line): cap})


def geometry_of(layout, mode):
    """The `Geometry` a plan was made with, rebuilt from the plan: the drawn row count, the measured
    outer rooms of its kind and the rows of the drawn extent that hold no card."""
    return flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                         *flow.margin_room(layout["kind"], mode, layout["footnotes"]),
                         empty=layout["empty_rows"])


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


class EmptyRowRoom(unittest.TestCase):
    """What `Geometry.room` states around an empty row of the drawn extent, against the browser
    measurement. Such a row has no cards, so the gutters beside it are not a row gap from anything
    and its own odd line is placed by `by()` alone, where a row of cards leaves the placing to the
    script and states no room at all."""

    def geo(self, kind, mode, rows, empty, footnotes=False):
        return flow.Geometry(flow.mode_for(kind, mode, None), 100.0, 3, rows,
                             *flow.margin_room(kind, mode, footnotes), empty=empty)

    def test_every_line_of_the_band_against_the_measurement(self):
        for shape, (rows, empty, per_mode) in sorted(EMPTY_BAND.items()):
            for kind in ("flow", "swimlane"):
                for mode, want in sorted(per_mode.items()):
                    with self.subTest(shape=shape, kind=kind, mode=mode):
                        geo = self.geo(kind, mode, rows, empty)
                        topward = flow.TOP_ROOM[kind, mode][0] - flow.EDGE_CLEAR
                        got = {line: geo.room("h", line) for line in want}
                        self.assertEqual(got, {line: ((topward if lo == TOPWARD else lo), hi)
                                               for line, (lo, hi) in want.items()})

    def test_a_row_of_cards_states_no_room_for_its_own_line(self):
        for shape, (rows, empty, _) in sorted(EMPTY_BAND.items()):
            with self.subTest(shape=shape):
                geo = self.geo("flow", "page", rows, empty)
                self.assertEqual([2 * r + 1 for r in range(rows) if geo.room("h", 2 * r + 1) is None],
                                 [2 * r + 1 for r in range(rows) if r not in empty])

    def test_a_column_of_cards_states_no_room_either(self):
        # only rows can be empty on the lattice: `tracks()` fills every column up to --dg-cols at
        # the regular pitch, so an empty column's gutters are where they always were
        geo = self.geo("flow", "page", 3, (1,))
        self.assertIsNone(geo.room("v", 1))
        self.assertIsNone(geo.room("v", 3))

    def test_the_outer_margins_move_only_where_the_first_row_is_empty(self):
        # the last row of the drawn extent always holds cards, so the bottom margin never moves
        plain = self.geo("flow", "page", 3, ())
        interior = self.geo("flow", "page", 3, (1,))
        self.assertEqual(interior.room("h", 0), plain.room("h", 0))
        self.assertEqual(interior.room("h", 6), plain.room("h", 6))
        self.assertNotEqual(self.geo("flow", "page", 3, (0,)).room("h", 0), plain.room("h", 0))

    def test_an_empty_row_leaves_the_gutters_it_does_not_touch(self):
        geo = self.geo("flow", "page", 4, (2,))
        self.assertEqual(geo.room("h", 2), (18, 18))  # between the two rows of cards above it

    def test_without_the_measurement_only_the_top_margin_stays_unstated(self):
        # the away-from-the-cards side of that one line is the browser's; the rest of the band is
        # geometry and is stated either way
        geo = flow.Geometry(flow.mode_for("flow", "page", None), 100.0, 3, 2, empty=(0,))
        self.assertIsNone(geo.room("h", 0))
        self.assertEqual(geo.room("h", 1), (9.0, 5.0))
        self.assertEqual(geo.room("h", 2), (5.0, 6.0))

    def test_how_many_lines_the_band_holds(self):
        # what a capacity message prints for these lines. A row gutter between two rows of cards
        # holds eight on a page; with an empty row between them the three lines of the band hold
        # five each, and a leading empty row leaves three above the cards instead of none.
        self.assertEqual([router.capacity(self.geo("flow", "page", 3, (1,)).room("h", y))
                          for y in (2, 3, 4)], [5, 5, 5])
        self.assertEqual([router.capacity(self.geo("flow", "page", 2, (0,)).room("h", y))
                          for y in (0, 1, 2)], [0, 3, 3])

    def test_a_deep_leading_run_ends_in_a_gutter_that_holds_nothing(self):
        # the halving puts the last gutter of a run of three 2.5 px over the cards, inside
        # LINE_CLEAR of them: no pitch draws a line there, and the message says to move the nodes
        geo = self.geo("flow", "page", 4, (0, 1, 2))
        self.assertEqual(geo.room("h", 6), (1.25, -1.5))
        self.assertEqual(router.capacity(geo.room("h", 6)), 0)
        self.assertEqual([router.capacity(geo.room("h", y)) for y in range(7)], [0, 2, 2, 1, 1, 1, 0])


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


class EmptyRowPrice(unittest.TestCase):
    """The cells of an empty row carry lines along its odd line, so `Lattice` resolves the capacity of
    every line that states one — the odd ones among them — and `route` prices a step along a full one
    as it prices a step along a full gutter. A row or a column of cards states none, and that is what
    leaves the lines through the cards unpriced."""

    def lattice(self, capacity=None):
        return router.Lattice(3, 2, EMPTY_ROW_CELLS, capacity=capacity)

    def rows_of(self, path):
        return {y for _, y in path}

    def test_every_lattice_line_is_asked_once(self):
        asked = []
        self.lattice(lambda axis, line: asked.append((axis, line)))
        self.assertEqual(sorted(asked),
                         sorted([("h", y) for y in range(5)] + [("v", x) for x in range(7)]))

    def test_an_odd_row_line_keeps_the_capacity_it_states(self):
        self.assertEqual(self.lattice(only("h", 1, 3)).cap_h, [None, 3, None, None, None])

    def test_a_lattice_without_a_capacity_states_none_anywhere(self):
        lat = self.lattice()
        self.assertEqual((lat.cap_h, lat.cap_v), ([None] * lat.H, [None] * lat.W))

    def test_the_line_takes_the_empty_row_when_the_gutter_and_the_margin_are_full(self):
        # the case exists only if the empty row is where the line goes once nothing cheaper is left
        got = router.route(self.lattice(stated({("h", 2): 0, ("h", 4): 0})), *A_TO_C)
        self.assertIn(1, self.rows_of(got), got)

    def test_and_leaves_it_when_the_empty_row_is_full_as_well(self):
        got = router.route(self.lattice(stated({("h", 1): 0, ("h", 2): 0, ("h", 4): 0})), *A_TO_C)
        self.assertNotIn(1, self.rows_of(got), got)


class TheGateModel(unittest.TestCase):
    """The model the branch gate reported: a flow with one leading empty row and six lines between the
    outer cards. The gutter above those cards is drawn OVER_THE_CARDS px from them rather than
    row_gap / 2, so the four lines the plan put there at the 8 px pitch reached 2 px inside the middle
    card on a page, and no capacity error said so."""

    def planned(self, mode):
        return flow.plan(json.loads(json.dumps(GATE)), mode)

    def test_no_line_is_drawn_into_a_card(self):
        for mode in bench_routing.MODES:
            with self.subTest(mode=mode):
                try:
                    layout, _ = self.planned(mode)
                except flow.ModelError:
                    continue  # refused: the author moves the nodes and nothing is drawn
                widest = max((abs(oy) for e in layout["edges"] for _, y, _, oy in e["path"] if y == 2),
                             default=0.0)
                self.assertLessEqual(widest, OVER_THE_CARDS - flow.LINE_CLEAR)

    def test_it_is_refused_or_every_group_fits_its_line(self):
        for mode in bench_routing.MODES:
            with self.subTest(mode=mode):
                try:
                    layout, _ = self.planned(mode)
                except flow.ModelError as exc:
                    self.assertTrue([m for m in exc.layout if "помещается" in m], exc.layout)
                    continue
                geo = geometry_of(layout, mode)
                self.assertEqual(router.overfull(layout["paths"], frozenset(layout["lattice"].blocked),
                                                 geo.room), [])


class CapacityMessage(unittest.TestCase):
    """Spec 4.4, criterion B2: the layout error a group over its line's capacity becomes. It names
    the line the way the rest of the renderer names a column or a row, how many lines are drawn
    there against how many fit, the edges the author can move, and what to do."""

    def error(self, axis, line, count, cols=3, rows=3, room=(5, 5)):
        paths = group_on(axis, line, count)
        edges = [{"a": f"n{k}", "b": f"m{k}"} for k in range(count)]
        (group,) = router.overfull(paths, frozenset(), room_at(axis, line, room))
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

    def test_the_row_line_of_an_empty_row(self):
        # room (2.5, 2.5) is the row line of the second of two leading empty rows on a page: the
        # cells beside it are free already, so freeing another would not help and the advice is to
        # take the row out
        self.assertEqual(self.error("h", 3, 4, room=(2.5, 2.5)),
                         "в пустом ряду 1 линий 4, помещается 2: n0 -> m0, n1 -> m1, n2 -> m2, "
                         "n3 -> m3; уберите пустой ряд или переставьте узлы")

    def test_the_row_line_of_an_empty_row_that_holds_no_line_at_all(self):
        # even where no pitch puts a line there, taking the row out is what frees the band
        self.assertEqual(self.error("h", 1, 1, room=(1.0, -1.5)),
                         "в пустом ряду 0 линий 1, помещается 0: n0 -> m0; уберите пустой ряд или "
                         "переставьте узлы")

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
                    geo = geometry_of(layout, mode)
                    nodes = frozenset(layout["lattice"].blocked)
                    self.assertEqual(router.overfull(layout["paths"], nodes, geo.room), [])
                    self.assertEqual(router.assign_offsets(layout["paths"], nodes=nodes, room=geo.room),
                                     router.assign_offsets(layout["paths"], nodes=nodes))

    def test_no_example_has_an_empty_row_in_its_drawn_extent(self):
        # which is why the band of an empty row leaves every shipped render where it was: the rooms
        # it changes are rooms no example asks for
        for path, model in bench_routing.examples():
            for mode in bench_routing.MODES:
                with self.subTest(example=path.name, mode=mode):
                    layout, _ = flow.plan(json.loads(json.dumps(model)), mode)
                    self.assertEqual(layout["empty_rows"], [])


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
