"""Classify the non-integer active-space cells by whether the number is recoverable.

Most start with an integer, which invites the obvious sweep: take the
leading number, move the rest to prose, done. That sweep would be WRONG, and
wrong in the exact way this session has been correcting all along -- recording
a space the paper reports but does not compute with. Three of the first
thirty samples are counter-examples:

    "8 in the minimal space, 12 in the extended one"   which is production?
    "12 for geometry optimization; 8 for Hessian"      two different jobs
    "10, 12, 14, and 18"                               a convergence series,
                                                       leading = smallest

and one is not a formatting problem at all:

    "9 for F2+, 7 for O2+, 4 for Be2 and 14 for NiC"   FOUR compounds, one row

So the question is not "can a number be parsed" but "does the cell say which
number the calculation used". Three vocabularies decide it:

  AUX      the trailing numbers are explicitly marked as something other than
           the production space -- test, check, validation, probe, also,
           additional, benchmark. The leading number is the answer.
  RIVAL    the cell offers two spaces with no production marker (minimal /
           extended, smaller / larger) or splits them across jobs (geometry /
           Hessian / spectra). Needs a reading.
  SPLIT    the qualifiers name compounds, so the row is standing for several.
           A class-named-row problem wearing a formatting problem's clothes.

As measured on 2026-10-11 over 511 cells in 308 rows:

    PACKED  N unlabelled spaces, semicolon-separated   256 cells  143 rows
    RIVAL   two spaces, no production marker            61 cells   35 rows
    RIVAL   unclassified                                60 cells   43 rows
    RIVAL   a bare series                               49 cells   38 rows
    (no number at all)                                  37 cells   30 rows
    RIVAL   a space per purpose                         16 cells    9 rows
    RIVAL   number not leading                          12 cells    8 rows
    SPLIT   a space per electronic state                 8 cells    4 rows
    SPLIT   needs per-compound rows                      5 cells    3 rows

HALF THE PROBLEM IS ONE CONVENTION, NOT 143 MISTAKES. The PACKED cells are a
deliberate mining-era habit: two or three whole spaces in one cell, positionally
paired across the two fields, so nel "14; 8" beside norb "10; 7" means CAS(14,10)
and CAS(8,7). One row even says so -- "both active-space variants are
consolidated". The schema has one slot, so this was the only way to keep both.

THE OBVIOUS FIX FOR THAT BUCKET IS UNPROVEN, AND THE ATTEMPT TO PROVE IT
MISFIRED. "Take the leading pair" looked testable: find an (n,m) in the prose
fields next to a production marker and see whether it equals the leading pair.
That returned 10 disagreements against 6 agreements -- which looked like a
refutation and was not. Every disagreement was the regex's fault: the prose
reads "...used for the variational calculations AND (6,7) for [something else]",
and a 90-character window after the marker word reaches past the space the
marker describes to the next one. The hypothesis is therefore UNTESTED, not
refuted. It also cannot be settled this way at scale: 118 of the 143 packed
rows carry no production marker in their prose at all, so even a correct regex
would decide about 25 of them.

Run with --apply to fix the AUX bucket only -- and only where BOTH fields of a
row are recoverable, since a row whose nel is structured and whose norb is still
prose is more misleading than one where both are prose. That converted 23 cells
across 14 rows on 2026-10-11; the 7 cells it skipped for a prose partner are in
the count above.
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

csv.field_size_limit(10 ** 9)
P = str(config.LITERATURE_CSV)
F = ("active_space_nel", "active_space_norb")

LEAD = re.compile(r"^(\d+)\s*(?:[;,(]|\s)")
ONLY = re.compile(r"^\d+$")
SERIES = re.compile(r"^\d+\s*(?:,\s*\d+\s*)*(?:,?\s*(?:and|or|to|through|[-–])\s*)\d+\s*$")
# the trailing numbers are explicitly NOT the production space
AUX = re.compile(r"\b(test|tests|tested|check|checks|validation|validate|"
                 r"probe|probes|also|additional|additionally|benchmark|"
                 r"trial|verification|sensitivity|exploratory|variant|"
                 r"variants|comparison|convergence)\b", re.I)
# two candidate spaces with nothing saying which was used
RIVAL = re.compile(r"\b(minimal|minimum|smaller|small|larger|large|extended|"
                   r"enlarged|expanded|reduced|geometry|optimi[sz]ation|"
                   r"hessian|frequenc|spectra|spectrum|dynamics)\b", re.I)
# the qualifier names compounds, not a purpose
SPLIT = re.compile(r"\bfor\s+(?:[A-Z][a-z]?\d|[A-Z][a-z]?[A-Z]|[A-Z][a-z]+\d|"
                   r"the\s+[a-z]+\s+(?:complex|compound|cation|anion|dimer))")
# A mining-era CONVENTION rather than prose: two or three whole spaces packed
# into one cell, semicolon-separated, positionally paired with the other field
# -- "14; 8" in nel beside "10; 7" in norb is CAS(14,10) and CAS(8,7). Nothing
# in the cell says which the paper computes with, and the schema has one slot.
PACKED = re.compile(r"^\d+(?:\s*,\s*\d+)*(?:\s*;\s*\d+(?:\s*,\s*\d+)*)+\s*$")
# the qualifier names an electronic state or a reaction branch, so the row is
# standing for more than one calculation target
BYSTATE = re.compile(r"\bfor\s+(?:the\s+)?[A-Za-z]?\d?[\'\u2032]*\s*"
                     r"\d?(?:Sigma|Pi|Delta|Phi|[A-Z])[_\^]?[gu]?[+-]?\b")
# the qualifier names a job the number belongs to
BYPURPOSE = re.compile(r"\bfor\s+(?:the\s+)?(?:default|vertical|stability|"
                       r"orbital|geometry|single-point|spectra|dynamics|"
                       r"excitation|transition|surfaces?|branch)", re.I)


def bucket(v):
    v = v.strip()
    if ONLY.match(v):
        return "integer"
    if not re.search(r"\d", v):
        return "no-number"
    if SPLIT.search(v):
        return "SPLIT needs per-compound rows"
    if SERIES.match(v):
        return "RIVAL a bare series"
    if PACKED.match(v):
        return "PACKED N unlabelled spaces, semicolon-separated"
    if BYSTATE.search(v):
        return "SPLIT a space per electronic state"
    m = LEAD.match(v)
    if not m:
        return "RIVAL number not leading"
    rest = v[m.end(1):]
    if BYPURPOSE.search(rest):
        return "RIVAL a space per purpose"
    if RIVAL.search(rest):
        return "RIVAL two spaces, no production marker"
    if AUX.search(rest):
        return "AUX leading number is production"
    return "RIVAL unclassified"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show", help="print cells in this bucket")
    args = ap.parse_args(argv)

    with open(P, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)
    assert fields == config.LITERATURE_COLUMNS

    cells = [(r, f, r[f].strip()) for r in rows for f in F
             if r[f].strip() and not ONLY.match(r[f].strip())]
    tally = Counter()
    byrow = {}
    for r, f, v in cells:
        b = bucket(v)
        tally[b] += 1
        byrow.setdefault(b, set()).add(r["entry_id"])
        if args.show and b.startswith(args.show):
            print("  %-16s %-5s %r" % (r["entry_id"], f[13:], v[:88]))

    print("\n%d cell(s) / %d row(s) are not an integer" %
          (len(cells), len({r["entry_id"] for r, _, _ in cells})))
    for b, n in tally.most_common():
        print("  %-42s %4d cells  %4d rows" % (b, n, len(byrow[b])))

    if not args.apply:
        return 0

    # Only the AUX bucket, and only when BOTH fields of the row agree on it or
    # the other field is already an integer -- a row whose nel is recoverable
    # and whose norb is not would end up half-structured and misleading.
    fixed = Counter()
    touched = []
    for r in rows:
        want = {}
        ok = True
        for f in F:
            v = r[f].strip()
            if ONLY.match(v) or not v:
                continue
            if bucket(v) == "AUX leading number is production":
                want[f] = (LEAD.match(v).group(1), v)
            else:
                ok = False
        if not ok or not want:
            continue
        say = []
        for f, (num, orig) in want.items():
            r[f] = num
            say.append("%s was %r" % (f[13:], orig))
            fixed[f] += 1
        extra = ("The paper reports more than one active space for this "
                 "system and the field held all of them: %s. The structured "
                 "fields now carry the production space -- the leading number, "
                 "which the cell's own wording marked as the one used, the "
                 "others being described there as a test, check or variant. "
                 "What the cell said is preserved in full." % "; ".join(say))
        r["active_space_protocol"] = (r["active_space_protocol"].rstrip()
                                      + (" " if r["active_space_protocol"].strip() else "")
                                      + extra)
        r["notes"] = r["notes"].rstrip() + (
          " ACTIVE SPACE CONVERTED TO INTEGERS on 2026-10-11: %s. A field that "
          "is supposed to be an integer cannot be filtered or sorted on while "
          "it holds prose, and these cells said which number the calculation "
          "used. Cells offering two spaces with no production marker, or "
          "naming a different space per compound, were deliberately left alone."
          % "; ".join(say))
        touched.append(r["entry_id"])

    print("\nconverted %d cell(s) across %d row(s): %s"
          % (sum(fixed.values()), len(touched), dict(fixed)))
    tmp = P + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, P)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
