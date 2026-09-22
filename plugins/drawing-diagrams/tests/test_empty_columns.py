"""Browser acceptance for the uniform explicit grid, derived before implementation.

1. Empty first, several leading, internal and trailing columns still occupy equal
   CSS tracks. Real card edges and routed gutter centrelines agree with Python
   Geometry, in flow/swimlane, widget/page and at a non-default width.
2. Label anchors attached to those routed lines have the same x coordinate as
   Geometry and the rendered SVG; every edge and label must actually be drawn.
3. An occupied-column control and an empty-row combination retain their geometry.
4. Browser absence may skip; failed launches and browser errors fail the test.
5. The same CASES inside an ancestor `transform:scale(0.5)` (flow and swimlane, page mode, default
   width): the page measures k = 0.5 as the grid's bounding width over its offsetWidth and card edges
   stand on screen at k times the CSS track edges. The script draws in the grid's own layout px (the
   SVG viewBox is the grid's layout size, every measured rectangle is taken back to it), so the drawn
   SVG content -- viewBox, every path d with its arrowheads and markers, every label's x, y and
   text-anchor -- is the unscaled page's within TOL and agrees with Geometry exactly as there, while
   on screen the SVG box and the box of every line, arrowhead, marker and label, with its offset from
   the grid, is k times the unscaled page's (a label's top and height within the whole px to which
   the browser rounds font metrics at the size it renders). The outer margin M, the router's slot
   offsets, the label offsets and the clamp insets are all drawn in those units, so they scale with
   the cards as well.
6. Schema (schema.js gx reads the same tracks): two tables stacked in one column beside an empty
   grid column — first, several leading, internal on either side, trailing — send their line down
   the gutter between them (schema.plan via GL/GR). The gutter is drawn at the middle of the CSS
   track edges on either side, unscaled and inside the same transform. route right/left run
   outside the outermost column, which then holds both tables, so they never border an empty column.
"""
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import support
import render
import test_browser_lines as browser
from diagrams import flow, router, schema


# name, column count, source column, target column, source row, target row,
# total rows, lattice x coordinates to measure. Odd x is a column centre;
# even x is a gutter or an outer margin. Leading/trailing empty rows accompany
# an empty column in the final case, so preserving rows is exercised too.
CASES = (
    ("first", 2, 1, 1, 0, 1, 2, (0, 1, 2)),
    ("leading", 3, 2, 2, 0, 1, 2, (0, 1, 2, 3, 4)),
    ("internal", 3, 0, 2, 0, 1, 2, (2, 3, 4)),
    ("trailing", 2, 0, 0, 0, 1, 2, (2, 3, 4)),
    ("occupied", 2, 0, 1, 0, 1, 2, (2,)),
    ("empty-rows", 2, 1, 1, 1, 3, 5, (0, 1, 2)),
)
TOL = 0.1  # CSS subpixel rounding, in the grid's layout px (the SVG's user units)
SCALE = 0.5  # the ancestor transform of the scaled configurations
# Screen px: the browser rounds a font's ascent and descent to whole px at the size it renders it, so
# a label's line box at scale 0.5 is 6 px high where half the unscaled 13 would be 6.5.
FONT_TOL = 1.0

# kind, mode, total width (None: the mode's default), ancestor scale (1: none). One page each.
FLOW_CONFIGS = tuple((kind, mode, width, 1) for kind in ("flow", "swimlane")
                     for mode in ("widget", "page") for width in (None, 913)) + (
    ("flow", "page", None, SCALE), ("swimlane", "page", None, SCALE))
SCHEMA_CONFIGS = (("schema", "page", None, 1), ("schema", "page", None, SCALE))

# name, grid, side of column(a) whose gutter the line b.a_id -> a.id of the stacked tables a and b
# takes. The column across that gutter holds no table; c only makes an internal column internal.
SCHEMA_CASES = (
    ("first", (". a", ". b"), "L"),
    ("leading", (". . a", ". . b"), "L"),
    ("internal-right", ("a . c", "b . ."), "R"),
    ("internal-left", ("c . a", ". . b"), "L"),
    ("trailing", ("a .", "b ."), "R"),
)

