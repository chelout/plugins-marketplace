"""router.route_all: what the search promises whatever the model (spec 5.3, 5.4).

The routing does not depend on the order `ends` are given in — on the seeded instances, and on the
hand-made models whose edges run between one pair of cards, where the canonical key comes down to
the label — two calls on one model give the same paths, the descents stay inside the budget of
`route` calls they share, half of it to the first and what the first left to the second, while every
routable edge still comes back with a path, an edge with no route is None in its own place and takes
no part in the rest, and two routings of equal Phi are told apart by their crossings and then by the
sum of `own`, before the start they came from.

What the search priced is also what gets drawn, so the promise reaches the offsets: a model planned
through `flow.plan` with its `edges` shuffled is drawn the way it was drawn before, and that reading
is here rather than with the objective because it is the same promise as the routes'.

The identity with the loop of `tests/reference.py` went with this task: `route_all` is no longer
that loop, and what replaced the comparison is Phi against it in `tests/test_objective.py`.
"""
import json
import random
import unittest
from unittest import mock

import support  # noqa: F401
import instances
from diagrams import flow, router

# The instances the order and the determinism are checked on: a few of each generator, because every
# one of them is routed six times over.
SHUFFLED = ((14, 8), (15, 4))
SEEDS = (1, 2, 3, 4, 5)

# The model spec 9 names as the one nothing bounds: two cards with a great many edges between them,
# where the two starts alone ask for more calls of `route` than the whole descent budget.
PARALLEL = 350
SMALL_BUDGET = 10

# The model the budget is read on where it binds: two cards with this many edges between them, which
# is what the descents of spec 5.3 item 3 ask more calls of than they are given. The first converges
# after two passes, 260 calls of the 300 that half the budget is, and the second would take 390 and
# is cut at the 340 the first left it — so the two of them spend the budget itself, and no split
# that gives the second a half of its own reaches that number. The dense instances above never reach
# the bound at all: they spend 64 to 174 calls of 600 and stop with nothing left to improve.
BOUND_PARALLEL = 130

# The hand-made models the canonical key of spec 5.3 item 1 is read on where its last two components
# decide something: edges between one pair of cards, which production models carry and no seeded
# instance holds — `instances.random_instance` samples distinct unordered pairs, so no two of its
# edges are ever the same routing problem. Two runs between the two diagonal pairs, 2 to 5 edges
# each, labelled as `labels_of` labels an instance, so a run holds both kinds and `labelled` is the
# only key that tells its edges apart.
PARALLEL_CELLS = {"a": (0, 0), "b": (0, 2), "c": (2, 0), "d": (2, 2)}
PARALLEL_GRID = (3, 3)
PARALLEL_RUNS = (2, 3, 4, 5)

# The first hand-made pair of routings the tie of spec 5.3 item 4 is read on, where the crossings
# tie and the sum of `own` decides: four cards, two edges, and `c -> d` drawn two ways that cost the
# same Phi and differ by one in the sum — the shape the shipped `verdict-row-lifecycle` has it in,
# where the sums are 52 and 53.
TIE_CELLS = {"a": (0, 0), "b": (2, 2), "c": (0, 2), "d": (2, 0)}
TIE_GRID = (3, 3)
TIE_EDGES = (("a", "b"), ("c", "d"))
TIE_SHARED = [(1, 1), (4, 1), (4, 4), (5, 4), (5, 5)]  # a -> b, drawn the same way in both, own 15
TIE_CHEAP = [(5, 1), (5, 4), (1, 4), (1, 5)]           # c -> d down the gutter of its own, own 13
TIE_DEAR = [(5, 1), (4, 1), (4, 4), (1, 4), (1, 5)]    # c -> d along the other line's, own 14
TIE_COSTS = ((42, 28, 1), (42, 29, 1))                 # (Phi, sum of own, crossings), cheap first

