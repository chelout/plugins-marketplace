"""advice: what a rearrangement advice may propose on a grid, and the search that prices it (spec 6
"Moves", "Swimlane" and "Search", criteria D1 and D2).

The moves come in the order spec 6 asks for — inside one row, then to the adjacent row, then the
rest — and every one of them is judged against the grid the author wrote, never against the grid it
starts from, so that a sequence of moves cannot walk past a rule one step at a time. Two rules:
an edge that runs downward in the original grid never has its target above its source, and a node
the author gave no incoming edge stays in the first row if that is where it stood.

The first rule is the spec's own and not a stricter reading of it: a move may lay the two cards of a
downward edge in one row. What keeps the reading the author wrote is that every produced grid is
judged against the **original** — a later move cannot take the target of such an edge above its
source, however level the grid in hand has left the two. `MakesNothingUpward` holds the pair, and
`TheOriginalGrid` holds the sequence it takes to tell the two grids apart: the level placement is
accepted, and the move that would reverse it from there is refused although the grid in hand no
longer has anything to refuse it with.

A swimlane moves no node of its own: a column is a lane and a row is a moment, so the only move is a
lane order that takes the grid columns with it. `LaneOrders` holds the cap of the plan's gate
finding G3 with a model of twelve lanes, and `lane_orders()` is what makes the evidence a failure
rather than a wait: a run that asks for the orders of more lanes than the cap allows stops there
instead of building 479 001 600 of them and leaving the suite to time out.

The search is held to the twelve seeded models of `bench_routing.seeded_models` — the first twelve
instances of `instances.small` whose naive reading-order grid crosses three times or more, which is
what makes the renderer ask for advice at all. The benchmark owns them because it measures the
search on the very population the tests hold it to, and two lists could drift apart.

Every plan the search makes goes through `flow.plan`, so `counted()` puts a spy in its place and the
tests read the count and the arguments off it: the allowance of plans (spec 6), the gate's finding
G3 (a model over a limit of its mode is advised nothing and plans nothing at all) and its finding G2
(the render's overrides reach every verifying plan, so a move is never verified against a geometry
the render will not use).
"""
import contextlib
import copy
import json
import re
import unittest

import support  # noqa: F401
from bench_routing import ADVICE_MODE, seeded_models
from diagrams import advice, flow
from diagrams.common import ModelError
from diagrams.grid import parse_grid

TOKEN = re.compile(r"\S+")


def card(i):
    return {"id": i, "title": i.capitalize()}


def terminal(i):
    return {"id": i, "kind": "terminal", "title": i.capitalize()}


def model(name):
    return json.loads((support.ROOT / "tests" / "models" / name).read_text())


def placement(m):
    cells, width, height = parse_grid(m["grid"], [])
    return cells, width, height


def rows_of(m):
    return {nid: rc[0] for nid, rc in placement(m)[0].items()}


def named(moves):
    """A move as the triple a test reads it by: kind, what it moves, and where it puts it."""
    out = []
    for m in moves:
        if m.kind == "swap":
            out.append(("swap", m.a, m.b))
        elif m.kind == "shift":
            out.append(("shift", m.node, m.cell))
        else:
            out.append(("lanes", tuple(m.lanes), m.order))
    return out


def starts(row):
    return [m.start() for m in TOKEN.finditer(row)]


@contextlib.contextmanager
def counted():
    """`flow.plan` with a spy in front of it for the length of the block, yielding the list of calls
    it saw — one dict of (mode, overrides, draft) per plan. The advice reaches the planner through
    the module, so this is every plan it makes and no plan of anyone else's."""
    calls = []
    real = flow.plan

    def spy(model, mode_name, overrides=None, draft=False):
        calls.append({"mode": mode_name, "overrides": overrides, "draft": draft})
        return real(model, mode_name, overrides, draft)

    flow.plan = spy
    try:
        yield calls
    finally:
        flow.plan = real


@contextlib.contextmanager
def lane_orders():
    """`itertools` as `advice` reaches it, with `permutations` bounded for the length of the block,
    yielding the list of lane counts it was asked for.

    The cap of `advice.MAX_LANES` is what keeps the search away from the 479 001 600 orders of a
    twelve-lane model, and a test cannot hold it by returning: a run that builds them does not fail,
    it runs for hours. Asked for the orders of more lanes than the cap allows, this raises, so the
    evidence is a failed assertion on the spot."""
    calls = []
    real = advice.itertools

    class Bounded:
        @staticmethod
        def permutations(iterable, r=None):
            seq = list(iterable)
            calls.append(len(seq))
            if len(seq) > advice.MAX_LANES:
                raise AssertionError(f"the orders of {len(seq)} lanes were asked for; "
                                     f"the cap is {advice.MAX_LANES}")
            return real.permutations(seq) if r is None else real.permutations(seq, r)

    advice.itertools = Bounded
    try:
        yield calls
    finally:
        advice.itertools = real


def one_seeded():
    """The cheapest of the twelve seeded models to search — the fewest edges, and the earliest
    instance among those. The tests that ask the search one question rather than twelve use it, so
    that asking it costs one small routing."""
    return min(seeded_models(), key=lambda km: (len(km[1]["edges"]), km[0]))[1]


def move_named(model, mode_name, kind, **want):
    """The one move of `model` the test means, by kind and by the attributes that name it."""
    return next(m for m in advice.moves(model, model, mode_name)
                if m.kind == kind and all(getattr(m, k) == v for k, v in want.items()))


