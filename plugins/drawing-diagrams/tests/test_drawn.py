import unittest

import support
from diagrams import router
from test_crossings import NO_SWAP_PATHS, SWAP_PATHS

# the cards of SWAP (grid ["b d", "a c"]) and of NO_SWAP (grid ["a b .", ". c d"])
SWAP_NODES = frozenset({(1, 1), (3, 1), (1, 3), (3, 3)})
NO_SWAP_NODES = frozenset({(1, 1), (3, 1), (3, 3), (5, 3)})


class Drawn(unittest.TestCase):
    """router.drawn_crossings and router.drawn_overlaps count the centrelines as they are drawn,
    spread by assign_offsets: what the reader sees, not what the lattice paths alone say."""

    def counts(self, paths, nodes, offsets=None):
        offs = router.assign_offsets(paths, nodes=nodes) if offsets is None else offsets
        return router.drawn_crossings(paths, offs, nodes), router.drawn_overlaps(paths, offs, nodes)

    def test_a_swap_in_one_gutter_is_drawn_once(self):
        self.assertEqual(self.counts(SWAP_PATHS, SWAP_NODES), (1, 0))

    def test_a_shared_gutter_without_a_swap_draws_nothing(self):
        self.assertEqual(self.counts(NO_SWAP_PATHS, NO_SWAP_NODES), (0, 0))

    def test_two_sides_of_one_node_do_not_meet_at_its_centre(self):
        # one line reaches the node from above, the other from the right: they touch it, they do
        # not cross
        paths = [[(1, 1), (1, 5)], [(5, 5), (1, 5)]]
        nodes = frozenset({(1, 1), (1, 5), (5, 5)})
        self.assertEqual(self.counts(paths, nodes), (0, 0))
        # and still not when each is spread across the centre towards the other, which without the
        # anchor of flow.js would put every such arrival through every other one
        bent = [[(4.0, 0.0)] * 2, [(0.0, -4.0)] * 2]
        self.assertEqual(self.counts(paths, nodes, bent), (0, 0))

    def test_a_line_through_another_is_drawn_crossing_it(self):
        paths = [[(1, 1), (1, 3), (5, 3)], [(3, 1), (3, 5)]]
        nodes = frozenset({(1, 1), (5, 3), (3, 1), (3, 5)})
        self.assertEqual(self.counts(paths, nodes), (1, 0))

    def test_two_lines_in_one_slot_overlap(self):
        # offsets by hand: assign_offsets would give these two their own slots
        path = [(1, 1), (2, 1), (2, 5), (3, 5)]
        flat = [[(0.0, 0.0)] * len(path)] * 2
        self.assertGreaterEqual(router.drawn_overlaps([path, path], flat, frozenset()), 1)


if __name__ == "__main__":
    unittest.main()
