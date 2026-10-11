#!/usr/bin/env python3
"""Find papers whose source text states a g tensor the rows do not carry.

The `properties` field is populated from each row's own PROSE, which is a
summary written during mining and is lossy by construction. So a thin g count
is ambiguous: either the papers do not report g tensors, or they do and the
prose never captured them. This separates the two by going back to
`text/<key>.txt`.

Two states, scored separately because they need different work:

  **unparsed** -- the row's prose already talks about a g tensor but states no
    component, so `tools_properties.py` had nothing to lift. Fixing one means
    re-reading a few lines of a text already on disk.
  **unmined** -- the row's prose does not mention g at all, yet the paper
    reports one. The value was missed when the paper was first read, and
    fixing it means a genuine second read.

Tiers, strongest first:

  `g-values`  a component with an explicit value near a computational or EPR
              marker -- "gzz = 19.92", "gx = 2.053, gy = 2.006, gz = 2.360".
              This is the actionable tier.
  `g-phrase`  the paper discusses a g tensor near such a marker but no
              component parses. Usually means the numbers are in a table the
              PDF text layer flattened, which is the same reason the ZFS
              D-value tier fires on only 3% of known-ZFS papers.
  `mention`   a g-tensor phrase with no marker nearby: background, a method
              description, or a citation. Listed for completeness.

THE WORD-BOUNDARY TRAP, which produced a confident wrong answer first. An
unanchored /g[- ]factor/ matches the trailing g of ordinary English:
"influencinG FACTORs", "couplinG VALUEs", "correspondinG VALUE", "controllinG
FACTOR", and "EFG tensor" for /g[- ]tensor/. Without \\b it reported 30% of all
texts as discussing g tensors; with it, 9%. Every pattern here anchors the g.

Other exclusions, each of which is a real collision in this corpus:

  * gerade labels. `t2g`, `eg`, `a1g`, `b1g`, `1Ag`, `sigma_g`, `pi_g` are
    everywhere in a CASSCF paper. All are excluded for free by requiring \\b
    before the g, since the preceding character is a word character in each.
  * `g` as gram, and `g` as the Gaussian program's initial.
  * a g in the reference list is not a result.
  * a g quoted for a different compound, or from someone else's work.

Usage, from the repository root:
    code/.venv/bin/python benchmark/find_missed_g.py
    code/.venv/bin/python benchmark/find_missed_g.py --tier g-values --show 40
    code/.venv/bin/python benchmark/find_missed_g.py --evidence W4399981127
    code/.venv/bin/python benchmark/find_missed_g.py --calibrate
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
from tools.tools_properties import parse                       # noqa: E402

DB = ROOT / "database" / "aimdb.csv"
INDEX = ROOT / "database" / "papers_index.csv"
TEXT_DIR = ROOT / "text"
DEFAULT_REPORT = ROOT / "logs" / "missed_g.csv"

PROSE = ("electronic_structure_description", "Other", "notes",
         "active_space_protocol", "method")

NUM = r"[-+]?\d+(?:\.\d+)?"
# A g component with a value. The leading \b is what keeps t2g, eg, a1g, 1Ag,
# sigma_g and pi_g out: in every one of those the g is preceded by a word
# character, so \bg cannot match. The component label is required -- a bare
# "g = 2.0" is too easily a gram, a gerade label or a fit parameter.
# The numeric labels g1/g2/g3 need (?![A-Za-z0-9]) after them, not just
# (?![A-Za-z]): with a letter-only guard, "g35 = 0.5479162" -- the NUCLEAR g
# of 35Cl in W7160562793 -- reads as g3 = 5, a g value out of thin air.
# A DECIMAL POINT IS REQUIRED when no "=" or ":" separates the label from the
# value, because a flattened table header followed by a row index reads as a
# value otherwise: "KD 1 2 | E gx gy gz | 1 0 0.71 0.73 8.93" yields "gz 1".
# Every real g in this corpus is written with a decimal.
# Two label classes, because they carry different risk.
#
# An AXIS label (z, xx, perp, ...) is unambiguous, so a bare juxtaposition is
# allowed -- "gx 0.011, gy 0.013, gz 6.138" is how plenty of papers write it --
# subject only to the decimal requirement, which keeps a flattened table
# header plus row index ("E gx gy gz | 1 0 0.71 ...") from reading as a value.
#
# A NUMERIC label needs an explicit = or :, because without one it collides
# with the GERADE SUBSCRIPT of a symmetry or orbital label followed by a state
# index. Four classes of that turned up the moment the scan was widened to the
# whole text, all of them real:
#     "A g 1 5.96 48100 208"   the A_g state, index 1, at 5.96 eV
#     "B g 1 2.22 17966 557"   likewise
#     "t g1 0.029"             the t_1g orbital of C60, energy in hartree
#     "3<Delta>g 1 2.76 3.28"  a term symbol with Omega = 1, then a bond length
# A negative lookbehind on the preceding letter cannot separate these, since
# "e" is both the e_g label and the last letter of "the". Requiring the
# separator does, and costs little: every g1/g2/g3 value in the database has
# one in its source clause bar a single paper.
G_VALUE = re.compile(
    r"\bg\s*[_ -]?\s*(?:"
    r"(zz|xx|yy|iso|avg|par|perp|eff|z|x|y|\|\|)(?![A-Za-z0-9])"
    r"\s*(?:[=:]\s*(%s)|\s*([-+]?\d+\.\d+))"
    r"|([123])(?![A-Za-z0-9])\s*[=:]\s*(%s)"
    r")(?![A-Za-z0-9])" % (NUM, NUM))


def _g_value(m):
    """The numeric group of a G_VALUE match, whichever alternative fired."""
    for i in (2, 3, 5):
        if m.group(i) is not None:
            return m.group(i)
    return None
# The paper is talking about a g tensor at all.
G_PHRASE = re.compile(
    r"\bg[-\s]?tensors?\b|\bg[-\s]?factors?\b|\bg[-\s]?values?\b|"
    r"\bg[-\s]?matrix\b|\bg[-\s]?anisotrop\w*|principal\s+\bg\b|"
    r"\bEPR\b|\bESR\b|electron paramagnetic resonance", re.I)
# The paper's own calculation or its own measurement -- either makes the g a
# result rather than background.
MARKER = re.compile(
    r"calculat|comput|\bCASSCF\b|\bNEVPT|\bCASPT|\bRASSCF\b|ab initio|"
    r"\bSORCI\b|\bMRCI\b|\bQDPT\b|\bMCSCF\b|RASSI|SINGLE_?ANISO|\bDFT\b|"
    # The technique itself is a measurement. Without these, "EPR (solid 2 K):
    # g1 = 7.136, g2 = 1.829, g3 = 1.214" had no marker in range and could not
    # reach the g-values tier.
    r"\bEPR\b|\bESR\b|HFEPR|HF-ESR|magnetometr|susceptibilit|"
    r"predict|measured|experiment|fitted|simulat|our (?:value|result)", re.I)

# 2*J*g_J is 20.00 for Dy(III) and Ho(III); nothing above that is a g.
MAX_G = 20.5
WINDOW = 400          # characters either side, for "near"

# A hit inside the bibliography is not a result.
REFS = re.compile(r"\n\s*(?:References|Bibliography|REFERENCES)\s*\n")
# "g" as a mass, and the Gaussian program.
GRAM = re.compile(r"\d\s*g\b\s*(?:of|per|/)|\bg/mol|\bmg\b|\bkg\b", re.I)


def load_rows():
    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_dois():
    if not INDEX.exists():
        return {}
    csv.field_size_limit(10 ** 9)
    with INDEX.open(newline="", encoding="utf-8") as fh:
        return {r.get("key", ""): r.get("doi", "")
                for r in csv.DictReader(fh)}


def row_has_g(rows):
    """Whether any row of this paper already carries a g key."""
    for r in rows:
        for key, _ in parse(r["properties"] or ""):
            if key.startswith("g"):
                return True
    return False


def prose_mentions_g(rows):
    """Whether the rows' prose talks about a g tensor at all.

    This is what separates `unparsed` from `unmined`: prose that discusses g
    but yielded no value is a parsing gap, prose that never mentions it is a
    reading gap.
    """
    for r in rows:
        blob = " ".join(r[c] or "" for c in PROSE)
        if G_PHRASE.search(blob) or G_VALUE.search(blob):
            return True
    return False


def evidence(text):
    """Return (tier, quote) for the strongest g evidence in `text`."""
    cut = REFS.search(text)
    if cut and cut.start() > len(text) * 0.4:
        text = text[:cut.start()]
    text = re.sub(r"[ \t]+", " ", text)

    # A labelled component with a plausible value is the strongest evidence
    # available and needs no phrase to vouch for it, so it is sought across
    # the WHOLE text rather than only inside windows around a "g-tensor"
    # phrase. The phrase logic below is the fallback.
    for v in G_VALUE.finditer(text):
        if GRAM.search(text[max(0, v.start() - 20):v.end() + 12]):
            continue
        raw = _g_value(v)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= abs(val) <= MAX_G:
            continue
        near = text[max(0, v.start() - WINDOW):v.end() + WINDOW]
        if not MARKER.search(near):
            continue
        return "g-values", text[max(0, v.start() - 120):v.end() + 70].strip()

    phrases = list(G_PHRASE.finditer(text))
    if not phrases:
        return "", ""
    best = ("mention", text[max(0, phrases[0].start() - 90):
                            phrases[0].end() + 120].strip())
    for m in phrases:
        lo, hi = max(0, m.start() - WINDOW), m.end() + WINDOW
        near = text[lo:hi]
        if not MARKER.search(near):
            continue
        if best[0] == "mention":
            best = ("g-phrase", near[:220].strip())
        for v in G_VALUE.finditer(near):
            if GRAM.search(near[max(0, v.start() - 20):v.end() + 12]):
                continue
            try:
                val = float(_g_value(v))
            except (TypeError, ValueError):
                continue
            if not 0.0 <= abs(val) <= MAX_G:
                continue
            quote = near[max(0, v.start() - 120):v.end() + 70].strip()
            return "g-values", quote
    return best


def scan():
    rows = load_rows()
    dois = load_dois()
    bypaper = defaultdict(list)
    for r in rows:
        bypaper[r["entry_id"].split("-")[0]].append(r)

    out, no_text, already = [], 0, 0
    for key, rs in sorted(bypaper.items()):
        path = TEXT_DIR / (key + ".txt")
        if not path.exists():
            no_text += 1
            continue
        if row_has_g(rs):
            already += 1
            continue
        tier, quote = evidence(path.read_text(errors="ignore"))
        if not tier:
            continue
        out.append({
            "paper": key,
            "doi": dois.get(key, ""),
            "tier": tier,
            "state": "unparsed" if prose_mentions_g(rs) else "unmined",
            "rows": len(rs),
            "evidence": re.sub(r"\s+", " ", quote)[:300],
        })
    return out, no_text, already, len(bypaper)


def calibrate():
    """Recall per tier, measured on papers whose rows ALREADY carry a g.

    A tier that cannot find g in a paper known to report one will not find it
    in the others either, and the number says how much the absence of a hit is
    worth. This is the check that exposed the ZFS D-value tier as a 3% screen.
    """
    rows = load_rows()
    bypaper = defaultdict(list)
    for r in rows:
        bypaper[r["entry_id"].split("-")[0]].append(r)
    known = [(k, rs) for k, rs in bypaper.items()
             if row_has_g(rs) and (TEXT_DIR / (k + ".txt")).exists()]
    tiers = Counter()
    for k, _ in known:
        tier, _ = evidence((TEXT_DIR / (k + ".txt")).read_text(errors="ignore"))
        tiers[tier or "(nothing)"] += 1
    n = len(known)
    print("calibration against %d papers whose rows already carry a g "
          "and that have local text:" % n)
    for t in ("g-values", "g-phrase", "mention", "(nothing)"):
        if tiers[t]:
            print("   %-10s %3d  (%.0f%%)" % (t, tiers[t], 100 * tiers[t] / n))
    if n:
        print("\nreading: a `g-values` hit is strong evidence; its recall here "
              "is what\nthe absence of one is worth.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", choices=("g-values", "g-phrase", "mention"))
    ap.add_argument("--state", choices=("unparsed", "unmined"))
    ap.add_argument("--show", type=int, default=15)
    ap.add_argument("--evidence", metavar="KEY",
                    help="print the evidence for one paper and exit")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    args = ap.parse_args(argv)

    if args.calibrate:
        return calibrate()

    if args.evidence:
        path = TEXT_DIR / (args.evidence + ".txt")
        if not path.exists():
            print("no local text for %s" % args.evidence)
            return 1
        tier, quote = evidence(path.read_text(errors="ignore"))
        print("%s: %s\n\n%s" % (args.evidence, tier or "(nothing)", quote))
        return 0

    found, no_text, already, total = scan()
    print("%d papers with rows; %d have no local text and cannot be checked; "
          "%d already carry a g" % (total, no_text, already))
    rank = {"g-values": 0, "g-phrase": 1, "mention": 2}
    found.sort(key=lambda d: (rank[d["tier"]], d["state"], -d["rows"]))

    by = Counter((d["tier"], d["state"]) for d in found)
    print("\ncandidates, by tier and state:")
    for tier in ("g-values", "g-phrase", "mention"):
        for state in ("unparsed", "unmined"):
            if by[(tier, state)]:
                print("   %-10s %-9s %4d papers" % (tier, state, by[(tier, state)]))

    sel = [d for d in found
           if (not args.tier or d["tier"] == args.tier)
           and (not args.state or d["state"] == args.state)]
    if sel:
        print("\nshowing %d of %d:" % (min(args.show, len(sel)), len(sel)))
        for d in sel[:args.show]:
            print("\n  %-14s %-9s %-9s %d row(s)  %s"
                  % (d["paper"], d["tier"], d["state"], d["rows"], d["doi"]))
            print("      %s" % d["evidence"][:220])

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["paper", "doi", "tier", "state",
                                           "rows", "evidence"])
        w.writeheader()
        w.writerows(found)
    print("\nwrote %s (%d papers)" % (report, len(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
