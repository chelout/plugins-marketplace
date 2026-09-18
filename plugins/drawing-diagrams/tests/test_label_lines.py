import re
import unittest

import support
from diagrams import flow
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

    def test_a_line_down_the_gutter_through_the_label_is_a_warning(self):
        # c -> a runs up the gutter past the label's row: drawn from above, through the text
        for grid in ABOVE:
            with self.subTest(grid=grid):
                layout, warnings = flow.plan(loop_model(grid, EDGES + ["c -> a"]), "widget")
                row, spans = self.label_and_gutter(layout, ("c", "a"))
                self.assertTrue(any(lo < row <= hi for lo, hi in spans), f"row {row}, loop in the gutter {spans}")
                found = self.label_warnings(warnings)
                self.assertEqual(len(found), 1, warnings)
                self.assertTrue(found[0].startswith("связь b? -> c: подпись 'да' у выхода вбок ляжет на другую линию"),
                                found)

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

    def test_a_straight_line_back_above_the_labels_own_line_is_a_warning(self):
        # c -> b? runs straight back between the same two cards, 8 px from b? -> c: the one listed
        # first lies above
        for grid in ABOVE:
            for edges, own_oy, back_oy, warned in ((["c -> b?"] + EDGES, 4.0, -4.0, True),
                                                   (EDGES + ["c -> b?"], -4.0, 4.0, False)):
                for mode in ("widget", "page"):
                    with self.subTest(grid=grid, first=edges[0], mode=mode):
                        layout, warnings = flow.plan(loop_model(grid, edges), mode)
                        oy, near = self.along_the_row(layout, ("b?", "c"))
                        self.assertEqual((oy, near), (own_oy, [(("c", "b?"), "h", back_oy)]))
                        found = self.label_warnings(warnings)
                        self.assertEqual(len(found), int(warned), warnings)
                        if warned:
                            self.assertTrue(found[0].startswith("связь b? -> c: подпись 'да' у выхода вбок "
                                                                "ляжет на другую линию"), found)

    def test_a_line_along_the_row_above_the_labels_own_line_is_a_warning(self):
        # e -> f crosses an empty cell; e -> d and f -> b run along the same row and turn up, so the
        # label's own line lies lowest, 8 px under the row's base, and e -> d runs along the base
        # through the text; f -> b turns up past the text's far end
        for grid in (["d b .", "f . e"], [". b d", "e . f"]):
            for mode in ("widget", "page"):
                with self.subTest(grid=grid, mode=mode):
                    layout, warnings = flow.plan(exit_model(grid, ["e -> f : да", "e -> d", "f -> b"]), mode)
                    oy, near = self.along_the_row(layout, ("e", "f"))
                    self.assertEqual((oy, near), (8.0, [(("e", "d"), "h", 0.0)]))
                    found = self.label_warnings(warnings, ("e", "f"))
                    self.assertEqual(len(found), 1, warnings)
                    self.assertTrue(found[0].startswith("связь e -> f: подпись 'да' у выхода вбок ляжет на другую линию"),
                                    found)

    def test_lines_along_the_row_under_the_labels_own_line_are_no_warning(self):
        # four lines leave or enter c's side along the row, 8 px apart, and the label's own line
        # c -> a is the topmost, 12 px above the row's base: a -> c, above the base but under c -> a,
        # passes under the text like c -> e and c -> b below the base
        model = exit_model(["c . a", "d b e"], ["b -> c", "c -> a : да", "c -> e", "a -> c", "d -> c", "c -> b"])
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
DOWN = exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> c : нет"], terminals=("b", "c"))
UP = exit_model(["c b", "d a?"], ["a? -> d : да", "a? -> c : да", "b -> d : да", "c -> b : да", "d -> b : да",
                                  "d -> c : да"])