# The flow the order of spec 6 is read on: `start` and `spare` share the first row, `check` stands
# under them and `done` two rows below it, so the grid has an empty row and an empty column to move
# into and the moves fall into the first two of the three groups. `start` and `spare` have no
# incoming edge and stand in the first row, so both are held there; `check` has to stay under both
# of them and above `done`.
ORDER = {"kind": "flow",
         "nodes": [card("start"), card("spare"),
                   {"id": "check", "title": "Проверка", "text": "по правилам [1]"}, terminal("done")],
         "grid": ["start  spare  .",
                  ".      check  .",
                  ".      .      .",
                  ".      done   ."],
         "edges": ["start -> check", "spare -> check", "check -> done"],
         "routes": {"основной": ["start", "check", "done"]},
         "footnotes": ["Правила лежат в конфиге"]}

# The chain the downward rule is read on: three cards in three rows, one column free beside them.
# `b` may move sideways and nowhere else — up puts it level with `a`, down level with `c` — and the
# swap of `b` and `c` is the move that would turn `b -> c` upward.
CHAIN = {"kind": "flow",
         "nodes": [card("a"), card("b"), terminal("c")],
         "grid": ["a  .", "b  .", "c  ."],
         "edges": ["a -> b", "b -> c"]}

# The model the level placement is read on: `a -> b` runs downward and the free cell beside `a` is
# where a move puts `b` level with it — which spec 6 allows. `b -> c` runs sideways in the author's
# own grid, so nothing holds it and `c` may go up past `b`.
LEVEL = {"kind": "flow",
         "nodes": [card("a"), card("b"), terminal("c")],
         "grid": ["a  .", "b  c"],
         "edges": ["a -> b", "b -> c"]}

# The model the sequence case is read on, and the one that tells the original grid from the grid in
# hand. `a -> b` runs downward; `s -> a` runs sideways, so `a` is the target of an edge and the
# first-row rule does not hold it where it stands. Carrying `b` up beside `s` lays the two cards of
# `a -> b` in one row, which the spec allows; from that grid, carrying `a` down again would put `b`
# above `a`, and only the original still says so.
SEQUENCE = {"kind": "flow",
            "nodes": [card("s"), card("a"), terminal("b")],
            "grid": ["a  s  .", ".  .  .", "b  .  ."],
            "edges": ["s -> a", "a -> b"]}

# T1's smallest model: `x` has no incoming edge and stands in the first row, so it stays there —
# out of it `flow.plan` calls it unreachable. Nothing else holds it: `x -> y` runs along row 0 and
# the downward edge `y -> z` does not touch it, so the rule is the only thing between the search and
# "перенести x в пустую ячейку [1, 0]".
ROOT = {"kind": "flow",
        "nodes": [card("x"), card("y"), terminal("z")],
        "grid": ["x  y", ".  z"],
        "edges": ["x -> y", "y -> z"]}

# The fork the wording of a swap across two rows is read on: `x` and `y` hang off `src` and neither
# holds the other, so they may exchange rows.
FORK = {"kind": "flow",
        "nodes": [card("src"), terminal("x"), terminal("y")],
        "grid": ["src  .", "x    .", "y    ."],
        "edges": ["src -> x", "src -> y"]}

# A node with no incoming edge that the author did not put in the first row: `flow.plan` already
# calls it unreachable, so nothing holds it where it stands.
LOOSE = {"kind": "flow",
         "nodes": [card("a"), terminal("b"), terminal("c")],
         "grid": ["a  .", "b  c"],
         "edges": ["a -> b"]}

# The grid whose first line leaves off the empty cells at its end, and whose last column holds the
# one card `c`: carrying `c` out of that column has to bring the cells back, or the grid narrows
# and every card on the page grows with it.
SHORT = {"kind": "flow",
         "nodes": [card("a"), terminal("b"), terminal("c")],
         "grid": ["a", "b  .  c"],
         "edges": ["a -> b", "a -> c"]}

LANES = {"client": {"label": "клиент", "ramp": "pink"},
         "back": {"label": "бэкенд", "ramp": "teal"},
         "prov": {"label": "провайдер", "ramp": "coral"}}

# The swimlane: every node carries the group of its own lane, which is what a lane order has to keep
# true — the column moves with the lane, so the node stays in the lane the author gave it.
SWIM = {"kind": "swimlane",
        "groups": LANES,
        "lanes": ["client", "back", "prov"],
        "nodes": [dict(card("ask"), group="client"),
                  dict(card("look"), group="back"),
                  dict(card("call"), group="prov"),
                  dict(terminal("done"), group="client")],
        "grid": ["ask   .     .",
                 ".     look  .",
                 ".     .     call",
                 "done  .     ."],
        "edges": ["ask -> look", "look -> call", "call -> done"]}


# A column of three cards and a free column beside it. Every swap turns a downward edge, so the
# moves are the six that carry one card sideways, and each of them lengthens a line that runs
# straight down: the search verifies them and keeps none.
STRAIGHT = {"kind": "flow",
            "nodes": [card("a"), card("b"), terminal("c")],
            "grid": ["a  .", "b  .", "c  ."],
            "edges": ["a -> b", "b -> c"]}

# Gate finding G2: the render forwards --width to `flow.plan`, so a verifying plan run at another
# width verifies a picture the render will not draw. Swapping `c` and `d` takes the one crossing of
# this grid out — which is what keeps the move in the advised sequence at all — and it lays
# `a -> d` straight down the first column, where the label hangs at the exit and what is left of the
# page bounds it: 24 characters against the ~23 that fit at 560 and enough of them at the page's own
# 1100. So the move is an improvement at the default width and a label that does not fit at the
# narrow one.
NARROW = {"total": 560}
G2 = {"kind": "flow",
      "nodes": [card("a"), card("b"), card("c"), card("d"), terminal("e")],
      "grid": ["a  b", "c  d", "e  ."],
      "edges": ["b -> c", "b -> e", "a -> b", "a -> e", "c -> d", "d -> e",
                "a -> d : ответ провайдера получен"]}


