"""Stamp reference_doi into row JSONs from papers_index.csv, never by hand.

A DOI typed from memory while writing a batch of rows is the one error that
looks completely normal in the database and silently misattributes a row to
another paper. The index already holds the authoritative DOI for every key, so
the entry_id prefix is all that is needed.

Usage:
  .venv/bin/python tools_stampdoi.py rows/*.json        # rewrite in place
  .venv/bin/python tools_stampdoi.py --check rows/*.json
"""
import argparse
import csv
import json
import re
import sys

from mining_agent import config


def index_dois():
    with open(config.PAPERS_INDEX_CSV, newline="", encoding="utf-8") as f:
        return {r["key"]: r["doi"] for r in csv.DictReader(f)}


def key_of(entry_id):
    """W4390412534-a -> W4390412534 (also tolerates -aa and bare keys)."""
    return re.sub(r"-[a-z]+$", "", entry_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--check", action="store_true",
                    help="report mismatches without rewriting")
    args = ap.parse_args()

    dois = index_dois()
    bad = 0
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            row = json.load(f)
        key = key_of(row.get("entry_id", ""))
        want = dois.get(key)
        if want is None:
            print(f"  ? {path}: key {key!r} not in the index")
            bad += 1
            continue
        have = row.get("reference_doi", "")
        if have == want:
            continue
        bad += 1
        print(f"  ! {row['entry_id']}: {have or '(empty)'} -> {want}")
        if not args.check:
            row["reference_doi"] = want
            with open(path, "w", encoding="utf-8") as f:
                json.dump(row, f, indent=1)
    print(f"{len(args.files)} file(s), {bad} corrected"
          if not args.check else f"{len(args.files)} file(s), {bad} mismatched")
    return 1 if (args.check and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
