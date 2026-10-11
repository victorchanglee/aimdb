#!/usr/bin/env python3
"""Find rows whose own prose would feed the extractor a value they already hold.

`properties` is normally lifted FROM a row's prose by tools_properties.py. When
a value is instead entered by hand -- read from the paper's text or a table the
row's prose never carried -- the note explaining that provenance must not quote
the number. If it does, the next extraction run reads the hand-curated value
back out of the note describing the curation, and the two can then drift apart
the moment the extraction rules change.

This has happened three times in one day's work, each time in a note written to
explain a correction:

    "...stored gx = 2.475, gy = 2.624, gz = 2.022, computed by..."
    "...would have put gz = 18.323 on a Tb(III), which is impossible..."
    "...the computed g3 = 0.68 is the paper's suggestion for..."

so it is worth a check rather than vigilance. Run it after any hand edit to
`properties`. A clean run prints nothing but the count.

What counts as a leak: the row holds a key in `properties`, AND extracting from
its prose yields that same key, AND the value was entered BY HAND FROM THE
PAPER rather than lifted from the row's own prose. That last condition is what
makes the check meaningful, and getting it wrong makes the check useless: a
first version keyed on any row whose notes mention `properties:` and reported
154 of 209 rows, almost all of them values that tools_properties.py had
correctly lifted from prose, where re-deriving them is the intended behaviour
rather than a defect.

The marker is therefore the phrase the hand-backfills actually write -- "read
from the source text", which asserts that the row's own prose never carried the
value. If prose then yields it anyway, the note is quoting it back.

BASELINE on 2026-10-11: seven rows are flagged, and NONE of them is a note
written by a hand-backfill. All seven are mining-era prose restating a column
the row already holds -- "experimental D = -17(1) cm-1, E/D = ..." in
W1924454284's `Other`, "Its 3d anisotropy is small and EASY-AXIS, D = -4..."
in W4400983456's `notes`, and so on. That is a real defect (a prose column
must not restate a structured one) but a different and older one, and it is
not what this check was written to catch. Treat a count above seven as a new
leak; the seven themselves need the prose trimmed, not a note reworded.

    W1924454284-a  W3185980134-a  W4322492641-a  W4398193622-a
    W4398193622-b  W4400983456-a  W4402253705-a

Usage, from code/:
    .venv/bin/python tools/tools_check_property_leaks.py
    .venv/bin/python tools/tools_check_property_leaks.py --all
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from tools.tools_properties import extract, parse          # noqa: E402

DB = ROOT / "database" / "aimdb.csv"
# The phrase a hand-backfill writes when it takes a value from the paper
# rather than from the row's prose. Prose-lifted values are excluded by
# construction, because for those a prose match is correct.
HAND = "read from the source text"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true",
                    help="check every row, not only the hand-edited ones. "
                         "Slower, and a hit on a row whose value really did "
                         "come from its prose is expected rather than a bug")
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    checked = 0
    leaks = []
    for r in rows:
        if not args.all and HAND not in r["notes"]:
            continue
        held = {k for k, _ in parse(r["properties"] or "")}
        if not held:
            continue
        checked += 1
        # EXTRACT FROM THE ANNOTATION ALONE. The row's mining-era prose
        # legitimately carries values that tools_properties.py lifted, and
        # re-deriving those is correct; comparing against all of a row's prose
        # therefore reports them as leaks and buries the real thing. What must
        # not happen is a NOTE OR `Other` WRITTEN BY HAND quoting a value the
        # same edit stored, so only those two fields are fed to the extractor.
        annotated = {k: ("" if k not in ("notes", "Other") else r[k])
                     for k in r}
        derived = {k for k, _ in extract(annotated)[0]}
        both = sorted(held & derived)
        if both:
            leaks.append((r["entry_id"], both))

    for eid, keys in leaks:
        print("  LEAK %-16s %s" % (eid, ", ".join(keys)))
    print("checked %d row(s)%s; %d leak(s)"
          % (checked, "" if args.all else " with a hand-edited `properties`",
             len(leaks)))
    if leaks:
        print("\nThe fix is to reword the note so it describes the value "
              "without printing it.\nA prose column must not restate a filled "
              "structured column in any case.")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
