"""Kinds `flow` (algorithm with decisions) and `swimlane` (steps by participant)."""
import collections
import json
import math
import re

from . import assets, labels, router
from .common import (BASE_MODES, ID_RE, RAMPS, ModelError, esc, fit_prefix, label_width, labels_for, text_width,
                     too_wide_word, wrap_lines)
from .grid import check_placement, empty_lines, parse_grid
# The label offsets, in one copy, beside the model that measures with them. Nothing here reads them
# any more — diagrams/labels.py places every label and emits the anchor that carries them to the
# script — but the tests that measure a drawn label reach them under this name.
from .labels import (LABEL_ABOVE, LABEL_BELOW, LABEL_BEND, LABEL_BESIDE, LABEL_CLEAR, LABEL_DROP,
                     LABEL_LIFT, LABEL_OVER, LABEL_SIDE, LABEL_SINK, LABEL_UNDER, LABEL_WORD,
                     LINE_REACH)

MODES = {
    "state": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 4, "max_nodes": 16},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 6, "max_nodes": 30},
    },
    "blocks": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 3, "max_nodes": 12},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 5, "max_nodes": 20},
    },
    "flow": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 4, "max_nodes": 16},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 6, "max_nodes": 30},
    },
    "swimlane": {
        "widget": {"gap": 18, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 5, "max_nodes": 16, "max_lanes": 5},
        "page": {"gap": 28, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 7, "max_nodes": 30, "max_lanes": 7},
    },
}
NODE_KINDS = ("step", "decision", "terminal", "note", "state", "block")
DEFAULT_KIND = {"state": "state", "blocks": "block"}
LABEL_MAX_CHARS, LABEL_MAX_WORDS = 24, 3
FOOT_RE = re.compile(r"\s*\[(\d+)\]\s*$")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# What a layout error a draft keeps going past is prefixed with in the warnings. The advice reads it
# back off them to tell the messages a move introduced from the ones the author's own grid already
# had, so the two sides of the prefix are one constant.
DRAFT = "черновик: "

# What the crossings warning starts with. The advice counts the warnings of a plan to drop a move
# that brings one the author's grid did not have, and this is the one it does not count: lowering
# that very number is what the moves are for.
CROSSINGS = "пересечений линий: "

# A measurement switch, and nothing else. It is the calls of `route` the search inside `route_all`
# may spend (router.BUDGET), named here rather than written at the call so that the stage D
# measurement of tools/bench_routing.py can price a verifying plan that stops at the better start
# (`budget=0`, spec 6 as amended) without a public argument on `plan` that a renderer could reach
# for. No renderer path may set it: the tool moves it for the length of its own measurement and puts
# it back, and a production value other than router.BUDGET would mean the page is drawn by a routing
# nothing was measured against.
_ROUTE_BUDGET = router.BUDGET

# What a line on an even lattice line keeps clear, in px, and so cannot spend on the lines beside
# it: LINE_CLEAR from the nearest card edge, EDGE_CLEAR from the bound on the other side — the edge
# that clips or covers it, or the nearest content beyond the grid box.
LINE_CLEAR = 4
EDGE_CLEAR = 1

# The raw px an unoffset line on an outer margin has on each side, lower coordinate first: for the
# top margin towards whatever bounds it away from the cards and then towards the cards, for the
# bottom margin the other way round. The side margins follow from `pad_l`, `pad_r` and `margin`,
# and these do not: .dg-grid pads 8 px above and below the cards while by() of template/js/flow.js
# puts a margin line `margin` px outside them, so in a flow both margin lines fall outside the grid
# box. The two ends of that box are not alike, though.
#
# Above it the bound is the box's own top edge, because whatever stands directly above it is either
# the edge that clips or content nearer than the line. In a widget nothing in the section's flow
# stands above the grid, so the section's top edge coincides with the box's and clips there:
# overflow-x:auto on .dg makes overflow-y compute to auto. In a page the h3 title lies right above
# the box with margin-bottom 4 px — the draft badge and the route chips too when the model has
# them — so a line 10 px up runs through that text. Either way a negative number says the line is
# already past the bound. A swimlane's top margin instead falls one row gap under the lane headers,
# which cover it.
#
# Below the box nothing clips — .dg-svg is drawn with overflow:visible (template/css/base.css) —
# and the section goes on. The bound there is the first content after the grid: the .dg-foot list,
# margin-top 8 px, when the model has footnotes, else the text of the .dg-legend that render()
# always emits for these kinds, which starts a padding-top of 12 px inside its box. So the bottom
# room is keyed by the footnotes as well, and is the narrower of the two when there are any.
#
# Measured in the browser by tests/test_browser_lines.py, which fails when a change of the CSS
# moves them.
TOP_ROOM = {("flow", "widget"): (-4, 12), ("flow", "page"): (-10, 18),
            ("swimlane", "widget"): (28, 12), ("swimlane", "page"): (26, 18)}
BOTTOM_ROOM = {("flow", "widget", False): (12, 8), ("flow", "widget", True): (12, 4),
               ("flow", "page", False): (18, 2), ("flow", "page", True): (18, -2),
               ("swimlane", "widget", False): (12, 8), ("swimlane", "widget", True): (12, 4),
               ("swimlane", "page", False): (18, 2), ("swimlane", "page", True): (18, -2)}

# Where tracks() of template/js/head.js puts the track of the first row of the grid when that row
# holds no card, in px above the top of the first cards: `rows[dn].t - 20`, whatever the kind and the
# mode. Also measured by tests/test_browser_lines.py (case 17), which holds the whole band of an
# empty row against the page.
TRACK_LEAD = 20

# Stands, inside Geometry.band, for the top margin's away-from-the-cards side: the one side of a line
# of such a band that no rule here derives, because only the browser measurement states it.
MEASURED = object()


