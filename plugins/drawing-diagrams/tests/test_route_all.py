"""router.route_all: what the search promises whatever the model (spec 5.3, 5.4).

The routing does not depend on the order `ends` are given in, two calls on one model give the same
paths, the descents stay inside their budget of `route` calls while every routable edge still comes
back with a path, and an edge with no route is None in its own place and takes no part in the rest.

The identity with the loop of `tests/reference.py` went with this task: `route_all` is no longer
that loop, and what replaced the comparison is Phi against it in `tests/test_objective.py`.
"""
import random
import unittest
from unittest import mock

import support  # noqa: F401
import instances
from diagrams import router

# The instances the order and the determinism are checked on: a few of each generator, because every
# one of them is routed six times over.
SHUFFLED = ((14, 8), (15, 4))
SEEDS = (1, 2, 3, 4, 5)

# The model spec 9 names as the one nothing bounds: two cards with a great many edges between them,
# where the two starts alone ask for more calls of `route` than the whole descent budget.
PARALLEL = 350
SMALL_BUDGET = 10


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


def counting():
    """`router.route` behind a counter, as (wrapper, calls): the only way to see how many times the
    search proposes a path, since the count is what the budget bounds."""
    calls = []
    real = router.route

    def wrapper(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    return wrapper, calls


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
    calls. So the calls the search makes are the two starts — one per edge each — and at most
    `budget` more, whatever the model."""

    def descent_calls(self, lat, ends, labelled, **kwargs):
        """The paths, and how many calls of `route` the descents made: the starts route every edge
        once each, so what is left of the count is the descents'."""
        wrapper, calls = counting()
        with mock.patch.object(router, "route", wrapper):
            paths = router.route_all(lat, ends, labelled, **kwargs)
        return paths, len(calls) - 2 * len(ends)

    def test_a_dense_model_stays_inside_the_budget_it_is_given(self):
        for budget in (SMALL_BUDGET, router.BUDGET):
            for cols, rows, cells, edges in instances.dense(*SHUFFLED[1]):
                lat = router.Lattice(cols, rows, cells)
                ends, labelled = ends_of(cells, edges), labels_of(len(edges))
                with self.subTest(budget=budget, edges=len(edges)):
                    paths, spent = self.descent_calls(lat, ends, labelled, budget=budget)
                    self.assertLessEqual(spent, budget)
                    self.assertGreaterEqual(spent, 0, "the starts route every edge exactly once")
                    self.assertTrue(all(p is not None for p in paths))

    def test_a_model_of_many_parallel_edges_still_routes_every_one_of_them(self):
        """Spec 9: nothing limits the number of edges, and such a model spends the starts alone
        beyond the whole descent budget. The starts are completed anyway — a routing is complete or
        it is not a routing — and only the descent is cut."""
        cells = {"a": (0, 0), "b": (2, 2)}
        lat = router.Lattice(3, 3, cells)
        ends = ends_of(cells, [("a", "b")] * PARALLEL)
        labelled = labels_of(len(ends))
        paths, spent = self.descent_calls(lat, ends, labelled)
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


if __name__ == "__main__":
    unittest.main()