class ExitLabelCase(unittest.TestCase):
    """Where template/js/flow.js draws the label of a straight exit down or up, as the tests
    assert it before asserting what the check says about it."""

    def text_span(self, layout, edge):
        """The layout's geometry, the exit side of `edge` and the px span of its label: 5 px
        beside the line, as wide as its glyphs."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        own = next(e for e in layout["edges"] if (e["a"], e["b"]) == edge)
        self.assertEqual(len(own["path"]), 2, own)
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

    def fit_error(self, model, edge, overrides=None):
        """The one fit error about `edge`'s label; the draft layout of the same model is what the
        premise is asserted on."""
        with self.assertRaises(ModelError) as ctx:
            flow.plan(model, "widget", overrides)
        found = [m for m in ctx.exception.fit if m.startswith(f"связь {edge[0]} -> {edge[1]}: подпись")]
        self.assertEqual(len(found), 1, ctx.exception.errors)
        return found[0]


class StraightExitLabel(ExitLabelCase):
    def test_a_line_from_the_card_through_the_label_is_a_warning(self):
        # the other line leaves (or enters) the same side of the card beside the label and turns in
        # the gutter: its vertical runs from the card edge to the middle of the gutter, through the text
        for model, edge, side, cross, where in ((DOWN, ("a?", "b"), "B", ("a?", "c"), "у выхода вниз"),
                                                (UP, ("d", "c"), "T", ("b", "d"), "у выхода вверх")):
            for mode in ("widget", "page"):
                with self.subTest(edge=edge, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, row, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    card_side = (row - 1, row) if side == "B" else (row, row + 1)
                    self.assertIn((cross, "v", *card_side), near)
                    found = self.label_warnings(warnings, edge)
                    self.assertEqual(len(found), 1, warnings)
                    self.assertTrue(found[0].startswith(f"связь {edge[0]} -> {edge[1]}: подпись 'да' {where} "
                                                        f"ляжет на другую линию"), found)

    def test_a_line_through_the_gutter_past_the_label_is_a_warning(self):
        # b -> a? runs down beside a? -> b, from b's bottom edge to a?'s top edge: it passes the gutter
        # the text stands in from one side to the other
        model = exit_model(["c", "b", "a?"], ["c -> a?", "a? -> c : да", "a? -> b : да", "b -> a?"])
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                sa, row, near = self.near_label(layout, ("a?", "b"))
                self.assertEqual(sa, "T")
                self.assertEqual(near, [(("b", "a?"), "v", row - 1, row + 1)])
                found = self.label_warnings(warnings, ("a?", "b"))
                self.assertEqual(len(found), 1, warnings)
                self.assertTrue(found[0].startswith("связь a? -> b: подпись 'да' у выхода вверх ляжет на другую линию"),
                                found)

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
        cases = ((exit_model(["a? b", "c d"], ["b -> c", "d -> c", "a? -> b : да", "d -> b", "a? -> c : да"]),
                  ("a?", "c"), "B", ("b", "c")),
                 (exit_model(["b e c", "a? f d"], ["b -> c", "a? -> c : да", "a? -> b : да"]),
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
                        ["a? -> f : да", "a? -> d : да", "b -> f", "g -> h", "g -> f", "a? -> g : да"]),
             ("a?", "d"), "B", 4.0, {"widget": False, "page": False}),
            # 8 px off the middle towards the card: through the text whatever the mode
            (exit_model(["e h g b", "d c a? f"], ["g -> h", "a? -> b : да", "b -> e", "g -> c", "d -> h",
                                                  "a? -> g : да", "g -> f", "f -> h", "d -> e"]),
             ("a?", "g"), "T", 8.0, {"widget": True, "page": True}),
            # 4 px towards the card: through the foot of the text in a widget, clear of it on a page
            (exit_model(["c a? . f", "e d b ."], ["e -> d", "b -> c", "a? -> d : да", "a? -> c : да", "f -> c", "d -> c"]),
             ("a?", "d"), "B", -4.0, {"widget": True, "page": False}),
            # the same over an exit up: through the top of the text in a widget, clear of it on a page
            (exit_model([". e b c", ". . a? d"], ["c -> e", "d -> c", "c -> a?", "a? -> e : да", "e -> c", "e -> d",
                                                  "b -> e", "a? -> b : да"]),
             ("a?", "b"), "T", 4.0, {"widget": True, "page": False}),
        )
        for model, edge, side, oy, crosses in cases:
            for mode, warned in crosses.items():
                with self.subTest(edge=edge, oy=oy, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, _, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    self.assertEqual([n[1:] for n in near], [("h", oy)], near)
                    self.assertEqual(len(self.label_warnings(warnings, edge)), int(warned), warnings)


class StraightExitRoom(ExitLabelCase):
    def test_a_label_past_the_right_edge_of_the_diagram_does_not_fit(self):
        # the last column's card: a card width of room would run the text out of the section
        model = exit_model(["p q r a?", "s t u b"], ["a? -> b : подтверждено вендором", "a? -> r : нет"])
        layout, _ = flow.plan(model, "widget", draft=True)
        geo, sa, x0, x1 = self.text_span(layout, ("a?", "b"))
        self.assertEqual(sa, "B")
        self.assertLess(x1 - x0, layout["card_w"])
        self.assertGreater(x1, geo.total)
        self.assertIn("не помещается у выхода вниз", self.fit_error(model, ("a?", "b")))

    def test_an_exit_up_that_does_not_fit_is_named_so(self):
        # the exit-up model on narrow cards: the label is wider than a card
        model = exit_model(UP["grid"], [e if e != "d -> c : да" else "d -> c : подтверждено вендором"
                                        for e in UP["edges"]])
        layout, _ = flow.plan(model, "widget", {"total": 300}, draft=True)
        _, sa, x0, x1 = self.text_span(layout, ("d", "c"))
        self.assertEqual(sa, "T")
        self.assertGreater(x1 - x0, layout["card_w"])
        self.assertIn("не помещается у выхода вверх", self.fit_error(model, ("d", "c"), {"total": 300}))


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
    """A label beside a vertical second segment, pinned to a row of cards: template/js/flow.js stands
    the middle of the text on the row's base, LABEL_BEND off the line."""

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
        # d -> b leaves d sideways, turns up in the gutter and into b's side. Every other place beside
        # its second segment is taken; pinned to d's row on the right the text meets only c -> d,
        # running straight along the row 8 px under its base, LINE_REACH and more from the text's
        # middle. template/js/flow.js clamps every line on a row line where lines enter or leave cards
        # sideways into one band, 10 px inside the shortest of those cards, and these cards are one
        # title line high: c -> d is drawn nearer the base than its offset, through the text
        model = exit_model(["a b e", "d . c"], ["e -> d", "c -> a", "d -> b : да", "c -> b", "b -> d", "c -> d"])
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                own = next(e for e in layout["edges"] if (e["a"], e["b"]) == ("d", "b"))
                self.assertEqual((own["sa"], own["path"][0][1], own["path"][1][1] != own["path"][2][1]), ("R", 3, True))
                self.assertEqual(self.along_the_row(layout, ("d", "b"), 3, "R"), [(("c", "d"), 8.0)])
                self.assertGreaterEqual(8.0, flow.LINE_REACH)
                found = [w for w in warnings if w.startswith("связь d -> b:")]
                self.assertEqual(len(found), 1, warnings)
                self.assertTrue(found[0].startswith("связь d -> b: подпись 'да' рядом со вторым отрезком ляжет на другую "
                                                    "линию"), found)

    def test_a_line_along_a_gutter_row_counts_by_its_offset(self):
        # a -> d leaves a sideways, turns up and pins its label to gutter row 4 on the left of its
        # second segment, then turns along that row 8 px above its base. No card stands on a gutter
        # row, so no line enters or leaves a card sideways there and template/js/flow.js draws a line
        # along it at its own offset, unclamped: LINE_REACH and more from the text's middle, clear of it
        model = exit_model([". . d e", ". . . .", ". b c a"],
                           ["a -> c : да", "a -> d : да", "d -> a", "e -> c : да", "b -> c"], terminals=("e",))
        for mode in ("widget", "page"):
            with self.subTest(mode=mode):
                layout, warnings = flow.plan(model, mode)
                own = next(e for e in layout["edges"] if (e["a"], e["b"]) == ("a", "d"))
                self.assertEqual((own["sa"], own["ly"], own["ls"]), ("R", 4, "L"))
                self.assertEqual(self.along_the_row(layout, ("a", "d"), 4, "L"), [(("a", "d"), -8.0)])
                self.assertGreaterEqual(8.0, flow.LINE_REACH)
                self.assertEqual([e for e in layout["edges"]
                                  if e["path"][0][1] == e["path"][1][1] == 4 or e["path"][-1][1] == e["path"][-2][1] == 4], [])
                self.assertEqual([w for w in warnings if w.startswith("связь a -> d:")], [], warnings)