def wide_swimlane(n):
    """A swimlane of `n` lanes, one card per lane in a row of its own."""
    ids = [f"l{i}" for i in range(n)]
    return {"kind": "swimlane",
            "groups": {i: {"label": i, "ramp": "teal"} for i in ids},
            "lanes": list(ids),
            "nodes": [dict(card(i), group=i) for i in ids],
            "grid": ["  ".join(ids[c] if c == r else "." for c in range(n)) for r in range(n)],
            "edges": [f"{a} -> {b}" for a, b in zip(ids, ids[1:])]}


class OrderOfTheMoves(unittest.TestCase):
    """Spec 6: tried in order of how little they disturb the reading — inside one row, then to the
    adjacent row, then the rest — and ties go to the earlier node in the model."""

    def distance(self, m, cells):
        if m.kind == "swap":
            return abs(cells[m.a][0] - cells[m.b][0])
        return abs(cells[m.node][0] - m.cell[0])

    def test_the_rows_a_move_reaches_over_never_shrink(self):
        cells = placement(ORDER)[0]
        seen = [min(2, self.distance(m, cells)) for m in advice.moves(ORDER, ORDER)]
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(set(seen), {0, 1, 2}, "harness: this model no longer reaches all three groups")

    def test_a_swap_inside_one_row_comes_first(self):
        first = advice.moves(ORDER, ORDER)[0]
        self.assertEqual(("swap", "start", "spare"), named([first])[0])

    def test_ties_go_to_the_earlier_node_in_the_model(self):
        order = [n["id"] for n in ORDER["nodes"]]
        cells = placement(ORDER)[0]
        for kind in ("swap", "shift"):
            moved = [m for m in advice.moves(ORDER, ORDER)
                     if m.kind == kind and self.distance(m, cells) == 0]
            ranks = [order.index(m.a if kind == "swap" else m.node) for m in moved]
            with self.subTest(kind=kind):
                self.assertEqual(ranks, sorted(ranks))

    def test_two_calls_give_the_same_moves(self):
        self.assertEqual(named(advice.moves(ORDER, ORDER)), named(advice.moves(ORDER, ORDER)))


class MakesNothingUpward(unittest.TestCase):
    """Spec 6: an edge that runs downward in the original grid never has its target above its
    source, and the rule holds for the whole sequence of moves and not for one of them at a time.
    Level is allowed — the spec drops the move that puts the target above the source, and no more
    than that."""

    def down(self, original):
        cells = placement(original)[0]
        pairs = []
        for raw in original["edges"]:
            a, b = (s.strip() for s in raw.split("->"))
            if cells[a][0] < cells[b][0]:
                pairs.append((a, b))
        return pairs

    def reached(self, original, depth):
        """Every grid a sequence of at most `depth` moves reaches from the author's own."""
        seen, frontier = {}, [original]
        for _ in range(depth):
            nxt = []
            for m in frontier:
                for move in advice.moves(original, m):
                    out = move.apply(m)
                    key = tuple(out["grid"])
                    if key not in seen:
                        seen[key] = out
                        nxt.append(out)
            frontier = nxt
        return list(seen.values())

    def test_a_move_that_would_turn_an_edge_upward_is_not_offered(self):
        self.assertNotIn(("swap", "b", "c"), named(advice.moves(CHAIN, CHAIN)))

    def test_a_move_that_only_levels_an_edge_is_offered(self):
        offered = named(advice.moves(LEVEL, LEVEL))
        self.assertIn(("shift", "b", (0, 1)), offered)
        self.assertIn(("shift", "c", (0, 1)), offered,
                      "harness: `b -> c` runs sideways in the author's grid, so nothing holds `c`")

    def test_no_sequence_of_moves_turns_a_downward_edge_upward(self):
        for original in (LEVEL, CHAIN, ORDER):
            pairs = self.down(original)
            grids = self.reached(original, 3)
            with self.subTest(grid=tuple(original["grid"])):
                self.assertTrue(pairs and grids, "harness: nothing to hold, or nothing reached")
                for m in grids:
                    rows = rows_of(m)
                    for a, b in pairs:
                        self.assertLessEqual(rows[a], rows[b], f"{a} -> {b} in {m['grid']}")


class TheOriginalGrid(unittest.TestCase):
    """Spec 6: every produced grid is judged against the grid the author **wrote**, not against the
    grid the move starts from. The two only differ once a move has been made, so the witness is a
    sequence: `b` goes up beside `s`, which lays `a -> b` level and is allowed, and from that grid
    carrying `a` back down is refused — by the original alone, since the grid in hand has `a` and
    `b` in one row and nothing there runs downward any more.

    The same model reads the other half of the first-row rule: `a` stands in the first row and is
    the target of `s -> a`, so the rule does not hold it — only a node nothing enters is held."""

    def carried(self):
        """(the move that lays `a -> b` level, the grid it leaves behind)."""
        move = move_named(SEQUENCE, None, "shift", node="b", cell=(0, 2))
        return move, move.apply(SEQUENCE)

    def test_the_level_placement_is_accepted(self):
        self.assertIn(("shift", "b", (0, 2)), named(advice.moves(SEQUENCE, SEQUENCE)))

    def test_a_node_an_edge_enters_is_not_held_in_the_first_row(self):
        self.assertIn(("shift", "a", (1, 0)), named(advice.moves(SEQUENCE, SEQUENCE)))

    def test_the_reversal_is_refused_from_the_grid_the_level_move_reached(self):
        _, current = self.carried()
        self.assertEqual(["a  s  b", ".  .  .", ".  .  ."], current["grid"])
        self.assertIn(("shift", "a", (1, 0)), named(advice.moves(current, current)),
                      "harness: judged against the grid in hand, this move is allowed")
        self.assertNotIn(("shift", "a", (1, 0)), named(advice.moves(SEQUENCE, current)))