# The second pair, where the crossings do not tie and decide before the sum: four cards again, with
# `e` between `n` and `s` so that `n -> s` has to go round it. The cheap way round is the gutter
# beside `m`, where it cuts across `m -> e`; the dear way is round the far side and the bottom
# margin, which crosses nothing and costs ten more in `own` — exactly what Phi charges the crossing,
# so the two routings cost the same and the sum of `own` alone would take the one that crosses.
CROSS_CELLS = {"m": (1, 0), "e": (1, 1), "n": (0, 1), "s": (2, 1)}
CROSS_GRID = (3, 3)
CROSS_EDGES = (("m", "e"), ("n", "s"))
CROSS_SHARED = [(1, 3), (3, 3)]                           # m -> e, straight across the gutter, own 2
CROSS_CHEAP = [(3, 1), (2, 1), (2, 5), (3, 5)]            # n -> s across m -> e, own 10
CROSS_CLEAR = [(3, 1), (4, 1), (4, 6), (3, 6), (3, 5)]    # n -> s round the far side, own 20
CROSS_COSTS = ((22, 12, 1), (22, 22, 0))                  # as above, the crossing routing first


def ends_of(cells, edges):
    return [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]


def labels_of(n):
    # a labelled edge prices its first step differently, so a run holds both kinds
    return [k % 3 == 0 for k in range(n)]


def by_edge(ends, labelled, paths):
    """The paths per (source, target, labelled): what spec 5.4 promises is the same however `ends`
    are ordered. Two edges equal in all three are the same routing problem, so what is compared is
    the multiset of their paths and not which index took which."""
    out = {}
    for i, p in enumerate(paths):
        out.setdefault((ends[i][0], ends[i][1], labelled[i]), []).append(p)
    return {key: sorted(found, key=repr) for key, found in out.items()}


def shuffled_runs():
    for cols, rows, cells, edges in instances.small(*SHUFFLED[0]):
        yield cols, rows, cells, edges
    for cols, rows, cells, edges in instances.dense(*SHUFFLED[1]):
        yield cols, rows, cells, edges


def parallel_runs():
    """The hand-made models above as instances, one per run length: `n` edges from `a` to `d` and
    `n` more from `c` to `b`, on the grid those four cards sit in."""
    for n in PARALLEL_RUNS:
        yield (*PARALLEL_GRID, PARALLEL_CELLS, [("a", "d")] * n + [("c", "b")] * n)


def model_of(cols, rows, cells, edges):
    """An instance as a flow model: a card per node in its own cell, an edge per pair in the order
    the instance lists them, and the label of every third of them, as `labels_of` labels an
    instance. A label travels with its edge, so a shuffle of the list moves the edges and not which
    of them are labelled."""
    at = {rc: nid for nid, rc in cells.items()}
    labelled = labels_of(len(edges))
    return {"kind": "flow",
            "grid": [" ".join(at.get((r, c), ".") for c in range(cols)) for r in range(rows)],
            "nodes": [{"id": nid, "title": nid.upper()} for nid in sorted(cells)],
            "edges": [f"{a} -> {b}" + (" : да" if labelled[k] else "")
                      for k, (a, b) in enumerate(edges)]}


def shuffle_of(model, seed):
    """The model with its `edges` shuffled, as an author might have listed them."""
    mixed = dict(model, edges=list(model["edges"]))
    random.Random(seed).shuffle(mixed["edges"])
    return mixed


def table_route(first, second):
    """`router.route` replaced by a table of paths per edge: `second`'s for a call given no traffic
    at all, which is the second start and nothing else (`_alone`), and `first`'s for every other
    call — the first start, and every proposal either descent makes."""
    def fake(lat, src, dst, labelled=False, traffic=None, cost=None):
        return list((second if traffic is None else first)[(src, dst)])
    return fake


