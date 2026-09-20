"""The moves a rearrangement advice may propose, and the rules that keep the author's reading.

Spec 6. The author's grid stays the layout: nothing here changes a model, it only says what could
be tried on one. A move is a swap of two cards, a card carried into an empty cell, or — in a
swimlane, where a column is a lane and a row is a moment, so no card moves on its own — a lane
order that takes the grid columns with it. `moves` offers them in the order of how little they
disturb the reading, and the search of the next stage prices them.

Every move produces a deep copy of the model with a new `grid` and nothing else touched. That is
not tidiness: `flow.plan` writes `_note` and `_text` into the nodes of the model it plans, so a
move that shared them would hand the next plan the notes the last one left behind.
"""
import copy
import itertools
import re

from . import flow
from .grid import parse_grid

# A lane order is a permutation of the lanes, and permutations grow the way factorials do: a model
# of twelve lanes has 479 001 600 of them, which no allowance of verifying plans bounds. A mode's
# own `max_lanes` is a layout error that `draft=True` downgrades to a warning, so it does not stop
# such a model reaching the advice, and this cap is what does. Seven is the widest `max_lanes` any
# mode declares (flow.MODES["swimlane"]["page"]); a model over it is advised nothing at all rather
# than advised from a part of its orders, and the orders are drawn from `itertools.permutations`
# after the cap has been read, so nothing larger is ever built.
MAX_LANES = 7
MAX_LANE_ORDERS = 5040  # 7!

TOKEN = re.compile(r"\S+")


class Move:
    """One rearrangement of a grid. `kind` says which of the three it is; `apply` produces the model
    it would leave behind; `text()` names it to the author, in the wording of spec 6's output
    block, counting rows and cells from zero as `grid, ряд N` and the two cells of a node placed
    twice count them."""

    kind = ""

    def moved(self, cells):
        """The placement this move produces from `cells` — id to (row, column)."""
        raise NotImplementedError

    def apply(self, model):
        out = copy.deepcopy(model)
        cells, width, height = parse_grid(model.get("grid"), [])
        out["grid"] = write_grid(model["grid"], self.moved(cells), width, height)
        return out

    def text(self):
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.kind}: {self.text()}>"


class Swap(Move):
    """Two cards exchange cells."""

    kind = "swap"

    def __init__(self, a, b, rows):
        self.a, self.b = a, b
        self.rows = rows  # the rows the two stood in before the swap, for the wording

    def moved(self, cells):
        out = dict(cells)
        out[self.a], out[self.b] = cells[self.b], cells[self.a]
        return out

    def text(self):
        lo, hi = min(self.rows), max(self.rows)
        where = f"ряд {lo}" if lo == hi else f"ряды {lo} и {hi}"
        return f"поменять местами {self.a} и {self.b} ({where})"


class Shift(Move):
    """One card is carried into an empty cell of the grid."""

    kind = "shift"

    def __init__(self, node, cell):
        self.node, self.cell = node, cell

    def moved(self, cells):
        out = dict(cells)
        out[self.node] = self.cell
        return out

    def text(self):
        return f"перенести {self.node} в пустую ячейку [{self.cell[0]}, {self.cell[1]}]"


class Lanes(Move):
    """A lane order, with the grid columns moving with it. `order` lists the columns of the grid in
    their new left-to-right order, so the card that stood in a lane stands in it still and only the
    lanes beside it change — which is the whole of what a swimlane may rearrange."""

    kind = "lanes"

    def __init__(self, order, lanes):
        self.order = order
        self.lanes = [lanes[c] for c in order]

    def moved(self, cells):
        at = {c: new for new, c in enumerate(self.order)}
        return {nid: (r, at[c]) for nid, (r, c) in cells.items()}

    def apply(self, model):
        out = super().apply(model)
        out["lanes"] = list(self.lanes)
        return out

    def text(self):
        return "переставить дорожки: " + ", ".join(self.lanes)


class _Rules:
    """What every grid a move produces is judged against, read once from the model the author
    wrote. Judging the produced grid rather than the step that produced it is what closes the rules
    over a whole sequence of moves: a rule read from the grid a move starts at would forget, one
    step at a time, what the author's own grid said.

    Two rules, spec 6.

    An edge that runs downward in the original grid keeps running downward. The spec drops a move
    that puts such a target *above* its source, which leaves a target level with its source
    allowed; this is read one step stricter and keeps the target strictly below. The sequence is
    what asks for it: a downward edge made horizontal is the state the next move would have to be
    judged in, and by then the reading the author wrote — this step follows that one — is already
    gone, whether or not a later move goes on to turn the edge upward. Strictness costs the search
    the moves that bring two cards of one edge into one row; it buys a rule the author can read off
    the advised grid without holding the original beside it.

    And a node with no incoming edge that stands in the first row stays there: out of it
    `flow.plan` calls the node unreachable, which is an error the author's own grid did not have. A
    node the author already put lower carries that warning already, so nothing holds it."""

    def __init__(self, model):
        cells = parse_grid(model.get("grid"), [])[0]
        edges = edges_of(model)
        self.down = [(a, b) for a, b in edges
                     if a in cells and b in cells and cells[a][0] < cells[b][0]]
        targets = {b for _, b in edges}
        self.rooted = {nid for nid, (r, _) in cells.items() if r == 0 and nid not in targets}

    def hold(self, cells):
        for a, b in self.down:
            here, there = cells.get(a), cells.get(b)
            if here is None or there is None or here[0] >= there[0]:
                return False
        return all(cells[nid][0] == 0 for nid in self.rooted if nid in cells)