class TheFirstRow(unittest.TestCase):
    """Spec 6: a move never takes a node without incoming edges out of the first row — out of it
    `flow.plan` calls the node unreachable, which is an error the author's own grid did not have."""

    def test_a_node_nothing_enters_stays_in_the_first_row(self):
        for original in (CHAIN, ORDER):
            with self.subTest(grid=tuple(original["grid"])):
                for m in advice.moves(original, original):
                    rows = rows_of(m.apply(original))
                    for nid in ("a", "start", "spare"):
                        if nid in rows:
                            self.assertEqual(0, rows[nid], m.text())

    def test_it_may_still_move_along_that_row(self):
        self.assertIn(("shift", "a", (0, 1)), named(advice.moves(CHAIN, CHAIN)))

    def test_a_node_the_author_put_lower_is_not_held_there(self):
        self.assertIn(("shift", "c", (0, 1)), named(advice.moves(LOOSE, LOOSE)))

    def test_the_one_move_the_rule_exists_to_refuse(self):
        # the smallest grid where nothing but this rule stands between the search and a node it
        # would carry out of the first row, leaving `flow.plan` to call it unreachable
        offered = named(advice.moves(ROOT, ROOT))
        self.assertNotIn(("shift", "x", (1, 0)), offered)
        self.assertIn(("shift", "y", (1, 0)), offered,
                      "harness: the empty cell is reachable, and `y` is entered by an edge")
        carried = advice.Shift("x", (1, 0)).apply(ROOT)
        _, warnings = flow.plan(copy.deepcopy(carried), "page")
        self.assertTrue([w for w in warnings if w.startswith("узел x: нет входящих связей")],
                        "harness: the grid this rule refuses no longer carries that warning")


class ApplyingAMove(unittest.TestCase):
    """Spec 6: every move is applied to a deep copy of the model and changes `grid` alone —
    `flow.plan` writes `_note` and `_text` into the nodes of the model it plans, so a move that
    shared them would hand the next plan the notes of the last one."""

    def test_the_argument_is_left_untouched(self):
        before = copy.deepcopy(ORDER)
        for m in advice.moves(ORDER, ORDER):
            out = m.apply(ORDER)
            out["nodes"][0]["title"] = "изменено"
            out["grid"][0] = "изменено"
            with self.subTest(move=m.text()):
                self.assertEqual(before, ORDER)

    def test_only_the_grid_differs(self):
        for m in advice.moves(ORDER, ORDER):
            out = m.apply(ORDER)
            with self.subTest(move=m.text()):
                for key in ("nodes", "edges", "routes", "footnotes", "kind"):
                    self.assertEqual(ORDER[key], out[key])
                self.assertNotEqual(ORDER["grid"], out["grid"])

    def test_the_notes_a_plan_wrote_are_not_shared(self):
        planned = copy.deepcopy(ORDER)
        flow.plan(planned, "page")
        self.assertIn("_note", planned["nodes"][2], "harness: this model no longer carries a footnote")
        out = advice.moves(planned, planned)[0].apply(planned)
        self.assertEqual(planned["nodes"][2], out["nodes"][2])
        self.assertIsNot(planned["nodes"][2], out["nodes"][2])

    def test_the_grid_keeps_its_width_and_its_height(self):
        want = placement(ORDER)[1:]
        for m in advice.moves(ORDER, ORDER):
            with self.subTest(move=m.text()):
                self.assertEqual(want, placement(m.apply(ORDER))[1:])

    def test_the_result_plans(self):
        for m in advice.moves(ORDER, ORDER):
            out = m.apply(ORDER)
            with self.subTest(move=m.text()):
                layout, _ = flow.plan(copy.deepcopy(out), "page")
                self.assertEqual(len(ORDER["nodes"]), len(layout["cells"]))


class TheGridTheAuthorWrote(unittest.TestCase):
    """The grid is written back at the column offsets the input used, so a diff of the author's JSON
    shows only what moved. `dense-widget-flow` is the model that asks for it: its columns are one
    character wider than the longest token in them, which no rule derives and only the input says."""

    def test_a_row_nothing_moved_in_is_written_back_byte_for_byte(self):
        m = model("dense-widget-flow.json")
        for move in advice.moves(m, m)[:40]:
            out = move.apply(m)
            changed = [r for r, (a, b) in enumerate(zip(m["grid"], out["grid"])) if a != b]
            with self.subTest(move=move.text()):
                self.assertLessEqual(len(changed), 2)
                self.assertTrue(changed)
                for r in changed:
                    self.assertEqual(starts(m["grid"][r]), starts(out["grid"][r]))

    def test_a_swap_inside_one_row_rewrites_that_row_alone(self):
        m = model("dense-widget-flow.json")
        move = next(x for x in advice.moves(m, m) if x.kind == "swap" and x.a == "retry" and x.b == "check")
        out = move.apply(m)
        self.assertEqual([".       check   retry"] + m["grid"][1:], out["grid"])

    def test_the_empty_cells_a_line_left_off_come_back_with_the_width(self):
        move = next(m for m in advice.moves(SHORT, SHORT) if m.kind == "shift" and m.node == "c")
        out = move.apply(SHORT)
        self.assertEqual(["a", "b  c  ."], out["grid"])
        self.assertEqual(placement(SHORT)[1:], placement(out)[1:])


