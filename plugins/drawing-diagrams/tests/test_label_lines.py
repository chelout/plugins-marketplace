import unittest

import support  # noqa: F401
from diagrams import flow
from diagrams.common import label_width


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

    def label_warnings(self, warnings):
        return [w for w in warnings if w.startswith("связь b? -> c:")]

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


def exit_model(grid, edges, terminals=()):
    ids = [n for n in " ".join(grid).split() if n != "."]
    return {"kind": "flow", "grid": grid, "edges": edges,
            "nodes": [{"id": n, "title": n.upper(), **({"kind": "terminal"} if n in terminals else {})} for n in ids]}


# A straight exit down or up keeps its label in the gutter under or over the card, 5 px beside the
# line: template/js/flow.js puts the baseline 14 px under the card's bottom edge or 6 px over its
# top edge, so the text stands between the card and the middle of the gutter, where lines run.
DOWN = exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> c : нет"], terminals="bc")
UP = exit_model(["c b", "d a?"], ["a? -> d : да", "a? -> c : да", "b -> d : да", "c -> b : да", "d -> b : да",
                                  "d -> c : да"])


class StraightExitLabel(unittest.TestCase):
    def near_label(self, layout, edge):
        """The gutter row template/js/flow.js draws the label of the straight exit `edge` in, and
        the other lines' segments in that row whose px span meets the text: (edge, "v", lo, hi)
        for a vertical one, as lattice rows, and (edge, "h", oy) for one along the row."""
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
        edges = {(e["a"], e["b"]): e for e in layout["edges"]}
        own = edges[edge]
        self.assertEqual(len(own["path"]), 2, own)
        X, Y, ox, _ = own["path"][0]
        x0 = geo.clamp(layout["cells"][edge[0]][1], geo.x(X) + ox) + 5
        x1 = x0 + label_width(own["label"])
        row = Y + (1 if own["sa"] == "B" else -1)
        near = []
        for key, e in edges.items():
            if key == edge:
                continue
            for (xa, ya, oxa, oya), (xb, yb, oxb, _) in zip(e["path"], e["path"][1:]):
                pa, pb = geo.x(xa) + oxa, geo.x(xb) + oxb
                if xa == xb and min(ya, yb) <= row <= max(ya, yb) and x0 < pa < x1:
                    near.append((key, "v", min(ya, yb), max(ya, yb)))
                elif ya == yb == row and min(pa, pb) < x1 and max(pa, pb) > x0:
                    near.append((key, "h", oya))
        return own["sa"], row, near

    def label_warnings(self, warnings, edge):
        return [w for w in warnings if w.startswith(f"связь {edge[0]} -> {edge[1]}:")]

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

    def test_a_lone_exit_is_no_warning(self):
        # the same card, the other branch leaves sideways: nothing else in the gutter under the label
        model = exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> x : нет"], terminals="bc")
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
        )
        for model, edge, side, oy, crosses in cases:
            for mode, warned in crosses.items():
                with self.subTest(edge=edge, oy=oy, mode=mode):
                    layout, warnings = flow.plan(model, mode)
                    sa, _, near = self.near_label(layout, edge)
                    self.assertEqual(sa, side)
                    self.assertEqual([n[1:] for n in near], [("h", oy)], near)
                    self.assertEqual(len(self.label_warnings(warnings, edge)), int(warned), warnings)


if __name__ == "__main__":
    unittest.main()
