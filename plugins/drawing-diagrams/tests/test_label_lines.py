import unittest

import support
from diagrams import flow, router
from diagrams.common import ModelError, label_width


def loop_model(grid, edges):
    nodes = [{"id": "a", "title": "A"}, {"id": "b?", "title": "B?"}, {"id": "c", "title": "C"},
             {"id": "d", "kind": "terminal", "title": "D"}, {"id": "e", "title": "E"}]
    placed = " ".join(grid).split()
    return {"kind": "flow", "groups": {"g": {"label": "g", "ramp": "teal"}},
            "nodes": [n for n in nodes if n["id"] in placed], "grid": grid, "edges": edges}


# The decision b? leaves sideways into its occupied neighbour c with the label "да": one place,
# 3 px from the card edge in the gutter, above its own line. Both ways round the grid.
EDGES = ["a -> b?", "b? -> c : да", "b? -> d : нет"]
ABOVE = (["a .", "b? c", "d ."], [". a", "c b?", ". d"])
BELOW = (["a .", "b? c", "d e"], [". a", "c b?", "e d"])


class SidewaysLabel(unittest.TestCase):
    def label_and_gutter(self, layout, loop):
        """The px interval template/js/flow.js draws "да" in, and the loop's vertical segments whose
        px x falls in it, as lattice (lo, hi) against the label's row."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        edges = {(e["a"], e["b"]): e for e in layout["edges"]}
        exit_ = edges[("b?", "c")]
        self.assertEqual(len(exit_["path"]), 2, exit_)
        col = layout["cells"]["b?"][1]
        need = label_width("да")
        if exit_["sa"] == "R":
            x0 = geo.right(col) + flow.LABEL_SIDE
            x1 = x0 + need
        else:
            x1 = geo.left(col) - flow.LABEL_SIDE
            x0 = x1 - need
        path = edges[loop]["path"]
        spans = [(min(p[1], q[1]), max(p[1], q[1])) for p, q in zip(path, path[1:])
                 if p[0] == q[0] and x0 < geo.x(p[0]) + p[2] < x1]
        return exit_["path"][0][1], spans

    def label_warnings(self, warnings, edge=("b?", "c")):
        return [w for w in warnings if w.startswith(f"связь {edge[0]} -> {edge[1]}:")]

    def label_place(self, layout, edge):
        """The `dy` of the anchor a straight sideways exit's label was given: -LABEL_LIFT where it
        stands above its own line, LABEL_SINK where it stands below it (spec 7.2)."""
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        return own["la"][4]

    def along_the_row(self, layout, edge):
        """The oy of the straight sideways `edge`, and the other lines' segments whose px span meets
        the text template/js/flow.js draws its label in, 3 px off the card edge: (edge, "h", oy)
        along the label's row, (edge, "v", lo, hi) for a vertical one reaching it."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        self.assertEqual(len(own["path"]), 2, own)
        col = layout["cells"][edge[0]][1]
        need = label_width(own["label"])
        if own["sa"] == "R":
            x0 = geo.right(col) + flow.LABEL_SIDE
            x1 = x0 + need
        else:
            x1 = geo.left(col) - flow.LABEL_SIDE
            x0 = x1 - need
        row = own["path"][0][1]
        near = []
        for e in layout["edges"]:
            key = (e["a"], e["b"])
            if key == edge:
                continue
            for (xa, ya, oxa, oya), (xb, yb, oxb, _) in zip(e["path"], e["path"][1:]):
                pa, pb = geo.x(xa) + oxa, geo.x(xb) + oxb
                if xa == xb and min(ya, yb) <= row <= max(ya, yb) and x0 < pa < x1:
                    near.append((key, "v", min(ya, yb), max(ya, yb)))
                elif ya == yb == row and min(pa, pb) < x1 and max(pa, pb) > x0:
                    near.append((key, "h", oya))
        return own["path"][0][3], near

    def test_a_line_down_the_gutter_takes_the_label_under_its_own_line(self):
        # c -> a runs up the gutter past the label's row and ends there, so it covers that row above
        # the base and nothing below it. Until spec 7.2 the text had only the room above its own
        # line, where that end lies, and was warned about; with the room below its line offered it
        # stands there instead and there is nothing to warn about.
        for grid in ABOVE:
            with self.subTest(grid=grid):
                layout, warnings = flow.plan(loop_model(grid, EDGES + ["c -> a"]), "widget")
                row, spans = self.label_and_gutter(layout, ("c", "a"))
                self.assertTrue(any(lo < row <= hi for lo, hi in spans), f"row {row}, loop in the gutter {spans}")
                self.assertEqual(self.label_place(layout, ("b?", "c")), flow.LABEL_SINK)
                self.assertEqual(self.label_warnings(warnings), [], warnings)

    def test_a_line_from_below_into_the_source_is_no_warning(self):
        # e -> b? comes up the same gutter and turns into b? at the label's row, below its own line:
        # the text above it stays clear
        for grid in BELOW:
            with self.subTest(grid=grid):
                layout, warnings = flow.plan(loop_model(grid, EDGES + ["c -> e", "e -> b?"]), "widget")
                row, spans = self.label_and_gutter(layout, ("e", "b?"))
                self.assertEqual(spans and [lo for lo, _ in spans], [row], f"row {row}, loop in the gutter {spans}")
                self.assertEqual(self.label_warnings(warnings), [], warnings)

    def test_an_empty_gutter_is_no_warning(self):
        for grid in ABOVE:
            with self.subTest(grid=grid):
                _, warnings = flow.plan(loop_model(grid, EDGES + ["c -> d"]), "widget")
                self.assertEqual(self.label_warnings(warnings), [], warnings)

    # template/js/flow.js draws every line along a row of cards from one base plus its offset, a
    # straight line between two cards included, and the text stands above the label's own line:
    # a line along the row with a smaller offset than the label's runs through the text, one with
    # a larger offset passes under it, whether the row's middle lies above or below that line

    def test_a_straight_line_back_above_the_labels_own_line_takes_the_label_under_it(self):
        # c -> b? runs straight back between the same two cards, 8 px from b? -> c. The two share
        # the whole of that stretch, so which of them lies above is the order they are placed in,
        # and that is the order the search priced them in: between two edges of one length the
        # lower source point comes first and is drawn above, so it is the grid that decides and not
        # the order the model lists the two edges in. The two grids are one another mirrored — b?
        # stands in the left column of the first and in the right column of the second — and each
        # of them is read with the back edge listed first and listed last, which is the premise
        # that the list does not decide.
        #
        # Which side of its own line the text takes is what the back line then decides (spec 7.2):
        # drawn above the label's line it takes the room the text used to be warned about, and the
        # text goes below; drawn below it, the text keeps the place above. Neither is a warning now.
        for grid, own_oy, back_oy, dy in ((ABOVE[0], -4.0, 4.0, -flow.LABEL_LIFT),
                                          (ABOVE[1], 4.0, -4.0, flow.LABEL_SINK)):
            for edges in (["c -> b?"] + EDGES, EDGES + ["c -> b?"]):
                for mode in ("widget", "page"):
                    with self.subTest(grid=grid, first=edges[0], mode=mode):
                        layout, warnings = flow.plan(loop_model(grid, edges), mode)
                        oy, near = self.along_the_row(layout, ("b?", "c"))
                        self.assertEqual((oy, near), (own_oy, [(("c", "b?"), "h", back_oy)]))
                        self.assertEqual(self.label_place(layout, ("b?", "c")), dy)
                        self.assertEqual(self.label_warnings(warnings), [], warnings)

    def test_a_line_along_the_row_above_the_labels_own_line_takes_the_label_under_it(self):
        # e -> f crosses an empty cell; e -> d and f -> b run along the same row and turn up, so the
        # label's own line lies lowest, 8 px under the row's base, and e -> d runs along the base
        # through the text; f -> b turns up past the text's far end.
        #
        # The row under the cards is what e -> d goes round when it is free, so f -> g takes it: g
        # stands under the empty cell in both grids, which are one another mirrored, and the line
        # down to it is the same line either way round. The premise is asserted below: the offsets
        # and who holds them, not only the place they decide.
        #
        # e -> d runs along the base, 8 px above the label's own line and through the room above it;
        # under that line the row is empty as far as the text reaches, so the text stands there
        # (spec 7.2) and nothing is warned about.
        for grid in (["d b .", "f . e", ". g ."], [". b d", "e . f", ". g ."]):
            for mode in ("widget", "page"):
                with self.subTest(grid=grid, mode=mode):
                    layout, warnings = flow.plan(exit_model(grid, ["e -> f : да", "e -> d", "f -> b",
                                                                   "f -> g"]), mode)
                    oy, near = self.along_the_row(layout, ("e", "f"))
                    self.assertEqual((oy, near), (8.0, [(("e", "d"), "h", 0.0)]))
                    self.assertEqual(self.label_place(layout, ("e", "f")), flow.LABEL_SINK)
                    self.assertEqual(self.label_warnings(warnings, ("e", "f")), [], warnings)

    def test_lines_along_the_row_under_the_labels_own_line_are_no_warning(self):
        # four lines leave or enter c's side along the row, 8 px apart, and the label's own line
        # c -> a is the topmost, 12 px above the row's base: a -> c, above the base but under c -> a,
        # passes under the text like c -> e and c -> b below the base.
        #
        # c -> e and c -> b keep to that row only while the gutter under it is worth more than the
        # detour: c -> f runs down the margin beside c to the row below, and f is there for it. The
        # four offsets are asserted, so a line that left c another way fails as the premise it is.
        model = exit_model(["c . a", "d b e", "f . ."],
                           ["b -> c", "c -> a : да", "c -> e", "a -> c", "d -> c", "c -> b", "c -> f"])
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                oy, near = self.along_the_row(layout, ("c", "a"))
                self.assertEqual((oy, near), (-12.0, [(("c", "e"), "h", 4.0), (("a", "c"), "h", -4.0),
                                                      (("c", "b"), "h", 12.0)]))
                self.assertEqual(self.label_warnings(warnings, ("c", "a")), [], warnings)


