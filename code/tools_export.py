"""Export aimdb.csv with QUEST-sourced rows dropped.

The QUEST database is held out as a benchmark in claude-casscf/test/questdb/.
Any row mined from a QUEST-series or QUEST-adjacent paper shadows that
benchmark and must not reach a database the decision agent can read. The DOI
list below is the one maintained in CLAUDE.md ("QUEST-sourced rows: keep here,
filter on export") — keep the two in sync.

Usage: tools_export.py [output.csv]
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kept in sync with the list in CLAUDE.md. Lower-cased for comparison.
QUEST_DOIS = {
    "10.1021/acs.jctc.8b01205",   # Reference Energies for Double Excitations
    "10.48550/arxiv.2409.00302",  # QUEST#4X
    "10.1063/5.0095887",          # CASPT3 benchmark (QUEST-adjacent)
    "10.1002/wcms.1517",          # QUESTDB, the database paper itself
    "10.1021/acs.jctc.9b01216",   # QUEST#3, Mountaineering Strategy
    "10.1021/acs.jctc.4c00410",   # Double Excitations: Improvement and Extension
    "10.1021/acs.jctc.3c01080",   # Transition metal compounds (QUEST-TM)
    "10.1021/acs.jctc.1c01197",   # CASPT2 vs NEVPT2 assessment (QUEST-adjacent)
}

# Any row that mentions QUEST outside the known DOIs is reported, not dropped —
# a paper mined without being added to the list above would show up here.
QUEST_TEXT = re.compile(r"\bquest\b", re.I)
SCAN_FIELDS = ("reference_short", "notes", "compound_name", "active_space_protocol")


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