def counting():
    """`router.route` behind a counter, as (wrapper, calls): the only way to see how many times the
    search proposes a path, since the count is what the budget bounds."""
    calls = []
    real = router.route

    def wrapper(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    return wrapper, calls


def descent_calls(lat, ends, labelled, **kwargs):
    """The paths, and how many calls of `route` the descents made: the starts route every edge once
    each, so what is left of the count is the descents'."""
    wrapper, calls = counting()
    with mock.patch.object(router, "route", wrapper):
        paths = router.route_all(lat, ends, labelled, **kwargs)
    return paths, len(calls) - 2 * len(ends)


class CanonicalOrder(unittest.TestCase):
    """Spec 5.4: the same model with `ends` shuffled gives the same route for every (source, target,
    labelled). The canonical order of spec 5.3 is what carries it — the model index decides only
    between edges equal in all four keys, which are the same routing problem."""

    def test_five_shuffles_route_every_edge_the_way_the_model_order_did(self):
        seen = 0
        for cols, rows, cells, edges in shuffled_runs():
            lat = router.Lattice(cols, rows, cells)
            ends, labelled = ends_of(cells, edges), labels_of(len(edges))
            want = by_edge(ends, labelled, router.route_all(lat, ends, labelled))
            seen += len(edges)
            for seed in SEEDS:
                rng = random.Random(seed)
                order = list(range(len(ends)))
                rng.shuffle(order)
                mixed_ends = [ends[i] for i in order]
                mixed_labels = [labelled[i] for i in order]
                with self.subTest(cols=cols, rows=rows, edges=len(edges), seed=seed):
                    got = router.route_all(lat, mixed_ends, mixed_labels)
                    self.assertEqual(by_edge(mixed_ends, mixed_labels, got), want)
        self.assertGreater(seen, 100, "harness: too few edges were ever shuffled")

    def test_five_shuffles_route_parallel_edges_the_way_the_model_order_did(self):
        """The same promise on models that carry several edges between one pair of cards. Such a
        pair is where the key of spec 5.3 item 1 has anything left to decide: the distance and the
        two points tie on every edge of it, so `labelled` is the one key before the model index, and
        the edges of one label are the same routing problem asked twice — which is why what is
        compared is the multiset of the paths under a key and not which edge took which."""
        most, both = 0, 0
        for cols, rows, cells, edges in parallel_runs():
            lat = router.Lattice(cols, rows, cells)
            ends, labelled = ends_of(cells, edges), labels_of(len(edges))
            want = by_edge(ends, labelled, router.route_all(lat, ends, labelled))
            most = max([most] + [len(found) for found in want.values()])
            both += sum(1 for src, dst, lab in want if lab and (src, dst, False) in want)
            for seed in SEEDS:
                order = list(range(len(ends)))
                random.Random(seed).shuffle(order)
                mixed_ends = [ends[i] for i in order]
                mixed_labels = [labelled[i] for i in order]
                with self.subTest(edges=len(edges), seed=seed):
                    got = router.route_all(lat, mixed_ends, mixed_labels)
                    self.assertEqual(by_edge(mixed_ends, mixed_labels, got), want)
        self.assertGreater(most, 1, "harness: every key carries one path, so no two edges of these "
                                    "models are one routing problem and the multiset reads nothing")
        self.assertGreater(both, 0, "harness: no pair of cards carries a labelled edge and an "
                                    "unlabelled one, so `labelled` tells no two edges apart here")


class OffsetsFollowTheOrderTheSearchPricedIn(unittest.TestCase):
    """Spec 5.4 as amended for finding G6: the offsets follow the canonical order too, so the same
    model with its `edges` shuffled is drawn exactly as it was — the same route and the same offsets
    for every (source, target, labelled). The width of a group depends on the order its paths are
    given in, and `flow.plan` places through `router.place`, which gives them in the order the
    search priced them in; before that they were placed in the model's order and a shuffle moved
    them.

    Read through `flow.plan` rather than through `place`, because the promise is the planner's: what
    an author reorders is the model."""

    MODE = "widget"

    def drawn(self, model):
        """The paths `flow.plan` draws with the offsets it draws them at, per (source, target,
        labelled). The plan is a draft, so a model whose capacity check refuses a group is drawn
        rather than raised. Two edges equal in all three keys are one routing problem, and which of
        them takes which of the paths is the model's order, so what is compared is the multiset."""
        layout, _ = flow.plan(json.loads(json.dumps(model)), self.MODE, draft=True)
        out = {}
        for e in layout["edges"]:
            out.setdefault((e["a"], e["b"], bool(e["label"])), []).append(e["path"])
        return {key: sorted(map(repr, found)) for key, found in out.items()}

    def test_five_shuffles_draw_every_edge_where_the_model_order_did(self):
        seen = 0
        for instance in shuffled_runs():
            model = model_of(*instance)
            want = self.drawn(model)
            seen += len(model["edges"])
            self.assertEqual(len(want), len(model["edges"]),
                             "harness: this instance has two edges of one routing problem, so a "
                             "shuffle may hand them each other's path and offsets")
            for seed in SEEDS:
                with self.subTest(grid=tuple(model["grid"]), seed=seed):
                    self.assertEqual(self.drawn(shuffle_of(model, seed)), want)
        self.assertGreater(seen, 100, "harness: too few edges were ever shuffled")


class TwoCallsAgree(unittest.TestCase):
    """Spec 5.4: no randomness and no clock, so one model routes the same way twice."""

    def test_the_same_model_twice(self):
        for cols, rows, cells, edges in shuffled_runs():
            lat = router.Lattice(cols, rows, cells)
            ends, labelled = ends_of(cells, edges), labels_of(len(edges))
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                self.assertEqual(router.route_all(lat, ends, labelled),
                                 router.route_all(lat, ends, labelled))


class WithinTheBudget(unittest.TestCase):
    """Spec 5.3: the two starts are always completed, and the descents share a budget of `route`
    calls — half of it to the first and everything the first left to the second. So the calls the
    search makes are the two starts — one per edge each — and at most `budget` more, whatever the
    model.

    A budget nothing reaches is a budget nobody measured, and the dense instances below spend 64 to
    174 calls of the 600 they are given. So the two cases after them are read on BOUND_PARALLEL
    parallel edges, where both descents ask for more than they are given and what they spend is the
    bound itself."""

    @classmethod
    def setUpClass(cls):
        """The model that reaches the bound, routed once for the two cases that read it."""
        cells = {"a": (0, 0), "b": (2, 2)}
        lat = router.Lattice(3, 3, cells)
        ends = ends_of(cells, [("a", "b")] * BOUND_PARALLEL)
        cls.bound = descent_calls(lat, ends, labels_of(len(ends)))

    def test_a_dense_model_stays_inside_the_budget_it_is_given(self):
        for budget in (SMALL_BUDGET, router.BUDGET):
            for cols, rows, cells, edges in instances.dense(*SHUFFLED[1]):
                lat = router.Lattice(cols, rows, cells)
                ends, labelled = ends_of(cells, edges), labels_of(len(edges))
                with self.subTest(budget=budget, edges=len(edges)):
                    paths, spent = descent_calls(lat, ends, labelled, budget=budget)
                    self.assertLessEqual(spent, budget)
                    self.assertGreaterEqual(spent, 0, "the starts route every edge exactly once")
                    self.assertTrue(all(p is not None for p in paths))

    def test_a_model_that_asks_for_more_than_the_budget_stays_inside_it(self):
        """The bound where it binds: the descents of this model have somewhere to go for more passes
        than the budget pays for, so what they spend is the budget and not what they would take."""
        paths, spent = self.bound
        self.assertTrue(all(p is not None for p in paths))
        self.assertLessEqual(spent, router.BUDGET)

    def test_the_second_descent_gets_what_the_first_one_left(self):
        """Spec 5.3 item 3: half the budget to the first descent and everything left to the second.
        The first descent of this model stops short of its half — it has nothing left to change
        after two passes, 260 calls of the 300 it was given — and the second would take 390, more
        than a half. So the whole budget is spent here only because the second descent is given the
        340 the first left it, and a second descent given half of its own would stop at 560."""
        _, spent = self.bound
        self.assertEqual(spent, router.BUDGET)

    def test_a_model_of_many_parallel_edges_still_routes_every_one_of_them(self):
        """Spec 9: nothing limits the number of edges, and such a model spends the starts alone
        beyond the whole descent budget. The starts are completed anyway — a routing is complete or
        it is not a routing — and only the descent is cut."""
        cells = {"a": (0, 0), "b": (2, 2)}
        lat = router.Lattice(3, 3, cells)
        ends = ends_of(cells, [("a", "b")] * PARALLEL)
        labelled = labels_of(len(ends))
        paths, spent = descent_calls(lat, ends, labelled)
        self.assertEqual(len(paths), PARALLEL)
        self.assertTrue(all(p is not None for p in paths))
        self.assertLessEqual(spent, router.BUDGET)


class Unroutable(unittest.TestCase):
    """An edge with no route is None in its own place and takes no part in the search; the others
    route as if it had never been asked for."""

    def walled(self):
        """A grid of three cards where nothing can reach or leave `b`. One card cannot wall
        another in: lat.blocked holds the cards' own points, odd in both coordinates, and the
        gutters between them are never blocked, so the wall is put in by hand."""
        cells = {"a": (0, 0), "b": (0, 2), "c": (2, 2)}
        lat = router.Lattice(3, 3, cells)
        x, y = router.Lattice.point(*cells["b"])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            lat.blocked[(x + dx, y + dy)] = "wall"
        ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b]))
                for a, b in (("a", "b"), ("a", "c"), ("c", "a"))]
        return lat, ends, [False] * len(ends)

    def test_the_walled_in_edge_alone_is_none(self):
        lat, ends, labelled = self.walled()
        got = router.route_all(lat, ends, labelled)
        self.assertIsNone(got[0])
        self.assertTrue(all(p is not None for p in got[1:]), got)

    def test_it_leaves_the_others_where_they_would_be_without_it(self):
        lat, ends, labelled = self.walled()
        got = router.route_all(lat, ends, labelled)
        self.assertEqual(got[1:], router.route_all(lat, ends[1:], labelled[1:]))