def shared_room(distance):
    """What a side of a band line facing another lattice line takes of the `distance` to it: half of
    what is left once one smallest pitch (`router.PITCHES[-1]`) is kept between the two groups, so
    their outermost lines stay that pitch apart — as near as two lines of one group ever come.

    Sharing the whole distance instead let both groups reach the very same y, and no counter saw it:
    `router.drawn_overlaps` works in lattice coordinates, where the two lines lie on lines of their
    own."""
    return (distance - router.PITCHES[-1]) / 2


def margin_room(kind, mode_name, footnotes):
    """(top, bottom) raw room of the outer margins for this kind and mode: only a swimlane carries
    lane headers, so every other kind is measured as a flow. `footnotes` says whether the model has
    any, which moves what the bottom margin is bounded by and nothing above the grid box."""
    key = ("swimlane" if kind == "swimlane" else "flow", mode_name)
    return TOP_ROOM[key], BOTTOM_ROOM[(*key, bool(footnotes))]


# Where the base of a row line stands against the cards around it (`Geometry.frame`). A frame is
# the run of row lines between two rows of cards — one gutter, an outer margin, or every line of a
# band of empty rows — and its lines are read in the px of its lowest one, `row`: `at` is the base
# of the line asked about from the base of `row`, `top` and `bottom` the card edges over and under
# the frame from that same base, infinite where no row of cards stands on that side, and `first` the
# frame's highest line.
Frame = collections.namedtuple("Frame", "row at top bottom first")