def exit_model(grid, edges, terminals=(), nodes=()):
    """A flow on `grid`, a node per id titled with it; `terminals` are ids, `nodes` replace the
    default node of their id."""
    given = {n["id"]: n for n in nodes}
    ids = [n for n in " ".join(grid).split() if n != "."]
    return {"kind": "flow", "grid": grid, "edges": edges,
            "nodes": [given.get(n) or {"id": n, "title": n.upper(), **({"kind": "terminal"} if n in terminals else {})}
                      for n in ids]}


# A straight exit down or up keeps its label in the gutter under or over the card, 5 px beside the
# line: template/js/flow.js puts the baseline 14 px under the card's bottom edge or 6 px over its
# top edge, so the text stands between the card and the middle of the gutter, where lines run.
#
# An exit up costs the router more than a step round a free margin, so `d -> c` is the straight one
# only while the way round is taken: `c -> e` runs down the margin beside d to the row under the
# cards, the row is there for that line, and `e -> b` comes back up the other side, which is what
# leaves the search nothing cheaper than the two steps straight up.
DOWN = exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> c : нет"], terminals=("b", "c"))


def band_model(grid, edges):
    """A flow on `grid` whose nodes are titled with their own ids, as the band models below are."""
    return {"kind": "flow", "grid": grid, "edges": edges,
            "nodes": [{"id": n, "title": n} for n in " ".join(grid).split() if n != "."]}


