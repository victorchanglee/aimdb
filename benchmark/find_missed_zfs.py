#!/usr/bin/env python3
"""Find papers whose source text states a zero-field splitting the rows do not.

Two gaps, scored separately because they need different work:

  **unparsed** -- the row's prose already discusses ZFS but never states D, so
    `tools_zfs_columns.py` had nothing to lift into the columns. The number may
    well be in the paper. Fixing one means re-reading a few lines of a text
    that is already on disk.
  **unmined** -- the row's prose does not mention ZFS at all, yet the paper
    computes it. The value was missed when the paper was first read, and
    fixing it means a genuine second read.

The detector is case-sensitive on the symbol D and carries the exclusions that
earlier passes in this project learned the hard way, because every one of them
produced a confident wrong answer first:

  * lowercase `d` is a shell label and `De` is a dissociation energy. An
    `re.I` pattern over `[DE]\\s*=\\s*\\d+` matched `omega-e=140 cm-1` and
    `De=3.02 eV` and inflated a ZFS count from 210 to 252.
  * `D` is also the DMRG bond dimension, the Debye, and a pseudo-Jahn-Teller
    energy gap in eV. All three have appeared as spurious ZFS values.
  * `D` in gauss cannot be converted without g, so a gauss value is not
    evidence of a ZFS in cm-1.
  * a paper that merely CITES someone else's ZFS has not computed one, so a
    computational marker must appear near the value.

Tiers, and what each is actually worth -- measured, not assumed, by
--calibrate against the papers that DO carry a ZFS column value:

  `ZFS-phrase` a ZFS phrase near a computational marker, no parseable D.
              **This is the usable screen**: 94% of known-ZFS papers reach it.
  `D-value`   additionally a D = <number> <ZFS unit>. Reads like the strong
              tier and is not: it fires on only 3% of known-ZFS papers,
              because D values live in tables and tables are what a PDF text
              layer loses. A hit here is good evidence; the absence of one
              means almost nothing.
  `mention`   a ZFS phrase with no computational marker nearby: probably
              background or a citation, listed for completeness.

Hand-scoring 10 ZFS-phrase candidates on 2026-10-10 gave about 6 probable true
positives, 2 clear false positives and 2 borderline. Treat the tier as a
worklist, never as a count.

Two exclusions come from those false positives. A complex whose ground state
is a singlet cannot have a zero-field splitting, however much its paper
discusses magnetic anisotropy; and a match inside the reference list is not a
result. The borderline pair were Kramers lanthanides, where the splitting is
reported as crystal-field Kramers-doublet gaps rather than a spin-Hamiltonian
D and E -- those are flagged, not dropped, because whether they belong in
these columns is a chemist's call.

Usage, from the repository root:
    code/.venv/bin/python benchmark/find_missed_zfs.py
    code/.venv/bin/python benchmark/find_missed_zfs.py --tier D-value --show 40
    code/.venv/bin/python benchmark/find_missed_zfs.py --evidence W2056986513
    code/.venv/bin/python benchmark/find_missed_zfs.py --calibrate
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database" / "aimdb.csv"
TEXT_DIR = ROOT / "text"
DEFAULT_REPORT = ROOT / "logs" / "missed_zfs.csv"

ZFS_COLUMNS = ("zfs_D_calc", "zfs_ED_calc", "zfs_D_exp", "zfs_ED_exp")
PROSE = ("electronic_structure_description", "Other", "notes",
         "active_space_protocol")

# A ZFS is being discussed at all.
ZFS_PHRASE = re.compile(
    r"zero[- ]field splitting|zero[- ]field split|\bZFS\b|\bzfs\b|"
    r"axial anisotropy|rhombicity|magnetic anisotropy parameter", re.I)

# The paper's own calculation, not a quoted literature value.
CALC = re.compile(
    r"calculat|comput|\bCASSCF\b|\bNEVPT|\bCASPT|\bRASSCF\b|ab initio|"
    r"\bSORCI\b|\bMRCI\b|\bQDPT\b|\bMCSCF\b|\bDMRG\b|effective Hamiltonian|"
    r"our (?:value|result)|predict", re.I)

NUM = r"[-+]?\d+(?:\.\d+)?"
# Case-sensitive D. `absD` is what the pipe-normalisation leaves behind.
D_VALUE = re.compile(
    r"\b(?:absD|D)\b\s*(?:value|parameter)?s?\s*(?:=|of|is|:)\s*(%s)" % NUM)
# Units a ZFS is actually reported in.
ZFS_UNIT = re.compile(r"\s*(?:cm\s*\^?-?1|cm-1|reciprocal centimet|"
                      r"per centimetre|GHz|MHz|THz|\bK\b)", re.I)
# Units that rule the value out, and contexts that are not a ZFS at all.
BAD_UNIT = re.compile(r"\s*(?:eV|meV|kcal|kJ|hartree|a\.u\.|angstrom|Å|"
                      r"\bnm\b|\bG\b|gauss|\bmT\b|\bT\b|tesla|Debye|"
                      r"\bD\b|degree|%)", re.I)
BOND_DIM = re.compile(r"bond[- ]dimension[^.;|]{0,14}$", re.I)
ABSBARS = ((re.compile(r"\|\s*E\s*/\s*D\s*\|"), "E/D"),
           (re.compile(r"\|\s*D\s*\|"), "absD"),
           (re.compile(r"\|\s*E\s*\|"), "absE"))

WINDOW = 400          # characters either side, for "near"

# A singlet ground state has no zero-field splitting to compute, whatever the
# paper says about magnetic anisotropy elsewhere.
SINGLET = re.compile(r"\bS\s*=\s*0\b|diamagnetic ground state|"
                     r"singlet ground state", re.I)
# Kramers lanthanides report crystal-field Kramers-doublet gaps, not a
# spin-Hamiltonian D and E; flagged rather than dropped.
KRAMERS = re.compile(r"\bKramers doublet|\bm_?J\s*=|\bKD\b", re.I)
# A hit inside the bibliography is not a result.
REFS = re.compile(r"\n\s*(?:References|Bibliography|REFERENCES)\s*\n", re.I)


def unbar(text):
    for pat, repl in ABSBARS:
        text = pat.sub(repl, text)
    return text


def evidence(text):
    """Return (tier, quote) for the strongest ZFS evidence in `text`.

    The bibliography is cut off first: a ZFS phrase or a D value appearing in
    a reference title is not a result of the paper.
    """
    raw = text
    cut = REFS.search(text)
    if cut and cut.start() > len(text) * 0.4:
        text = text[:cut.start()]
    text = unbar(re.sub(r"[ \t]+", " ", text))
    phrases = list(ZFS_PHRASE.finditer(text))
    if not phrases:
        return "", ""
    best = ("mention", text[max(0, phrases[0].start() - 90):
                            phrases[0].end() + 110].strip())
    for m in phrases:
        lo, hi = max(0, m.start() - WINDOW), m.end() + WINDOW
        near = text[lo:hi]
        if not CALC.search(near):
            continue
        if best[0] == "mention":
            best = ("ZFS-phrase", near[:220].strip())
        for d in D_VALUE.finditer(near):
            tail = near[d.end():d.end() + 30]
            if BAD_UNIT.match(tail) or not ZFS_UNIT.match(tail):
                continue
            if BOND_DIM.search(near[max(0, d.start() - 48):d.start()]):
                continue
            quote = near[max(0, d.start() - 110):d.end() + 60].strip()
            return "D-value", quote
    return best


def load():
    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_key = defaultdict(list)
    for r in rows:
        by_key[r["entry_id"].rsplit("-", 1)[0]].append(r)
    return by_key


def classify(rs):
    """How the rows of one paper already treat ZFS."""
    if any(r[c].strip() for r in rs for c in ZFS_COLUMNS):
        return "has-columns"
    if any(ZFS_PHRASE.search(r[c]) for r in rs for c in PROSE):
        return "unparsed"        # prose discusses it, no number reached a column
    return "unmined"             # prose does not mention it at all


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", choices=("D-value", "ZFS-phrase", "mention"),
                   help="only report this tier")
    p.add_argument("--state", choices=("unparsed", "unmined"),
                   help="only report this row state")
    p.add_argument("--show", type=int, default=20)
    p.add_argument("--evidence", metavar="KEY",
                   help="print the evidence found for one paper key")
    p.add_argument("--calibrate", action="store_true",
                   help="measure each tier's recall against the papers that "
                        "already carry a ZFS column value")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = p.parse_args()

    by_key = load()

    if args.calibrate:
        from collections import Counter
        pos = [k for k, rs in by_key.items()
               if any(r[c].strip() for r in rs for c in ZFS_COLUMNS)
               and (TEXT_DIR / ("%s.txt" % k)).is_file()]
        c = Counter()
        for k in pos:
            tier, _ = evidence((TEXT_DIR / ("%s.txt" % k)).read_text(
                encoding="utf-8", errors="ignore"))
            c[tier or "no-evidence"] += 1
        print("recall against %d papers that DO carry a ZFS column value:"
              % len(pos))
        for tier in ("D-value", "ZFS-phrase", "mention", "no-evidence"):
            n = c.get(tier, 0)
            print("   %-12s %3d  (%4.0f%%)" % (tier, n, 100 * n / len(pos)))
        strong = c.get("D-value", 0)
        usable = strong + c.get("ZFS-phrase", 0)
        print("\nD-value alone sees %.0f%% of known cases -- a hit is good "
              "evidence, an\nabsence means almost nothing, because D lives in "
              "tables and tables are what\na PDF text layer loses. "
              "the two tiers together\nreach %.0f%% and are the screen to use."
              % (100 * strong / len(pos), 100 * usable / len(pos)))
        return 0

    if args.evidence:
        path = TEXT_DIR / ("%s.txt" % args.evidence)
        if not path.is_file():
            sys.exit("no local text for %s" % args.evidence)
        tier, quote = evidence(path.read_text(encoding="utf-8",
                                              errors="ignore"))
        print("%s: tier=%s\n  %s" % (args.evidence, tier or "none", quote))
        return 0

    found, counts = [], defaultdict(int)
    for key, rs in by_key.items():
        path = TEXT_DIR / ("%s.txt" % key)
        if not path.is_file():
            counts["no-text"] += 1
            continue
        state = classify(rs)
        if state == "has-columns":
            counts["has-columns"] += 1
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        tier, quote = evidence(body)
        # A singlet ground state rules a ZFS out entirely.
        if tier and SINGLET.search(body) and not re.search(
                r"\bS\s*=\s*(?:1|2|3|1/2|3/2|5/2|7/2)\b", body):
            counts["excluded/singlet-ground-state"] += 1
            continue
        counts["%s/%s" % (state, tier or "no-evidence")] += 1
        if tier in ("D-value", "ZFS-phrase"):
            found.append({"key": key, "state": state, "tier": tier,
                          "rows": len(rs),
                          "kramers": "yes" if KRAMERS.search(body) else "",
                          "doi": rs[0]["reference_doi"],
                          "compound": rs[0]["compound_name"][:70],
                          "evidence": quote[:300]})

    print("papers with rows: %d  (%d have no local text and cannot be checked)"
          % (len(by_key), counts["no-text"]))
    print("  already carry a ZFS column value : %d" % counts["has-columns"])
    for k in sorted(counts):
        if "/" in k:
            print("  %-28s %d" % (k, counts[k]))

    order = {"D-value": 0, "ZFS-phrase": 1}
    found.sort(key=lambda f: (order[f["tier"]], f["state"], -f["rows"]))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(found[0]) if found else
                           ["key", "state", "tier", "rows", "doi",
                            "compound", "evidence"])
        w.writeheader()
        w.writerows(found)
    print("\nwrote %s (%d papers)" % (args.report, len(found)))

    sel = [f for f in found
           if (not args.tier or f["tier"] == args.tier)
           and (not args.state or f["state"] == args.state)]
    print("\nshowing %d of %d:" % (min(args.show, len(sel)), len(sel)))
    for f in sel[:args.show]:
        print("\n  %-14s %-11s %-10s %d row(s)  %s"
              % (f["key"], f["tier"], f["state"], f["rows"], f["doi"][:34]))
        print("      %s" % f["evidence"][:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