ERROR_CAPTURE = """<script>
window.columnErrors=[];
window.addEventListener('error',function(e){columnErrors.push(e.message||'resource error')},true);
window.addEventListener('unhandledrejection',function(e){columnErrors.push(String(e.reason))});
var columnConsoleError=console.error;
console.error=function(){columnErrors.push(Array.from(arguments).join(' '));
  columnConsoleError.apply(console,arguments)};
</script>"""

# Observe only the rendered DOM. No renderer functions are exposed or replaced.
PROBE = """<script>setTimeout(function(){
var result={errors:window.columnErrors,diagrams:{}};
document.querySelectorAll('.dg').forEach(function(sec){
  var grid=sec.querySelector('.dg-grid'),svg=sec.querySelector('.dg-svg');
  var r=grid.getBoundingClientRect(),css=getComputedStyle(grid);
  var s=svg.getBoundingClientRect();
  var o={k:r.width/grid.offsetWidth,ow:grid.offsetWidth,
    tracks:css.gridTemplateColumns.split(' ').map(parseFloat),
    gap:parseFloat(css.columnGap),padding:parseFloat(css.paddingLeft),cards:{},lines:[],texts:[],
    view:(svg.getAttribute('viewBox')||'').split(' ').map(Number),svgbox:[s.width,s.height],
    shapes:[],boxes:[]};
  sec.querySelectorAll('.dg-c[data-t]').forEach(function(card){
    var b=card.getBoundingClientRect();
    o.cards[card.getAttribute('data-t')]=[b.left-r.left,b.top-r.top,b.right-r.left,b.bottom-r.top];
  });
  svg.querySelectorAll(':scope > g').forEach(function(g){
    var p=g.querySelector('path'),t=g.querySelector('text');
    o.lines.push([g.getAttribute('data-e'),p?p.getAttribute('d'):null]);
    o.texts.push(t?[+t.getAttribute('x'),+t.getAttribute('y'),t.getAttribute('text-anchor')]:null);
    var kids=Array.prototype.slice.call(g.children);
    o.shapes.push([g.getAttribute('data-e'),kids.map(function(el){var n=el.tagName,c=el.getAttribute('class');
      return n==='path'?[n,c,el.getAttribute('d')]:n==='circle'?[n,c,+el.getAttribute('cx'),
        +el.getAttribute('cy'),+el.getAttribute('r')]:[n,c,+el.getAttribute('x'),+el.getAttribute('y'),
        el.getAttribute('text-anchor'),el.textContent]})]);
    o.boxes.push(kids.map(function(el){var b=el.getBoundingClientRect();
      return[el.tagName,b.left-r.left,b.top-r.top,b.width,b.height]}));
  });
  result.diagrams[sec.getAttribute('data-dg')]=o;
});
var pre=document.createElement('pre');pre.id='probe';pre.textContent=JSON.stringify(result);
document.body.appendChild(pre);
},800)</script>"""


def fixture(kind, case, x):
    name, cols, ac, bc, ar, br, rows, _ = case
    cells = [["."] * cols for _ in range(rows)]
    cells[ar][ac], cells[br][bc] = "a", "b"
    groups = {f"g{c}": {"label": f"Lane {c}", "ramp": "teal"} for c in range(cols)}
    model = {"kind": kind, "id": f"{name}-{x}", "groups": groups,
             "nodes": [{"id": "a", "title": "A", "group": f"g{ac}"},
                       {"id": "b", "title": "B", "group": f"g{bc}"}],
             "grid": [" ".join(row) for row in cells], "edges": ["a -> b : x"]}
    if kind == "swimlane":
        model["lanes"] = list(groups)
    path = [(2 * ac + 1, 2 * ar + 1), (x, 2 * ar + 1),
            (x, 2 * br + 1), (2 * bc + 1, 2 * br + 1)]
    return model, path


def schema_fixture(case):
    name, grid, _ = case

    def table(tid, *columns):
        return {"id": tid, "name": tid, "group": "g",
                "columns": [{"name": col, "flags": [flag]} for col, flag in columns]}
    tables = [table("a", ("id", "PK")), table("b", ("id", "PK"), ("a_id", "FK"))]
    if any("c" in row.split() for row in grid):
        tables.append(table("c", ("id", "PK")))
    return {"kind": "schema", "id": f"schema-{name}", "groups": {"g": {"label": "G", "ramp": "teal"}},
            "tables": tables, "grid": list(grid), "edges": ["b.a_id -> a.id"]}