# Plans that put a label on a line of a band of empty rows, where `tracks()` of template/js/head.js
# invents a track for each empty row and by() of template/js/flow.js places the lines from it, so
# the lines of the band stand nearer each other and nearer the cards than a row gap. name: (the
# grid, the edges, how many empty rows the band has, whether it leads the grid, the modes in which
# the router puts a label on the band). The leading ones are the four the class answer of the fourth
# round of the branch gate found, each with a place whose text reached the cards under the band
# while the model said it reached nothing; the interior ones put a label on every kind of line of a
# band of one, two and three rows between two rows of cards.
BAND_LEAD_EDGES = ["a -> c : yes", "a -> c : yes", "a -> d : yes"]
BAND_INNER_EDGES = ["a -> f : yes", "a -> g : yes", "b -> e : yes", "h -> a : yes"]
BAND_MODELS = {
    "a leading band of one": ([". . . .", "a b c d"], BAND_LEAD_EDGES + ["c -> a : yes"], 1, True,
                              ("page",)),
    "a leading band of two": ([". . . .", ". . . .", "a b c d"], BAND_LEAD_EDGES, 2, True,
                              ("widget", "page")),
    "a leading band of three": ([". . . .", ". . . .", ". . . .", "a b c d"], BAND_LEAD_EDGES, 3,
                                True, ("widget",)),
    "a leading band of three, turning back": ([". . . .", ". . . .", ". . . .", "a b c d"],
                                              ["a -> c : yes", "a -> d : yes", "c -> a : yes"], 3,
                                              True, ("page",)),
    **{f"an interior band of {n}": (["a b c d"] + [". . . ."] * k + ["e f g h"], BAND_INNER_EDGES, k,
                                    False, ("widget", "page"))
       for k, n in ((1, "one"), (2, "two"), (3, "three"))},
}
UP = exit_model(["c b", "d a?", "e ."], ["a? -> d : да", "a? -> c : да", "b -> d : да", "c -> b : да",
                                         "d -> b : да", "d -> c : да", "c -> e", "e -> b"])