class Geometry:
    """Pixel x of cards and lattice lines, relative to the grid box, as template/js/flow.js derives
    them (tracks, bx, clampX). Card heights are unknown here, so there is no y, only the gutter
    between two rows of cards, `row_gap` high, whose middle by() puts lines in.

    `top` and `bottom` are the measured raw room of the outer row margins, which no rule here
    derives; a geometry built without them answers None for those two lines, which is what a
    caller with no capacity to enforce needs.

    `empty` names the rows of the drawn extent that hold no card. They have no card edge for a line
    beside them to keep clear of, and their own row line carries lines, so the band around such a row
    is the one place where the distances between row lines are not a row gap (see `_band`). The last
    row of the drawn extent always holds cards, so it is never among them."""

    def __init__(self, mode, card_w, cols, rows=0, top=None, bottom=None, empty=()):
        self.w = float(f"{card_w:.0f}")  # --dg-w is written rounded
        self.gap, self.pad_l, self.cols, self.total = mode["gap"], mode["pad_l"], cols, mode["total"]
        self.pad_r, self.rows = mode["pad_r"], rows
        self.row_gap = mode["row_gap"]
        self.margin = max(8, mode["pad_l"] - 6)
        self.top_room, self.bottom_room = top, bottom
        self.empty = sorted(r for r in empty if 0 <= r < rows - 1)
        self.tracks = self._tracks()
        self.band = self._band()
        self.frames = {}

    def left(self, c):
        return self.pad_l + c * (self.w + self.gap)

    def right(self, c):
        return self.left(c) + self.w

    def x(self, X):
        if X % 2:
            return self.left(X // 2) + self.w / 2
        g = X // 2
        if g == 0:
            return self.left(0) - self.margin
        if g == self.cols:
            return self.right(self.cols - 1) + self.margin
        return self.left(g) - self.gap / 2

    def clamp(self, c, x):
        return min(max(x, self.left(c) + 12), self.right(c) - 12)

    def _tracks(self):
        """Every run of empty rows of the drawn extent as tracks() of template/js/head.js lays it
        out: [(a, b, above, {lattice line: px of its base})], `a`..`b` the empty rows of the run and
        `above` the card edge over it, None over a leading run, which the top margin bounds.

        tracks() gives an empty row of the drawn extent a track at one y and fills the empty rows in
        ascending order, so each of them sees the tracks already invented above it: the first row of
        the grid lands TRACK_LEAD px above the first cards, and every other empty row halfway
        between the row above it and the top of the next row of cards. So a run of k empty rows
        halves what is left of the span below it, k times. An empty implicit grid row is 0 px high
        and both of its row gaps stay, so that span is (k + 1) row gaps between two rows of cards.
        by() then puts a row line in the middle of its own track, a gutter in the middle between two
        tracks, and the top margin `margin` above the first track.

        Each run is measured in px from the card edge that ends it, downwards, so its own lines are
        negative and the cards below it are at 0. `_band` prices the lines of a run from these px
        and `frame` states them; neither reads the other."""
        runs = []
        for r in self.empty:
            if runs and runs[-1][-1] == r - 1:
                runs[-1].append(r)
            else:
                runs.append([r])
        out = []
        for run in runs:
            a, b = run[0], run[-1]
            if a == 0:
                # a leading run: nothing occupied above it, and the top margin is what bounds it
                ys = [-TRACK_LEAD / 2 ** j for j in range(len(run))]
                above, first = None, ys[0] - self.margin
            else:
                span = (len(run) + 1) * self.row_gap
                ys = [-span / 2 ** (j + 1) for j in range(len(run))]
                above, first = -span, (-span + ys[0]) / 2
            # gutters[k] is the lattice line 2 * (a + k), the one above the empty row a + k
            gutters = [first] + [(ys[j - 1] + ys[j]) / 2 for j in range(1, len(ys))] + [ys[-1] / 2]
            at = {2 * (a + j): y for j, y in enumerate(gutters)}
            at.update({2 * (a + j) + 1: y for j, y in enumerate(ys)})
            out.append((a, b, above, at))
        return out

    def _band(self):
        """The room of every lattice row line an empty row governs: {line: (lower side, higher side)},
        with MEASURED in place of the top margin's away-from-the-cards side, which only the browser
        measurement states. The px of the lines are `_tracks`'.

        A side facing a card edge keeps LINE_CLEAR off the distance to it; a side facing another
        lattice line takes `shared_room` of the distance — the two groups share it, less one
        smallest pitch kept between them, which is what stops the outermost lines of two
        neighbouring groups being drawn on one y."""
        out = {}
        for a, b, above, at in self.tracks:
            for r in range(a, b + 1):
                y = at[2 * r + 1]
                out[2 * r + 1] = (shared_room(y - at[2 * r]), shared_room(at[2 * r + 2] - y))
            out[2 * a] = (MEASURED if above is None else at[2 * a] - above - LINE_CLEAR,
                          shared_room(at[2 * a + 1] - at[2 * a]))
            for r in range(a + 1, b + 1):
                out[2 * r] = (shared_room(at[2 * r] - at[2 * r - 1]),
                              shared_room(at[2 * r + 1] - at[2 * r]))
            out[2 * (b + 1)] = (shared_room(at[2 * b + 2] - at[2 * b + 1]), -at[2 * b + 2] - LINE_CLEAR)
        return out

    def frame(self, line):
        """Where the base of row line `line` stands against the cards around it, as a Frame, or None
        where this side cannot say: a row of cards, whose base template/js/flow.js puts in the middle
        of its tallest card, or of the band its sideways lines are clamped into.

        Every other row line stands at px this side knows from the same construction the room of
        stage B is priced with: a gutter in the middle of the `row_gap` between two rows of cards, an
        outer row margin `margin` outside them, and every line of a band of empty rows where
        `_tracks` puts it. The lines between the same two rows of cards are one frame, read in the px
        of its lowest line, so that what stands on one of them is measured against what stands on
        the others (spec 7.1 as amended a fourth time)."""
        found = self.frames.get(line)
        if found is None:
            found = self.frames[line] = self._frame(line)
        return found

    def _frame(self, line):
        for a, b, above, at in self.tracks:
            if 2 * a <= line <= 2 * (b + 1):
                row = 2 * (b + 1)
                return Frame(row, at[line] - at[row], -math.inf if above is None else above - at[row],
                             -at[row], 2 * a)
        if line % 2:
            return None
        g = line // 2
        top = -math.inf if g == 0 else -(self.margin if g == self.rows else self.row_gap / 2)
        bottom = math.inf if g == self.rows else (self.margin if g == 0 else self.row_gap / 2)
        return Frame(line, 0.0, top, bottom, line)

    def room(self, axis, line):
        """The px the lines of one group on this lattice line may spread over, on each side of it,
        lower coordinate first, with LINE_CLEAR already taken off towards a card and EDGE_CLEAR
        towards whatever bounds them on the other side — the edge that clips or covers them, or,
        under the bottom margin, the content the section goes on with. Towards another lattice line,
        which only the band of an empty row brings this near, the room is `shared_room` of the
        distance to it: the two groups share it and keep one smallest pitch between them (`_band`).
        A negative number says a line on the lattice line itself is already past that bound.

        None where there is no room to state: a column of cards, a row of cards — both placed against
        card heights by the script, which this side knows nothing of — and an outer row margin this
        geometry was not given the measurement of."""
        if axis == "h":
            found = self.band.get(line)
            if found is not None:
                lo, hi = found
                if lo is not MEASURED:
                    return (lo, hi)
                if self.top_room is None:
                    return None
                return (self.top_room[0] - EDGE_CLEAR, hi)
        if line % 2:
            return None
        g = line // 2
        if axis == "v":
            if g == 0:
                return (self.pad_l - self.margin - EDGE_CLEAR, self.margin - LINE_CLEAR)
            if g == self.cols:
                return (self.margin - LINE_CLEAR, self.pad_r - self.margin - EDGE_CLEAR)
            return (self.gap / 2 - LINE_CLEAR, self.gap / 2 - LINE_CLEAR)
        if g in (0, self.rows):
            raw = self.top_room if g == 0 else self.bottom_room
            if raw is None:
                return None
            lo, hi = (EDGE_CLEAR, LINE_CLEAR) if g == 0 else (LINE_CLEAR, EDGE_CLEAR)
            return (raw[0] - lo, raw[1] - hi)
        return (self.row_gap / 2 - LINE_CLEAR, self.row_gap / 2 - LINE_CLEAR)


OVERFULL_NAMED = 4  # edges a capacity error names before it ends the list with an ellipsis


def line_name(axis, line, cols, rows):
    """How a message names a lattice line: an inner gutter by the two columns or rows it lies
    between, an outer one by its margin, and the row line of an empty row — the one odd line that
    states a room — by that row. Columns and rows are counted from zero, as `grid, ряд N` and the two
    cells of a node placed twice count them."""
    g = line // 2
    if axis == "v":
        if g == 0:
            return "по левому полю"
        return "по правому полю" if g == cols else f"между столбцами {g - 1} и {g}"
    if line % 2:
        return f"в пустом ряду {g}"
    if g == 0:
        return "по верхнему полю"
    return "по нижнему полю" if g == rows else f"между рядами {g - 1} и {g}"


def overfull_error(group, edges, cols, rows):
    """The layout error for one group of `router.overfull`, which gives it as
    (axis, line, width, [path indices], capacity): where it lies, how many lines are drawn there
    against how many fit, the edges among them, and what the author can do about it.

    The count is the width — the slots the group is drawn in, which is what has to fit — while the
    list is who to move: an edge whose two runs in the gutter lie beside each other is two of the
    lines and one of the names, and where two runs share a slot the list is longer than the count.
    At most OVERFULL_NAMED of them, in the order of the model's edges.

    Where the line holds nothing at all — a flow's top margin, a page's bottom margin under a
    footnote list — freeing a cell beside it would not help: no pitch puts a line there.

    Along an empty row the cells are free already, and what leaves the lines no room is the row
    itself: `tracks()` of template/js/head.js draws the whole band of such a row inside what would
    otherwise be one gutter, so the advice there is to take the row out."""
    axis, line, width, idx, cap = group
    named = [f"{edges[i]['a']} -> {edges[i]['b']}" for i in sorted(set(idx))]
    shown = ", ".join(named[:OVERFULL_NAMED]) + (", …" if len(named) > OVERFULL_NAMED else "")
    if axis == "h" and line % 2:
        advice = "уберите пустой ряд или переставьте узлы"
    elif cap:
        advice = "освободите ячейку рядом или переставьте узлы"
    elif axis == "h":
        away = "ниже" if line == 0 else "выше"
        advice = f"линии здесь не проходят, переставьте узлы так, чтобы связи шли {away} или между рядами"
    else:
        advice = "линии здесь не проходят, переставьте узлы так, чтобы связи шли между столбцами"
    return f"{line_name(axis, line, cols, rows)} линий {width}, помещается {cap}: {shown}; {advice}"


def in_the_way(blocked, routed):
    """What the error of a label that fits nowhere calls the nearest thing in its way, ready to
    follow the room it names (criterion E3), or the empty string where nothing stands there.

    `blocked` is the Clash `labels.place` answers with: a card by the id of the node standing on it,
    a line by the (path, segment) of the run, which names the routed edge it belongs to, another
    label by the edge it belongs to, and a bound by the side of the drawn area it is."""
    if blocked is None:
        return ""
    if blocked.kind == labels.CARD:
        return f", мешает карточка {blocked.owner}"
    if blocked.kind == labels.LINE:
        other = routed[blocked.owner[0]]
        return f", мешает линия {other['a']} -> {other['b']}"
    if blocked.kind == labels.LABEL:
        other = routed[blocked.owner]
        return f", мешает подпись связи {other['a']} -> {other['b']}"
    return ", мешает край диаграммы"


def mode_for(kind, mode_name, overrides):
    mode = dict(BASE_MODES[mode_name])
    mode.update(MODES[kind][mode_name])
    mode.update(overrides or {})
    return mode


def node_kind(n, diagram="flow"):
    k = n.get("kind")
    if k:
        return k
    if n["id"].endswith("?"):
        return "decision"
    return DEFAULT_KIND.get(diagram, "step")


def parse_edge(e, errors, i):
    """'a -> b : label [n] | dashed' or the object form."""
    label_id = f"связь #{i + 1}"
    if isinstance(e, str):
        body, _, mods = e.partition("|")
        if "->" not in body:
            errors.append(f"{label_id}: ожидается 'a -> b : подпись'")
            return None
        ends, _, label = body.partition(":")
        a, b = (s.strip() for s in ends.split("->", 1))
        out = {"a": a, "b": b, "label": label.strip(), "dashed": False}
        for m in (x.strip() for x in mods.split(",") if x.strip()):
            if m == "dashed":
                out["dashed"] = True
            else:
                errors.append(f"{label_id}: неизвестный модификатор {m!r}; допустим dashed")
        return out
    try:
        return {"a": e["from"], "b": e["to"], "label": (e.get("label") or "").strip(), "dashed": bool(e.get("dashed"))}
    except (KeyError, TypeError):
        errors.append(f"{label_id}: нужны from и to")
        return None


def plan(model, mode_name, overrides=None, draft=False):
    kind = model.get("kind", "flow")
    lanes_mode = kind == "swimlane"
    errors, layout_errors, fit_errors, warnings = [], [], [], []

    def fit_error(msg):
        layout_errors.append(msg)
        fit_errors.append(msg)

    mode = mode_for(kind, mode_name, overrides)

    groups = model.get("groups") or {}
    nodes = model.get("nodes") or []
    footnotes = model.get("footnotes") or []
    max_groups = mode.get("max_lanes", 4)
    if len(groups) > max_groups:
        warnings.append(f"групп {len(groups)}: больше {max_groups} цветов читаются плохо")
    for gid, g in groups.items():
        if not ID_RE.match(gid) or gid.endswith("?"):
            errors.append(f"группа {gid!r}: id только из строчных латинских букв, цифр и _")
        if g.get("ramp") not in RAMPS:
            errors.append(f"группа {gid}: ramp должен быть одним из {', '.join(RAMPS)}")

    cells, grid_cols, grid_rows = parse_grid(model.get("grid"), errors)
    if grid_cols < 1 or grid_cols > mode["max_cols"]:
        layout_errors.append(f"grid шириной {grid_cols}: режим {mode_name} для {kind} допускает от 1 до {mode['max_cols']} столбцов")
    grid_cols = max(grid_cols, 1)
    card_w = (mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["gap"] * (grid_cols - 1)) / grid_cols
    ch, tch = mode["char"], mode["tchar"]

    lanes = model.get("lanes") or []
    if lanes_mode:
        # a string or a mapping is iterable too: every reader below would take a character or a key
        # for a lane id, so a lanes that is not a list is refused and the readers keep a list
        if not lanes or not isinstance(lanes, list):
            lanes = []
            errors.append("swimlane: нужен список lanes с id групп, по одной на столбец")
        elif len(lanes) != grid_cols:
            errors.append(f"swimlane: дорожек {len(lanes)}, а столбцов в grid {grid_cols}; каждая дорожка это столбец")
        if len(lanes) > mode.get("max_lanes", 99):
            layout_errors.append(f"swimlane: дорожек {len(lanes)}, режим {mode_name} допускает до {mode['max_lanes']}; "
                                 f"объедините второстепенных участников в одну дорожку")
        for l in lanes:
            if l not in groups:
                errors.append(f"swimlane: дорожка {l!r} не описана в groups")

    by_id = {}
    if len(nodes) > mode["max_nodes"]:
        layout_errors.append(f"узлов {len(nodes)}, режим {mode_name} допускает до {mode['max_nodes']}: "
                             f"разбейте схему на обзор и детали")
    for n in nodes:
        nid = n.get("id")
        if not nid or not ID_RE.match(nid):
            errors.append(f"узел {nid!r}: id только из строчных латинских букв, цифр и _, знак ? допустим последним")
            continue
        if nid in by_id:
            errors.append(f"узел {nid}: id повторяется")
        by_id[nid] = n
        k = node_kind(n, kind)
        if k not in NODE_KINDS:
            errors.append(f"узел {nid}: kind {k!r} не из {NODE_KINDS}")
        if nid.endswith("?") and k != "decision":
            errors.append(f"узел {nid}: id с ? на конце это развилка, а kind = {k}")
        # a title of white space alone draws a card lower than labels.CARD_LEAST, the least height
        # the label model reads every card at, so it is no title at all
        if not str(n.get("title") or "").strip():
            errors.append(f"узел {nid}: нет title")
            continue
        if n.get("group") and n["group"] not in groups:
            errors.append(f"узел {nid}: группа {n['group']!r} не описана в groups")
        if lanes_mode and nid in cells:
            lane = lanes[cells[nid][1]] if cells[nid][1] < len(lanes) else None
            if n.get("group") and lane and n["group"] != lane:
                errors.append(f"узел {nid}: стоит в дорожке {lane}, а group = {n['group']}; цвет узла задаёт дорожка")
        extra = 21 if k == "decision" else 0
        if lanes_mode:
            extra += 30
        def title_fits(s, extra=extra, card_w=card_w):
            return text_width(s) * 1.04 + 20 + extra <= card_w
        if not title_fits(n["title"]):
            fit_error(f"узел {nid}: заголовок {len(n['title'])} симв., влезает "
                      f"{fit_prefix(n['title'], title_fits)}; "
                      f"сократите заголовок или сузьте grid")
        text = n.get("text") or ""
        m_note = FOOT_RE.search(text) if text else None
        if m_note:
            ref = int(m_note.group(1))
            if ref < 1 or ref > len(footnotes):
                errors.append(f"узел {nid}: сноска [{ref}] не описана в footnotes")
            else:
                n["_note"] = ref
                text = text[: m_note.start()].rstrip() + " " + CIRCLED[ref - 1]
                n["_text"] = text
        def text_fits(s, card_w=card_w):
            return wrap_lines(s, card_w - 20) <= 2
        if text:
            wide = too_wide_word(text, card_w - 20)
            if wide:
                fit_error(f"узел {nid}: слово {len(wide[0])} симв., влезает ~{wide[1]}")
            elif not text_fits(text):
                fit_error(f"узел {nid}: текст {len(text)} симв., в две строки влезает ~{fit_prefix(text, text_fits)}; "
                          f"сократите или вынесите в сноску")
        items = n.get("items") or []
        if items and k != "block":
            warnings.append(f"узел {nid}: items показываются только у block")
        if len(items) > 5:
            layout_errors.append(f"узел {nid}: пунктов {len(items)}, допустимо пять")
        def item_fits(s, card_w=card_w):
            return wrap_lines(s, card_w - 30) <= 2
        for pos, it in enumerate(items, 1):
            wide = too_wide_word(it, card_w - 30)
            if wide:
                fit_error(f"узел {nid}: пункт {pos} — слово {len(wide[0])} симв., влезает ~{wide[1]}")
            elif not item_fits(it):
                fit_error(f"узел {nid}: пункт {pos} — {len(it)} симв., влезает ~{fit_prefix(it, item_fits)}")
        if k == "terminal" and text:
            warnings.append(f"узел {nid}: у terminal текст не показывается, только заголовок")

    check_placement(cells, list(by_id), errors, "узел")
    er, ec = empty_lines(cells, grid_cols, grid_rows)
    if er:
        warnings.append(f"пустые ряды в grid: {er}")
    if ec:
        warnings.append(f"пустые столбцы в grid: {ec}")
    if lanes_mode:
        rows_of = {}
        for nid, (r, _) in cells.items():
            rows_of.setdefault(r, []).append(nid)
        for r, ids in sorted(rows_of.items()):
            if len(ids) > 1:
                warnings.append(f"swimlane, ряд {r}: узлы {ids} стоят в одном ряду, читается как одновременность; так задумано?")

    # edges
    edges = []
    for i, raw in enumerate(model.get("edges") or []):
        e = parse_edge(raw, errors, i)
        if e is None:
            continue
        a, b = e["a"], e["b"]
        tag = f"связь {a} -> {b}"
        if a not in by_id or b not in by_id:
            errors.append(f"{tag}: неизвестный узел")
            continue
        if a == b:
            errors.append(f"{tag}: связь узла с собой не рисуется")
            continue
        label = e["label"]
        note = None
        m = FOOT_RE.search(label)
        if m:
            note = int(m.group(1))
            label = label[: m.start()].strip()
            if note < 1 or note > len(footnotes):
                errors.append(f"{tag}: сноска [{note}] не описана в footnotes")
        if label and (len(label) > LABEL_MAX_CHARS or len(label.split()) > LABEL_MAX_WORDS):
            errors.append(f"{tag}: подпись {label!r} длиннее {LABEL_MAX_WORDS} слов или {LABEL_MAX_CHARS} символов; "
                          f"оставьте короткую и вынесите текст в footnotes со ссылкой [n]")
        edges.append({"a": a, "b": b, "label": label, "note": note, "dashed": e["dashed"]})

    outgoing, incoming = {}, {}
    for e in edges:
        outgoing.setdefault(e["a"], []).append(e)
        incoming.setdefault(e["b"], []).append(e)
    for nid, n in by_id.items():
        k = node_kind(n, kind)
        outs = outgoing.get(nid, [])
        if k == "decision":
            if len(outs) < 2:
                errors.append(f"развилка {nid}: исходящих связей {len(outs)}, нужно не меньше двух")
            for e in outs:
                if not e["label"]:
                    errors.append(f"развилка {nid}: ветка в {e['b']} без подписи")
        if kind in ("flow", "swimlane"):
            if k != "terminal" and not outs and k != "note":
                warnings.append(f"узел {nid}: нет исходящих связей, а это не terminal")
            if k != "note" and not incoming.get(nid) and k != "terminal" and cells.get(nid, (1,))[0] != 0:
                warnings.append(f"узел {nid}: нет входящих связей, недостижим")

    used_notes = {e["note"] for e in edges if e["note"]} | {n["_note"] for n in by_id.values() if n.get("_note")}
    for i in range(1, len(footnotes) + 1):
        if i not in used_notes:
            warnings.append(f"сноска [{i}] не используется")

    # routes (scenarios)
    routes = model.get("routes") or {}
    edge_set = {(e["a"], e["b"]) for e in edges}
    for name, seq in routes.items():
        if not isinstance(seq, list) or len(seq) < 2:
            errors.append(f"маршрут {name!r}: нужен список хотя бы из двух узлов")
            continue
        for a, b in zip(seq, seq[1:]):
            if a not in by_id or b not in by_id:
                errors.append(f"маршрут {name!r}: неизвестный узел {a if a not in by_id else b}")
            elif (a, b) not in edge_set:
                errors.append(f"маршрут {name!r}: между {a} и {b} нет связи")

    if errors:
        raise ModelError(errors + layout_errors, layout=layout_errors, fit=fit_errors)

    # The lattice ends where the page's rows end. tracks() of template/js/head.js takes its row
    # count from the cards — the last occupied row plus one — and invents a track for an empty row
    # above or between them, never for one after the last, so a line under the last card row is a
    # line by() of template/js/flow.js has no y for. Rows after it are no part of the lattice, of
    # the geometry (whose bottom margin is then the line the page really draws as one), or of the
    # row count a capacity error names lines by. The rows above stay: an empty one among them has
    # its track. The author still hears about every empty row of the grid, that one included.
    placed = {nid: rc for nid, rc in cells.items() if nid in by_id}
    drawn_rows = max((r for r, _ in placed.values()), default=-1) + 1
    drawn_empty = [r for r in er if r < drawn_rows]

    # every gutter, margin and empty row knows its room, so the router prices a step along a full one,
    # the objective the whole routing is searched against prices the slots a group takes past what its
    # line holds, and a group of lines too wide for the 8 px pitch closes up to 6 or 5 rather than
    # reaching over a card edge or out of the grid box
    top, bottom = margin_room(kind, mode_name, footnotes)
    geo = Geometry(mode, card_w, grid_cols, drawn_rows, top, bottom, drawn_empty)

    def line_capacity(axis, line):
        room = geo.room(axis, line)
        return None if room is None else router.capacity(room)

    # routing
    lat = router.Lattice(grid_cols, drawn_rows, placed, capacity=line_capacity)
    ends = [(router.Lattice.point(*cells[e["a"]]), router.Lattice.point(*cells[e["b"]])) for e in edges]
    labelled = [bool(e["label"] or e["note"]) for e in edges]
    paths, routed, kept = [], [], []
    # the room goes to the search as it goes to the offsets below: a routing is priced against the
    # room its groups are drawn in, or the term that counts a full gutter is zero wherever it matters
    for i, (e, p) in enumerate(zip(edges, router.route_all(lat, ends, labelled, room=geo.room,
                                                           budget=_ROUTE_BUDGET))):
        if p is None:
            layout_errors.append(f"связь {e['a']} -> {e['b']}: нет маршрута, не проходящего сквозь узлы; "
                                 f"освободите ячейку между ними или переставьте узлы")
            continue
        paths.append(p)
        routed.append(e)
        kept.append(i)
    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)
    if layout_errors:
        warnings = [DRAFT + x for x in layout_errors] + warnings

    on_cards = frozenset(lat.blocked)
    # the offsets and the check go through `place`, which draws the paths in the order the search
    # priced them in and answers in the model's: the slots a group takes depend on that order, so a
    # routing placed in another one is drawn in slots the search never paid for
    offsets, groups = router.place([ends[i] for i in kept], [labelled[i] for i in kept], paths,
                                   on_cards, geo.room)
    # what Φ pays for a full gutter, in the unit it pays it in (router.overflow, spec 5.2): the
    # slots these groups take past what their lines hold. The advice of spec 6 ranks a grid by it
    # first of all, and a plan that is not a draft always answers zero — a group past its capacity
    # is a layout error, and without `draft` the plan below raises instead of returning
    overflow = sum(width - cap for _, _, width, _, cap in groups)
    # the price above makes a full gutter rare and promises nothing: it reads the load of one unit
    # edge, and what a group costs its line is the slots it is drawn in over the whole of its
    # reach. What does not fit at the smallest pitch is refused here, one error per group, so the
    # author moves nodes instead of reading a line drawn over a card
    for group in groups:
        layout_errors.append(overfull_error(group, routed, grid_cols, drawn_rows))
    occupied = set(placed.values())

    # where every label goes: diagrams/labels.py searches the places of all the labels together for
    # the cheapest arrangement, answers with the place each one took and with what stands in its way
    # there, as rectangles of the lattice row they share, and the messages are written here. A label
    # raises one warning where it lies on a line along its rows or on another label, one per line
    # crossing a text on a horizontal second segment, and one per pair of labels that land in one
    # place, on the later of the two — the numbers the advice of spec 6 counts
    texts = [(e["label"] + (" " + CIRCLED[e["note"] - 1] if e["note"] else "")).strip()
             if e["label"] or e["note"] else "" for e in routed]
    choices = labels.place(routed, texts, paths, offsets, geo, cells, occupied, card_w)
    for choice in choices:
        e, text, spot = routed[choice.edge], texts[choice.edge], choice.cand
        if any(c.kind == labels.ON_LINE for c in choice.clashes):
            warnings.append(f"связь {e['a']} -> {e['b']}: подпись {text!r} {spot.where} ляжет на другую линию "
                            f"или подпись; переставьте узлы или уберите подпись в сноску")
        if choice.room is not None:
            def label_fits(s, room=choice.room):
                return label_width(s) <= room
            fit_error(f"связь {e['a']} -> {e['b']}: подпись {text!r} {len(text)} симв. не помещается {spot.where}, "
                      f"влезает ~{fit_prefix(text, label_fits)}{in_the_way(choice.blocked, routed)}; "
                      f"сократите, вынесите в сноску [n] "
                      f"или переставьте узлы так, чтобы линия уходила вниз")
        e["la"] = spot.la
        for clash in choice.clashes:
            if clash.kind == labels.SAME_PLACE:
                first = routed[clash.owner]
                warnings.append(f"связи {first['a']} -> {first['b']} и {e['a']} -> {e['b']}: подписи встанут "
                                f"в одно место и наложатся; переставьте узлы или уберите одну подпись в сноску")

    # the lines that run through a label over a horizontal second segment, by edge: the labels above
    # are answered for in the order they were placed, which is not the order of the model
    for choice in sorted(choices, key=lambda c: c.edge):
        e = routed[choice.edge]
        for clash in choice.clashes:
            if clash.kind == labels.CROSSED:
                other = routed[clash.owner]
                warnings.append(f"связь {e['a']} -> {e['b']}: подпись {e['label']!r} пересечёт линию "
                                f"{other['a']} -> {other['b']}; переставьте узлы или уберите подпись в сноску")

    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)
    if layout_errors:
        warnings = [DRAFT + x for x in layout_errors if x not in " ".join(warnings)] + warnings

    # what the reader sees, not what the lattice paths would cross: with the offsets assigned the
    # two are the same number, and where they are not the author is told about the drawing
    n_cross = router.drawn_crossings(paths, offsets, frozenset(lat.blocked))
    if n_cross >= 3:
        warnings.append(f"{CROSSINGS}{n_cross}; переставьте узлы, чтобы их стало меньше")
    out_edges = []
    for e, p, off in zip(routed, paths, offsets):
        out = {
            "a": e["a"], "b": e["b"],
            "sa": router.side_of(p[0], p[1]), "sb": router.side_of(p[-1], p[-2]),
            "path": [[x, y, ox, oy] for (x, y), (ox, oy) in zip(p, off)],
            "d": 1 if e["dashed"] else 0,
            "label": (e["label"] + (" " + CIRCLED[e["note"] - 1] if e["note"] else "")).strip(),
        }
        if out["label"]:
            # where the script draws that label: (pt, ref, Y, dx, dy, anchor) of spec 7.4
            out["la"] = e["la"]
        out_edges.append(out)

    # grid_rows is the drawn count: a swimlane's lane background, which render() spans from it, ends
    # with the last card row, where the tracks and the lattice end. empty_rows are the rows inside it
    # that hold no card, which is what the Geometry needs besides the count to answer for their band
    layout = {"kind": kind, "edges": out_edges, "card_w": card_w, "grid_cols": grid_cols, "grid_rows": drawn_rows,
              "empty_rows": drawn_empty,
              "cells": cells, "mode": mode, "nodes": by_id, "lanes": lanes, "lattice": lat, "paths": paths,
              "crossings": n_cross, "draft": bool(layout_errors), "routes": routes, "footnotes": footnotes,
              "overflow": overflow, "overfull": groups}
    return layout, warnings