class ScriptOffsets(unittest.TestCase):
    SCRIPT = (support.SKILL / "template" / "js" / "flow.js").read_text(encoding="utf-8")

    def test_the_check_mirrors_where_the_script_puts_labels(self):
        # each pattern captures one offset of the label code in template/js/flow.js, and names the
        # constant diagrams/flow.py measures it with
        for pattern, name in ((r"lx=rt\?p2\.x-(\d+):", "LABEL_BEND"),
                              (r"\{lx=p1\.x\+(\d+);ly=my\}", "LABEL_BEND"),
                              (r"\(p1\.y\+p2\.y\)/2\)\+(\d+);", "LABEL_DROP"),
                              (r"e\.sa==='B'\)\{lx=a0\.x\+(\d+);", "LABEL_BESIDE"),
                              (r"e\.sa==='B'\)\{lx=a0\.x\+\d+;ly=a0\.y\+(\d+)\}", "LABEL_BELOW"),
                              (r"e\.sa==='T'\)\{lx=a0\.x\+(\d+);", "LABEL_BESIDE"),
                              (r"e\.sa==='T'\)\{lx=a0\.x\+\d+;ly=a0\.y-(\d+)\}", "LABEL_ABOVE"),
                              (r"e\.sa==='R'\)\{lx=a0\.x\+(\d+);", "LABEL_SIDE")):
            with self.subTest(constant=name, pattern=pattern):
                found = re.findall(pattern, self.SCRIPT)
                self.assertEqual(len(found), 1, f"{pattern!r} in template/js/flow.js")
                self.assertEqual(int(found[0]), getattr(flow, name, None))


if __name__ == "__main__":
    unittest.main()
