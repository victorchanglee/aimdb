"""Find active-space statements in the text of papers whose rows lack one.

861 rows have an empty active_space_nel or norb, and the A-active-space tier of
the second-read queue lists 507 papers. Most of those rows are not a reading
problem but a transcription one: the paper states a space and the row never got
it. W7168274527 proved the pattern -- its rows asserted the size was "never
stated as a count" while section 2.4 said "both with 12 electrons in 12
orbitals".

This reports, per paper, every distinct (n,m) its text states, in the forms
papers actually use, so a batch can be adjudicated instead of one paper at a
time. It writes nothing.

Measured 2026-10-11 over all 506 papers with a gap and local text:

    exactly one space stated :  25 papers,  34 gap rows
    several spaces stated    :  45 papers,  86 gap rows
    no space stated anywhere : 436 papers, 650 gap rows

so THREE QUARTERS OF THE GAP IS NOT A TRANSCRIPTION FAILURE, which is what
CLAUDE.md already says to expect: "Many are genuinely absent from the source --
that is a finding, not a defect." Some will be in supplementary information
that was never fetched.

A BARE (n,m) IS WEAK EVIDENCE AND MUST BE READ IN CONTEXT. About two thirds of
the single-space papers were NOT fillable, and the reasons recur:

  * the number is in a LITERATURE COMPARISON TABLE of other groups' methods,
    each with its own reference marker (W2318674172's "CASSCF(10/10)/6-31G**++");
  * it is explicitly another group's work (W2162377719 cites "Johnson and
    Irikura [8] studied the excited states of PF2 using the CASSCF (3,8)");
  * it is a general remark rather than a calculation (W3088435364 on where
    "the classical quantum chemical limit" lies);
  * the row is CLASS-NAMED, so there is nothing to attribute it to -- and that
    is the real defect, upstream of the empty cell;
  * the paper gives a RANGE with the per-member values in supplementary
    material (W4324049352, "ranged between 8 electrons in 8 pi orbitals (8,8)
    up to 14 electrons in 14 orbitals (14,14)").

And the gap is sometimes the right answer. W4415130779-a's blank is correct:
"No electronic active space was used for HeHHe+", in a nuclear-electronic study
where the proton carries the active space. Three sibling rows at (2e,2o) made
it look like an omission.

    CAS(10,8)  CASSCF(10,8)  RASSCF(6,6)  (10e,8o)  (10e,8orb)
    "ten electrons in eight orbitals"  "10 electrons in 12 orbitals"

A paper reporting exactly ONE space is the actionable case: there is nothing to
choose between, so the row's space is that one. Papers reporting several are
listed too, with every candidate, because this session has repeatedly found
that the several are a production space plus tests -- and which is which needs
the sentence, not the number.
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

ROOT = config.LITERATURE_CSV.parent.parent
csv.field_size_limit(10 ** 9)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
         "twenty": 20}
NUMW = "|".join(WORDS)
PATS = [
 # CAS(n,m) / CASSCF(n,m) / RASSCF(n,m), with optional e/o suffixes
 re.compile(r"\b(?:CAS|CASSCF|RASSCF|CASPT2|NEVPT2|SA-CASSCF|SS-CASSCF)\s*"
            r"\(\s*(\d{1,2})\s*e?\s*[,/]\s*(\d{1,2})\s*(?:o|orb)?\s*\)", re.I),
 # bare (10e,8o) with explicit e and o, which is unambiguous without a prefix
 re.compile(r"\(\s*(\d{1,2})\s*e\s*[,/]\s*(\d{1,2})\s*o(?:rb)?\s*\)", re.I),
 # "N electrons in M orbitals", digits or words
 re.compile(r"\b(\d{1,2})\s+electrons?\s+in\s+(\d{1,2})\s+(?:active\s+)?orbitals",
            re.I),
 re.compile(r"\b(%s)\s+electrons?\s+in\s+(%s)\s+(?:active\s+)?orbitals"
            % (NUMW, NUMW), re.I),
]

def num(t):
    t = t.lower()
    return WORDS.get(t, None) if not t.isdigit() else int(t)

def spaces_in(txt):
    out = Counter()
    for pat in PATS:
        for m in pat.finditer(txt):
            a, b = num(m.group(1)), num(m.group(2))
            if a and b and 1 <= a <= 40 and 1 <= b <= 40:
                out[(a, b)] += 1
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--one-only", action="store_true",
                    help="only papers whose text states exactly one space")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(config.LITERATURE_CSV, newline="",
                                    encoding="utf-8")))
    gap = defaultdict(list)
    for r in rows:
        if not r["active_space_nel"].strip() or not r["active_space_norb"].strip():
            gap[r["entry_id"].split("-")[0]].append(r)

    single, multi, none_ = [], [], []
    for key, rs in gap.items():
        p = str(ROOT / "text" / ("%s.txt" % key))
        if not os.path.exists(p):
            continue
        sp = spaces_in(open(p, encoding="utf-8").read())
        if not sp:
            none_.append((key, rs, sp))
        elif len(sp) == 1:
            single.append((key, rs, sp))
        else:
            multi.append((key, rs, sp))

    print("papers with an active-space gap and local text: %d"
          % (len(single) + len(multi) + len(none_)), file=sys.stderr)
    print("  exactly one space stated : %4d papers, %4d gap rows"
          % (len(single), sum(len(r) for _, r, _ in single)), file=sys.stderr)
    print("  several spaces stated    : %4d papers, %4d gap rows"
          % (len(multi), sum(len(r) for _, r, _ in multi)), file=sys.stderr)
    print("  no space stated anywhere : %4d papers, %4d gap rows"
          % (len(none_), sum(len(r) for _, r, _ in none_)), file=sys.stderr)

    show = single if args.one_only else single + multi
    show.sort(key=lambda x: -len(x[1]))
    for key, rs, sp in show[:args.limit]:
        tag = ",".join("(%d,%d)x%d" % (a, b, n)
                       for (a, b), n in sp.most_common(6))
        print("%-14s %3d gap row(s)  %s" % (key, len(rs), tag))

if __name__ == "__main__":
    main()
