"""An empty row after the last card is no part of the lattice: the page has no track there.

`tracks()` of template/js/head.js takes its row count from the cards — the last occupied row plus
one — and invents a track for an empty row above or between them, never for one after the last. So
`by()` of template/js/flow.js has no y for a line under the last card row: it reads an undefined
row, the script stops there and the page is left without the lines it had not drawn yet. `flow.plan`
therefore ends the lattice, the geometry and the row count its messages name lines by where the
cards end. The rows above stay as they are, and the author still hears about every empty row of the
grid.

The models below are the branch gate's and the controller's: a row of cards whose lines have to
leave it, and an empty row under it to leave into. A flow's top margin is the dearest line of all —
it holds nothing, and a line leaving through the top pays for that as well — so the lines go down
first, and each of these models put one below the last card row, into the empty row's own cells or
along the margin under it. One of them puts a line over the first row too, which is the only way
the message about the top margin can be measured at all. The plans here are drafts, so that a group
the trimmed lattice cannot hold is a warning and the paths are there to be looked at either way.

What the browser draws for such a model is case 16 of tests/test_browser_lines.py.
"""
import json
import unittest

import support  # noqa: F401
import bench_routing
from diagrams import flow

MODES = ("page", "widget")
LANES = {"one": {"label": "Первый", "ramp": "teal"}, "two": {"label": "Второй", "ramp": "blue"},
         "three": {"label": "Третий", "ramp": "purple"}}


def step(i):
    return {"id": i, "title": i.upper()}


TRAILING = {
    # four lines between one pair of cards, two each way: the margin under the row holds three of
    # them and the fourth is the one line over the row, which is what the top margin is named by
    "both-ways": {"kind": "flow", "nodes": [step(i) for i in "abc"], "grid": ["a b c", ". . ."],
                  "edges": ["a -> c", "a -> c", "c -> a", "c -> a"]},
    "three-lines": {"kind": "flow", "nodes": [step(i) for i in "abc"], "grid": ["a b c", ". . ."],
                    "edges": ["a -> c"] * 3},
    "four-columns": {"kind": "flow", "nodes": [step(i) for i in "abcd"], "grid": ["a b c d", ". . . ."],
                     "edges": ["a -> c", "b -> d", "a -> d"]},
    "swimlane": {"kind": "swimlane", "lanes": ["one", "two", "three"], "groups": LANES,
                 "nodes": [step(i) for i in "abc"], "grid": ["a b c", ". . ."], "edges": ["a -> c"] * 3},
}
# A leading empty row and a trailing one: the first gets a track, the second does not. Four lines,
# because three of them find room in the gutter under the empty row and in the margin under the
# cards; the fourth is the one that runs along the empty row's own cells, which is what this model
# is here to show.
LEADING = {"kind": "flow", "nodes": [step(i) for i in "abc"], "grid": [". . .", "a b c", ". . ."],
           "edges": ["a -> c"] * 4}


def planned(model, mode, draft=True):
    """The plan of a copy of `model`: flow.plan annotates the model it is given."""
    return flow.plan(json.loads(json.dumps(model)), mode, draft=draft)


def with_a_row_appended(model):
    """The same model with one empty row under its grid — a row the page never draws, so nothing
    about the drawing may move."""
    out = json.loads(json.dumps(model))
    out["grid"] = out["grid"] + [" ".join(["."] * max(len(r.split()) for r in out["grid"]))]
    return out


def drawing(model, mode):
    """What a plan says about the drawing: the edges with their paths and offsets, the row count the
    lattice and a swimlane's lane span follow, and the crossings the author is warned about."""
    layout, _ = planned(model, mode)
    return layout["edges"], layout["grid_rows"], layout["crossings"]


