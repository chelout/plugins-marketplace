#!/usr/bin/env python3
"""Render diagrams from JSON models. A model's `kind` picks the renderer.

Usage:
    render.py MODEL.json [MODEL.json ...] [--mode widget|page] [--out FILE | --out-dir DIR]
              [--assets cdn|inline|none] [--no-assets] [--check] [--draft]
              [--format html|mermaid|ascii] [--open] [--types] [--width PX] [--harness]

Kinds: schema, flow, swimlane, state, blocks, timeline (reference/common.md).

Every render checks the model first. On errors stdout stays empty, the exit status is 1 and stderr
lists every problem, with the ASCII map when a line or the grid failed rather than the length of a
text. Warnings go to stderr and the output is still produced. --draft turns layout errors into
warnings and stamps the output as a draft.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagrams import assets  # noqa: E402
from diagrams import flow, schema, timeline  # noqa: E402
from diagrams.common import ModelError  # noqa: E402
from diagrams.grid import ascii_map, parse_grid  # noqa: E402

KINDS = {"schema": schema, "flow": flow, "swimlane": flow, "state": flow, "blocks": flow, "timeline": timeline}
SUFFIX = {"html": ".html", "mermaid": ".mmd", "ascii": ".txt"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


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
    """The ASCII map of a model that failed on layout rather than on the length of a text, else None."""
    if not any(e not in exc.fit for e in exc.layout):
        return None
    if mod is schema:
        cells, cols, rows = parse_grid(model.get("grid"), [])
        return ascii_map(cells, cols, rows)
    try:
        layout, _ = mod.plan(model, mode_name, overrides, draft=True)
    except ModelError:
        # G6: the draft re-plan can itself raise, e.g. an ordinary validation error (duplicate node
        # id) alongside the layout error. Fall back to the raw grid map for kinds that have one.
        if mod is flow:
            cells, cols, rows = parse_grid(model.get("grid"), [])
            return ascii_map(cells, cols, rows)
        return None
    return mod.ascii(model, layout)


def batch_target(path, model, target_dir, resolved_dir, fmt):
    """(target, resolved target) to write one model's output to in --out-dir mode; raises
    ValueError with the message to print when the id is not a safe file name or the target
    would land outside target_dir."""
    model_id = model.get("id")
    if model_id:
        if not ID_RE.match(model_id):
            raise ValueError(f"ошибка: --out-dir: {path}: id «{model_id}» не годится для имени файла "
                              f"(разрешены только буквы, цифры, _ и -, без точек и разделителей)")
        stem = model_id
    else:
        stem = Path(path).stem
    target = target_dir / f"{stem}{SUFFIX[fmt]}"
    resolved = target.resolve()
    if resolved.parent != resolved_dir:
        raise ValueError(f"ошибка: --out-dir: {path}: цель {target} выходит за пределы {target_dir}")
    return target, resolved


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
            picture = failure_map(mod, model, args.mode, overrides, exc)
            if picture:
                print(picture, file=sys.stderr)
            if args.draft and mod is schema:
                print("черновик: для schema ошибки раскладки нужно исправить, маршрутизатора у схем нет",
                      file=sys.stderr)
            failed = True
            continue
        for w in warnings:
            print("предупреждение: " + w, file=sys.stderr)
        if not args.check and args.format != "ascii" and layout.get("crossings", 0) >= 3:
            print(mod.ascii(model, layout), file=sys.stderr)
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
