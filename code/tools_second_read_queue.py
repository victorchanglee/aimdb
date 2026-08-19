"""Regenerate logs/second_read_queue.csv from aimdb.csv + papers_index.csv.

The queue is a derived worklist, not a source of truth: it says which papers
have rows with an empty core field, and whether the text needed to fill it is
already on disk. Regenerate it whenever rows have been added or text fetched —
a stale queue is worse than none, because it hides work behind a wrong
`text_available=no`.

Tiers, in the order the file is sorted:

  A-active-space   a row is missing active_space_nel or active_space_norb, and
                   the paper's text is local. Highest value: a row without
                   (nel, norb) cannot answer the question the database exists
                   for.
  B-basis-orbitals space is present; basis_set or the orbital description is
                   not. Read the sentence — a paper often names only its DFT
                   geometry basis, which is not this column.
  D-software       only software is missing. Cheapest to close, usually one
                   sentence of the methods section.
  C-refetch        no local text at all; needs `refetch` or `si` before
                   anything can be read. Do these last.

Usage, from code/:
    .venv/bin/python tools_second_read_queue.py [--out PATH]
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database" / "aimdb.csv"
INDEX = ROOT / "database" / "papers_index.csv"
TEXT = ROOT / "text"
OUT = ROOT / "logs" / "second_read_queue.csv"

CORE = [
    "active_space_nel",
    "active_space_norb",
    "active_space_orbital_description",
    "basis_set",
    "software",
]
# how much closing each gap is worth, used only to order the file
WEIGHT = {
    "active_space_nel": 8,
    "active_space_norb": 8,
    "active_space_orbital_description": 3,
    "basis_set": 2,
    "software": 1,
}


def key_of(entry_id):
    """entry_id is the papers_index key plus an -a/-b/... suffix."""
    head, _, tail = entry_id.rpartition("-")
    return head if head and re.fullmatch(r"[a-z]{1,3}", tail) else entry_id


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    index = {r["key"]: r for r in csv.DictReader(INDEX.open(encoding="utf-8"))}
    files = set(p.name for p in TEXT.iterdir()) if TEXT.is_dir() else set()

    papers = defaultdict(lambda: {"rows": 0, "gapped": 0, "missing": defaultdict(int),
                                  "models": set()})
    for row in csv.DictReader(DB.open(encoding="utf-8")):
        key = key_of(row["entry_id"])
        p = papers[key]
        p["rows"] += 1
        p["models"].add(row.get("mining_model", ""))
        gaps = [c for c in CORE if not (row.get(c) or "").strip()]
        if gaps:
            p["gapped"] += 1
            for c in gaps:
                p["missing"][c] += 1

    out_rows = []
    for key, p in papers.items():
        if not p["gapped"]:
            continue
        meta = index.get(key, {})
        has_text = f"{key}.txt" in files
        has_si = any(f.startswith(f"{key}_si_") for f in files)
        m = p["missing"]
        if not has_text:
            tier = "C-refetch"
        elif m["active_space_nel"] or m["active_space_norb"]:
            tier = "A-active-space"
        elif m["basis_set"] or m["active_space_orbital_description"]:
            tier = "B-basis-orbitals"
        else:
            tier = "D-software"
        out_rows.append({
            "tier": tier,
            "key": key,
            "doi": meta.get("doi", ""),
            "title": meta.get("title", ""),
            "status": meta.get("status", ""),
            "rows": p["rows"],
            "rows_with_gaps": p["gapped"],
            "priority_score": sum(WEIGHT[c] * n for c, n in m.items()),
            **{f"missing_{c.replace('active_space_', '')}": m[c] for c in CORE},
            "mining_model": ";".join(sorted(x for x in p["models"] if x)),
            "text_available": "yes" if has_text else "no",
            "si_fetched": "yes" if has_si else "no",
        })

    order = {"A-active-space": 0, "B-basis-orbitals": 1, "D-software": 2, "C-refetch": 3}
    out_rows.sort(key=lambda r: (order[r["tier"]], -r["priority_score"], r["key"]))

    path = Path(args.out)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    counts = defaultdict(int)
    for r in out_rows:
        counts[r["tier"]] += 1
    print(f"{len(out_rows)} papers with core-field gaps -> {path}")
    for tier in sorted(counts, key=lambda t: order[t]):
        print(f"  {tier:16s} {counts[tier]:5d} papers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