class TheLatticeEndsWithTheCards(unittest.TestCase):
    def test_the_row_count_is_the_last_occupied_row_plus_one(self):
        for name, model in TRAILING.items():
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    layout, _ = planned(model, mode)
                    rows = max(r for r, _ in layout["cells"].values()) + 1
                    # the case exists only if the author wrote a row the page does not draw
                    self.assertGreater(len(model["grid"]), rows, "harness: no trailing empty row")
                    self.assertEqual(layout["grid_rows"], rows)
                    self.assertEqual(layout["lattice"].rows, rows)

    def test_no_point_of_a_path_lies_below_the_bottom_margin(self):
        # the bound comes from the cards, as `tracks()` takes it: the bottom margin of the last
        # occupied row is the last lattice line the page can draw a point on
        for name, model in TRAILING.items():
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    layout, _ = planned(model, mode)
                    bottom = 2 * (max(r for r, _ in layout["cells"].values()) + 1)
                    below = [f"{e['a']} -> {e['b']}: {e['path']}" for e in layout["edges"]
                             if any(p[1] > bottom for p in e["path"])]
                    self.assertEqual(below, [], f"{name} {mode}: a line below the bottom margin Y={bottom}")
                    # the case exists only if the lines press against that bound
                    self.assertTrue(any(p[1] == bottom for e in layout["edges"] for p in e["path"]),
                                    f"harness: {name} {mode}: no line reaches the bottom margin")


class TheMessagesCountTheRowsThatAreDrawn(unittest.TestCase):
    """A capacity error names the line the script draws, so it counts rows by the trimmed count: the
    lines under the last card row are under the bottom margin, not between two rows of the grid."""

    def drafted(self, name, mode):
        _, warnings = planned(TRAILING[name], mode)
        return [w for w in warnings if w.startswith("черновик: ")]

    def test_a_group_under_the_last_card_row_is_named_by_the_bottom_margin(self):
        got = self.drafted("four-columns", "page")
        self.assertTrue(any(w.startswith("черновик: по нижнему полю линий 3, помещается 1: a -> c, b -> d, a -> d")
                            for w in got), got)

    def test_a_group_over_the_first_one_is_named_by_the_top_margin(self):
        got = self.drafted("both-ways", "page")
        self.assertTrue(any(w.startswith("черновик: по верхнему полю линий 1, помещается 0: a -> c")
                            for w in got), got)


class TheRowsAboveTheCardsStay(unittest.TestCase):
    """`tracks()` gives an empty row above or between the cards a track, so the lattice keeps every
    row up to the last occupied one, empty or not."""

    def test_a_leading_empty_row_keeps_its_place(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                layout, _ = planned(LEADING, mode)
                self.assertEqual(max(r for r, _ in layout["cells"].values()), 1, "harness: the cards moved")
                self.assertEqual(layout["grid_rows"], 2)
                # and a line does run along the empty row, whose own cells are lattice row Y = 1
                self.assertTrue(any(p[1] == 1 for e in layout["edges"] for p in e["path"]))

    def test_the_warning_names_every_empty_row_of_the_grid(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                _, warnings = planned(LEADING, mode)
                self.assertIn("пустые ряды в grid: [0, 2]", warnings)


class AnAppendedEmptyRowChangesNothing(unittest.TestCase):
    """The property that matters: a row the page never creates must not change the drawing."""

    # a model whose lines use the gutter under its last card row, which an appended row turned into
    # an inner gutter with room for eight
    TIGHT = {"kind": "flow", "nodes": [step(i) for i in "abcdef"], "grid": ["a b c", "d e f"],
             "edges": ["a -> c", "d -> f", "a -> d", "c -> f", "d -> c"]}

    def test_a_model_whose_lines_reach_its_last_row(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(drawing(self.TIGHT, mode), drawing(with_a_row_appended(self.TIGHT), mode))

    def test_the_shipped_examples(self):
        found = bench_routing.examples()
        self.assertEqual({m["kind"] for _, m in found}, set(flow.MODES), "harness: a kind lost its example")
        for path, model in found:
            for mode in bench_routing.MODES:
                with self.subTest(example=path.name, mode=mode):
                    self.assertEqual(drawing(model, mode), drawing(with_a_row_appended(model), mode))


class TheLaneSpansTheRowsThatAreDrawn(unittest.TestCase):
    """`grid_rows` is the trimmed count, and a swimlane's lane background is drawn from it: the lane
    ends with the last card row, where the tracks and the lattice end, not under an empty row left
    at the foot of the grid. No shipped example has such a row, so no shipped lane moves."""

    def test_the_lane_of_a_swimlane_with_a_trailing_empty_row(self):
        model = json.loads(json.dumps(TRAILING["swimlane"]))
        layout, warnings = flow.plan(model, "page", draft=True)
        html = flow.render(model, "page", layout, warnings, assets_mode="none")
        self.assertEqual(html.count("grid-row:1 / span 2"), len(model["lanes"]))
        self.assertNotIn("span 3", html)


if __name__ == "__main__":
    unittest.main()
