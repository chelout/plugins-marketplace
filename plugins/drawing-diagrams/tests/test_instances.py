"""Seeded grids and edges for the routing tests and the benchmark: tools/instances.py."""
import random
import unittest

import support
import instances
from diagrams import router
from diagrams.common import ID_RE

SMALL = (20260918, 60)
DENSE = (20260919, 30)


def every_instance():
    return list(instances.small(*SMALL)) + list(instances.dense(*DENSE))


class Determinism(unittest.TestCase):
    """The generators draw from a random.Random of their own, so a seed names an instance and
    nothing else in the process can move it."""

    def test_the_same_seed_gives_the_same_instances_twice(self):
        self.assertEqual(list(instances.small(*SMALL)), list(instances.small(*SMALL)))
        self.assertEqual(list(instances.dense(*DENSE)), list(instances.dense(*DENSE)))
        self.assertEqual(instances.dense_scenario(3), instances.dense_scenario(3))

    def test_the_global_generator_does_not_move_them(self):
        random.seed(1)
        first = list(instances.small(5, 10))
        random.seed(2)
        random.random()
        self.assertEqual(list(instances.small(5, 10)), first)

    def test_a_longer_run_extends_a_shorter_one(self):
        # a later task raises a count; the instances it already had must not change under it
        self.assertEqual(list(instances.small(5, 4)), list(instances.small(5, 12))[:4])
        self.assertEqual(list(instances.dense(6, 4)), list(instances.dense(6, 12))[:4])

    def test_different_seeds_give_different_instances(self):
        self.assertNotEqual(list(instances.small(5, 10)), list(instances.small(6, 10)))
        self.assertNotEqual(instances.dense_scenario(1), instances.dense_scenario(2))


class Shape(unittest.TestCase):
    """What every instance promises its caller: cells inside the grid, one per node, and edges a
    router can take as they are."""

    def test_every_node_has_a_distinct_cell_inside_the_grid(self):
        for cols, rows, cells, _ in every_instance():
            with self.subTest(cols=cols, rows=rows, nodes=len(cells)):
                self.assertEqual(len(set(cells.values())), len(cells))
                for nid, (r, c) in cells.items():
                    self.assertTrue(ID_RE.match(nid), nid)
                    self.assertTrue(0 <= r < rows and 0 <= c < cols, (nid, r, c))

    def test_no_edge_repeats_or_reverses_another(self):
        for cols, rows, cells, edges in every_instance():
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                self.assertEqual(edges, sorted(edges))
                seen = set()
                for a, b in edges:
                    self.assertIn(a, cells)
                    self.assertIn(b, cells)
                    self.assertNotEqual(a, b)
                    self.assertNotIn(frozenset((a, b)), seen)
                    seen.add(frozenset((a, b)))

    def test_small_stays_within_its_declared_bounds(self):
        for cols, rows, cells, edges in instances.small(*SMALL):
            with self.subTest(cols=cols, rows=rows):
                self.assertTrue(3 <= cols <= 6 and 3 <= rows <= 6)
                self.assertTrue(5 <= len(cells) <= min(18, cols * rows))
                self.assertTrue(len(cells) <= len(edges) <= 3 * len(cells) // 2)

    def test_dense_stays_within_its_declared_bounds(self):
        for cols, rows, cells, edges in instances.dense(*DENSE):
            with self.subTest(cols=cols, rows=rows):
                self.assertTrue(4 <= cols <= 6 and 4 <= rows <= 8)
                self.assertTrue(15 <= len(edges) <= 30)
                fill = len(cells) / (cols * rows)
                self.assertTrue(instances.DENSE_FILL[0] <= fill <= instances.DENSE_FILL[1], fill)

    def test_the_dense_scenario_is_its_constants(self):
        cols, rows, n_nodes, n_edges = instances.DENSE_SCENARIO
        self.assertEqual((cols, rows, n_nodes, n_edges), (6, 7, 30, 40))
        got_cols, got_rows, cells, edges = instances.dense_scenario(1)
        self.assertEqual((got_cols, got_rows, len(cells), len(edges)), (cols, rows, n_nodes, n_edges))

    def test_an_instance_larger_than_its_grid_is_refused(self):
        rng = random.Random(0)
        with self.assertRaises(ValueError):
            instances.random_instance(rng, 3, 3, 10, 5)
        with self.assertRaises(ValueError):
            instances.random_instance(rng, 4, 4, 5, 11)  # five nodes make ten distinct pairs


class Routable(unittest.TestCase):
    """The benchmark times routing, so an instance whose edges have no route would measure the
    wrong thing."""

    def test_every_edge_finds_a_route(self):
        for cols, rows, cells, edges in [instances.dense_scenario(1)] + list(instances.small(5, 5)):
            lat = router.Lattice(cols, rows, cells)
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                for a, b in edges:
                    p = router.route(lat, router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b]))
                    self.assertIsNotNone(p, (a, b))


if __name__ == "__main__":
    unittest.main()
