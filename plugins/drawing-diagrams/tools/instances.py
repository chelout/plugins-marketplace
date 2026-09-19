"""Seeded grids and edges for the routing tests and the routing benchmark.

An instance is `(cols, rows, cells, edges)`: `cells` maps a node id to its `(row, col)` in the grid,
`edges` is a sorted list of `(a, b)` node ids without duplicates, reverses or loops. It is what
`router.Lattice(cols, rows, cells)` and `router.route` take, and what a model's `grid` is built from
by a caller that wants one.

Randomness comes only from a `random.Random` the caller passes in, or from the seed the generators
take; nothing here touches the module-level generator, so a seed names an instance whatever else the
process does. Instance k of a generator depends on the seed and k alone, so raising a count leaves
the instances it already had where they were.

Node ids are `n00`, `n01`, … — lexicographic order is numeric order, and a grid map written from
them has one token width. Ids run in reading order of the cells: `n00` is the topmost, leftmost.
"""
import math
import random

# The dense page scenario of the performance budget: grid 6x7, 30 nodes, 40 edges.
DENSE_SCENARIO = (6, 7, 30, 40)
# What part of a dense grid holds a node. The scenario above sits inside it (30 of 42 cells).
DENSE_FILL = (0.6, 0.75)


def node_id(k, width):
    return f"n{k:0{width}d}"


def random_instance(rng, cols, rows, n_nodes, n_edges):
    """`n_nodes` nodes on distinct cells of a `cols` x `rows` grid and `n_edges` edges between
    them, drawn from `rng`. Raises when the grid has no room for the nodes or the nodes no room
    for the edges."""
    if n_nodes > cols * rows:
        raise ValueError(f"{n_nodes} узлов не помещаются в сетку {cols}x{rows}")
    if n_edges > n_nodes * (n_nodes - 1) // 2:
        raise ValueError(f"{n_nodes} узлов дают меньше {n_edges} различных пар")
    width = max(2, len(str(n_nodes - 1)))
    cells = {}
    for k, flat in enumerate(sorted(rng.sample(range(cols * rows), n_nodes))):
        cells[node_id(k, width)] = (flat // cols, flat % cols)
    ids = list(cells)
    pairs = [(a, b) for k, a in enumerate(ids) for b in ids[k + 1:]]
    edges = []
    for a, b in rng.sample(pairs, n_edges):
        edges.append((b, a) if rng.random() < 0.5 else (a, b))
    return cells, sorted(edges)


def small(seed, count):
    """`count` small instances: grids 3-6 x 3-6, 5-18 nodes, 1-1.5 edges per node."""
    rng = random.Random(seed)
    for _ in range(count):
        cols, rows = rng.randint(3, 6), rng.randint(3, 6)
        n_nodes = rng.randint(5, min(18, cols * rows))
        n_edges = rng.randint(n_nodes, 3 * n_nodes // 2)
        cells, edges = random_instance(rng, cols, rows, n_nodes, n_edges)
        yield cols, rows, cells, edges


def dense(seed, count):
    """`count` dense instances: grids 4-6 x 4-8 filled to DENSE_FILL, 15-30 edges."""
    rng = random.Random(seed)
    for _ in range(count):
        cols, rows = rng.randint(4, 6), rng.randint(4, 8)
        room = cols * rows
        n_nodes = rng.randint(math.ceil(DENSE_FILL[0] * room), math.floor(DENSE_FILL[1] * room))
        n_edges = rng.randint(15, 30)
        cells, edges = random_instance(rng, cols, rows, n_nodes, n_edges)
        yield cols, rows, cells, edges


def dense_scenario(seed):
    """One instance of DENSE_SCENARIO, the scenario the performance budget is stated on."""
    cols, rows, n_nodes, n_edges = DENSE_SCENARIO
    cells, edges = random_instance(random.Random(seed), cols, rows, n_nodes, n_edges)
    return cols, rows, cells, edges