# ------------------------------------------------------------------- render


def node_html(n, layout, groups):
    kind = layout["kind"]
    k = node_kind(n, kind)
    r, c = layout["cells"][n["id"]]
    row_offset = 2 if kind == "swimlane" else 1
    gid = n.get("group") or (layout["lanes"][c] if kind == "swimlane" and c < len(layout["lanes"]) else None)
    ramp = f"r-{groups[gid]['ramp']}" if gid else "r-none"
    num = f'<span class="dg-num" data-n="{r + 1}"></span>' if kind == "swimlane" else ""
    attrs = f'data-t="{esc(n["id"])}" data-r="{r}" data-c="{c}" style="grid-row:{r + row_offset};grid-column:{c + 1}"'
    title = esc(n["title"])
    text = n.get("_text") or n.get("text") or ""
    if k == "terminal":
        return f'<div class="dg-c dg-node k-terminal {ramp}" {attrs}><div class="dg-pill">{num}<span>{title}</span></div></div>'
    if k == "note":
        body = title + (f"<br>{esc(text)}" if text else "")
        return f'<div class="dg-c dg-node k-note" {attrs}><div class="dg-t">{num}{body}</div></div>'
    marker = '<span class="dg-q" aria-label="развилка">?</span>' if k == "decision" else ""
    body = f'<div class="dg-t">{esc(text)}</div>' if text else ""
    if k == "state":
        stripe = f"s-{groups[gid]['ramp']}" if gid else ""
        return (f'<div class="dg-c dg-node k-state {stripe}" {attrs}><div class="dg-h r-none">{num}<span class="ttl">{title}</span></div>'
                f'{body}</div>')
    if k == "block":
        items = n.get("items") or []
        lst = ('<ul class="dg-items">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>") if items else ""
        return (f'<div class="dg-c dg-node k-block" {attrs}><div class="dg-h {ramp}">{num}<span class="ttl">{title}</span></div>'
                f'{body}{lst}</div>')
    return (f'<div class="dg-c dg-node k-{k}" {attrs}><div class="dg-h {ramp}">{num}<span class="ttl">{title}</span>{marker}</div>'
            f'{body}</div>')


def legend_html(model, layout, labels):
    items = []
    for gid, g in (model.get("groups") or {}).items():
        items.append(f'<span><span class="sw sw-{g["ramp"]}"></span>{esc(g.get("label", gid))}</span>')
    items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H27" stroke="currentColor" '
                 f'stroke-width="1.5" fill="none"/><path d="M27 2l5 3-5 3z" fill="currentColor"/></svg>{esc(labels["flow_solid"])}</span>')
    if any(e["d"] for e in layout["edges"]):
        items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H27" stroke="currentColor" '
                     f'stroke-width="1.5" stroke-dasharray="5 4" fill="none"/><path d="M27 2l5 3-5 3z" fill="currentColor"/></svg>{esc(labels["flow_dashed"])}</span>')
    if any(node_kind(n, layout["kind"]) == "decision" for n in layout["nodes"].values()):
        items.append(f'<span><span class="dg-q" style="vertical-align:-3px;margin-right:4px">?</span>{esc(labels["decision"])}</span>')
    return '<div class="dg-legend">' + "".join(items) + "</div>"


