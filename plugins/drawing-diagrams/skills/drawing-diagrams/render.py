#!/usr/bin/env python3
"""Render a diagram from a JSON model. The model's `kind` picks the renderer.

Usage:
    render.py MODEL.json [--mode widget|page] [--out FILE] [--check] [--draft]
                         [--format html|mermaid|ascii] [--no-assets]
                         [--open] [--types] [--width PX] [--harness]

Kinds: schema, flow, swimlane, state, blocks, timeline (see design.md).

Exit status 1 on validation errors (printed to stderr). Warnings go to stderr;
the output is still produced. --draft turns layout errors into warnings and
stamps the output as a draft.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagrams import assets  # noqa: E402
from diagrams import flow, schema, timeline  # noqa: E402
from diagrams.common import ModelError  # noqa: E402

KINDS = {"schema": schema, "flow": flow, "swimlane": flow, "state": flow, "blocks": flow, "timeline": timeline}
PLANNED = ()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="JSON model (see reference/model.md)")
    ap.add_argument("--mode", choices=("widget", "page"), default="widget",
                    help="widget: 680px fragment for a chat widget; page: 1100px section for a page or artifact")
    ap.add_argument("--format", choices=("html", "mermaid", "ascii"), default="html",
                    help="html for chat and artifacts; mermaid for markdown in a repository; ascii for the terminal")
    ap.add_argument("--out", help="write the output here instead of stdout")
    ap.add_argument("--check", action="store_true",
                    help="validate only and print the ASCII map (width checks honour --open, --types, --width)")
    ap.add_argument("--draft", action="store_true",
                    help="downgrade layout errors to warnings and stamp the output as a draft")
    ap.add_argument("--no-assets", action="store_true",
                    help="omit <style> and <script>; for the second and later diagrams on one page")
    ap.add_argument("--open", action="store_true", help="schema: start with all columns visible")
    ap.add_argument("--types", action="store_true", help="schema: show types on key rows too")
    ap.add_argument("--width", type=int, help="total width in px instead of the mode default (680 / 1100)")
    ap.add_argument("--harness", action="store_true",
                    help="widget mode: wrap the fragment into a standalone page for a browser")
    args = ap.parse_args(argv)

    try:
        model = json.loads(Path(args.model).read_text())
    except (OSError, ValueError) as exc:
        print(f"ошибка: не читается модель {args.model}: {exc}", file=sys.stderr)
        return 1
    kind = model.get("kind")
    if kind not in KINDS:
        hint = f"вид {kind!r} запланирован, но ещё не реализован (см. design.md)" if kind in PLANNED \
            else f"поле kind обязательно; доступны: {', '.join(KINDS)}"
        print("ошибка: " + hint, file=sys.stderr)
        return 1
    mod = KINDS[kind]

    overrides = {}
    if args.open:
        overrides["open"] = True
    if args.types:
        overrides["type_on_keys"] = True
    if args.width:
        overrides["total"] = args.width

    try:
        layout, warnings = mod.plan(model, args.mode, overrides, draft=args.draft)
    except ModelError as exc:
        print(exc, file=sys.stderr)
        if args.draft and kind == "schema":
            print("черновик: для schema ошибки раскладки нужно исправить, маршрутизатора у схем нет", file=sys.stderr)
        return 1
    draft_used = bool(layout.get("draft"))

    for w in warnings:
        print("предупреждение: " + w, file=sys.stderr)

    if args.check or args.format == "ascii":
        text = mod.ascii(model, layout)
        if args.check:
            print(text)
            print(f"ок: вид {kind}, {len(model.get('tables') or model.get('nodes') or model.get('moments') or [])} узлов, "
                  f"{len(layout['edges'])} связей, {len(warnings)} предупреждений", file=sys.stderr)
            return 0
        out = text + "\n"
    elif args.format == "mermaid":
        out = mod.mermaid(model, layout) + "\n"
    else:
        out = mod.render(model, args.mode, layout, warnings, assets_mode="none" if args.no_assets else "inline", draft=draft_used)
        if args.harness:
            if args.mode != "widget":
                print("ошибка: --harness имеет смысл только в режиме widget", file=sys.stderr)
                return 1
            out = assets.harness(out)

    if args.out:
        Path(args.out).write_text(out)
        print(f"записано {args.out} ({len(out)} байт)", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
