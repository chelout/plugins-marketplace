"""advice.moves: what a rearrangement advice may propose on a grid (spec 6 "Moves" and "Swimlane",
criterion D1).

The moves come in the order spec 6 asks for — inside one row, then to the adjacent row, then the
rest — and every one of them is judged against the grid the author wrote, never against the grid it
starts from, so that a sequence of moves cannot walk past a rule one step at a time. Two rules:
an edge that runs downward in the original grid keeps running downward, and a node the author gave
no incoming edge stays in the first row if that is where it stood.

The first rule is read one step stricter than spec 6 words it. The spec drops a move that puts such
a target *above* its source, which leaves a target level with its source allowed; the rule below
keeps it strictly below. The sequence case is what asks for it: a move that makes a downward edge
horizontal is the state from which the next move has nothing left in the grid to be judged against,
and the reading the author wrote — this step follows that one — is already gone once the two stand
in one row. `MakesNothingUpward` holds both readings: the move that levels an edge is not offered,
and no sequence of moves reaches a grid where a downward edge of the original runs level or up.

A swimlane moves no node of its own: a column is a lane and a row is a moment, so the only move is a
lane order that takes the grid columns with it. `LaneOrders` holds the cap of the plan's gate
finding G3 with a model of twelve lanes: the test returning at all is the evidence that no
permutation of it was ever drawn.
"""
import copy
import json
import re
import unittest

import support  # noqa: F401
from diagrams import advice, flow
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

# The model the sequence case is read on: `a -> b` runs downward and the free cell beside `a` is
# where a move would put `b` level with it. `b -> c` runs sideways in the author's own grid, so
# nothing holds it and `c` may go up past `b`.
LEVEL = {"kind": "flow",
         "nodes": [card("a"), card("b"), terminal("c")],
         "grid": ["a  .", "b  c"],
         "edges": ["a -> b", "b -> c"]}

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
        self.assertEqual(set(seen), {0, 1}, "harness: this model no longer reaches two of the three groups")

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
    """Spec 6: an edge that runs downward in the original grid keeps its target below its source,
    and the rule holds for the whole sequence of moves and not for one of them at a time."""

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

    def test_a_move_that_would_only_level_an_edge_is_not_offered_either(self):
        offered = named(advice.moves(LEVEL, LEVEL))
        self.assertNotIn(("shift", "b", (0, 1)), offered)
        self.assertIn(("shift", "c", (0, 1)), offered,
                      "harness: `b -> c` runs sideways in the author's grid, so nothing holds `c`")

    def test_no_sequence_of_moves_loses_a_downward_edge(self):
        for original in (LEVEL, CHAIN, ORDER):
            pairs = self.down(original)
            grids = self.reached(original, 3)
            with self.subTest(grid=tuple(original["grid"])):
                self.assertTrue(pairs and grids, "harness: nothing to hold, or nothing reached")
                for m in grids:
                    rows = rows_of(m)
                    for a, b in pairs:
                        self.assertLess(rows[a], rows[b], f"{a} -> {b} in {m['grid']}")


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
    bound them. A model over the limit of its mode gets no moves at all, and this test returning is
    the evidence that no order of it was ever drawn."""

    def test_a_model_over_the_widest_limit_gets_nothing(self):
        self.assertEqual([], advice.moves(wide_swimlane(12), wide_swimlane(12)))

    def test_the_cap_holds_where_no_other_limit_would(self):
        # A lane per column is what `flow.plan` asks of a swimlane, so a model of twelve lanes is
        # over the column limit too and that one would answer first. This model puts the twelve
        # lanes over a grid of three columns — a model the renderer refuses, and the one reading
        # where the cap is the only thing between the advice and 479 001 600 orders.
        narrow = wide_swimlane(12)
        narrow["grid"] = ["l0  .   .", ".   l1  .", ".   .   l2"]
        self.assertEqual([], advice.moves(narrow, narrow))

    def test_the_widest_mode_is_the_cap_when_no_mode_is_named(self):
        seven = wide_swimlane(7)
        self.assertEqual(advice.MAX_LANE_ORDERS - 1, len(advice.moves(seven, seven)))
        eight = wide_swimlane(8)
        self.assertEqual([], advice.moves(eight, eight))

    def test_a_named_mode_brings_its_own_limit(self):
        seven = wide_swimlane(7)
        self.assertEqual([], advice.moves(seven, seven, "widget"))
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


if __name__ == "__main__":
    unittest.main()