def edges_of(model):
    """The (source, target) pairs of a model, read by the renderer's own parser so that both forms
    of an edge are understood. An edge that does not parse has no ends and takes no part in a
    rule — the plan refuses such a model before any advice is asked for."""
    out = []
    for i, raw in enumerate(model.get("edges") or []):
        e = flow.parse_edge(raw, [], i)
        if e is not None:
            out.append((e["a"], e["b"]))
    return out


def limits(kind, mode_name):
    """The (columns, nodes, lanes) a model of this kind may have before it is advised nothing. A
    named mode brings its own; without one — `moves` is reached from a plan that already knows its
    mode, and from tests that do not — the widest of the kind's modes rules, so a model is refused
    only where no mode of its kind would advise it at all."""
    modes = flow.MODES.get(kind) or flow.MODES["flow"]
    chosen = [modes[mode_name]] if mode_name in modes else list(modes.values())
    return (max(m["max_cols"] for m in chosen),
            max(m["max_nodes"] for m in chosen),
            min(MAX_LANES, max(m.get("max_lanes", 0) for m in chosen)))


def _columns(rows, width):
    """Where each column of the author's map starts, in characters: the rightmost start any row
    gives it. A grid written in aligned columns is written back in the very same ones, whatever the
    longest token in a column is — `dense-widget-flow` pads its middle column one character past
    that, which no rule derives and only the input says."""
    starts = [0] * width
    for row in rows:
        for c, m in enumerate(TOKEN.finditer(row)):
            if c < width:
                starts[c] = max(starts[c], m.start())
    return starts


def write_grid(rows, cells, width, height):
    """The placement back as a grid map, at the column offsets `rows` used.

    A row whose cards did not move keeps the author's own line, byte for byte, so a diff of the
    JSON shows only what the move moved. A row that changed is written out in full, every column of
    it, including the trailing empty cells an author may have left off the end of a line: the width
    of a grid is the widest of its rows, and a card carried out of the last column would otherwise
    take the column with it and narrow every card on the page."""
    at = {rc: nid for nid, rc in cells.items()}
    starts = _columns(rows, width)
    out = []
    for r in range(height):
        tokens = [at.get((r, c), ".") for c in range(width)]
        if _trimmed(rows[r].split()) == _trimmed(tokens):
            out.append(rows[r])
            continue
        line = ""
        for tok, start in zip(tokens, starts):
            line += " " * (max(1, start - len(line)) if line else start) + tok
        out.append(line.rstrip())
    return out


def _trimmed(tokens):
    """Tokens without the empty cells at the end of a row, which a line may leave off."""
    end = len(tokens)
    while end and tokens[end - 1] == ".":
        end -= 1
    return tokens[:end]


def moves(original, current, mode_name=None):
    """The moves that may be tried on `current`, in the order of spec 6: inside one row first, then
    to the adjacent row, then the rest. Ties go to the earlier node in the model — inside one reach
    every swap comes before every card carried into an empty cell, and both run in the order of the
    model's nodes and then of the grid, so two calls give one answer.

    `original` is the grid the author wrote, and every produced grid is judged against it by
    `_Rules` — never against `current`, which is how the rules hold over a sequence of moves rather
    than over one of them at a time.

    A model larger than `limits` allows is advised nothing: a lane order is a permutation, and a
    swimlane wide enough makes more of them than any allowance of verifying plans could bound."""
    cells, width, height = _placement(current)
    if not cells:
        return []
    kind = current.get("kind", "flow")
    max_cols, max_nodes, max_lanes = limits(kind, mode_name)
    lanes = current.get("lanes") or []
    if width > max_cols or len(current.get("nodes") or []) > max_nodes:
        return []
    rules = _Rules(original)
    if kind == "swimlane":
        if not lanes or len(lanes) > max_lanes:
            return []
        found = _lane_moves(lanes)
    else:
        found = _card_moves(current, cells, width, height)
    return [m for m in found if rules.hold(m.moved(cells))]


def _placement(model):
    """(cells, width, height) of a model's grid, or no cells at all when the map does not parse —
    the renderer refuses such a model, and there is nothing to advise about it."""
    errors = []
    cells, width, height = parse_grid(model.get("grid"), errors)
    return ({} if errors else cells), width, height


def _lane_moves(lanes):
    """Every lane order but the author's own, in the order `itertools.permutations` draws them —
    which is the columns read as numbers, so the orders nearest the author's come first."""
    out = []
    for order in itertools.permutations(range(len(lanes))):
        if order != tuple(range(len(lanes))):
            out.append(Lanes(order, lanes))
    return out


def _card_moves(model, cells, width, height):
    """Every swap of two cards and every empty cell each of them could be carried into, sorted by
    the rows the move reaches over — none, one, more — and then by the model's own order of nodes."""
    rank = {}
    for i, n in enumerate(model.get("nodes") or []):
        if n.get("id") and n["id"] not in rank:
            rank[n["id"]] = i
    last = len(rank)
    ids = sorted(cells, key=lambda nid: (rank.get(nid, last), nid))
    taken = set(cells.values())
    empty = [(r, c) for r in range(height) for c in range(width) if (r, c) not in taken]
    keyed = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            rows = (cells[a][0], cells[b][0])
            keyed.append((_reach(*rows), 0, rank.get(a, last), (rank.get(b, last),), Swap(a, b, rows)))
    for a in ids:
        for cell in empty:
            keyed.append((_reach(cells[a][0], cell[0]), 1, rank.get(a, last), cell, Shift(a, cell)))
    keyed.sort(key=lambda row: row[:4])
    return [row[-1] for row in keyed]


def _reach(here, there):
    """How far a move reaches, in the three steps spec 6 names: inside one row, to the row beside
    it, or anywhere else."""
    return min(2, abs(here - there))