class TieCase(unittest.TestCase):
    """A pick between two routings of one Phi, read on a hand-made pair through a table of `route`.

    The pair is hand-made because the two starts of a real model cannot be made to hold an arbitrary
    pair: `_alone` routes every edge with nothing else there, so the second start's sum of `own` is
    the lowest any routing of that model has, and "the lower sum" and "the second start" would be
    one answer. Only a descent can raise it — which is what happens on the shipped model of
    `TheTieKeepsTheLabelOfTheShippedExample` in `tests/test_objective.py` — and a table raises it
    directly, so every rule below is read both ways round.

    Neither descent moves anything: every proposal is the path the routing already holds (the first
    start) or ties with it (the second), so the trace stays empty and what the cases read is the
    pick between the starts and nothing else.

    A subclass states the model in `cells`, `grid` and `edges`, and the path its first edge is drawn
    with in both routings as `shared`; its cases vary the second edge."""

    cells = grid = edges = shared = None

    def setUp(self):
        self.lat = router.Lattice(*self.grid, self.cells)
        self.ends = ends_of(self.cells, self.edges)
        self.labelled = [False] * len(self.ends)

    def picked(self, first, second):
        """What `route_all` returns when the first start draws the second edge the one way and the
        second start the other."""
        tables = ({self.ends[0]: self.shared, self.ends[1]: first},
                  {self.ends[0]: self.shared, self.ends[1]: second})
        trace = []
        with mock.patch.object(router, "route", table_route(*tables)):
            got = router.route_all(self.lat, self.ends, self.labelled, trace=trace)
        self.assertEqual(trace, [], "harness: a descent accepted a change, so what the pick was "
                                    "given is no longer the pair of routings this case states")
        return got

    def costs(self, *others):
        """(Phi, sum of `own`, crossings) per routing, counted here from `describe`, `phi` and
        `crossings` rather than taken from the search: what a case asserts its own premise on."""
        nodes = frozenset(self.lat.blocked)
        out = []
        for other in others:
            infos = [router.describe(self.lat, p, False) for p in (self.shared, other)]
            out.append((router.phi(infos, nodes, None), sum(info.own for info in infos),
                        router.crossings([self.shared, other])))
        return tuple(out)