def render(model, mode_name, layout, warnings, assets_mode="inline", draft=False):
    kind, mode = layout["kind"], layout["mode"]
    labels = labels_for(model)
    groups = model.get("groups") or {}
    style_vars = (f"--dg-cols:{layout['grid_cols']};--dg-w:{layout['card_w']:.0f}px;--dg-gap:{mode['gap']}px;"
                  f"--dg-rowgap:{mode['row_gap']}px;--dg-padl:{mode['pad_l']}px;--dg-padr:{mode['pad_r']}px")
    summary = model.get("summary") or model.get("title") or "Схема"
    labels_js = esc(json.dumps({}, ensure_ascii=False))

    before, after = assets.asset_blocks(assets_mode, mode_name, kind, {g["ramp"] for g in groups.values()},
                                        layout["edges"], layout["routes"], layout["footnotes"])
    parts = [before] if before else []
    parts.append(assets.section_open(model, kind, style_vars, labels_js, summary))
    if mode_name == "page" and model.get("title"):
        parts.append(f'<h3 style="margin:0 0 4px {mode["pad_l"]}px;font-size:16px;font-weight:500">{esc(model["title"])}</h3>')
    if draft or layout.get("draft"):
        parts.append(f'<span class="dg-draft">{esc(labels["draft"])}</span>')
    routes = layout["routes"]
    if routes:
        chips = "".join(f'<button type="button" class="dg-route" data-nodes="{esc(" ".join(seq))}">{esc(name)}</button>'
                        for name, seq in routes.items())
        parts.append(f'<div class="dg-routes"><span class="dg-routes-l">{esc(labels["routes"])}</span>{chips}</div>')
    parts.append('<div class="dg-grid">')
    if kind == "swimlane":
        span = layout["grid_rows"] + 1
        for c, gid in enumerate(layout["lanes"]):
            g = groups[gid]
            parts.append(f'<div class="dg-lane r-{g["ramp"]}" style="grid-row:1 / span {span};grid-column:{c + 1}"></div>')
            parts.append(f'<div class="dg-lanehead r-{g["ramp"]}" style="grid-row:1;grid-column:{c + 1}">{esc(g.get("label", gid))}</div>')
    for n in model["nodes"]:
        parts.append(node_html(n, layout, groups))
    parts.append('<svg class="dg-svg" aria-hidden="true"></svg></div>')
    if layout["footnotes"]:
        parts.append('<ol class="dg-foot">' + "".join(f"<li>{f}</li>" for f in layout["footnotes"]) + "</ol>")
    parts.append(legend_html(model, layout, labels))
    parts.append(assets.edges_json(layout["edges"]))
    parts.append("</section>")
    if after:
        parts.append(after)
    return "\n".join(parts)


