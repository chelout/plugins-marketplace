"""router.Traffic as reference counts a path can be taken back out of.

`route` asks a traffic three yes-or-no questions — does this step cross an earlier line, does it
run along one, is this point another line's corner — and two counted ones, the exits of a node side
and the arrows into it. The counts answer all five and let `remove` undo one `add`, which is what a
rip-up pass needs; the answers must not move a hair, because every path the router returns and
every diagram it draws would move with them.

The oracle is `OldTraffic` of reference.py, the class as it stood, so nothing here compares the
code under change with itself.
"""
import unittest

import support  # noqa: F401
import instances
from diagrams import router
from reference import OldTraffic, reference_route_all
from test_drawn_property import DENSE, SMALL


def identical_runs():
    """The instances both classes route, to compare the paths they give: the 300 of the property
    test, whose seeds and counts are imported from `tests/test_drawn_property.py` so that the
    population the criterion names and the one this file samples cannot drift apart."""
    yield from instances.small(*SMALL)
    yield from instances.dense(*DENSE)


def swept_runs():
    """Fewer instances: their traffic is asked at every point of the lattice, both ways."""
    yield from instances.small(9, 10)
    yield from instances.dense(10, 4)


def ends_of(cells, edges):
    return [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]


def labels_of(n):
    # a labelled edge prices its first step differently, so a run holds both kinds
    return [k % 3 == 0 for k in range(n)]


def routed(instance):
    """One instance routed without lattice capacities or a search room argument, retaining the
    paths a traffic can hold. Production `flow.plan` supplies both forms of capacity information."""
    cols, rows, cells, edges = instance
    lat = router.Lattice(cols, rows, cells)
    ends = ends_of(cells, edges)
    return lat, [p for p in router.route_all(lat, ends, labels_of(len(ends))) if p is not None]


def filled(cls, paths):
    t = cls()
    for p in paths:
        t.add(p)
    return t


class SameAnswers(unittest.TestCase):
    """Every question `route` can put to a traffic, at every point of the lattice, answered as the
    scan over the segment list answered it."""

    def assertAgrees(self, new, old, lat):
        for x in range(lat.W):
            for y in range(lat.H):
                for vertical in (True, False):
                    self.assertIs(new.crosses(x, y, vertical), old.crosses(x, y, vertical),
                                  f"crosses({x}, {y}, vertical={vertical})")
                self.assertEqual((x, y) in new.corners, (x, y) in old.corners, f"corner ({x}, {y})")
                for nx, ny in ((x + 1, y), (x, y + 1)):
                    if nx >= lat.W or ny >= lat.H:
                        continue
                    for a, b in (((x, y), (nx, ny)), ((nx, ny), (x, y))):
                        self.assertIs(new.shares(*a, *b), old.shares(*a, *b), f"shares {a} {b}")
        self.assertEqual(new.exits, old.exits)
        self.assertEqual(new.entries, old.entries)

    def test_the_traffic_of_a_whole_diagram(self):
        for instance in swept_runs():
            lat, paths = routed(instance)
            with self.subTest(cols=lat.cols, rows=lat.rows, paths=len(paths)):
                self.assertGreater(len(paths), 1, "harness: an instance with nothing to share")
                self.assertAgrees(filled(router.Traffic, paths), filled(OldTraffic, paths), lat)


class Removing(unittest.TestCase):
    """`remove` takes one path back out of a traffic many paths are in, which is how a rip-up pass
    reaches the traffic of all the other lines without building it again."""

    def test_it_leaves_the_traffic_the_rest_would_have_built(self):
        for instance in swept_runs():
            _, paths = routed(instance)
            for k in range(len(paths)):
                one = filled(router.Traffic, paths)
                one.remove(paths[k])
                rest = filled(router.Traffic, [p for j, p in enumerate(paths) if j != k])
                with self.subTest(paths=len(paths), removed=k):
                    # every attribute of a Traffic is one of its reference counts
                    self.assertEqual(vars(one), vars(rest))

    def test_add_and_remove_of_every_path_leaves_every_mapping_empty(self):
        for instance in swept_runs():
            _, paths = routed(instance)
            t = filled(router.Traffic, paths)
            with self.subTest(paths=len(paths)):
                self.assertTrue(any(vars(t).values()), "harness: these paths occupy nothing")
                for p in paths:
                    t.remove(p)
                self.assertEqual({name: held for name, held in vars(t).items() if held}, {})

    def test_one_line_twice_is_one_answer_and_one_remove_keeps_it(self):
        """Two edges between one pair of cards route the same way. `route` prices the second line
        of a step once, as it does today, while exits and entries count the lines and multiply
        theirs; and the step stays occupied until the last of them is gone."""
        path = [(1, 1), (1, 5), (5, 5)]
        t = router.Traffic()
        t.add(path)
        t.add(path)
        self.assertEqual(t.exits[((1, 1), "D")], 2)
        self.assertEqual(t.entries[((5, 5), "R")], 2)
        for left in (1, 0):
            t.remove(path)
            standing = bool(left)
            self.assertIs(t.crosses(1, 3, False), standing)  # a step across the vertical run
            self.assertIs(t.shares(1, 1, 1, 2), standing)  # a step along it
            self.assertEqual((1, 5) in t.corners, standing)
            self.assertEqual(t.exits.get(((1, 1), "D"), 0), left)
            self.assertEqual(t.entries.get(((5, 5), "R"), 0), left)


class RoutesIdentically(unittest.TestCase):
    """Criterion C1: the paths do not move when the class does. One routing loop — the reference
    loop of reference.py, the three passes `flow.plan` routed with before the search — is run twice
    over one instance, once holding its lines in `OldTraffic` and once in `router.Traffic`, and the
    two answers are the same paths.

    The loop is the constant of the comparison and the class the variable, which is what makes a
    difference here the new class answering differently and nothing else; every one of these paths
    is a diagram that would be drawn differently. `router.route_all` is no party to it: task 12
    made it the search of spec 5.3, which is another routing on purpose, and it has its own
    criterion (C3, tests/test_objective.py)."""

    def test_it_compares_the_instances_the_criterion_names(self):
        """The criterion names the property test's instances, so a seed or a count of this file's
        own would answer for a population nobody measured. Kept out of the comparison below so a
        population that drifted fails as itself and not as a path that moved."""
        self.assertEqual(len(list(identical_runs())), SMALL[1] + DENSE[1])

    def test_seeded_small_and_dense_grids(self):
        for cols, rows, cells, edges in identical_runs():
            lat = router.Lattice(cols, rows, cells)
            ends = ends_of(cells, edges)
            labelled = labels_of(len(ends))
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                self.assertEqual(reference_route_all(lat, ends, labelled, router.Traffic),
                                 reference_route_all(lat, ends, labelled, OldTraffic))


if __name__ == "__main__":
    unittest.main()
