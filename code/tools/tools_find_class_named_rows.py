"""Find rows that stand for several compounds, ranked, with the text on disk.

CLAUDE.md: "`compound_name` is what makes a row answerable -- a consumer asks
*what active space does this molecule need*. A row whose `compound_name` names
no chemical species answers that for nothing." The remedy is almost always a
SPLIT rather than a removal, and splitting also corrects fields: a merged row
carries one active space and the paper rarely uses one.

This is the queue for that work. It reports rows whose `compound_name` shows an
explicit enumeration signal, ranked by how many compounds appear to be
compressed into them, and tells you whether the source text is on disk -- a row
cannot be split without it.

IT IS A CANDIDATE LIST, NOT A DEFECT LIST, and CLAUDE.md says why in as many
words: screening on `compound_name` "over-fires badly: a row named
'[Co(L1)2(NCS)2(MeOH)2], the mononuclear thiocyanate complex, one of four'
names a specific species and is perfectly usable. That proxy inflated the
blocked count from 11 to 19 and left eight readable papers sitting unread.
Decide this by reading the name, not by matching it."

THE COUNT IS THE EASY THING TO GET WRONG, so two kinds of range are excluded
rather than counted. A first version read "Iron(II) spin-crossover complexes
(13-61-atom [FeL6]-type models)" as 49 compounds -- it is an ATOM count -- and
"trans-PSB3 with 0-30 water molecules" as 31, which is one solute with a
varying solvent shell. A range only counts when the thing being ranged over is
the compound itself: `n = 2-12` on a formula, or `complexes 1-7`.

Usage, from code/:
  .venv/bin/python tools/tools_find_class_named_rows.py
  .venv/bin/python tools/tools_find_class_named_rows.py --limit 40
  .venv/bin/python tools/tools_find_class_named_rows.py --unexamined
"""
import argparse
import csv
import re

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

csv.field_size_limit(10 ** 9)
ROOT = config.LITERATURE_CSV.parent.parent

# A plural or set word in the name. Deliberately broad: this is a candidate
# filter and the reading decides.
ENUM = re.compile(
    r"\bn\s*=\s*\d|\bbenchmark set\b|\btest set\b|\btest systems\b|\bset of\b|"
    r"\bsuite\b|\bcomplexes\b|\bmolecules\b|\bderivatives\b|\bcongeners\b|"
    r"\banalogues\b|\bclusters\b|\boligomers\b|\bpolyenes\b|\bmetallocenes\b|"
    r"\bfragments\b|\bprototypes\b|\bseries\b", re.I)

# Ranges that are NOT a compound count, checked before the counters below.
NOT_A_COUNT = re.compile(
    r"\d+\s*[-–]\s*\d+\s*-?\s*atom"            # "13-61-atom models"
    r"|\d+\s*[-–]\s*\d+\s+(?:water|solvent|H2O)"  # "0-30 water molecules"
    r"|\d+\s*[-–]\s*\d+\s*(?:K|cm-1|eV|A|nm|GHz|T)\b", re.I)

# "(11 molecules)" / "complexes 1-7" / "n = 2-12". The count need not close the
# bracket: the real XS-CASSCF row reads "(11 molecules, 56 excited states)", and
# requiring ")" scored it zero.
C_PAREN = re.compile(r"\((\d{1,3})\s+(?:molecules|compounds|complexes|systems)\b", re.I)
C_LABEL = re.compile(r"\b(?:complexes|compounds|molecules|systems)\s+(\d+)\s*[-–]\s*(\d+)", re.I)
C_NEQ   = re.compile(r"\bn\s*=\s*(\d+)\s*[-–]\s*(\d+)")
C_LIST  = re.compile(r"\bn\s*=\s*((?:\d+\s*,\s*){2,}(?:and\s*)?\d+)")


def compound_count(name):
    """How many compounds the name seems to cover, or 0 when it does not say."""
    if NOT_A_COUNT.search(name):
        name = NOT_A_COUNT.sub(" ", name)
    m = C_PAREN.search(name)
    if m:
        return int(m.group(1))
    for pat in (C_LABEL, C_NEQ):
        m = pat.search(name)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi > lo and hi - lo < 100:
                return hi - lo + 1
    m = C_LIST.search(name)
    if m:
        return len(re.findall(r"\d+", m.group(1)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--unexamined", action="store_true",
                    help="hide rows already carrying a class-named verdict")
    args = ap.parse_args(argv)

    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    cands, no_text, examined = [], 0, 0
    for r in rows:
        if not ENUM.search(r["compound_name"]):
            continue
        key = r["entry_id"].split("-")[0]
        has_text = (ROOT / "text" / ("%s.txt" % key)).exists()
        done = "NOT THIS ROW'S DEFECT" in r["notes"]
        if done:
            examined += 1
            if args.unexamined:
                continue
        if not has_text:
            no_text += 1
        cands.append((compound_count(r["compound_name"]), has_text, done,
                      r["entry_id"], r["compound_name"]))

    cands.sort(key=lambda c: (-c[0], not c[1]))
    print("rows whose compound_name carries an enumeration signal : %d" % len(cands))
    print("   with the source text on disk (splittable now)       : %d"
          % sum(1 for c in cands if c[1]))
    print("   without text (blocked on a fetch)                   : %d" % no_text)
    print("   already examined and recorded as class-named        : %d" % examined)
    print("\nA CANDIDATE LIST, not a defect list -- read the name before acting.\n")
    print("%-16s %5s %5s  %s" % ("entry_id", "cmpds", "text", "compound_name"))
    for n, has_text, done, e, name in cands[:args.limit]:
        print("%-16s %5s %5s  %s" % (e, n or "-", "yes" if has_text else "NO",
                                     name[:66]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