class TheTieGoesToTheLowerSumOfOwn(TieCase):
    """Spec 5.3 item 4, as amended on 2026-09-20: the lower Phi wins; on a tie of Phi the fewer
    crossings, then the lower sum of `own` — the routing whose lines are each nearer their own
    best — and the first start only when all three tie.

    Here the crossings tie, so the sum is what decides, which is the shape the shipped
    `verdict-row-lifecycle` has the tie in."""

    cells, grid, edges, shared = TIE_CELLS, TIE_GRID, TIE_EDGES, TIE_SHARED

    def test_the_second_start_takes_the_tie_when_its_sum_is_the_lower_one(self):
        # what the first text of the spec answered wrong: the tie went to the first start
        self.assertEqual(self.picked(TIE_DEAR, TIE_CHEAP), [TIE_SHARED, TIE_CHEAP])

    def test_the_first_start_takes_it_when_its_sum_is(self):
        # the same tie the other way round, which "always the second start" answers wrong
        self.assertEqual(self.picked(TIE_CHEAP, TIE_DEAR), [TIE_SHARED, TIE_CHEAP])

    def test_the_two_routings_tie_on_phi_and_on_crossings_and_differ_in_the_sum_of_own(self):
        """What the pair has to be for the two cases above to read the sum at all: one Phi and one
        count of crossings for both routings, so neither key before the sum decides anything, and
        two sums, so the sum decides."""
        self.assertEqual(self.costs(TIE_CHEAP, TIE_DEAR), TIE_COSTS)


