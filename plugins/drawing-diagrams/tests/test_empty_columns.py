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
   the cards as well: case 7 draws each of them where it changes a coordinate.
6. Schema (schema.js gx reads the same tracks): two tables stacked in one column beside an empty
   grid column — first, several leading, internal on either side, trailing — send their line down
   the gutter between them (schema.plan via GL/GR). The gutter is drawn at the middle of the CSS
   track edges on either side, unscaled and inside the same transform. route right/left run
   outside the outermost column, which then holds both tables, so they never border an empty column.
7. The atlas: one page of flow and schema diagrams, drawn unscaled and inside `transform:scale(0.5)`
   and `scale(1.5)`, held by the comparison of case 5. Between them its diagrams reach every place of
   template/js where a measured rectangle, a computed-style length or a drawing constant enters a
   drawn coordinate, each where it changes that coordinate: slot offsets across and down, straight
   exits up and down, the three label references, all four outer margins with M taken from the
   padding, from its floor and from its fallback, the row line of a leading and of an interior empty
   row, a row band taller than 16 px whose middle is not its row's, lines held by a band's 10 px inset
   (among them a run between two bends on a band under 30 px, where a 20 px threshold taken in screen
   px at scale 1.5 would not hold it; next to a line's ends clampY holds the same range), both
   endpoint clamps bound on either side at either end, and schema's outer routes, inner and outer
   gutters, adjacent and vertical routes, each with a slot offset. ATLAS names what each diagram is
   there for and the unscaled page is asserted to reach it -- from the payload the page was given
   and the cards it measured -- so a model edit that drops a member fails instead of leaving it
   undrawn; every line is drawn with its arrowhead or end markers and its label at every scale.
   clamp-x, clamp-y, row-clamp-threshold and schema-vertical are drawing-layer payloads, not plans:
   on these pages a planned side exit's row band, never taller than its card, already holds it 10 px
   inside the card, a straight exit leaves its column's centre by a slot offset of a few px, no
   planned run between bends lies off a band under 30 px, and schema.plan attaches no line to a
   table's top or bottom. The row band's 16 px threshold is compared in no scaled test:
   every band these pages measure is a whole card high, 28.6 px or more, over 16 px at either scale.
"""
import json
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
  var o={k:r.width/grid.offsetWidth,ow:grid.offsetWidth,padl:getComputedStyle(sec).getPropertyValue('--dg-padl'),
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


def table(tid, *columns):
    return {"id": tid, "name": tid, "group": "g",
            "columns": [{"name": col, "flags": [flag]} for col, flag in columns]}


def schema_model(name, grid, tables, edges):
    return {"kind": "schema", "id": name, "groups": {"g": {"label": "G", "ramp": "teal"}},
            "tables": tables, "grid": list(grid), "edges": edges}


def schema_fixture(case):
    name, grid, _ = case
    tables = [table("a", ("id", "PK")), table("b", ("id", "PK"), ("a_id", "FK"))]
    if any("c" in row.split() for row in grid):
        tables.append(table("c", ("id", "PK")))
    return schema_model(f"schema-{name}", grid, tables, ["b.a_id -> a.id"])


# Case 7 (docstring): the atlas, one page drawn at each of ATLAS_SCALES.
ATLAS_SCALES = (1, SCALE, 1.5)
ATLAS_CONFIGS = tuple(("atlas", "page", None, scale) for scale in ATLAS_SCALES)
FAR = 1000  # px: a slot offset past any card, so that the endpoint clamp of the line has to bind
EDGES_RE = re.compile(r'(<script type="application/json" class="dg-edges">)(.*?)(</script>)', re.S)
PADL_RE = re.compile(r'(<section class="dg"[^>]*?--dg-padl:)[\d.]+px')
# flow.js takes a line's y on a row line into its band this far inside the band's top and bottom
# (rowY) and a side exit's y this far inside its card (clampY); a straight exit's x this far inside
# its card (clampX). A reach is counted where a drawn point stands on one of these bounds.
ROW_IN, SIDE_IN, END_IN = 10, 10, 12
BAND_MID = 16  # px: flow.js takes a row line's base from the band of its side exits over this height
BAND_CLAMP = 20  # px: and holds the lines on it inside the band from this height


def two_by_two(edges):
    return {"kind": "flow", "nodes": [browser.step(i) for i in "abcd"], "grid": ["a b", "c d"],
            "edges": edges}


def far_across(edges):
    """clamp-x: the slot offsets of each line's run between its two straight exits pushed FAR past
    both cards, the first line's rightwards out of its source and leftwards into its target, the
    second's the other way round."""
    for e, sign in zip(edges, (1, -1)):
        e["path"][1][2], e["path"][2][2] = sign * FAR, -sign * FAR
    return edges


def along_margins(edges):
    """clamp-y: each line leaves and enters its cards sideways along an outer margin, Y = 0 over the
    grid or Y = 4 under it, instead of along its cards' row lines."""
    for e, (out, into) in zip(edges, ((0, 4), (4, 0))):
        for i, p in enumerate(e["path"]):
            p[1] = out if i < 2 else into
    return edges


def off_the_band(edges):
    """row-clamp-threshold: c -> d runs between its bends along the row line of a and b, whose band
    a -> b makes one title-only card high, and that run is put 12 px above the band's middle. Only
    rowY holds such a run: clampY holds just the point next to either end, and there to its card."""
    for p in edges[1]["path"][2:4]:
        p[3] = -12
    return edges


def top_to_bottom(edges):
    """schema-vertical: the line leaves the bottom of a table and enters the top of the other,
    attached to no column, with a slot offset."""
    edges[0].update(a=["a", None, "B"], b=["b", None, "T"], via=None, off=4)
    return edges


def keyed(tid, *names):
    return table(tid, *((n, "PK" if i == 0 else "U") for i, n in enumerate(names)))


def referring(tid, count):
    return table(tid, *((f"x{i}", "FK") for i in range(1, count + 1)))


EXAMPLE = {path.stem: json.loads(path.read_text()) for path in browser.EXAMPLES.rglob("*.json")}
PARALLEL = ["b.x1 -> a.k1", "b.x2 -> a.k2", "b.x3 -> a.k1", "b.x4 -> a.k2"]
# name: (planner module, model, hand paths or None, payload edit or None, --dg-padl in px or None,
# the members the diagram is drawn for). A payload edit changes the edge JSON the page draws from;
# a --dg-padl changes the section's own padding and with it the M flow.js and schema.js read.
ATLAS = {
    "four-blocks": (flow, EXAMPLE["four-blocks"], None, None, None,
                    {"slot x", "slot y", "exit up/down", "label p", "label m", "label r"}),
    "reported": (flow, browser.REPORTED, None, None, None, {"row band"}),
    "two-point-side-miss": (flow, browser.CASES["two-point-side-miss"], None, None, None,
                            {"row clamp"}),
    "row-clamp-threshold": (flow, two_by_two(["a -> b", "c -> d"]),
                            [[(1, 1), (3, 1)], [(1, 3), (2, 3), (2, 1), (4, 1), (4, 3), (3, 3)]],
                            off_the_band, None, {"row clamp threshold"}),
    "empty-band-1": (flow, *browser.EMPTY_BANDS["empty-band-1-flow"], None, None,
                     {"empty row leading", "empty row between"}),
    "margins": (flow, {**browser.MARGINS["margin-flow"][0],
                       "edges": browser.MARGINS["margin-flow"][0]["edges"] + ["a -> c", "b -> d"]},
                browser.MARGIN_PATHS
                + [[(1, 1), (0, 1), (0, 3), (1, 3)], [(3, 1), (4, 1), (4, 3), (3, 3)]], None, None,
                {"margin top", "margin bottom", "margin left", "margin right", "flow M padding"}),
    "margins-floor": (flow, browser.MARGINS["margin-flow"][0], browser.MARGIN_PATHS, None, 10,
                      {"margin top", "margin bottom", "flow M floor"}),
    "margins-fallback": (flow, browser.MARGINS["margin-flow"][0], browser.MARGIN_PATHS, None, 0,
                         {"margin top", "margin bottom", "flow M fallback"}),
    "clamp-x": (flow, two_by_two(["a -> d", "b -> c"]),
                [[(1, 1), (1, 2), (3, 2), (3, 3)], [(3, 1), (3, 2), (1, 2), (1, 3)]], far_across, None,
                {"clamp x source left", "clamp x source right", "clamp x target left",
                 "clamp x target right"}),
    "clamp-y": (flow, two_by_two(["a -> d", "c -> b"]),
                [[(1, 1), (2, 1), (2, 3), (3, 3)], [(1, 3), (2, 3), (2, 1), (3, 1)]], along_margins,
                None, {"clamp y source top", "clamp y source bottom", "clamp y target top",
                       "clamp y target bottom"}),
    "schema-small": (schema, EXAMPLE["schema-small"], None, None, None, {"adjacent"}),
    "schema-outer": (schema, schema_model("", ("a", "b"), [keyed("a", "id", "k"), referring("b", 4)],
                                          ["b.x1 -> a.id | right", "b.x2 -> a.k | right",
                                           "b.x3 -> a.id | left", "b.x4 -> a.k | left"]),
                     None, None, None, {"outer right off", "outer left off", "schema M padding"}),
    "schema-outer-floor": (schema, schema_model("", ("a", "b"), [keyed("a", "id"), referring("b", 2)],
                                                ["b.x1 -> a.id | right", "b.x2 -> a.id | left"]),
                           None, None, 10, {"outer right", "outer left", "schema M floor"}),
    "schema-outer-fallback": (schema, schema_model("", ("a", "b"), [keyed("a", "id"), referring("b", 2)],
                                                   ["b.x1 -> a.id | right", "b.x2 -> a.id | left"]),
                              None, None, 0, {"outer right", "outer left", "schema M fallback"}),
    "schema-adjacent": (schema, schema_model("", ("a b",), [keyed("a", "k1", "k2"), keyed("b", "k1", "k2")],
                                             ["a.k1 -> b.k2", "a.k2 -> b.k1"]),
                        None, None, None, {"adjacent off"}),
    "schema-gutters-left": (schema, schema_model("", (". a", ". b"), [keyed("a", "k1", "k2"),
                                                                      referring("b", 4)], PARALLEL),
                            None, None, None, {"inner gutter off", "outer gutter off"}),
    "schema-gutters-right": (schema, schema_model("", ("a .", "b ."), [keyed("a", "k1", "k2"),
                                                                       referring("b", 4)], PARALLEL),
                             None, None, None, {"inner gutter off", "outer gutter off"}),
    "schema-vertical": (schema, schema_model("", ("a b",), [keyed("a", "id"), referring("b", 1)],
                                             ["b.x1 -> a.id"]),
                        None, top_to_bottom, None, {"vertical off"}),
}
# Every member case 7 names, by the place of template/js it stands for; the diagrams of ATLAS are
# drawn for them all between them.
MEMBERS = frozenset({
    "slot x", "slot y",  # flow.js: bx(p[0]) + p[2], rowY(p[1], p[3])
    "exit up/down",  # flow.js: anchor() and clampX() of a straight exit
    "label p", "label m", "label r",  # flow.js: the label's y reference, then A[3] and A[4]
    "margin left", "margin right", "margin top", "margin bottom",  # flow.js: bx() and by() +- M
    "flow M padding", "flow M floor", "flow M fallback",  # flow.js: max(8, (--dg-padl || 14) - 6)
    "empty row leading", "empty row between",  # head.js tracks(): rows[dn].t - 20, the midpoint
    "row band", "row clamp", "row clamp threshold",  # flow.js: ov, base() over 16, rowY() from 20
    "clamp x source left", "clamp x source right", "clamp x target left", "clamp x target right",
    "clamp y source top", "clamp y source bottom", "clamp y target top", "clamp y target bottom",
    "outer right", "outer right off", "outer left", "outer left off",  # schema.js: via R and L
    "inner gutter off", "outer gutter off",  # schema.js: gx() both arms, + off
    "adjacent", "adjacent off", "vertical off",  # schema.js: mx and my, + off
    "schema M padding", "schema M floor", "schema M fallback",  # schema.js: its own M
})


def render_atlas(page, scale):
    """Write the atlas page; returns {name: (layout, the edge payload the page draws from)}."""
    args = render.parse_args([str(page), "--mode", "page", "--assets", "inline"])
    drawn, fragments = {}, []
    for name, (mod, model, paths, edit, padl, _) in ATLAS.items():
        model = {**json.loads(json.dumps(model)), "id": name}
        if paths is None:
            out, _, layout = render.produce(model, mod, args, {}, "inline")
        else:
            given = [[tuple(pt) for pt in p] for p in paths]
            with mock.patch.object(router, "route_all", lambda lat, ends, labelled, **kw: given), \
                    mock.patch.object(router, "overfull", lambda paths, nodes, room: []):
                out, _, layout = render.produce(model, mod, args, {}, "inline")
        edges = json.loads(EDGES_RE.search(out).group(2))
        if edit is not None:
            edges = edit(edges)
            text = json.dumps(edges, ensure_ascii=False).replace("</", "<\\/")
            out = EDGES_RE.sub(lambda m: m.group(1) + text + m.group(3), out, count=1)
        if padl is not None:
            out, n = PADL_RE.subn(lambda m: f"{m.group(1)}{padl}px", out, count=1)
            assert n == 1, name
        drawn[name] = (layout, edges)
        fragments.append(out)
    write_page(page, fragments, scale)
    return drawn


def margin_member(kind, got):
    """The branch of M = max(8, (--dg-padl || 14) - 6) the page took for a diagram of `kind`."""
    padl = float(got["padl"].strip().replace("px", "") or 0)
    return f"{kind} M " + ("fallback" if padl == 0 else "floor" if padl - 6 < 8 else "padding")


def flow_reach(layout, edges, got):
    """The members of case 7 a flow diagram reaches, from the payload it was drawn from and the cards
    and lines of its unscaled page, whose px are the grid's own."""
    cards, lines = got["cards"], [browser.polyline(d or "") for _, d in got["lines"]]
    rows = {}
    for nid, (r, _) in layout["cells"].items():
        top, bottom = cards[nid][1], cards[nid][3]
        rows[r] = (min(top, rows[r][0]), max(bottom, rows[r][1])) if r in rows else (top, bottom)
    bands = {}
    for e in edges:
        for side, nid, Y in ((e["sa"], e["a"], e["path"][0][1]), (e["sb"], e["b"], e["path"][-1][1])):
            if side in ("L", "R"):
                top, bottom = cards[nid][1], cards[nid][3]
                bands[Y] = (max(top, bands[Y][0]), min(bottom, bands[Y][1])) if Y in bands else (top, bottom)
    R, C, found = max(rows) + 1, layout["grid_cols"], set()
    for e, points in zip(edges, lines):
        path = e["path"]
        found |= {"slot x"} if any(p[2] for p in path[1:-1]) else set()
        found |= {"slot y"} if any(p[3] for p in path[1:-1]) else set()
        found |= {"exit up/down"} if {e["sa"], e["sb"]} & {"T", "B"} else set()
        found |= {f"label {e['la'][1]}"} if e.get("la") else set()
        for i, (X, Y, _, oy) in enumerate(path):
            found |= {m for m, hit in (("margin left", X == 0), ("margin right", X == 2 * C),
                                       ("margin top", Y == 0), ("margin bottom", Y == 2 * R)) if hit}
            if Y % 2 == 1 and (Y - 1) // 2 not in rows:
                found.add("empty row between" if min(rows) < (Y - 1) // 2 else "empty row leading")
            band = bands.get(Y) if Y % 2 == 1 else None
            if band is None:
                continue
            top, bottom = band
            middle, row = (top + bottom) / 2, sum(rows[(Y - 1) // 2]) / 2
            if bottom - top > BAND_MID and abs(middle - row) > 1:
                found.add("row band")
            y = (middle if bottom - top > BAND_MID else row) + oy
            if bottom - top >= BAND_CLAMP and not top + ROW_IN - 1 < y < bottom - ROW_IN + 1:
                found.add("row clamp")
                # a run between the bends, which only rowY holds, on a band a threshold of 20 screen
                # px at the largest scale would leave unclamped
                if 1 < i < len(path) - 2 and bottom - top < BAND_CLAMP * max(ATLAS_SCALES):
                    found.add("row clamp threshold")
        if len(points) != len(path):
            continue
        for end, nid, side, i in (("source", e["a"], e["sa"], 1), ("target", e["b"], e["sb"], -2)):
            left, top, right, bottom = cards[nid]
            x, y = points[i]
            if side in ("T", "B") and abs(path[i][2]) > right - left:
                for bound, at in (("left", left + END_IN), ("right", right - END_IN)):
                    found |= {f"clamp x {end} {bound}"} if abs(x - at) < TOL else set()
            if side in ("L", "R") and path[i][1] != 2 * layout["cells"][nid][0] + 1:
                for bound, at in (("top", top + SIDE_IN), ("bottom", bottom - SIDE_IN)):
                    found |= {f"clamp y {end} {bound}"} if abs(y - at) < TOL else set()
    if found & {"margin left", "margin right", "margin top", "margin bottom"}:
        found.add(margin_member("flow", got))
    return found


def schema_reach(layout, edges, got):
    """The members of case 7 a schema diagram reaches: the routing arm of schema.js each line takes,
    with ` off` where it carries a slot offset, and the branch of M under an outer route."""
    found = set()
    for e in edges:
        via, col = e.get("via"), layout["cells"][e["a"][0]][1]
        if via in ("R", "L"):
            arm = "outer right" if via == "R" else "outer left"
        elif via in ("GR", "GL"):
            outer = col + 1 == layout["grid_cols"] if via == "GR" else col == 0
            arm = "outer gutter" if outer else "inner gutter"
        else:
            arm = "vertical" if e["a"][2] in ("T", "B") else "adjacent"
        found |= {arm, f"{arm} off"} if e.get("off") else {arm}
    if found & {"outer right", "outer left", "outer gutter"}:
        found.add(margin_member("schema", got))
    return found


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
        cls.layouts, cls.schema_layouts, cls.atlas, cls.results, jobs = {}, {}, {}, {}, {}
        for key in FLOW_CONFIGS + SCHEMA_CONFIGS + ATLAS_CONFIGS:
            kind, mode, width, scale = key
            page = Path(tmp.name) / f"{kind}-{mode}-{width}-{scale}.html"
            if kind == "atlas":
                cls.atlas[key] = render_atlas(page, scale)
            elif kind == "schema":
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
        for key in FLOW_CONFIGS + SCHEMA_CONFIGS + ATLAS_CONFIGS:
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

    def test_the_atlas_reaches_every_member_it_is_drawn_for(self):
        self.assertEqual(frozenset().union(*(spec[-1] for spec in ATLAS.values())), MEMBERS)
        for key in ATLAS_CONFIGS:
            result = self.results[key]
            with self.subTest(configuration=key):
                self.assertNotIsInstance(result, Exception, f"browser unavailable: {result}")
                self.assertEqual(result["errors"], [], "browser errors during drawing")
                self.assertEqual(set(result["diagrams"]), set(ATLAS))
            if isinstance(result, Exception):
                continue
            for name, (layout, edges) in self.atlas[key].items():
                got = result["diagrams"].get(name)
                if got is None:
                    continue
                with self.subTest(configuration=key, diagram=name):
                    # every line is drawn, with its arrowhead or its two end markers and its label
                    self.assertEqual(len(got["shapes"]), len(edges))
                    for e, (_, shapes) in zip(edges, got["shapes"]):
                        tags = [s[0] for s in shapes]
                        if ATLAS[name][0] is flow:
                            want = ["path", "path"] + (["text"] if e.get("label") else [])
                        else:
                            want = ["path"] + [{"one": "circle", "many": "path"}[m]
                                               for m in (e["ae"], e["be"]) if m in ("one", "many")]
                        self.assertEqual(tags, want)
                        self.assertTrue(shapes[0][2], "empty path")
                    if key[3] != 1:
                        continue
                    reach = flow_reach if ATLAS[name][0] is flow else schema_reach
                    found = reach(layout, edges, got)
                    self.assertLessEqual(ATLAS[name][-1], found,
                                         f"{name} no longer reaches {sorted(ATLAS[name][-1] - found)}")

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
