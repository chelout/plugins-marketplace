"""The routing of flow.plan as it stood before router.route_all, kept as an oracle.

Task 1 of the routing plan moves this loop into `router.route_all` unchanged, and task 12 replaces
its body with a search against an objective. A test that compared the router with itself would
prove nothing across either step, so the loop lives on here, where nothing under test can reach it.
"""
import support  # noqa: F401
from diagrams import router


def reference_route_all(lat, ends, labelled):
    """One pass over `ends` in the given order with accumulating traffic, then two rip-up passes
    in which every line sees all the others. `ends[i]` is (source point, target point) and
    `labelled[i]` says whether the edge carries a label; the result holds one path per end pair,
    None where there is no route. An edge with no route takes no part in the rip-up passes."""
    paths, live = [], []
    traffic = router.Traffic()
    for i, (src, dst) in enumerate(ends):
        p = router.route(lat, src, dst, labelled=labelled[i], traffic=traffic)
        paths.append(p)
        if p is not None:
            traffic.add(p)
            live.append(i)
    for _ in range(2):
        for i in live:
            others = router.Traffic()
            for j in live:
                if j != i:
                    others.add(paths[j])
            p = router.route(lat, ends[i][0], ends[i][1], labelled=labelled[i], traffic=others)
            if p is not None:
                paths[i] = p
    return paths