class Swimlanes(unittest.TestCase):
    """Spec 6: a swimlane moves no node on its own; its only move is a lane order that takes the
    grid columns with it, so every node stays in the lane the author gave it."""

    def test_only_lane_orders(self):
        found = advice.moves(SWIM, SWIM)
        self.assertTrue(found)
        self.assertEqual({"lanes"}, {m.kind for m in found})

    def test_every_order_but_the_author_s_own(self):
        found = advice.moves(SWIM, SWIM)
        self.assertEqual(5, len(found))
        self.assertEqual(len(found), len({tuple(m.lanes) for m in found}))
        self.assertNotIn(tuple(SWIM["lanes"]), {tuple(m.lanes) for m in found})

    def test_the_columns_move_with_the_lanes(self):
        for m in advice.moves(SWIM, SWIM):
            out = m.apply(SWIM)
            cells = placement(out)[0]
            with self.subTest(move=m.text()):
                self.assertEqual(out["lanes"], list(m.lanes))
                for n in out["nodes"]:
                    self.assertEqual(n["group"], out["lanes"][cells[n["id"]][1]])

    def test_every_order_plans_without_a_lane_error(self):
        for m in advice.moves(SWIM, SWIM):
            out = m.apply(SWIM)
            with self.subTest(move=m.text()):
                _, warnings = flow.plan(copy.deepcopy(out), "page")
                self.assertEqual([], [w for w in warnings if "дорожк" in w or "группа" in w])

    def test_the_rows_never_move(self):
        want = rows_of(SWIM)
        for m in advice.moves(SWIM, SWIM):
            self.assertEqual(want, rows_of(m.apply(SWIM)))


class LaneOrders(unittest.TestCase):
    """Gate finding G3: `draft` downgrades the lane limit, so a model of twelve lanes reaches the
    advice; the orders of twelve lanes are 479 001 600 and the allowance of verifying plans does not
    bound them. A model over the limit of its mode gets no moves at all, and `lane_orders()` is what
    says so as a failure: every one of these runs under a `permutations` that refuses to build the
    orders of more lanes than the cap allows, so a cap that stopped holding is a failed assertion
    and not a suite that never finishes."""

    def test_a_model_over_the_widest_limit_gets_nothing(self):
        # A lane per column is what `flow.plan` asks of a swimlane, so this model is over the column
        # limit as well, and that limit is the one that answers here — the cap alone is read by
        # `test_the_cap_holds_where_no_other_limit_would`.
        with lane_orders() as asked:
            self.assertEqual([], advice.moves(wide_swimlane(12), wide_swimlane(12)))
        self.assertEqual([], asked)

    def test_the_cap_holds_where_no_other_limit_would(self):
        # The twelve lanes over a grid of three columns — a model the renderer refuses, and the one
        # reading where the cap is the only thing between the advice and 479 001 600 orders.
        narrow = wide_swimlane(12)
        narrow["grid"] = ["l0  .   .", ".   l1  .", ".   .   l2"]
        with lane_orders() as asked:
            self.assertEqual([], advice.moves(narrow, narrow))
        self.assertEqual([], asked)

    def test_the_widest_mode_is_the_cap_when_no_mode_is_named(self):
        seven = wide_swimlane(7)
        with lane_orders() as asked:
            self.assertEqual(advice.MAX_LANE_ORDERS - 1, len(advice.moves(seven, seven)))
        self.assertEqual([7], asked, "harness: the orders of the widest model are drawn once")
        eight = wide_swimlane(8)
        with lane_orders() as asked:
            self.assertEqual([], advice.moves(eight, eight))
        self.assertEqual([], asked)

    def test_a_named_mode_brings_its_own_limit(self):
        seven = wide_swimlane(7)
        with lane_orders() as asked:
            self.assertEqual([], advice.moves(seven, seven, "widget"))
        self.assertEqual([], asked)
        five = wide_swimlane(5)
        self.assertEqual(119, len(advice.moves(five, five, "widget")))

    def test_a_model_over_the_node_or_column_limit_gets_nothing(self):
        tall = copy.deepcopy(ORDER)
        tall["nodes"] = ORDER["nodes"] + [card(f"n{i}") for i in range(30)]
        self.assertEqual([], advice.moves(tall, tall))
        wide = copy.deepcopy(ORDER)
        wide["grid"] = [row + "  .  .  .  .  ." for row in ORDER["grid"]]
        self.assertEqual([], advice.moves(wide, wide))


class Wording(unittest.TestCase):
    """Spec 6's output block: the advice names nodes by their id and counts rows and cells from
    zero, the way `grid, ряд N` and the two cells of a node placed twice count them."""

    def test_a_swap_inside_one_row(self):
        move = next(m for m in advice.moves(ORDER, ORDER) if m.kind == "swap")
        self.assertEqual("поменять местами start и spare (ряд 0)", move.text())

    def test_a_swap_across_two_rows(self):
        move = next(m for m in advice.moves(FORK, FORK) if m.kind == "swap")
        self.assertEqual("поменять местами x и y (ряды 1 и 2)", move.text())

    def test_a_move_into_an_empty_cell(self):
        move = next(m for m in advice.moves(ORDER, ORDER) if m.kind == "shift" and m.node == "check")
        self.assertEqual("перенести check в пустую ячейку [1, 0]", move.text())

    def test_a_lane_order(self):
        move = next(m for m in advice.moves(SWIM, SWIM) if list(m.lanes) == ["client", "prov", "back"])
        self.assertEqual("переставить дорожки: client, prov, back", move.text())