def ascii(model, layout):
    ids_at = {rc: nid for nid, rc in layout["cells"].items()}
    text = router.ascii(layout["lattice"], ids_at, layout["paths"])
    lines = [text, ""]
    for e in layout["edges"]:
        lines.append(f"  {e['a']} -> {e['b']}" + (f"  : {e['label']}" if e["label"] else "") + ("  (пунктир)" if e["d"] else ""))
    lines.append(f"  пересечений линий: {layout['crossings']}")
    return "\n".join(lines)


def mermaid(model, layout):
    kind = layout["kind"]
    groups = model.get("groups") or {}

    def mid(nid):
        return nid.replace("?", "_q")

    def shape(n):
        k = node_kind(n, kind)
        t = n["title"].replace('"', "'")
        if k == "decision":
            return f'{mid(n["id"])}{{"{t}"}}'
        if k == "terminal":
            return f'{mid(n["id"])}(["{t}"])'
        if k == "note":
            return f'{mid(n["id"])}[/"{t}"/]'
        if k == "state":
            return f'{mid(n["id"])}(["{t}"])'
        return f'{mid(n["id"])}["{t}"]'

    lines = ["flowchart TD" if kind != "state" else "flowchart LR"]
    if kind == "swimlane":
        for c, gid in enumerate(layout["lanes"]):
            lines.append(f'    subgraph {gid} ["{groups[gid].get("label", gid)}"]')
            for n in model["nodes"]:
                if layout["cells"][n["id"]][1] == c:
                    lines.append("        " + shape(n))
            lines.append("    end")
    else:
        for n in model["nodes"]:
            lines.append("    " + shape(n))
    for e in layout["edges"]:
        arrow = "-.->" if e["d"] else "-->"
        label = f'|"{e["label"]}"|' if e["label"] else ""
        lines.append(f"    {mid(e['a'])} {arrow}{label} {mid(e['b'])}")
    for i, f in enumerate(layout["footnotes"], 1):
        lines.append(f"    %% {CIRCLED[i - 1]} {f}")
    return "\n".join(lines)
