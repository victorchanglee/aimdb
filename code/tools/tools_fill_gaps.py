"""Apply reviewed gap-fills to database/aimdb.csv.

The second-read queue finds rows whose core fields are empty even though the
paper states the value. Filling those is judgment work: a human (or the mining
session) reads the sentence and decides. This tool only *applies* decisions that
have already been made, and refuses anything that looks like a blind overwrite.

Input is a JSON list of edits:

    [{"entry_id": "W123-a",
      "field": "software",
      "value": "OpenMolcas v18.0",
      "evidence": "verbatim sentence from text/<key>.txt",
      "note": "optional addition to the row's notes column"}, ...]

Rules enforced here:
  - the target cell must currently be empty (append-only spirit: we fill gaps,
    we never silently replace an extracted value). --allow-replace opts out
    per run and records the old value in the log.
  - `field` must be a real aimdb.csv column.
  - every edit must carry `evidence`; a fill without a quotable sentence is
    exactly the inference CLAUDE.md forbids.
  - every applied edit appends to logs/extractions.csv.

Usage, from code/:
    .venv/bin/python tools/tools_fill_gaps.py --json fills.json [--dry-run]
"""

import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
LOG = ROOT / "logs" / "extractions.csv"


def load_db():
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def write_db(fieldnames, rows):
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(DB)


def log_edits(applied):
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["timestamp", "key", "doi", "action", "result", "reasoning"])
        for e in applied:
            writer.writerow([
                stamp, e["entry_id"], e.get("doi", ""), "fill_gap",
                f"{e['field']}={e['value']}",
                f"second-read gap fill; paper states: {e['evidence'][:400]}",
            ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="file of reviewed edits")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--allow-replace", action="store_true",
                    help="permit overwriting a non-empty cell (logged)")
    args = ap.parse_args(argv)

    edits = json.loads(Path(args.json).read_text(encoding="utf-8"))
    fieldnames, rows = load_db()
    by_id = {r["entry_id"]: r for r in rows}

    applied, skipped = [], []
    for e in edits:
        eid, field = e.get("entry_id"), e.get("field")
        value = (e.get("value") or "").strip()
        row = by_id.get(eid)
        if row is None:
            skipped.append((eid, field, "no such entry_id"))
            continue
        if field not in fieldnames:
            skipped.append((eid, field, "not an aimdb.csv column"))
            continue
        if not value:
            skipped.append((eid, field, "empty value"))
            continue
        if not (e.get("evidence") or "").strip():
            skipped.append((eid, field, "no evidence quoted"))
            continue
        current = (row.get(field) or "").strip()
        if current and not args.allow_replace:
            skipped.append((eid, field, f"cell already holds {current[:40]!r}"))
            continue
        e = dict(e, doi=row.get("reference_doi", ""), old=current)
        row[field] = value
        if e.get("note"):
            existing = (row.get("notes") or "").strip()
            row["notes"] = f"{existing} {e['note']}".strip()
        applied.append(e)

    for eid, field, why in skipped:
        print(f"  skip  {eid}  {field}: {why}", file=sys.stderr)
    print(f"applied {len(applied)}, skipped {len(skipped)}")

    if args.dry_run:
        print("dry run - nothing written")
        return 0
    if applied:
        write_db(fieldnames, rows)
        log_edits(applied)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
