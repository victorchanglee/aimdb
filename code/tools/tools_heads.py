"""Print the opening of several papers at once, for coarse queue ordering.

The reading pass spends most of its turns on papers that turn out to be
method/algorithm papers with no specific compound. Reading N abstracts in one
pass, rather than one paper per round trip, is what makes a 400-paper queue
tractable.

This orders work; it does not judge it. A paper whose abstract sounds like a
pure method paper still has to be opened before it can be called not_usable —
benchmark papers routinely report full active spaces on real molecules.

Usage:
  .venv/bin/python tools/tools_heads.py --status text_ready --limit 20 --skip 0
  .venv/bin/python tools/tools_heads.py --key W1 W2 --chars 1500
"""
import argparse
import re

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", nargs="*")
    ap.add_argument("--status", default="text_ready")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--chars", type=int, default=1100)
    args = ap.parse_args()

    rows = index.load()
    if args.key:
        keys = args.key
    else:
        keys = [r["key"] for r in rows if r["status"] == args.status]
        keys = keys[args.skip:args.skip + args.limit]
    titles = {r["key"]: r["title"] for r in rows}
    years = {r["key"]: r["year"] for r in rows}

    for key in keys:
        path = config.TEXT_DIR / f"{key}.txt"
        if not path.exists():
            print(f"### {key}  [no text file]\n")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        head = re.sub(r"\s+", " ", text[:args.chars * 3]).strip()
        print(f"### {key}  ({years.get(key,'')})  {titles.get(key,'')}")
        print(head[:args.chars])
        print()


if __name__ == "__main__":
    main()
