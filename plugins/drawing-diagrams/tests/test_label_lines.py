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


if __name__ == "__main__":
    unittest.main()