class TheTieGoesToTheFewerCrossingsBeforeTheSumOfOwn(TieCase):
    """The same rule where the two keys disagree: a tie of Phi can hide a crossing, because Phi
    charges ten for one and the routing that crosses can be ten cheaper in `own` for it. The reader
    is served worse by a crossing than by lines that run a little further from their own best, so
    the crossings are asked first and the routing that crosses nothing wins the tie it would lose on
    the sum alone.

    They are asked only on a tie: `crossings` walks every pair of a whole routing, which costs some
    three times what a whole Phi of it does, and two descents rarely end at one Phi."""

    cells, grid, edges, shared = CROSS_CELLS, CROSS_GRID, CROSS_EDGES, CROSS_SHARED

    def test_the_second_start_takes_the_tie_when_it_is_the_one_that_crosses_nothing(self):
        self.assertEqual(self.picked(CROSS_CHEAP, CROSS_CLEAR), [CROSS_SHARED, CROSS_CLEAR])

    def test_the_first_start_takes_it_when_it_is(self):
        # the same tie the other way round, so neither start can be what the pick follows
        self.assertEqual(self.picked(CROSS_CLEAR, CROSS_CHEAP), [CROSS_SHARED, CROSS_CLEAR])

    def test_the_two_routings_tie_on_phi_and_the_lower_sum_of_own_is_the_one_that_crosses(self):
        """What the pair has to be for the two cases above to read the order of the two keys: one
        Phi, so the crossings are reached at all, and a sum that points the other way, so a rule
        that asked for the lower sum first would answer both of them wrong."""
        self.assertEqual(self.costs(CROSS_CHEAP, CROSS_CLEAR), CROSS_COSTS)


if __name__ == "__main__":
    unittest.main()
