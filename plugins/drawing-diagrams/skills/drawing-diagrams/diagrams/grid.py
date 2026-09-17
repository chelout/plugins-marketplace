"""The grid map: rows of node ids, a dot for an empty cell."""
from .common import ID_RE


def parse_grid(rows, errors):
    """Return (cells, width, height): cells maps id -> (row, col).
    Appends messages to `errors` for malformed maps."""
    cells = {}
    width = 0
    if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
        errors.append("grid: нужен список строк, по строке на ряд; токен это id узла, точка это пустая ячейка")
        return cells, 0, 0
    for r, row in enumerate(rows):
        toks = row.split()
        width = max(width, len(toks))
        for c, tok in enumerate(toks):
            if tok == ".":
                continue
            if not ID_RE.match(tok):
                errors.append(f"grid, ряд {r}: токен {tok!r} не похож на id (строчные латинские буквы, цифры, _)")
                continue
            if tok in cells:
                errors.append(f"grid: узел {tok} стоит в двух ячейках {list(cells[tok])} и {[r, c]}")
                continue
            cells[tok] = (r, c)
    return cells, width, len(rows)


def check_placement(cells, ids, errors, what="узел"):
    """Every id must be placed once; every placed token must be a known id."""
    for i in ids:
        if i not in cells:
            errors.append(f"{what} {i} описан, но не стоит в grid")
    for tok in cells:
        if tok not in ids:
            errors.append(f"grid: {tok} стоит в карте, но не описан")


def empty_lines(cells, width, height):
    """Rows and columns without a single node."""
    rows_used = {r for r, _ in cells.values()}
    cols_used = {c for _, c in cells.values()}
    return [r for r in range(height) if r not in rows_used], [c for c in range(width) if c not in cols_used]


def ascii_map(cells, width, height, mark=None):
    """The map as aligned text. `mark(id) -> str` decorates a token."""
    grid = [["." for _ in range(width)] for _ in range(height)]
    for i, (r, c) in cells.items():
        grid[r][c] = mark(i) if mark else i
    colw = [max((len(grid[r][c]) for r in range(height)), default=1) for c in range(width)]
    lines = []
    for r in range(height):
        lines.append("  ".join(grid[r][c].ljust(colw[c]) for c in range(width)).rstrip())
    return "\n".join(lines)
