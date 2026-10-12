"""Split one aimdb.csv row that stands for several species or calculations.

A row may cover several compounds ("NiO and its NiO+ and NiO- ions"), or one
compound computed at several active spaces with different results. One row
holds one (nel,norb), so it cannot hold either. The fix is a split: one row per
compound or per calculation, each with its own active space and results.

What the tool does, per parent row:

  - the parent is copied verbatim to `logs/removed_rows.csv` first, with the
    reason, so the merged reading is always recoverable;
  - the FIRST child keeps the parent's entry_id; the rest get the next unused
    suffixes for the paper key (-a ... -z, -aa ...);
  - each child starts as a copy of the parent, and the JSON overrides fields.
    The fields that differ between species MUST be given for every child:
    compound_name, active_space_nel, active_space_norb and
    electronic_structure_description. Copying them from the parent is exactly
    the error a split exists to fix;
  - structure_file/structure_provenance are cleared unless the child sets
    "keep_structure": true, since a geometry belongs to one species;
  - `element` is re-derived from metal_center and formula, keeping the old
    value when the derivation would shrink it (see tools_fill_element.py);
  - every child's notes gain "Split from <parent> (<date>): <reason>", and each
    split is logged to `logs/extractions.csv` as action `split_row`.

Usage, from code/:
    .venv/bin/python tools/tools_split_row.py --json splits.json [--dry-run]

splits.json: [{"entry_id": "W1-a", "reason": "...",
               "children": [{"compound_name": "...", "active_space_nel": "14",
                             "active_space_norb": "9",
                             "electronic_structure_description": "...", ...}, ...]}]
"""

import argparse
import csv
import datetime as _dt
import json
import re
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
QUARANTINE = ROOT / "logs" / "removed_rows.csv"
LOG = ROOT / "logs" / "extractions.csv"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools_fill_element import derive  # noqa: E402

REQUIRED = ("compound_name", "active_space_nel", "active_space_norb",
            "electronic_structure_description")
INT_FIELDS = ("active_space_nel", "active_space_norb")


def suffixes():
    letters = string.ascii_lowercase
    for a in letters:
        yield a
    for a in letters:
        for b in letters:
            yield a + b


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames
        rows = list(reader)
    by = {r["entry_id"]: i for i, r in enumerate(rows)}
    taken = set(by)
    specs = json.load(open(args.json))
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    day = stamp[:10]

    errors, plan = [], []
    for s in specs:
        pid = s["entry_id"]
        if pid not in by:
            errors.append(f"{pid}: no such row")
            continue
        kids = s.get("children") or []
        if len(kids) < 1:
            errors.append(f"{pid}: no children")
            continue
        bad = False
        for k, c in enumerate(kids):
            unknown = set(c) - set(cols) - {"keep_structure"}
            if unknown:
                errors.append(f"{pid} child {k}: unknown fields {sorted(unknown)}")
                bad = True
            for f in REQUIRED:
                if f not in c:
                    errors.append(f"{pid} child {k}: missing {f}")
                    bad = True
            for f in INT_FIELDS:
                v = str(c.get(f, "")).strip()
                if v and not re.fullmatch(r"\d+", v):
                    errors.append(f"{pid} child {k}: {f}={v!r} is not an integer")
                    bad = True
        if bad:
            continue
        key = pid.rsplit("-", 1)[0]
        ids = [pid]
        gen = suffixes()
        while len(ids) < len(kids):
            cand = f"{key}-{next(gen)}"
            if cand not in taken:
                taken.add(cand)
                ids.append(cand)
        plan.append((s, ids))

    for e in errors:
        print("ERROR", e)
    if errors:
        print("nothing written")
        return 1

    new_rows, quarantined, log = {}, [], []
    for s, ids in plan:
        parent = rows[by[s["entry_id"]]]
        quarantined.append({**parent, "removed_reason": f"split into {', '.join(ids)}: {s['reason']}",
                            "removed_at": stamp})
        children = []
        for cid, c in zip(ids, s["children"]):
            child = dict(parent)
            keep = c.get("keep_structure", False)
            for f, v in c.items():
                if f != "keep_structure":
                    child[f] = str(v).strip()
            child["entry_id"] = cid
            if not keep and "structure_file" not in c:
                child["structure_file"] = ""
                child["structure_provenance"] = ""
            # A child that restates formula or metal_center gets the element set
            # those imply; otherwise it is the same chemistry as the parent and
            # keeps the parent's set, which may be hand-identified and wider.
            if "element" not in c and ("formula" in c or "metal_center" in c):
                derived = derive(child)
                if derived:
                    child["element"] = derived
            note = f"Split from {s['entry_id']} ({day}): {s['reason']}"
            child["notes"] = (child["notes"] + " " if child["notes"] else "") + note
            children.append(child)
            log.append([stamp, cid, child.get("reference_doi", ""), "split_row",
                        f"{s['entry_id']} -> {cid}: {child['compound_name'][:80]} "
                        f"({child['active_space_nel']},{child['active_space_norb']})",
                        s["reason"]])
        new_rows[s["entry_id"]] = children
        print(f"{s['entry_id']} -> " + "; ".join(
            f"{c['entry_id']} {c['compound_name'][:40]!r} ({c['active_space_nel']},{c['active_space_norb']})"
            for c in children))

    if args.dry_run:
        print(f"dry run: {len(plan)} rows would become "
              f"{sum(len(v) for v in new_rows.values())}")
        return 0

    out = []
    for r in rows:
        out.extend(new_rows.get(r["entry_id"], [r]))
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    tmp.replace(DB)

    with QUARANTINE.open(newline="", encoding="utf-8") as fh:
        qcols = csv.DictReader(fh).fieldnames
    with QUARANTINE.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=qcols, extrasaction="ignore")
        w.writerows(quarantined)
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(log)
    print(f"split {len(plan)} rows into {sum(len(v) for v in new_rows.values())}; "
          f"{len(rows)} -> {len(out)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
