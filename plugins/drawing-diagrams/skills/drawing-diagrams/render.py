#!/usr/bin/env python3
"""Render diagrams from JSON models. A model's `kind` picks the renderer.

Usage:
    render.py MODEL.json [MODEL.json ...] [--mode widget|page] [--out FILE | --out-dir DIR]
              [--assets cdn|inline|none] [--no-assets] [--check] [--draft] [--no-advice]
              [--format html|mermaid|ascii] [--open] [--types] [--width PX] [--harness]

Kinds: schema, flow, swimlane, state, blocks, timeline (reference/common.md).

Every render checks the model first. On errors stdout stays empty, the exit status is 1 and stderr
lists every problem, with the ASCII map when a line or the grid failed rather than the length of a
text. Warnings go to stderr and the output is still produced. --draft turns layout errors into
warnings and stamps the output as a draft. Where a gutter is over its capacity or three lines
cross, stderr also carries a rearrangement advice: node moves verified by the router and the grid
they leave behind, never a change to the model; --no-advice turns that search off.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagrams import advice, assets  # noqa: E402
from diagrams import flow, schema, timeline  # noqa: E402
from diagrams.common import ModelError, plural  # noqa: E402
from diagrams.grid import ascii_map, parse_grid  # noqa: E402

KINDS = {"schema": schema, "flow": flow, "swimlane": flow, "state": flow, "blocks": flow, "timeline": timeline}
SUFFIX = {"html": ".html", "mermaid": ".mmd", "ascii": ".txt"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# the crossings `flow.plan` warns at: the map is printed and the advice asked for at the same line
MANY_CROSSINGS = 3
# what the three terms of an advice score are called to the author, in the order spec 6 compares
# them: the slots the gutters take past what they hold, the crossings the plan reports, and the
# length of the lines. "линий" for the first because that is the word the capacity error uses for a
# slot, and the author has just read it
SCORE_TERMS = ("лишних линий", "пересечений", "длина линий")


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="+", help="JSON model; several models need --out-dir")
    ap.add_argument("--mode", choices=("widget", "page"), default="widget",
                    help="widget: 680px fragment for a chat widget; page: 1100px section for a page or artifact")
    ap.add_argument("--format", choices=("html", "mermaid", "ascii"), default="html",
                    help="html for chat and pages; mermaid for markdown in a repository; ascii for the terminal")
    ap.add_argument("--out", help="write the output here instead of stdout")
    ap.add_argument("--out-dir", help="write DIR/<id>.<ext> per model; nothing is written if any model fails")
    ap.add_argument("--assets", choices=("cdn", "inline", "none"),
                    help="cdn: links to the published CSS and JS (widget default); inline: CSS and JS inside "
                         "(page default); none: markup only, for the second and later diagrams of a page")
    ap.add_argument("--no-assets", action="store_true", help="same as --assets none")
    ap.add_argument("--check", action="store_true",
                    help="check only and print the ASCII map (width checks honour --open, --types, --width)")
    ap.add_argument("--draft", action="store_true",
                    help="downgrade layout errors to warnings and stamp the output as a draft")
    ap.add_argument("--no-advice", action="store_true",
                    help="do not search for node moves when a gutter is over its capacity or lines cross")
    ap.add_argument("--open", action="store_true", help="schema: start with all columns visible")
    ap.add_argument("--types", action="store_true", help="schema: show types on key rows too")
    ap.add_argument("--width", type=int, help="total width in px instead of the mode default (680 / 1100)")
    ap.add_argument("--harness", action="store_true",
                    help="widget mode: wrap the fragment into a standalone page for a browser")
    return ap.parse_args(argv)


def resolve_assets(args):
    """The assets mode of this run, and a warning when cdn has to fall back to inline."""
    mode = "none" if args.no_assets else args.assets or ("cdn" if args.mode == "widget" else "inline")
    if mode == "cdn" and assets.read_ref() is None:
        return "inline", "сборка для CDN не выпущена (нет template/dist/REF), CSS и JS встроены"
    return mode, None


def load(path):
    """(model, renderer module); raises ValueError with the message to print."""
    try:
        model = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"ошибка: не читается модель {path}: {exc}")
    if model.get("kind") not in KINDS:
        raise ValueError(f"ошибка: {path}: поле kind обязательно; доступны: {', '.join(KINDS)}")
    return model, KINDS[model["kind"]]


def failure_map(mod, model, mode_name, overrides, exc):
    """(the ASCII map of a model that failed on layout rather than on the length of a text, the
    draft layout it was drawn from) — either may be None.

    The layout is what `advise` reads its trigger off: a model whose plan raised has no layout of
    its own, and this draft plan is the one that says what its gutters and its crossings would be.
    A model refused for the length of a text alone gets neither: it needs a shorter text, not a
    rearrangement."""
    if not any(e not in exc.fit for e in exc.layout):
        return None, None
    if mod is schema:
        cells, cols, rows = parse_grid(model.get("grid"), [])
        return ascii_map(cells, cols, rows), None
    try:
        layout, _ = mod.plan(model, mode_name, overrides, draft=True)
    except ModelError:
        # G6: the draft re-plan can itself raise, e.g. an ordinary validation error (duplicate node
        # id) alongside the layout error. Fall back to the raw grid map for kinds that have one.
        if mod is flow:
            cells, cols, rows = parse_grid(model.get("grid"), [])
            return ascii_map(cells, cols, rows), None
        return None, None
    return mod.ascii(model, layout), layout


def batch_target(path, model, target_dir, resolved_dir, fmt):
    """(target, resolved target) to write one model's output to in --out-dir mode; raises
    ValueError with the message to print when the id is not a safe file name or the target
    would land outside target_dir."""
    model_id = model.get("id")
    if model_id is None:
        stem = Path(path).stem
    else:
        if not isinstance(model_id, str) or not ID_RE.match(model_id):
            raise ValueError(f"ошибка: --out-dir: {path}: id «{model_id!r}» не годится для имени файла "
                              f"(нужна строка из букв, цифр, _ и -, без точек и разделителей)")
        stem = model_id
    target = target_dir / f"{stem}{SUFFIX[fmt]}"
    resolved = target.resolve()
    if resolved.parent != resolved_dir:
        raise ValueError(f"ошибка: --out-dir: {path}: цель {target} выходит за пределы {target_dir}")
    return target, resolved


def advise(mod, model, path, args, overrides, layout, batch):
    """Print the rearrangement advice of spec 6 for one model on stderr, after the warnings or the
    errors it answers: the moves that lower the score of its grid, verified one by one by the
    router, and the grid they leave behind for the author to paste. The model itself is never
    changed.

    Called once per model, from `main` alone, and only where the renderer has already told the
    author something about the drawing — a group over the capacity of its line, or the crossings
    the warning counts. The gate is that trigger and not what the search finds: an advice nobody
    asked for would be noise on every render. Kinds the advice does not know — a schema, a
    timeline — are never searched."""
    if args.no_advice or mod is not flow or not triggered(layout):
        return
    found = advice.search(model, args.mode, overrides)
    if not found:
        return
    for line in advice_block(found, advised_grid(model, found), advised_lanes(found),
                             f"{path}: " if batch else ""):
        print(line, file=sys.stderr)


def triggered(layout):
    """Whether a plan is one the author is offered advice on: a group drawn past the capacity of
    its lattice line, or crossings enough for the warning. A plan that is not a draft always
    answers zero to the first — a group over capacity is a layout error and raises."""
    if not layout:
        return False
    return layout.get("overflow", 0) > 0 or layout.get("crossings", 0) >= MANY_CROSSINGS


def advice_block(found, grid, lanes, prefix):
    """The lines of spec 6's advice block: a headline, the moves numbered from one, the advised grid
    under `grid:` with each row as the author would paste it back into the model, and the lane order
    under `lanes:` where a move changed it.

    The headline counts the term of the score the whole sequence moved — the first of (overflow,
    crossings, length) whose two ends differ, which is the one that made the sequence an
    improvement, since the three are compared in that order. So a trigger answered is a trigger
    counted: where a group was over its capacity and the moves free it, that is what the headline
    says. Every step names the term it moved itself: the sequence climbs on the whole score, so a
    move inside it may have bought nothing but a shorter line, and a step that named the headline's
    term would then print a count standing still."""
    first, last = found[0][1], found[-1][2]
    term = moved_term(first, last)
    moves = len(found)
    out = [f"совет: {prefix}{SCORE_TERMS[term]} {first[term]} → {last[term]} за {moves} "
           f"{plural(moves, ('ход', 'хода', 'ходов'))} (проверено трассировкой)"]
    for i, (move, before, after) in enumerate(found, 1):
        step = moved_term(before, after)
        out.append(f"  {i}. {move.text()}: {SCORE_TERMS[step]} {before[step]} → {after[step]}")
    out.append("grid:")
    out += [f"  {json.dumps(row, ensure_ascii=False)}" for row in grid]
    if lanes is not None:
        out.append("lanes:")
        out.append(f"  {json.dumps(lanes, ensure_ascii=False)}")
    return out


def moved_term(before, after):
    """Which term of the score these two ends differ in first — the one they are worth naming by.
    Nothing moved at all is the length, the last of them, which is the term a caller would read off
    two equal scores anyway."""
    return next((i for i in range(len(before)) if before[i] != after[i]), len(before) - 1)


def advised_grid(model, found):
    """The grid the moves leave behind, written by `advice.write_grid`: the author's own column
    offsets, and every row nothing moved in kept byte for byte.

    The moves are walked over the placement rather than over the model, and the map is written once
    at the end. A grid written per move would be written from the one the move before it left, so a
    card carried into a column wider than the author's would push every row after it out of line —
    the same placement, and a map the author reads as a different one."""
    cells, width, height = parse_grid(model.get("grid"), [])
    for move, _, _ in found:
        cells = move.moved(cells)
    return advice.write_grid(model["grid"], cells, width, height)


def advised_lanes(found):
    """The lane order the moves leave behind, or None where no move changed it.

    A `lanes` move changes `lanes` and `grid` together (spec 6): the columns travel with the lanes,
    so a card stays in the lane the author gave it only while the two are read together. A block
    that printed the grid alone would hand the cards of one lane to the lane beside it."""
    lanes = None
    for move, _, _ in found:
        if move.kind == "lanes":
            lanes = list(move.lanes)
    return lanes


def produce(model, mod, args, overrides, assets_mode):
    """(output text, warnings, layout) of one model; raises ModelError."""
    layout, warnings = mod.plan(model, args.mode, overrides, draft=args.draft)
    if args.check or args.format == "ascii":
        return mod.ascii(model, layout) + "\n", warnings, layout
    if args.format == "mermaid":
        return mod.mermaid(model, layout) + "\n", warnings, layout
    out = mod.render(model, args.mode, layout, warnings, assets_mode=assets_mode, draft=bool(layout.get("draft")))
    return (assets.harness(out) if args.harness else out), warnings, layout


def main(argv=None):
    args = parse_args(argv)
    batch = len(args.model) > 1
    if batch and not args.out_dir:
        print("ошибка: несколько моделей рендерятся только с --out-dir", file=sys.stderr)
        return 1
    if args.out and args.out_dir:
        print("ошибка: --out и --out-dir вместе не используются", file=sys.stderr)
        return 1
    if args.harness and args.mode != "widget":
        print("ошибка: --harness имеет смысл только в режиме widget", file=sys.stderr)
        return 1
    overrides = {}
    if args.open:
        overrides["open"] = True
    if args.types:
        overrides["type_on_keys"] = True
    if args.width:
        overrides["total"] = args.width
    assets_mode, note = resolve_assets(args)
    if note and args.format == "html" and not args.check:
        print("предупреждение: " + note, file=sys.stderr)

    done, failed = [], False
    for path in args.model:
        if batch:
            print(f"== {path}", file=sys.stderr)
        try:
            model, mod = load(path)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            failed = True
            continue
        try:
            out, warnings, layout = produce(model, mod, args, overrides, assets_mode)
        except ModelError as exc:
            print(exc, file=sys.stderr)
            picture, draft_layout = failure_map(mod, model, args.mode, overrides, exc)
            if picture:
                print(picture, file=sys.stderr)
            if args.draft and mod is schema:
                print("черновик: для schema ошибки раскладки нужно исправить, маршрутизатора у схем нет",
                      file=sys.stderr)
            advise(mod, model, path, args, overrides, draft_layout, batch)
            failed = True
            continue
        for w in warnings:
            print("предупреждение: " + w, file=sys.stderr)
        if not args.check and args.format != "ascii" and layout.get("crossings", 0) >= MANY_CROSSINGS:
            print(mod.ascii(model, layout), file=sys.stderr)
        advise(mod, model, path, args, overrides, layout, batch)
        done.append((path, model, out, warnings, layout))
    if failed:
        return 1

    # G4: every successful render — --check included — prints one summary line per model to
    # stderr, in the --check shape, before any stdout/file output for that model is produced.
    # With several models the line also carries the model path, so it doesn't rely on order.
    for path, model, out, warnings, layout in done:
        n = len(model.get("tables") or model.get("nodes") or model.get("moments") or [])
        prefix = f"{path}: " if batch else ""
        print(f"ок: {prefix}вид {model['kind']}, {n} узлов, {len(layout['edges'])} связей, "
              f"{len(warnings)} предупреждений", file=sys.stderr)

    if args.check:
        for path, model, out, warnings, layout in done:
            sys.stdout.write(out)
        return 0
    if args.out_dir:
        target_dir = Path(args.out_dir)
        resolved_dir = target_dir.resolve()
        bad, targets, dups, computed = [], {}, {}, []
        for path, model, out, _, _ in done:
            try:
                target, resolved = batch_target(path, model, target_dir, resolved_dir, args.format)
            except ValueError as exc:
                bad.append(str(exc))
                continue
            if resolved in targets:
                dups.setdefault(resolved, [targets[resolved]]).append(path)
            else:
                targets[resolved] = path
                computed.append((target, out))
        if bad:
            for exc in bad:
                print(exc, file=sys.stderr)
            return 1
        if dups:
            for resolved, paths in dups.items():
                print(f"ошибка: --out-dir: несколько моделей пишут в {resolved.name}: {', '.join(paths)}",
                      file=sys.stderr)
            return 1
        target_dir.mkdir(parents=True, exist_ok=True)
        for target, out in computed:
            target.write_text(out)
            print(f"{target} ({len(out)} байт)")
        return 0
    out = done[0][2]
    if args.out:
        Path(args.out).write_text(out)
        print(f"записано {args.out} ({len(out)} байт)", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
