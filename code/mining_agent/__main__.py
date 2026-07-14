"""CLI entry points for the mining loop — see CLAUDE.md for the policy.

Run from code/ with .venv/bin/python -m mining_agent <command>.
"""
import argparse
import json
import sys
from collections import Counter

from . import config, csvio, fetch, index, pdftext, search


def cmd_search(args):
    found = search.openalex_search(args.query, max_results=args.max,
                                   from_year=args.from_year)
    added = index.add_candidates(found)
    for row in added:
        index.log_extraction(row["key"], row["doi"], "search", "candidate",
                             f"query: {args.query!r}")
        print(f"  + {row['key']}  {row['year']}  {row['title'][:80]}")
    print(f"{len(found)} results, {len(added)} new candidates added")


def cmd_fetch(args):
    if args.key:
        row = index.get(index.load(), args.key)
        if row is None:
            sys.exit(f"no index entry {args.key!r}")
        ok, detail = fetch.fetch_one(row)
        print(("fetched: " if ok else "FAILED: ") + detail)
    else:
        ok, failed = fetch.fetch_candidates(max_papers=args.max)
        print(f"fetched {ok}, failed {failed}")


def cmd_text(args):
    rows = index.load()
    if args.key:
        targets = [r for r in rows if r["key"] == args.key]
        if not targets:
            sys.exit(f"no index entry {args.key!r}")
    else:
        targets = [r for r in rows if r["status"] == "fetched"]
    for row in targets:
        ok, detail = pdftext.extract_text(row)
        print(f"{row['key']}: " + ("ok " if ok else "FAILED ") + detail)


def cmd_add_row(args):
    with open(args.json, encoding="utf-8") as f:
        fields = json.load(f)
    row = csvio.append_row(fields)
    index.log_extraction(fields["entry_id"], fields["reference_doi"],
                         "add-row", "appended",
                         args.reasoning or "row added via add-row")
    print(f"appended {row['entry_id']} ({row['reference_doi']})")


def cmd_mark(args):
    row = index.set_status(args.key, args.status)
    index.log_extraction(args.key, row["doi"], "mark", args.status,
                         args.reasoning)
    print(f"{args.key} -> {args.status}")


def cmd_status(_args):
    rows = index.load()
    counts = Counter(r["status"] for r in rows)
    print(f"{len(rows)} papers indexed:")
    for status in sorted(counts):
        print(f"  {counts[status]:4d}  {status}")
    n_rows = max(0, len(csvio.existing_entry_ids()))
    print(f"{n_rows} rows in literature.csv")


def cmd_show(args):
    row = index.get(index.load(), args.key)
    if row is None:
        sys.exit(f"no index entry {args.key!r}")
    for col in config.INDEX_COLUMNS:
        print(f"{col:12s} {row[col]}")


def main():
    parser = argparse.ArgumentParser(prog="mining_agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="query OpenAlex, add candidates")
    p.add_argument("--query", required=True)
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--from-year", type=int, default=None)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("fetch", help="download OA PDFs for candidates")
    p.add_argument("--key")
    p.add_argument("--max", type=int, default=5)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("text", help="extract text from fetched PDFs")
    p.add_argument("--key")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("add-row", help="append a validated literature.csv row")
    p.add_argument("--json", required=True,
                   help="path to a JSON dict of schema fields")
    p.add_argument("--reasoning", default="")
    p.set_defaults(func=cmd_add_row)

    p = sub.add_parser("mark", help="set a paper's index status")
    p.add_argument("--key", required=True)
    p.add_argument("--status", required=True,
                   choices=sorted(config.INDEX_STATUSES))
    p.add_argument("--reasoning", required=True)
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("status", help="index and database summary")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show", help="print one index entry")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
