"""Remove aimdb.csv rows that name no compound, quarantining them first.

`compound_name` is what makes a row answerable: a consumer asks "what active
space does *this molecule* need". A row whose compound_name is a dataset label
("Thiel benchmark set of organic molecules"), a generic class with no species
("iron(II) complexes - spin-state energetics benchmark set"), or the paper's
internal numbering ("compound 6") cannot answer that for any molecule, and
cannot be checked against the paper either.

This tool strips such rows. It never deletes silently:

  - every removed row is written verbatim to `logs/removed_rows.csv`,
    with the reason and the date, so the extraction is recoverable;
  - every removal appends to `logs/extractions.csv`;
  - the list of entry_ids is supplied by the caller and is expected to have
    been read one by one. There is deliberately no pattern mode: "names no
    compound" is a judgment, and a regex that decides it will delete rows that
    do name one (an early pass here matched `n ?= ?` and flagged every formula
    containing `N=O`).

Usage, from code/:
    .venv/bin/python tools/tools_strip_rows.py --json strip.json [--dry-run]

where strip.json is [{"entry_id": "...", "reason": "..."}, ...].
"""

import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
QUARANTINE = ROOT / "logs" / "removed_rows.csv"
LOG = ROOT / "logs" / "extractions.csv"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="file of {entry_id, reason} objects")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    wanted = {e["entry_id"]: e.get("reason", "") for e in
              json.loads(Path(args.json).read_text(encoding="utf-8"))}

    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    keep, removed = [], []
    for r in rows:
        (removed if r["entry_id"] in wanted else keep).append(r)

    absent = sorted(set(wanted) - {r["entry_id"] for r in removed})
    for eid in absent:
        print(f"  skip {eid}: no such entry_id", file=sys.stderr)
    print(f"removing {len(removed)} rows, keeping {len(keep)}")

    if args.dry_run:
        print("dry run - nothing written")
        return 0
    if not removed:
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    # Quarantine: the schema of aimdb.csv plus why and when the row left.
    # aimdb.csv gains columns over time (`element` was added 2026-08-20), so an
    # existing quarantine file can have a narrower header than the rows we are
    # about to append. Appending regardless would write more values than the
    # header has columns and silently shift every field in every new row. When
    # the headers disagree, rewrite the file under the union instead.
    qfields = fieldnames + ["removed_reason", "removed_at"]
    existing = []
    if QUARANTINE.exists():
        with QUARANTINE.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            old_fields = reader.fieldnames or []
            existing = list(reader)
        if old_fields != qfields:
            qfields = old_fields + [c for c in qfields if c not in old_fields]
            print(f"  quarantine header differs from aimdb.csv; rewriting "
                  f"{QUARANTINE.name} under {len(qfields)} columns "
                  f"(added: {[c for c in qfields if c not in old_fields] or 'none'})",
                  file=sys.stderr)
        else:
            existing = None  # header matches, plain append is safe

    rows_out = [{**r, "removed_reason": wanted[r["entry_id"]], "removed_at": stamp}
                for r in removed]
    mode = "a" if existing is None else "w"
    with QUARANTINE.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=qfields, restval="")
        if mode == "w":
            writer.writeheader()
            writer.writerows(existing)
        writer.writerows(rows_out)

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for r in removed:
            writer.writerow([
                stamp, r["entry_id"], r.get("reference_doi", ""), "strip_row",
                f"compound_name={r['compound_name'][:120]}",
                f"row names no compound: {wanted[r['entry_id']]}; "
                f"full row preserved in logs/removed_rows.csv",
            ])

    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(keep)
    tmp.replace(DB)
    print(f"quarantined to {QUARANTINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
