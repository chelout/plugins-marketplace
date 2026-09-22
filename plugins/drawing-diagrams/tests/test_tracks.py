"""Focused arithmetic checks for missing browser tracks; browser layout is tested separately."""
import json
import re
import shutil
import subprocess
import unittest

import support


NODE = shutil.which("node")
JS = support.SKILL / "template" / "js"
GRID = {"left": 101, "top": 203, "width": 1400, "height": 600}  # the grid's box, in layout px


def function_source(path, name):
    """The text of `function name(){...}` in `path` through its matching closing brace, skipping
    braces inside string literals; ValueError when the file defines no such function."""
    source = path.read_text()
    start = source.index(f"function {name}(")
    depth, i, quote = 0, source.index("{", start), None
    while True:
        ch = source[i]
        if quote:
            quote = None if ch == quote else quote
            i += 2 if ch == "\\" else 1
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1


def with_callees(path, name):
    """`name` of `path` and every function of the same file it calls, each exactly once."""
    source, out, todo = path.read_text(), {}, [name]
    while todo:
        fn = todo.pop()
        if fn in out:
            continue
        out[fn] = function_source(path, fn)
        todo += [c for c in re.findall(r"\b([A-Za-z_$][\w$]*)\(", out[fn])
                 if c != fn and f"function {c}(" in source]
    return list(out.values())


@unittest.skipUnless(NODE, "node is not installed")
class MissingColumnTracks(unittest.TestCase):
    def tracks(self, widths, cards, k=1):
        """tracks() as the page's draw() calls it, on a grid inside an ancestor transform scale(k):
        every bounding rectangle is k times its layout box, while offsetWidth and computed style stay
        in layout px. Only draw() of draw.js and tracks() of head.js with the functions it calls run;
        the harness stands in for the rest of the page."""
        functions = [function_source(JS / "draw.js", "draw")] + with_callees(JS / "head.js", "tracks")
        harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const g = input.grid, s = input.k;
var rr, k = 1, drawKind = {}, out;
drawKind.flow = function () { out = tracks(); };
const svg = {firstChild: null, setAttribute: () => {}, removeChild: () => {}};
const sec = {getAttribute: () => 'flow'};
const grid = {
  offsetWidth: g.width,
  getBoundingClientRect: () => ({left: g.left, top: g.top, width: g.width * s, height: g.height * s,
                                 right: g.left + g.width * s, bottom: g.top + g.height * s}),
  querySelectorAll: () => input.cards.map(c => ({
    getAttribute: name => name === 'data-c' ? c.col : c.row,
    getBoundingClientRect: () => ({left: g.left + c.l * s, right: g.left + c.r * s,
                                  top: g.top + c.t * s, bottom: g.top + c.b * s,
                                  width: (c.r - c.l) * s, height: (c.b - c.t) * s})
  }))
};
function getComputedStyle(element) {
  return element === grid ? {
    gridTemplateColumns: input.widths.map(w => w + 'px').join(' '),
    columnGap: '31.5px', paddingLeft: '38.25px'
  } : {getPropertyValue: name => ({'--dg-cols': input.widths.length,
                                 '--dg-gap': '31.5px'})[name]};
}
"""
        script = harness + "\n".join(functions) + "\ndraw();\nconsole.log(JSON.stringify(out));"
        result = subprocess.run([NODE, "-e", script],
                                input=json.dumps({"widths": widths, "cards": cards, "grid": GRID, "k": k}),
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_missing_tracks_use_resolved_grid_widths_and_origin(self):
        # Several leading holes plus an internal and trailing hole. Unequal resolved widths also
        # guard the shared schema renderer against assuming every track has the first width.
        result = self.tracks([173.5, 210, 180, 192.25, 205, 160], [
            {"col": 2, "row": 0, "l": 484.75, "r": 664.75, "t": 8, "b": 48},
            {"col": 4, "row": 0, "l": 920, "r": 1125, "t": 8, "b": 48},
        ])
        self.assertEqual(result["cols"], {
            "0": {"l": 38.25, "r": 211.75},
            "1": {"l": 243.25, "r": 453.25},
            "2": {"l": 484.75, "r": 664.75},
            "3": {"l": 696.25, "r": 888.5},
            "4": {"l": 920, "r": 1125},
            "5": {"l": 1156.5, "r": 1316.5},
        })
        self.assertEqual(result["C"], 6)

    def test_measured_bounds_and_empty_rows_are_preserved(self):
        result = self.tracks([173.5] * 3, [
            {"col": 1, "row": 1, "l": 244, "r": 416, "t": 8, "b": 48},
            {"col": 1, "row": 3, "l": 243.75, "r": 417.25, "t": 140, "b": 185},
        ])
        self.assertEqual(result["cols"]["1"], {"l": 243.75, "r": 417.25})
        self.assertEqual(result["rows"], {
            "0": {"t": -12, "b": -12}, "1": {"t": 8, "b": 48},
            "2": {"t": 94, "b": 94}, "3": {"t": 140, "b": 185},
        })
        self.assertEqual(result["R"], 4)

    def test_a_scaled_grid_yields_the_same_local_tracks(self):
        # Under an ancestor scale(k) the measured card rectangles shrink with the grid's box while
        # the CSS track list, gap and padding do not: both must land in the grid's own layout px,
        # so measured and empty columns, and the rows placed 20 px beyond a card, are the unscaled ones.
        widths = [173.5, 210, 180, 192.25, 205, 160]
        cards = [{"col": 2, "row": 1, "l": 484.75, "r": 664.75, "t": 8, "b": 48},
                 {"col": 4, "row": 3, "l": 920, "r": 1125, "t": 140, "b": 185}]
        expected = {
            "cols": {"0": {"l": 38.25, "r": 211.75}, "1": {"l": 243.25, "r": 453.25},
                     "2": {"l": 484.75, "r": 664.75}, "3": {"l": 696.25, "r": 888.5},
                     "4": {"l": 920, "r": 1125}, "5": {"l": 1156.5, "r": 1316.5}},
            "rows": {"0": {"t": -12, "b": -12}, "1": {"t": 8, "b": 48},
                     "2": {"t": 94, "b": 94}, "3": {"t": 140, "b": 185}},
        }
        for k in (1, 0.5, 0.75, 1.5):
            with self.subTest(k=k):
                result = self.tracks(widths, cards, k)
                self.assertEqual((result["C"], result["R"]), (6, 4))
                for axis, ends in (("cols", "lr"), ("rows", "tb")):
                    self.assertEqual(set(result[axis]), set(expected[axis]))
                    for index, box in expected[axis].items():
                        for end in ends:
                            self.assertAlmostEqual(result[axis][index][end], box[end], places=9,
                                                   msg=f"{axis}[{index}].{end} at k = {k}")

if __name__ == "__main__":
    unittest.main()