class ExitLabelCase(unittest.TestCase):
    """Where template/js/flow.js draws the label of a straight exit down or up, as the tests
    assert it before asserting what the check says about it."""

    def straight_exit(self, layout, edge):
        """The layout's own entry for `edge`, with the premise every case in this class rests on
        asserted rather than assumed: the exit is the straight one, a path of two points. A model
        here is built so that nothing the router can reach is cheaper than those two steps, so an
        exit that turned is a premise that has moved and not a check that failed."""
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        self.assertEqual(len(own["path"]), 2,
                         f"premise: {edge[0]} -> {edge[1]} no longer leaves straight, so there is "
                         f"no gutter beside its label to measure: {own['path']}")
        return own

    def text_span(self, layout, edge):
        """The layout's geometry, the exit side of `edge` and the px span of its label: 5 px
        beside the line, as wide as its glyphs."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        own = self.straight_exit(layout, edge)
        X, _, ox, _ = own["path"][0]
        x0 = geo.clamp(layout["cells"][edge[0]][1], geo.x(X) + ox) + 5
        return geo, own["sa"], x0, x0 + label_width(own["label"])

    def near_label(self, layout, edge):
        """The gutter row the label of the straight exit `edge` stands in, and the other lines'
        segments in that row whose px span comes within LABEL_CLEAR of the text (a vertical line
        is 2 px wide), as the check measures them: (edge, "v", lo, hi) for a vertical one, as
        lattice rows, and (edge, "h", oy) for one along the row."""
        geo, sa, x0, x1 = self.text_span(layout, edge)
        lo_x, hi_x = x0 - flow.LABEL_CLEAR, x1 + flow.LABEL_CLEAR
        row = layout["cells"][edge[0]][0] * 2 + 1 + (1 if sa == "B" else -1)
        near = []
        for e in layout["edges"]:
            key = (e["a"], e["b"])
            if key == edge:
                continue
            for (xa, ya, oxa, oya), (xb, yb, oxb, _) in zip(e["path"], e["path"][1:]):
                pa, pb = geo.x(xa) + oxa, geo.x(xb) + oxb
                if xa == xb and min(ya, yb) <= row <= max(ya, yb) and lo_x - 1 < pa < hi_x + 1:
                    near.append((key, "v", min(ya, yb), max(ya, yb)))
                elif ya == yb == row and min(pa, pb) < hi_x and max(pa, pb) > lo_x:
                    near.append((key, "h", oya))
        return sa, row, near

    def label_warnings(self, warnings, edge):
        return [w for w in warnings if w.startswith(f"связь {edge[0]} -> {edge[1]}:")]

    def label_side(self, layout, edge):
        """Which side of its own line a straight exit's label was given, read off the `dx` of its
        anchor: "R" right of the line, "L" left of it (spec 7.2)."""
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        self.assertEqual(abs(own["la"][3]), flow.LABEL_BESIDE, own["la"])
        return "R" if own["la"][3] > 0 else "L"

    def fit_error(self, model, edge, overrides=None):
        """The one fit error about `edge`'s label; the draft layout of the same model is what the
        premise is asserted on."""
        with self.assertRaises(ModelError) as ctx:
            flow.plan(model, "widget", overrides)
        found = [m for m in ctx.exception.fit if m.startswith(f"связь {edge[0]} -> {edge[1]}: подпись")]
        self.assertEqual(len(found), 1, ctx.exception.errors)
        return found[0]


class StraightExitLabel(ExitLabelCase):
    def test_a_line_from_the_card_through_the_label_takes_it_to_the_other_side(self):
        # the other line leaves (or enters) the same side of the card beside the label and turns in
        # the gutter: its vertical runs from the card edge to the middle of the gutter, through the
        # room right of the label's own line. Left of that line the gutter is empty, so the text
        # goes there (spec 7.2) instead of being warned about.
        for model, edge, side, cross in ((DOWN, ("a?", "b"), "B", ("a?", "c")),
                                         (UP, ("d", "c"), "T", ("b", "d"))):
            for mode in ("widget", "page"):
                with self.subTest(edge=edge, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, row, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    card_side = (row - 1, row) if side == "B" else (row, row + 1)
                    self.assertIn((cross, "v", *card_side), near)
                    self.assertEqual(self.label_side(layout, edge), "L")
                    self.assertEqual(self.label_warnings(warnings, edge), [], warnings)

    def test_a_line_through_the_gutter_past_the_label_takes_it_to_the_other_side(self):
        # c -> a? comes back into a?'s column over the free cell above it and runs down beside
        # a? -> b into a?'s top edge: from the gutter over that cell (row - 2) to a?'s own point
        # (row + 1), so it passes the gutter the text stands in from one side to the other, where
        # the line of the case above turns in that gutter and stops there.
        #
        # Which of two lines in one column is drawn on the side the text stands on follows the
        # order they were placed in, and of two lines between the same two cards that is the one
        # leaving the upper card — never the exit up whose label this is. So the line past the
        # label comes from further up the column, over the free cell b leaves above a?, and
        # e -> a? is what takes the side entry it would otherwise come in by.
        model = exit_model(["c .", "b .", ". e", "a? f"],
                           ["c -> a?", "a? -> c : да", "a? -> b : да", "e -> a?", "e -> f"],
                           terminals=("b", "f"))
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                sa, row, near = self.near_label(layout, ("a?", "b"))
                self.assertEqual(sa, "T")
                self.assertEqual(near, [(("c", "a?"), "v", row - 2, row + 1)])
                self.assertEqual(self.label_side(layout, ("a?", "b")), "L")
                self.assertEqual(self.label_warnings(warnings, ("a?", "b")), [], warnings)

    def test_a_lone_exit_is_no_warning(self):
        # the same card, the other branch leaves sideways: nothing else in the gutter under the label
        model = exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> x : нет"], terminals=("b", "c"))
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                self.assertEqual(self.near_label(layout, ("a?", "b"))[2], [])
                self.assertEqual(self.label_warnings(warnings, ("a?", "b")), [], warnings)

    def test_a_line_turning_in_the_gutter_from_the_far_side_is_no_warning(self):
        # the other line comes from the far side of the gutter and turns along its middle: it ends
        # where the text ends, short of it
        # over an exit up the same shape needs the margin beside a? taken, or the line goes round it
        # instead of straight up: b -> g runs down that margin to the row under the cards and
        # g -> a? comes back up it, so both ways round it cost more than the two steps up
        cases = ((exit_model(["a? b", "c d"], ["b -> c", "d -> c", "a? -> b : да", "d -> b", "a? -> c : да"]),
                  ("a?", "c"), "B", ("b", "c")),
                 (exit_model(["b e c", "a? f d", "g h i"],
                             ["b -> c", "a? -> c : да", "a? -> b : да", "b -> g", "g -> a?"]),
                  ("a?", "b"), "T", ("b", "c")))
        for model, edge, side, turn in cases:
            for mode in ("widget", "page"):
                with self.subTest(edge=edge, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, row, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    far_side = (row, row + 1) if side == "B" else (row - 1, row)
                    self.assertEqual(sorted(near), [(turn, "h", 0.0), (turn, "v", *far_side)])
                    self.assertEqual(self.label_warnings(warnings, edge), [], warnings)

    def test_a_line_along_the_gutter_counts_when_it_runs_on_the_card_side_of_the_text(self):
        # parallel lines spread 8 px apart around the middle of the gutter; the text's middle stands
        # 10 px off the card edge, half the gutter less 10 px from the middle (widget 10, page 12)
        cases = (
            # 4 px off the middle away from the card: under the text whatever the mode
            (exit_model(["f e a? g", "c h d b"],
                        ["a? -> f : да", "a? -> d : да", "b -> f", "g -> f", "a? -> g : да"]),
             ("a?", "d"), "B", 4.0, {"widget": False, "page": False}),
            # 8 px off the middle towards the card: through the text whatever the mode. Four lines
            # share that gutter row and are drawn in three slots — d -> h over the first column and
            # g -> f over the last never lie beside each other and take one between them — so
            # f -> c, which lies beside all of the others, is a whole pitch off the middle.
            (exit_model(["e h g b", "d c a? f"], ["a? -> b : да", "g -> c", "d -> h",
                                                  "a? -> g : да", "g -> f", "d -> e", "f -> c",
                                                  "e -> h"]),
             ("a?", "g"), "T", 8.0, {"widget": True, "page": True}),
            # 4 px towards the card: through the foot of the text in a widget, clear of it on a page
            (exit_model(["c a? . f", "e d b ."], ["e -> d", "b -> c", "a? -> d : да", "a? -> c : да", "f -> c",
                                                  "d -> c", "c -> e"]),
             ("a?", "d"), "B", -4.0, {"widget": True, "page": False}),
            # the same over an exit up: through the top of the text in a widget, clear of it on a
            # page. b -> d and d -> a? fill the gutter column on one side of a?, and f stands on
            # the other, where a labelled line that leaves sideways pays for the occupied cell it
            # heads towards: so the two steps straight up cost less than either way round, and
            # e -> d is the line along the gutter
            (exit_model([". e b c", ". f a? d"], ["d -> c", "a? -> e : да", "e -> d",
                                                  "b -> e", "a? -> b : да", "b -> d", "d -> a?"]),
             ("a?", "b"), "T", 4.0, {"widget": True, "page": False}),
        )
        for model, edge, side, oy, crosses in cases:
            for mode, warned in crosses.items():
                with self.subTest(edge=edge, oy=oy, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, _, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    self.assertEqual([n[1:] for n in near], [("h", oy)],
                                     f"the line beside the text no longer runs {oy} px off the middle "
                                     f"of the gutter, which is what this case measures: {near}")
                    self.assertEqual(len(self.label_warnings(warnings, edge)), int(warned), warnings)


class StraightExitRoom(ExitLabelCase):
    def test_a_label_past_the_right_edge_of_the_diagram_goes_left_and_still_does_not_fit(self):
        # the last column's card: a card width of room would run the text out of the section. Left
        # of the line the drawn area goes on, so that is where the text now stands (spec 7.2), and
        # the room there ends at the card r beside it — which is what the error names (E3).
        model = exit_model(["p q r a?", "s t u b"], ["a? -> b : подтверждено вендором", "a? -> r : нет"])
        layout, _ = flow.plan(model, "widget", draft=True)
        geo, sa, x0, x1 = self.text_span(layout, ("a?", "b"))
        self.assertEqual(sa, "B")
        self.assertLess(x1 - x0, layout["card_w"])
        self.assertGreater(x1, geo.total)
        self.assertEqual(self.label_side(layout, ("a?", "b")), "L")
        error = self.fit_error(model, ("a?", "b"))
        self.assertIn("не помещается у выхода вниз", error)
        self.assertIn("мешает карточка r", error)

    def test_an_exit_up_that_does_not_fit_is_named_so(self):
        # the exit-up model on narrow cards: the label is wider than a card
        model = exit_model(UP["grid"], [e if e != "d -> c : да" else "d -> c : подтверждено вендором"
                                        for e in UP["edges"]])
        layout, _ = flow.plan(model, "widget", {"total": 300}, draft=True)
        _, sa, x0, x1 = self.text_span(layout, ("d", "c"))
        self.assertEqual(sa, "T")
        self.assertGreater(x1 - x0, layout["card_w"])
        self.assertEqual(self.label_side(layout, ("d", "c")), "R")
        error = self.fit_error(model, ("d", "c"), {"total": 300})
        self.assertIn("не помещается у выхода вверх", error)
        # neither side of the line has the room, so the roomiest is kept and the error names what
        # stands nearest in it — a line here, where the case above names a card (E3)
        self.assertIn("мешает линия b -> d", error)


# Under a card shorter than its row the label of a straight exit down hangs inside the row:
# template/js/flow.js hangs the text 14 px under the card's own bottom edge, and cards align to the
# top of their row. A two-line text makes t twice as tall as a? beside it.
TALL = [{"id": "t", "title": "T", "text": "сверка документов и адреса"}]


class UnderShortCard(ExitLabelCase):
    EDGE = ("a?", "b")

    def plan(self, grid, edges, mode="widget", draft=False):
        return flow.plan(exit_model(grid, edges, nodes=TALL), mode, draft=draft)

    def in_card_row(self, layout, other):
        """The segments of `other` in the row of cards a? stands in whose px span meets the label
        under a?: ("h", oy) along the row, ("v", lo, hi) for a vertical one reaching the row."""
        geo, _, x0, x1 = self.text_span(layout, self.EDGE)
        R = layout["cells"]["a?"][0] * 2 + 1
        path = next(e["path"] for e in layout["edges"] if (e["a"], e["b"]) == other)
        out = []
        for (xa, ya, oxa, oya), (xb, yb, oxb, _) in zip(path, path[1:]):
            pa, pb = geo.x(xa) + oxa, geo.x(xb) + oxb
            if xa == xb and min(ya, yb) <= R <= max(ya, yb) and x0 < pa < x1:
                out.append(("v", min(ya, yb), max(ya, yb)))
            elif ya == yb == R and min(pa, pb) < x1 and max(pa, pb) > x0:
                out.append(("h", oya))
        return out

    def test_a_line_turning_into_the_next_card_through_the_label_is_a_warning(self):
        # p -> t comes down the gutter between a? and t and turns into t's side at the height of t,
        # through the text under a?; nothing reaches the gutter under a?, where the text would be
        # beside a card as tall as a?
        layout, warnings = self.plan(["p q . .", "a? t . .", "b . . ."],
                                     ["a? -> b : сверка вручную", "a? -> p : нет", "q -> t", "p -> t"])
        self.assertEqual(self.near_label(layout, self.EDGE)[2], [])
        self.assertIn(("v", 1, 3), self.in_card_row(layout, ("p", "t")))
        found = self.label_warnings(warnings, self.EDGE)
        self.assertEqual(len(found), 1, warnings)
        self.assertTrue(found[0].startswith("связь a? -> b: подпись 'сверка вручную' у выхода вниз ляжет на другую линию"),
                        found)

    def test_the_next_card_in_the_row_limits_the_room(self):
        grid, edges = [". q . .", "a? t . .", "b . . ."], ["a? -> b : ручная сверка данных", "a? -> t : нет", "q -> t"]
        layout, _ = self.plan(grid, edges, draft=True)
        geo, _, x0, x1 = self.text_span(layout, self.EDGE)
        self.assertTrue(x0 < geo.left(1) < x1, (x0, geo.left(1), x1))
        self.assertIn("не помещается у выхода вниз", self.fit_error(exit_model(grid, edges, nodes=TALL), self.EDGE))

    def test_a_card_alone_in_its_row_keeps_a_card_width(self):
        # a? is its row's only card, so the row is as tall as a? and the text stays in the gutter
        layout, warnings = self.plan(["q . . .", "a? . . .", "b . . ."],
                                     ["a? -> b : ручная сверка данных", "a? -> q : нет"])
        geo, _, x0, x1 = self.text_span(layout, self.EDGE)
        self.assertTrue(x0 < geo.left(1) < x1, (x0, geo.left(1), x1))
        self.assertEqual(self.label_warnings(warnings, self.EDGE), [], warnings)

    def test_lines_at_the_source_cards_own_height_are_no_warning(self):
        # a line leaving a? sideways, and one coming down the gutter into a?'s side, are drawn within
        # a?'s height, above the text under it
        cases = ((["a? . t .", "b . . ."], ["a? -> b : ручная проверка", "a? -> t : нет"], ("a?", "t")),
                 (["p q . .", "a? . t .", "b . . ."], ["a? -> b : ручная проверка", "a? -> t : нет", "p -> a?", "q -> a?"],
                  ("q", "a?")))
        for grid, edges, beside in cases:
            with self.subTest(grid=grid):
                layout, warnings = self.plan(grid, edges)
                self.assertTrue(self.in_card_row(layout, beside), beside)
                self.assertEqual(self.label_warnings(warnings, self.EDGE), [], warnings)


class BesideSecondSegment(unittest.TestCase):
    """A label beside a vertical second segment, pinned to a row of cards: the anchor stands the
    middle of the text on the row's base, LABEL_BEND off the line."""

    def along_the_row(self, layout, edge, Y, side):
        """The other lines along lattice row Y whose px span meets the text of `edge`'s label
        beside its vertical second segment on `side`, as (edge, oy)."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        X, _, ox, _ = own["path"][1]
        x, need = geo.x(X) + ox, label_width(own["label"])
        x0, x1 = (x + flow.LABEL_BEND, x + flow.LABEL_BEND + need) if side == "R" else (x - flow.LABEL_BEND - need,
                                                                                        x - flow.LABEL_BEND)
        near = []
        for e in layout["edges"]:
            for (xa, ya, oxa, oya), (xb, yb, oxb, _) in zip(e["path"], e["path"][1:]):
                pa, pb = geo.x(xa) + oxa, geo.x(xb) + oxb
                if ya == yb == Y and min(pa, pb) < x1 and max(pa, pb) > x0:
                    near.append(((e["a"], e["b"]), oya))
        return near

    def test_a_line_along_a_row_with_sideways_ends_counts_whatever_its_offset(self):
        # d -> b leaves d sideways, runs along d's row to the gutter between a and b, turns up there
        # and into b's side. Every other place beside that second segment is taken; pinned to the
        # gutter row on its right the text stands past that gutter, where the only line of d's row
        # is c -> d, running straight across it a whole pitch under its base — LINE_REACH and more
        # from the text's middle. template/js/flow.js clamps every line on a row line where lines
        # enter or leave cards sideways into one band, 10 px inside the shortest of those cards, and
        # these cards are one title line high: c -> d is drawn nearer the base than its offset,
        # through the text.
        #
        # Three lines lie beside one another on d's row — d -> a as far as the gutter beside d,
        # d -> b as far as the one beside b, and c -> d across the whole of it — so each takes a
        # slot of its own at the widest of router.PITCHES. c -> b, which leaves c the other way
        # round the right margin, meets none of them side by side and shares d -> b's slot. The
        # premise asserts those offsets and who holds them: a line that stopped lying beside the
        # others would share a slot, the group would close up, and the case would measure an offset
        # it was not written for.
        #
        # e -> c is what fills the row under the cards, which is the way d -> b takes when it is
        # free; without it the label's line never turns up in the gutter beside b at all.
        model = exit_model(["e a b", "d . c"],
                           ["e -> d", "c -> d", "c -> b", "d -> b : да", "d -> a", "a -> c", "e -> c"],
                           terminals=("b",))
        pitch = float(router.PITCHES[0])
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                on_row = sorted((oy, (e["a"], e["b"])) for e in layout["edges"]
                                for (_, ya, _, oy), (_, yb, _, _) in zip(e["path"], e["path"][1:])
                                if ya == yb == 3)
                self.assertEqual(on_row, [(-pitch, ("d", "a")), (0.0, ("c", "b")), (0.0, ("d", "b")),
                                          (pitch, ("c", "d"))],
                                 f"the lines along row 3 no longer take a slot each {pitch} px apart")
                own = next(e for e in layout["edges"] if (e["a"], e["b"]) == ("d", "b"))
                self.assertEqual((own["sa"], own["path"][0][1], own["path"][1][1] != own["path"][2][1]), ("R", 3, True))
                self.assertEqual(own["la"], (1, "r", 2, flow.LABEL_BEND, flow.LABEL_DROP, "start"))
                self.assertEqual(self.along_the_row(layout, ("d", "b"), 3, "R"), [(("c", "d"), pitch)])
                self.assertGreaterEqual(pitch, flow.LINE_REACH)
                found = [w for w in warnings if w.startswith("связь d -> b:")]
                self.assertEqual(len(found), 1, warnings)
                self.assertTrue(found[0].startswith("связь d -> b: подпись 'да' рядом со вторым отрезком ляжет на другую "
                                                    "линию"), found)

    def test_a_line_along_a_gutter_row_counts_by_its_offset(self):
        # a -> d leaves a sideways, turns up and pins its label to gutter row 2 on the left of its
        # second segment, then turns along that row 8 px above its base. No card stands on a gutter
        # row, so no line enters or leaves a card sideways there and template/js/flow.js draws a line
        # along it at its own offset, unclamped: LINE_REACH and more from the text's middle, clear of it.
        #
        # Three lines share that row — a -> d, d -> a and e -> c — and an ordinary gutter between two
        # rows of cards has the room to hold the three at the widest of router.PITCHES in both modes,
        # which is what puts a -> d's own line a whole pitch off the row line. The premise asserts those
        # three offsets: a row with less room beside it, or one line more on it, closes the group to a
        # narrower pitch, and the case would then measure an offset it was not written for.
        #
        # d -> b takes the way along the row of cards that a -> d would otherwise have, which is
        # what sends a -> d out to the right margin and back along the gutter row the label is on.
        model = exit_model([". . d e", ". b c a"],
                           ["a -> c : да", "a -> d : да", "d -> a", "e -> c : да", "b -> c", "d -> b"],
                           terminals=("e",))
        pitch = float(router.PITCHES[0])
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                room = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                                     empty=layout["empty_rows"]).room("h", 2)
                on_row = sorted(oy for e in layout["edges"]
                                for (_, ya, _, oy), (_, yb, _, _) in zip(e["path"], e["path"][1:]) if ya == yb == 2)
                self.assertEqual(on_row, [-pitch, 0.0, pitch],
                                 f"gutter row 2 has room {room}: the lines along it no longer lie {pitch} px apart")
                own = next(e for e in layout["edges"] if (e["a"], e["b"]) == ("a", "d"))
                self.assertEqual((own["sa"], own["la"]),
                                 ("R", (1, "r", 2, -flow.LABEL_BEND, flow.LABEL_DROP, "end")))
                self.assertEqual(self.along_the_row(layout, ("a", "d"), 2, "L"), [(("a", "d"), -pitch)])
                self.assertGreaterEqual(pitch, flow.LINE_REACH)
                self.assertEqual([e for e in layout["edges"]
                                  if e["path"][0][1] == e["path"][1][1] == 2 or e["path"][-1][1] == e["path"][-2][1] == 2], [])
                self.assertEqual([w for w in warnings if w.startswith("связь a -> d:")], [], warnings)


if __name__ == "__main__":
    unittest.main()