class NothingToAdvise(unittest.TestCase):
    """A model the advice can say nothing about: no grid to read, or a grid the renderer itself
    refuses. The search has nothing to try and says so with an empty list."""

    def test_a_model_without_a_grid(self):
        self.assertEqual([], advice.moves({"kind": "flow", "nodes": []}, {"kind": "flow", "nodes": []}))

    def test_a_grid_the_parser_refuses(self):
        broken = copy.deepcopy(CHAIN)
        broken["grid"] = ["a  .", "b  .", "a  ."]
        self.assertEqual([], advice.moves(broken, broken))

    def test_one_card_alone(self):
        alone = {"kind": "flow", "nodes": [terminal("a")], "grid": ["a"], "edges": []}
        self.assertEqual([], advice.moves(alone, alone))


class WhatADraftPlanReports(unittest.TestCase):
    """Spec 6 as amended: `flow.plan(…, draft=True)` puts into `layout` what the search needs — the
    slots the routing takes past what its lattice lines hold, and the groups that take them — and
    nothing else of `layout` changes. `overfull-gutter.json` is the model the check refuses in
    widget mode, so its draft is the one that has something to report."""

    def test_a_draft_plan_reports_the_overflow_and_its_group(self):
        layout, warnings = flow.plan(model("overfull-gutter.json"), "widget", None, draft=True)
        self.assertEqual(1, layout["overflow"])
        self.assertEqual(1, len(layout["overfull"]))
        axis, line, width, idx, cap = layout["overfull"][0]
        # the gutter between the first two columns holds three lines and is drawn with four
        self.assertEqual(("v", 2, 4, 3), (axis, line, width, cap))
        self.assertEqual(width - cap, layout["overflow"])
        named_edges = {(layout["edges"][i]["a"], layout["edges"][i]["b"]) for i in idx}
        self.assertEqual({("utochnenie", "otvet"), ("utochnenie", "peredano"),
                          ("robot", "zayavka"), ("razbor", "utochnenie")}, named_edges)
        self.assertTrue([w for w in warnings if w.startswith("черновик: между столбцами 0 и 1")])

    def test_without_the_draft_the_model_is_refused(self):
        with self.assertRaises(ModelError):
            flow.plan(model("overfull-gutter.json"), "widget")

    def test_a_plan_that_is_not_a_draft_carries_the_two_keys_too(self):
        # A plan without `draft` that returns at all has no group past its capacity — such a group
        # is a layout error and the plan raises instead of returning — so the two keys are there
        # with nothing in them, and a caller reads one shape whatever it asked for.
        layout, _ = flow.plan(copy.deepcopy(ORDER), "page")
        self.assertEqual((0, []), (layout["overflow"], layout["overfull"]))


class TheProxy(unittest.TestCase):
    """Spec 6: the cheap ranking — 10 per crossing of the straight lines between cell centres, 6 per
    node lying on the straight line of an edge along one row or column, 3 per edge going up, plus
    the Manhattan length of them all. It reads the grid and the edges and plans nothing."""

    def proxy_of(self, grid, edges):
        return advice.proxy({"kind": "flow", "grid": grid, "edges": edges,
                             "nodes": [card(t) for row in grid for t in row.split() if t != "."]})

    def test_the_length_of_one_edge(self):
        self.assertEqual(2, self.proxy_of(["a  .  b"], ["a -> b"]))

    def test_an_edge_that_goes_up(self):
        self.assertEqual(3 + 1, self.proxy_of(["b", "a"], ["a -> b"]))

    def test_a_node_on_the_line_of_an_edge_along_a_row(self):
        self.assertEqual(6 + 2, self.proxy_of(["a  c  b"], ["a -> b"]))

    def test_a_node_beside_the_line_is_not_on_it(self):
        self.assertEqual(2, self.proxy_of(["a  .  b", ".  c  ."], ["a -> b"]))

    def test_two_lines_that_cross(self):
        self.assertEqual(10 + 4 + 4, self.proxy_of(["a  .  d", ".  .  .", "c  .  b"],
                                                   ["a -> b", "d -> c"]))

    def test_two_lines_that_meet_at_a_card_do_not_cross(self):
        self.assertEqual(2 + 2, self.proxy_of(["a  .  b", ".  c  ."], ["a -> c", "b -> c"]))

    def test_a_grid_the_parser_refuses_scores_nothing(self):
        self.assertEqual(0, advice.proxy({"kind": "flow", "nodes": [], "edges": []}))


