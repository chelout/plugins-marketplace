"""router.route_all: the routing loop flow.plan used to hold, against the copy kept in reference.py."""
import unittest

import support  # noqa: F401
import bench_routing
import instances
from diagrams import flow, router
from reference import reference_route_all

SMALL = (5, 60)


def plan_route_all(model, mode):
    """What flow.plan hands router.route_all and what it gets back, per call: the ends and the
    labels it builds from the model's edges are part of the behaviour this task moves."""
    seen = []
    real = router.route_all

    def spy(lat, ends, labelled):
        out = real(lat, ends, labelled)
        seen.append((lat, list(ends), list(labelled), out))
        return out

    router.route_all = spy
    try:
        flow.plan(model, mode)
    finally:
        router.route_all = real
    return seen


class AsFlowPlanRouted(unittest.TestCase):
    """The move is behaviour-preserving: path for path, route_all gives what the loop gave."""

    def test_the_shipped_flow_like_examples(self):
        found = bench_routing.examples()
        self.assertEqual({m["kind"] for _, m in found}, set(flow.MODES), "harness: a kind lost its example")
        for path, model in found:
            for mode in bench_routing.MODES:
                with self.subTest(example=path.name, mode=mode):
                    calls = plan_route_all(model, mode)
                    self.assertEqual(len(calls), 1, "flow.plan routes a model once")
                    lat, ends, labelled, got = calls[0]
                    self.assertTrue(ends, "harness: the example routes nothing")
                    self.assertEqual(got, reference_route_all(lat, ends, labelled))

    def test_seeded_small_grids(self):
        for cols, rows, cells, edges in instances.small(*SMALL):
            lat = router.Lattice(cols, rows, cells)
            ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
            # a labelled edge prices its first step differently, so the run holds both kinds
            labelled = [i % 3 == 0 for i in range(len(ends))]
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                self.assertEqual(router.route_all(lat, ends, labelled),
                                 reference_route_all(lat, ends, labelled))


class Unroutable(unittest.TestCase):
    """An edge with no route is None in its own place and takes no part in the passes; the others
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
        self.assertEqual(got, reference_route_all(lat, ends, labelled))

    def test_it_leaves_the_others_where_they_would_be_without_it(self):
        lat, ends, labelled = self.walled()
        got = router.route_all(lat, ends, labelled)
        self.assertEqual(got[1:], router.route_all(lat, ends[1:], labelled[1:]))


if __name__ == "__main__":
    unittest.main()
