"""Export aimdb.csv with QUEST-sourced rows dropped.

The QUEST database is held out as a benchmark in claude-casscf/test/questdb/.
Any row mined from a QUEST-series or QUEST-adjacent paper shadows that
benchmark and must not reach a database the decision agent can read.

The DOI list used to live here. It now lives in mining_agent.config, because
mining_agent.query enforces the same boundary and two copies of a rule this
one matters would drift. CLAUDE.md keeps the annotated version.

Usage, from code/: tools/tools_export.py [output.csv]
"""
import csv
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (puts code/ on sys.path)
from mining_agent import config

ROOT = Path(__file__).resolve().parents[2]

QUEST_DOIS = config.QUEST_DOIS
QUEST_TEXT = config.QUEST_TEXT
SCAN_FIELDS = config.QUEST_SCAN_FIELDS


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "database/aimdb_no_quest.csv"
    with open(ROOT / "database/aimdb.csv", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    kept, dropped, suspect = [], [], []
    for r in rows:
        if r["reference_doi"].strip().lower() in QUEST_DOIS:
            dropped.append(r)
            continue
        if any(QUEST_TEXT.search(r.get(f) or "") for f in SCAN_FIELDS):
            suspect.append(r)
        kept.append(r)

    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)

    print(f"{len(rows)} rows in -> {len(kept)} kept, {len(dropped)} dropped")
    by_doi = {}
    for r in dropped:
        by_doi.setdefault(r["reference_doi"], []).append(r["entry_id"])
    for doi, ids in sorted(by_doi.items()):
        print(f"  dropped {len(ids):2d}  {doi}  ({ids[0]}...{ids[-1]})" if len(ids) > 1
              else f"  dropped  1  {doi}  ({ids[0]})")
    if suspect:
        print(f"\nCHECK {len(suspect)} kept row(s) mention QUEST but are not on the DOI list:")
        for r in suspect:
            print(f"  {r['entry_id']:16s} {r['reference_doi']}")
    print(f"\nwrote {out}")


main()