class Evaluating(unittest.TestCase):
    """Spec 6 as amended: `evaluate` plans a deep copy as a draft and answers the score the search
    compares — (slots over capacity, crossings as the plan reports them, the Manhattan length of the
    paths) — together with the messages the draft downgraded and how many warnings the plan carried,
    the crossings warning aside. The count is the one the search holds a move to: a grid the advice
    hands over may not bring a warning the author's own grid did not have, and the crossings warning
    is what the moves are there to lower."""

    def test_the_score_and_the_messages_of_the_draft(self):
        score, errors, _ = advice.evaluate(model("overfull-gutter.json"), "widget")
        self.assertEqual((1, 3), score[:2])
        self.assertGreater(score[2], 0)
        self.assertEqual(1, len(errors))
        self.assertTrue(next(iter(errors)).startswith("между столбцами 0 и 1"))
        self.assertFalse([e for e in errors if e.startswith("черновик")])

    def test_a_model_nothing_is_wrong_with_has_no_messages(self):
        score, errors, _ = advice.evaluate(ORDER, "page")
        self.assertEqual(set(), errors)
        self.assertEqual(0, score[0])

    def test_the_crossings_warning_is_not_counted_and_every_other_one_is(self):
        m = model("overfull-gutter.json")
        counted_warnings = advice.evaluate(m, "widget")[2]
        _, warnings = flow.plan(copy.deepcopy(m), "widget", None, draft=True)
        plain = [w for w in warnings if not w.startswith(flow.DRAFT)]
        self.assertEqual(1, len([w for w in plain if w.startswith(flow.CROSSINGS)]),
                         "harness: this model no longer crosses enough for the warning")
        self.assertEqual((4, 3), (len(plain), counted_warnings))
        # ORDER's own two: the empty row and the empty column of its grid
        self.assertEqual(2, advice.evaluate(ORDER, "page")[2])
        self.assertEqual(0, advice.evaluate(LOOSE, "page")[2])

    def test_the_argument_is_left_untouched(self):
        before = copy.deepcopy(ORDER)
        advice.evaluate(ORDER, "page")
        self.assertEqual(before, ORDER)

    def test_two_calls_agree(self):
        self.assertEqual(advice.evaluate(ORDER, "page"), advice.evaluate(ORDER, "page"))

    def test_the_plan_it_makes_is_a_draft_at_the_mode_and_the_overrides_it_was_given(self):
        with counted() as calls:
            advice.evaluate(ORDER, "page", NARROW)
        self.assertEqual([{"mode": "page", "overrides": NARROW, "draft": True}], calls)


class HillClimbing(unittest.TestCase):
    """Criterion D2, on the twelve seeded models: the search returns moves, the advised grid scores
    lower than the one the author wrote, a fresh plan of it gives that very score, and it carries no
    message and no extra warning the start did not carry."""

    def test_the_population_is_the_twelve_of_the_measurement(self):
        # the benchmark owns them and the tests are held to the very population it measures; a
        # population that quietly shrank would leave both green and neither of them saying much
        self.assertEqual(12, len(seeded_models()))

    def test_every_seeded_model_is_improved_and_the_advice_holds(self):
        for k, m in seeded_models():
            with self.subTest(instance=k):
                with counted() as calls:
                    found = advice.search(m, ADVICE_MODE)
                self.assertTrue(found, "no move improved this model")
                self.assertLessEqual(len(calls), advice.MAX_PLANS)
                self.assertLessEqual(len(found), advice.MAX_MOVES)
                advised = m
                for move, _, _ in found:
                    advised = move.apply(advised)
                start, start_errors, start_warnings = advice.evaluate(m, ADVICE_MODE)
                score, errors, warnings = advice.evaluate(advised, ADVICE_MODE)
                self.assertEqual(start, found[0][1])
                self.assertEqual(score, found[-1][2])
                self.assertLess(score, start)
                self.assertEqual(set(), errors - start_errors)
                self.assertLessEqual(warnings, start_warnings)
                # spec 6 as amended: the search climbs on the whole score, but the author is not
                # asked for the cosmetic moves — the sequence ends with the last move that lowered
                # overflow or crossings, never with one that only shortened the lines
                last, before, after = found[-1]
                self.assertLess(after[:2], before[:2], last.text())

    def test_the_score_falls_strictly_at_every_step(self):
        found = advice.search(one_seeded(), ADVICE_MODE)
        for move, before, after in found:
            self.assertLess(after, before, move.text())
        for (_, _, after), (_, before, _) in zip(found, found[1:]):
            self.assertEqual(after, before)

    def test_the_same_model_twice_gives_the_same_moves(self):
        m = one_seeded()
        self.assertEqual(named([x[0] for x in advice.search(m, ADVICE_MODE)]),
                         named([x[0] for x in advice.search(m, ADVICE_MODE)]))

    def test_the_argument_is_left_untouched(self):
        m = one_seeded()
        before = copy.deepcopy(m)
        self.assertTrue(advice.search(m, ADVICE_MODE))
        self.assertEqual(before, m)

    def test_a_model_no_move_improves_gets_nothing(self):
        with counted() as calls:
            self.assertEqual([], advice.search(STRAIGHT, "page"))
        self.assertGreater(len(calls), 1, "harness: this model no longer has a move to verify")