def write_page(page, fragments, scale):
    """The page of `fragments` with the error capture and the probe. With a scale other than 1 the
    fragments stand inside one ancestor that transforms them by it."""
    body = "\n".join(fragments)
    if scale != 1:
        body = f'<div style="transform:scale({scale});transform-origin:0 0">{body}</div>'
    page.write_text("<!doctype html><html><head><meta charset='utf-8'></head><body>"
                    + ERROR_CAPTURE + body + PROBE + "</body></html>")


def render_schema_cases(mode, page, scale):
    args = render.parse_args([str(page), "--mode", mode, "--assets", "inline"])
    layouts, fragments = {}, []
    for case in SCHEMA_CASES:
        model = schema_fixture(case)
        out, _, layout = render.produce(model, schema, args, {}, "inline")
        layouts[model["id"]] = layout
        fragments.append(out)
    write_page(page, fragments, scale)
    return layouts


def css_edges(got):
    """(left, right) of every CSS track in CSS px, from the track list, gap and padding the probe
    read from computed style; never from the page's own tracks()."""
    edges, x = [], got["padding"]
    for width in got["tracks"]:
        edges.append((x, x + width))
        x += width + got["gap"]
    return edges


def path_numbers(d):
    """(commands, numbers) of an SVG path d."""
    tokens = re.findall(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d or "")
    return ([t for t in tokens if t.isalpha()], [float(t) for t in tokens if not t.isalpha()])


def render_cases(kind, mode, width, page, scale=1):
    args = render.parse_args([str(page), "--mode", mode, "--assets", "inline"])
    overrides = {} if width is None else {"total": width}
    layouts, fragments = {}, []
    for case in CASES:
        for x in case[-1]:
            model, path = fixture(kind, case, x)
            # Hand routes measure every empty track even where route_all would
            # choose a nearer gutter. The production planner still computes
            # offsets, labels and the serialized drawing instructions.
            with mock.patch.object(router, "route_all", return_value=[path]):
                out, _, layout = render.produce(model, flow, args, overrides, "inline")
            layouts[model["id"]] = layout
            fragments.append(out)
    write_page(page, fragments, scale)
    return layouts


class EmptyColumnsBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chrome, reason = browser.find_chrome()
        if chrome is None:
            raise unittest.SkipTest(reason)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.layouts, cls.schema_layouts, cls.results, jobs = {}, {}, {}, {}
        for key in FLOW_CONFIGS + SCHEMA_CONFIGS:
            kind, mode, width, scale = key
            page = Path(tmp.name) / f"{kind}-{mode}-{width}-{scale}.html"
            if kind == "schema":
                cls.schema_layouts[key] = render_schema_cases(mode, page, scale)
            else:
                cls.layouts[key] = render_cases(kind, mode, width, page, scale)
            jobs[key] = page
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {key: pool.submit(browser.run_chrome, chrome, page) for key, page in jobs.items()}
            for key, future in futures.items():
                try:
                    cls.results[key] = future.result()
                except Exception as exc:  # a blocked browser is a failure, never a skip
                    cls.results[key] = exc

    def measured(self, configurations):
        for key, layouts in configurations.items():
            result = self.results[key]
            with self.subTest(configuration=key):
                self.assertNotIsInstance(result, Exception, f"browser unavailable: {result}")
                self.assertEqual(result["errors"], [], "browser errors during drawing")
                self.assertEqual(set(result["diagrams"]), set(layouts))
            if isinstance(result, Exception) or set(result["diagrams"]) != set(layouts):
                continue
            for name, layout in layouts.items():
                yield key, name, layout, result["diagrams"][name]

    def scale_of(self, key, got):
        """k the page measured for one diagram, held to the configured scale within TOL pixels."""
        self.assertAlmostEqual(got["k"] * got["ow"], key[3] * got["ow"], delta=TOL,
                               msg=f"k = {got['k']}: the ancestor transform {key[3]} did not apply")
        return got["k"]

    def test_css_cards_and_routed_columns_agree_with_geometry(self):
        for key, name, layout, got in self.measured(self.layouts):
            with self.subTest(configuration=key, diagram=name):
                k = self.scale_of(key, got)
                geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
                self.assertEqual(len(got["tracks"]), geo.cols)
                for track in got["tracks"]:
                    self.assertAlmostEqual(track, geo.w, delta=TOL)
                self.assertAlmostEqual(got["padding"], geo.pad_l, delta=TOL)
                self.assertAlmostEqual(got["gap"], geo.gap, delta=TOL)
                self.assertEqual(set(got["cards"]), {"a", "b"})
                edges = css_edges(got)
                for nid, box in got["cards"].items():
                    col = layout["cells"][nid][1]
                    self.assertAlmostEqual(box[0], k * edges[col][0], delta=TOL)
                    self.assertAlmostEqual(box[2], k * edges[col][1], delta=TOL)
                    self.assertAlmostEqual(box[0], k * geo.left(col), delta=TOL)
                    self.assertAlmostEqual(box[2], k * geo.right(col), delta=TOL)
                self.assertEqual([n for n, _ in got["lines"]], ["a b"])
                points = browser.polyline(got["lines"][0][1] or "")
                self.assertEqual(len(points), 4, "missing or collapsed routed segment")
                self.assertEqual(len(browser.runs(points)), 3)
                edge = layout["edges"][0]
                for index in (1, 2):
                    x, _, ox, _ = edge["path"][index]
                    self.assertAlmostEqual(points[index][0], geo.x(x) + ox, delta=TOL,
                                           msg=f"lattice x={x} disagrees with CSS/Python")
                # These side exits are centred on their real cards, whose screen box is k times
                # their layout box. This also guards empty rows without duplicating the row-band
                # algorithm.
                for index, nid in ((0, "a"), (3, "b")):
                    card = got["cards"][nid]
                    self.assertAlmostEqual(points[index][1], (card[1] + card[3]) / 2 / k, delta=TOL)

    def test_label_anchors_agree_with_geometry_and_drawn_path(self):
        for key, name, layout, got in self.measured(self.layouts):
            with self.subTest(configuration=key, diagram=name):
                k = self.scale_of(key, got)
                self.assertEqual([n for n, _ in got["lines"]], ["a b"])
                self.assertEqual(len(got["texts"]), 1)
                text = got["texts"][0]
                self.assertIsNotNone(text, "missing label")
                points = browser.polyline(got["lines"][0][1] or "")
                self.assertEqual(len(points), 4)
                edge = layout["edges"][0]
                pt, ref, row, dx, dy, anchor = edge["la"]
                self.assertIn(pt, (1, 2), "fixture must anchor on the measured empty track")
                geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
                x, _, ox, _ = edge["path"][pt]
                self.assertAlmostEqual(text[0], geo.x(x) + ox + dx, delta=TOL)
                self.assertAlmostEqual(text[0], points[pt][0] + dx, delta=TOL)
                bases = {edge["path"][i][1]: points[i][1] - edge["path"][i][3] for i in (1, 2)}
                ar, br = layout["cells"]["a"][0], layout["cells"]["b"][0]
                if br == ar + 1:
                    bases[2 * br] = (got["cards"]["a"][3] + got["cards"]["b"][1]) / 2 / k
                expected = browser.anchor_point(edge["la"], points, bases)
                self.assertIsNotNone(expected, f"unmeasured label row {row}, reference {ref}")
                self.assertAlmostEqual(text[1], expected[1], delta=TOL)
                self.assertEqual(text[2], anchor)

    def test_schema_gutter_beside_an_empty_column_follows_the_css_tracks(self):
        cases = {schema_fixture(case)["id"]: case for case in SCHEMA_CASES}
        for key, name, layout, got in self.measured(self.schema_layouts):
            with self.subTest(configuration=key, diagram=name):
                k = self.scale_of(key, got)
                side = cases[name][2]
                self.assertEqual(len(got["tracks"]), layout["grid_cols"])
                edges = css_edges(got)
                for nid, box in got["cards"].items():
                    col = layout["cells"][nid][1]
                    self.assertAlmostEqual(box[0], k * edges[col][0], delta=TOL)
                    self.assertAlmostEqual(box[2], k * edges[col][1], delta=TOL)
                self.assertEqual(len(layout["edges"]), 1)
                edge = layout["edges"][0]
                self.assertEqual(edge["via"], "G" + side, "fixture must route down the gutter it names")
                col = layout["cells"]["a"][1]
                across = col + 1 if side == "R" else col - 1
                self.assertNotIn(across, {c for _, c in layout["cells"].values()},
                                 "the column across the gutter must hold no table")
                gutter = (edges[min(col, across)][1] + edges[max(col, across)][0]) / 2
                self.assertEqual([n for n, _ in got["lines"]], ["b a"])
                points = browser.polyline(got["lines"][0][1] or "")
                self.assertEqual(len(points), 4, "missing or collapsed routed segment")
                self.assertEqual(len(browser.runs(points)), 3)
                for index in (1, 2):
                    self.assertAlmostEqual(points[index][0], gutter + edge["off"], delta=TOL,
                                           msg=f"gutter by empty column {across} disagrees with CSS")

    def test_a_scaled_page_draws_the_unscaled_drawing_k_times_on_screen(self):
        # The unscaled page of the same configuration is itself held to Geometry and the CSS track
        # list above; the scaled page must draw exactly it, and the transform alone scales it.
        for key in FLOW_CONFIGS + SCHEMA_CONFIGS:
            if key[3] == 1:
                continue
            base = key[:3] + (1,)
            scaled, unscaled = self.results[key], self.results[base]
            with self.subTest(configuration=key):
                for result in (scaled, unscaled):
                    self.assertNotIsInstance(result, Exception, f"browser unavailable: {result}")
                    self.assertEqual(result["errors"], [], "browser errors during drawing")
                self.assertEqual(set(scaled["diagrams"]), set(unscaled["diagrams"]))
            if isinstance(scaled, Exception) or isinstance(unscaled, Exception):
                continue
            for name, got in scaled["diagrams"].items():
                ref = unscaled["diagrams"].get(name)
                if ref is None:
                    continue
                with self.subTest(configuration=key, diagram=name):
                    k = self.scale_of(key, got)
                    self.assertEqual(len(got["view"]), 4)
                    for value, want in zip(got["view"], ref["view"]):
                        self.assertAlmostEqual(value, want, delta=TOL, msg="viewBox")
                    self.assertEqual([s[0] for s in got["shapes"]], [s[0] for s in ref["shapes"]])
                    self.assertTrue(ref["shapes"], "the unscaled page drew nothing")
                    for (edge, shapes), (_, want_shapes) in zip(got["shapes"], ref["shapes"]):
                        self.assertEqual([s[:2] for s in shapes], [s[:2] for s in want_shapes], edge)
                        for shape, want in zip(shapes, want_shapes):
                            self.assert_same_shape(edge, shape, want)
                    for value, want in zip(got["svgbox"], ref["svgbox"]):
                        self.assertAlmostEqual(value, k * want, delta=TOL, msg="SVG box on screen")
                    for (edge, _), boxes, want_boxes in zip(got["shapes"], got["boxes"], ref["boxes"]):
                        for box, want in zip(boxes, want_boxes):
                            for field, value, unscaled_value in zip(("left", "top", "width", "height"),
                                                                    box[1:], want[1:]):
                                font = box[0] == "text" and field in ("top", "height")
                                self.assertAlmostEqual(value, k * unscaled_value,
                                                       delta=FONT_TOL if font else TOL,
                                                       msg=f"{edge} {box[0]} {field} on screen")

    def assert_same_shape(self, edge, shape, want):
        """One drawn element of the scaled page against the unscaled page's, in SVG user units."""
        tag = shape[0]
        if tag == "path":
            got_cmds, got_nums = path_numbers(shape[2])
            want_cmds, want_nums = path_numbers(want[2])
            self.assertEqual(got_cmds, want_cmds, f"{edge} path commands")
            self.assertEqual(len(got_nums), len(want_nums), f"{edge} path length")
            for value, expected in zip(got_nums, want_nums):
                self.assertAlmostEqual(value, expected, delta=TOL, msg=f"{edge} {shape[1]} d")
            return
        numbers = (2, 3, 4) if tag == "circle" else (2, 3)
        for i in numbers:
            self.assertAlmostEqual(shape[i], want[i], delta=TOL, msg=f"{edge} {tag}[{i}]")
        self.assertEqual(shape[len(numbers) + 2:], want[len(numbers) + 2:], f"{edge} {tag}")


if __name__ == "__main__":
    unittest.main()
