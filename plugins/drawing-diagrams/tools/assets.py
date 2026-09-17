#!/usr/bin/env python3
"""Build and check the published assets of the drawing-diagrams skill. For the plugin's maintainer;
SKILL.md does not mention it.

  assets.py build       write template/dist/dg.css and dg.js from template/css, template/js and the ramps
  assets.py check       exit 1 when template/dist differs from a fresh build
  assets.py verify-cdn  exit 1 unless jsDelivr serves template/dist at template/dist/REF byte for byte

Release: build and check; commit template/dist; write the SHA of that commit into template/dist/REF
and commit it; merge with a merge commit; after the merge run verify-cdn.
"""
import argparse
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "drawing-diagrams"
sys.path.insert(0, str(SKILL))

from diagrams import assets  # noqa: E402

FILES = ("dg.css", "dg.js")


def built():
    return {"dg.css": assets.css_text().encode(), "dg.js": assets.js_text().encode()}


def build():
    assets.DIST.mkdir(parents=True, exist_ok=True)
    for name, data in built().items():
        (assets.DIST / name).write_bytes(data)
        print(f"записано {assets.DIST / name} ({len(data)} байт)")
    return 0


def check():
    stale = [name for name, data in built().items()
             if not (assets.DIST / name).exists() or (assets.DIST / name).read_bytes() != data]
    for name in stale:
        print(f"template/dist/{name} не совпадает с исходниками: запустите assets.py build", file=sys.stderr)
    return 1 if stale else 0


def fetch(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.status, resp.read()


def verify_cdn(get=fetch):
    ref = assets.read_ref()
    if not ref:
        print("нет template/dist/REF: сборка ещё не выпущена", file=sys.stderr)
        return 1
    bad = 0
    for name in FILES:
        url = assets.cdn_url(ref, name)
        try:
            status, data = get(url)
        except OSError as exc:  # URLError and HTTPError are OSError
            print(f"{url}: {exc}", file=sys.stderr)
            bad += 1
            continue
        local = (assets.DIST / name).read_bytes()
        if status != 200 or data != local:
            print(f"{url}: статус {status}, {len(data)} байт против {len(local)} локально", file=sys.stderr)
            bad += 1
        else:
            print(f"ок {url}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("build", "check", "verify-cdn"))
    args = ap.parse_args(argv)
    return {"build": build, "check": check, "verify-cdn": verify_cdn}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