class NoNewWarning(unittest.TestCase):
    """Spec 6 as amended: a move is dropped where its plan carries a layout error the start did not
    have, or more warnings than the start — the crossings warning aside, which is the count the
    moves exist to lower. `SKILL.md` tells the author to treat a warning as an error, so a grid the
    advice hands over must not bring one.

    The gate bites where the score alone would not. On seeded #15 it bites at the very first step:
    the best move by score opens an empty row, and the search takes a worse-scoring move instead.
    On #6 it bites three steps in, which no single step can be read off; that one is held by the
    population assertion of `HillClimbing`, which measures the grid the whole advice hands over."""

    def best_by_score(self, m):
        """The move the first step would take if nothing but the score were read — the best of the
        `TOP` the proxy ranks highest, priced by the same `evaluate` the search uses."""
        start, _, _ = advice.evaluate(m, ADVICE_MODE)
        cells = placement(m)[0]
        edges = advice.edges_of(m)
        found = advice.moves(m, m, ADVICE_MODE)
        ranked = sorted(range(len(found)),
                        key=lambda k: (advice._proxy(found[k].moved(cells), edges), k))
        best = None
        for k in ranked[:advice.TOP]:
            score, _, warnings = advice.evaluate(found[k].apply(m), ADVICE_MODE)
            if score < start and (best is None or score < best[0]):
                best = (score, warnings, found[k])
        return best

    def test_the_best_move_by_score_is_refused_where_it_brings_a_warning(self):
        m = dict(seeded_models())[15]
        allowed = advice.evaluate(m, ADVICE_MODE)[2]
        best = self.best_by_score(m)
        self.assertIsNotNone(best, "harness: nothing at the first step improves the score")
        self.assertGreater(best[1], allowed,
                           "harness: the best move by score no longer brings a warning")
        taken = advice.search(m, ADVICE_MODE)[0]
        self.assertNotEqual(best[2].text(), taken[0].text())
        # and the gate cost the search something: the move it refused scored lower than the one
        # it took
        self.assertLess(best[0], taken[2])


class TheNumbersOfTheSpec(unittest.TestCase):
    """Spec 6 fixes two of the three numbers of the search: an advice proposes at most eight moves,
    and one step verifies the best eight moves of the grid in hand. `MAX_PLANS` is the owner's — it
    was measured and ruled on — so `ThePlanAllowance` holds its mechanism and nothing holds its
    value."""

    def test_at_most_eight_moves_and_the_best_eight_verified(self):
        self.assertEqual((8, 8), (advice.MAX_MOVES, advice.TOP))

    def test_one_step_verifies_the_best_top_and_no_more(self):
        m = one_seeded()
        self.assertGreater(len(advice.moves(m, m, ADVICE_MODE)), advice.TOP,
                           "harness: this model no longer offers more moves than one step verifies")
        with counted() as calls:
            advice.search(m, ADVICE_MODE, None, max_moves=1)
        # the plan that prices the author's own grid, then the best `TOP` of the ranking and no more
        self.assertEqual(advice.TOP + 1, len(calls))


class ThePlanAllowance(unittest.TestCase):
    """Spec 6: the search is bounded in verifying plans and in moves, and the gate's finding G3 —
    a model over a limit of its mode is advised nothing and does not plan even once."""

    def test_the_allowance_is_what_stops_it(self):
        m = one_seeded()
        with counted() as calls:
            advice.search(m, ADVICE_MODE, None, max_plans=9)
        self.assertLessEqual(len(calls), 9)
        self.assertGreater(len(calls), 1)

    def test_the_move_count_is_what_stops_it(self):
        m = one_seeded()
        self.assertEqual(1, len(advice.search(m, ADVICE_MODE, None, max_moves=1)))

    def test_a_model_over_a_limit_of_its_mode_plans_nothing(self):
        with counted() as calls:
            self.assertEqual([], advice.search(wide_swimlane(12), ADVICE_MODE))
        self.assertEqual([], calls)

    def test_a_model_the_renderer_refuses_outright_is_advised_nothing(self):
        broken = copy.deepcopy(ORDER)
        broken["edges"] = ORDER["edges"] + ["check -> nowhere"]
        self.assertEqual([], advice.search(broken, "page"))


class TheRendersOwnWidth(unittest.TestCase):
    """Gate finding G2: every verifying plan is made at the geometry the render will draw, so a move
    is never offered on the strength of a width the render does not use."""

    def test_the_start_fits_at_both_widths(self):
        for overrides in (None, NARROW):
            with self.subTest(overrides=overrides):
                self.assertEqual(set(), advice.evaluate(G2, "page", overrides)[1])

    def test_the_move_carries_a_label_error_at_the_narrow_width_alone(self):
        moved = move_named(G2, "page", "swap", a="c", b="d").apply(G2)
        self.assertEqual(set(), advice.evaluate(moved, "page")[1])
        errors = advice.evaluate(moved, "page", NARROW)[1]
        self.assertEqual(1, len(errors))
        self.assertIn("не помещается у выхода вниз", next(iter(errors)))

    def test_the_move_is_offered_at_the_default_width(self):
        found = advice.search(G2, "page")
        self.assertEqual([("swap", "c", "d")], named([x[0] for x in found]))
        # and it is the crossing it takes out that keeps it in the advised sequence
        self.assertLess(found[-1][2][:2], found[0][1][:2])

    def test_and_is_not_offered_under_the_narrow_override(self):
        # What the width decides is that one move. The advice still has others to offer here: the
        # author's own grid carries a warning of its own — `b -> c` runs through the text over the
        # second segment of `a -> d`, which the occupancy model sees and the check before it, reading
        # the whole segment instead of the text, missed — so the climb is weighed against one warning
        # rather than none and reaches a move that takes the crossing out. The premise is asserted
        # first: without that warning the moves below are refused and nothing at all is offered.
        self.assertEqual(1, advice.evaluate(G2, "page", NARROW)[2])
        found = advice.search(G2, "page", NARROW)
        self.assertNotIn(("swap", "c", "d"), named([x[0] for x in found]))
        self.assertLess(found[-1][2][:2], found[0][1][:2])

    def test_every_verifying_plan_gets_the_overrides(self):
        with counted() as calls:
            advice.search(G2, "page", NARROW)
        self.assertTrue(calls)
        self.assertEqual([{"mode": "page", "overrides": NARROW, "draft": True}] * len(calls), calls)


if __name__ == "__main__":
    unittest.main()
