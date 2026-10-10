#!/usr/bin/env python3
"""Score aimdb against the Y/N/\\ extraction rubric of Shi, Rampal et al.

    "Comparison of LLMs in extracting synthesis conditions and generating Q&A
    datasets for metal-organic frameworks", Digital Discovery 2025, 4, 2676.
    DOI 10.1039/d5dd00081e

Their framework judges each extracted product on three criteria and marks it
`Y` (met), `N` (extracted but did not meet) or `\\` (never extracted), then
reports the proportions plus a **net-Y-ratio** of Y/(Y+N) — accuracy among what
was actually extracted, independent of coverage. Reported on 115 products from
50 DOIs, human-scored:

    criterion                 GPT-4 Turbo  Claude 3 Opus  Gemini 1.5 Pro
    completeness                    67.8%          83.5%           72.2%
    correctness                     83.5%          86.1%           95.7%
    characterization-free           80.9%          84.4%           95.7%
    net-Y-ratio                        --           >95%            >96%

This script transplants that rubric onto aimdb, where the task is harder (a
multireference active space, not a synthesis recipe) and the sample is larger
(12.5k rows, thousands of papers). The three criteria carry over as:

  * **completeness** — are the core fields filled *where the paper states
    them*? CLAUDE.md's second-read queue defines the core five:
    `active_space_nel`, `active_space_norb`,
    `active_space_orbital_description`, `basis_set`, `software`. The
    qualifier matters and is the hard part: CLAUDE.md is explicit that "a gap
    is only worth filling if the paper states the value", so an empty cell is
    often the correct answer. A row is only marked `N` when a field is empty
    AND the source text demonstrably contains it — which makes this the one
    check here that measures RECALL rather than precision.
  * **correctness** — is every value faithful to the source? Scored from the
    source-free invariants plus the numeral grounding in `check_grounding.py`.
    This is an automated proxy for what the paper's authors did by hand, so it
    detects a narrower class of error; the hand-scored sample of 25 rows
    (2026-10-09) remains the only human measurement.
  * **obedience** — their "characterization-free compliance" measured whether
    the model obeyed an explicit instruction in the prompt. aimdb's prompt is
    CLAUDE.md, so the analogue is adherence to its written extraction rules:
    don't narrate the extraction in `notes`, don't restate a structured column
    in prose, write `d_electron_count` with its shell, keep prose out of the
    numeric columns, and so on. Every rule scored here is one CLAUDE.md states
    in those terms.

`mining_model` makes their model comparison reproducible: rows carry the model
that extracted them, so the same table can be cut by model.

Usage, from the repository root:
    code/.venv/bin/python benchmark/extraction_rubric.py
    code/.venv/bin/python benchmark/extraction_rubric.py --by-model
    code/.venv/bin/python benchmark/extraction_rubric.py --explain obedience
    code/.venv/bin/python benchmark/extraction_rubric.py --report out.csv
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_grounding import (DB, TEXT_DIR, load_text,  # noqa: E402
                             triage, check_rows)

CORE_FIELDS = ("active_space_nel", "active_space_norb",
               "active_space_orbital_description", "basis_set", "software")

# Detecting whether a paper STATES a field the row left empty is the one place
# this script needs outside knowledge, and two cheaper designs were tried and
# discarded on 2026-10-09. Harvesting tokens from the corpus's own `software`
# column yields 587 "names" including `active`, `analysis`, `article` and
# `based`, so almost any paper appears to state a code. Scoring each token by
# how concentrated it is in `software` versus the chemistry prose columns is
# better but still keeps `visualization`, `programs`, `revisions` and `python`:
# those are specific to the column yet ordinary words in a paper. The reference
# corpus was wrong in both cases, so the list below is curated instead, which
# trades coverage for a precision that can be measured (see --validate).
#
# Names that are also ordinary words are matched case-sensitively or with a
# required companion cue, because "Gaussian basis functions", "block-diagonal"
# and "the Dalton" would otherwise each count as a code.
CODES_PLAIN = (
    # distinctive enough that a case-insensitive search is safe
    "molcas", "openmolcas", "molpro", "gamess", "turbomole", "nwchem",
    "pyscf", "psi4", "bagel", "columbus", "cfour", "terachem", "veloxchem",
    "xmvb", "gronor", "polyrate", "newton-x", "q-chem", "qchem", "multiwfn",
    "aimall", "molden", "chemshell", "cp2k", "quantum espresso", "openmopac",
    "monstergauss", "sweden", "dalton2", "orca",
)
CODES_CASED = (
    # Also ordinary words, method names or surnames, so these require the
    # capitalisation the code itself uses, or a version number. Validation on
    # 2026-10-09 caught "dirac" matching "Dirac-Fock calculations" and "ams"
    # matching "Ames Cray Y-MP"; both now need their all-caps spelling.
    r"Gaussian\s?(?:0[0-9]|1[0-9]|9[0-9])\b", r"\bG0?9\b", r"\bG16\b",
    r"\bBLOCK\b", r"\bBlock2\b", r"\bNECI\b", r"\bDIRAC\b", r"\bAMS\b",
    r"\bADF\b", r"\bACES\s?(?:II|III)?\b", r"\bMESA\b", r"\bARGOS\b",
    r"\bHONDO\b", r"\bReSpect\b", r"\bDice\b", r"\bFirefly\b", r"\bVASP\b",
    r"\bDALTON\b", r"\bMRCC\b", r"\bSHARC\b",
    r"\bCRYSTAL\s?(?:0[0-9]|1[0-9]|9[0-9])\b",
)
# Basis-set names are far safer: they carry digits, hyphens or a distinctive
# stem, so a search rarely collides with running prose. Bare "DZ", "DZP",
# "MIDI" and "SDD" are deliberately absent -- two or three letters match inside
# other words too readily, and losing them costs little, since a paper using a
# double-zeta basis almost always names a fuller form somewhere.
BASIS_PATTERNS = (
    r"\b(?:aug-)?cc-pV[DTQ5]Z\b", r"\bcc-pwCV[DTQ]Z\b", r"\bcc-pCV[DTQ]Z\b",
    r"\bANO-(?:RCC|S|L|DK3)\b", r"\bdef2-[SQT]Z?VPP?\b",
    r"\b6-31\+{0,2}G\b", r"\b6-311\+{0,2}G\b", r"\bSTO-3G\b", r"\bLANL2DZ\b",
    r"\b[TQ]ZVPP?\b", r"\bdyall\.\w+", r"\bSapporo\b", r"\bWachters\b",
    r"\bcc-pVTZ-DK\b", r"\bx2c-[A-Za-z]+VPP?all\b", r"\bjun-cc-pV[DTQ]Z\b",
    r"\bpc-[0-4]\b", r"\bSARC2?-[A-Z]{3}\b",
)


def states_software(text):
    """Does the paper name a quantum-chemistry code anywhere?"""
    low = text.lower()
    if any(c in low for c in CODES_PLAIN):
        return True
    return any(re.search(pat, text) for pat in CODES_CASED)


def states_basis(text):
    """Does the paper name a basis set anywhere?"""
    return any(re.search(pat, text, re.I) for pat in BASIS_PATTERNS)


def any_pair(text):
    """Does the text state ANY (nel,norb)-shaped active space at all?"""
    return bool(re.search(r"\(\s*\d{1,3}\s*[,/]\s*\d{1,3}\s*\)|"
                          r"\d{1,3}\s+electrons?\s+in\s+(?:the\s+)?\d{1,3}\s+"
                          r"(?:active\s+)?orbitals?", text, re.I))


NARRATION = re.compile(
    r"\b(?:gpt|claude|gemini|llm|o1|o3)\b[^.;|]{0,80}\b"
    r"(?:read|reviewed|examined|analy[sz]ed|extracted|inspected)\b"
    r"|comprehensively read|full text was read|all \d+ pages", re.I)
TAG_PREFIX = re.compile(r"^\s*\[\s*(?:CAS|RAS|SA-|\()", re.I)
SHELLED = re.compile(r"^[3-7][dfsp]\d{1,2}$")
INT_LIST = re.compile(r"^\d+(?:\s*;\s*\d+)*$")


def completeness(row, text):
    """Y / N / \\ for one row, plus the fields judged missed.

    `N` requires evidence in the source that the empty field was stated there,
    so a correct empty cell never counts against the extractor. Without local
    text nothing can be judged and the row is `\\`.
    """
    if text is None:
        return "\\", []
    missed = []
    for f in CORE_FIELDS:
        if row[f].strip():
            continue
        if f == "software" and states_software(text):
            missed.append("software")
        elif f == "basis_set" and states_basis(text):
            missed.append("basis_set")
        elif f in ("active_space_nel", "active_space_norb") and any_pair(text):
            missed.append(f)
        # active_space_orbital_description is prose; its presence in a paper
        # cannot be detected by matching, so an empty one is never scored N.
    return ("N" if missed else "Y"), missed


def invariants(row):
    """CLAUDE.md-independent physical checks on the active space."""
    bad = []
    nel, norb = row["active_space_nel"].strip(), row["active_space_norb"].strip()
    if INT_LIST.match(nel) and INT_LIST.match(norb):
        ns = [int(x) for x in nel.split(";")]
        ms = [int(x) for x in norb.split(";")]
        if len(ns) == len(ms):
            for n, m in zip(ns, ms):
                if n > 2 * m:
                    bad.append("nel %d exceeds capacity 2*%d" % (n, m))
        mult = row["ground_state_mult"].strip()
        if mult.isdigit() and len(ns) == 1:
            # Inactive electrons are all paired, so the unpaired count M-1
            # must share parity with the active electron count.
            if (ns[0] - (int(mult) - 1)) % 2:
                bad.append("nel %d parity conflicts with multiplicity %s"
                           % (ns[0], mult))
    return bad


def obedience(row):
    """Violations of the extraction rules CLAUDE.md states explicitly."""
    bad = []
    for f in ("active_space_nel", "active_space_norb"):
        v = row[f].strip()
        if v and not INT_LIST.match(v):
            bad.append("prose in numeric column %s" % f)
    if NARRATION.search(row["notes"]):
        bad.append("notes narrates the extraction")
    if row["Other"].strip() and \
            row["Other"].strip() == row["electronic_structure_description"].strip():
        bad.append("Other duplicates electronic_structure_description")
    d = row["d_electron_count"].strip()
    if d and not SHELLED.match(d):
        bad.append("d_electron_count %r lacks its shell" % d)
    el = row["element"].strip()
    if el:
        parts = el.split(" ")
        if parts != sorted(parts) or any(not re.fullmatch(r"[A-Z][a-z]?", p)
                                         for p in parts):
            bad.append("element not alphabetical space-separated symbols")
    for f in ("soc_included", "ss_included"):
        if row[f].strip() not in ("", "yes"):
            bad.append("%s is %r, not yes/empty" % (f, row[f].strip()))
    if row["metal_center"].strip().lower() == "none":
        bad.append("metal_center uses the retired 'none' marker")
    if row["system_class"].strip() and row["system_class"].strip() not in (
            "atom", "molecule", "cluster-model", "solid-state"):
        bad.append("system_class %r invalid" % row["system_class"].strip())
    for f in ("Other", "notes", "electronic_structure_description",
              "active_space_protocol"):
        if TAG_PREFIX.match(row[f]):
            bad.append("%s opens with the bracketed identifier tag" % f)
            break
    name = row["compound_name"].strip()
    if name and row["Other"].count(name) > 1:
        bad.append("compound_name restated in Other")
    return bad


def score(rows, cache, ground):
    """One record per row: the three criteria plus their reasons."""
    out = []
    for row in rows:
        key = row["entry_id"].rsplit("-", 1)[0]
        loaded = load_text(key, cache)
        text = loaded[0] if loaded else None
        comp, missed = completeness(row, text)

        inv = invariants(row)
        g = ground.get(row["entry_id"])
        if inv:
            corr, why = "N", inv
        elif g is None:
            # No local text, or no decimal to ground: invariants are all the
            # evidence there is, and they passed.
            corr, why = ("\\" if text is None else "Y"), []
        elif g["triage"].startswith("review"):
            corr, why = "N", ["ungrounded values: " + g["missing"][:120]]
        elif g["triage"].startswith("unverifiable"):
            corr, why = "\\", [g["triage"]]
        else:
            corr, why = "Y", []

        obd = obedience(row)
        out.append({
            "entry_id": row["entry_id"],
            "mining_model": row["mining_model"],
            "completeness": comp,
            "completeness_missed": "; ".join(missed),
            "correctness": corr,
            "correctness_why": "; ".join(why)[:200],
            "obedience": "N" if obd else "Y",
            "obedience_why": "; ".join(obd)[:200],
        })
    return out


def validate(records, field, n, seed):
    """Print flagged rows with the matching evidence, for hand scoring.

    Completeness is the one criterion whose `N` depends on outside knowledge --
    a curated list of code and basis names -- so its precision is a measured
    quantity, not an assumption. Read the context line and decide whether the
    paper really states the field the row left empty.

    Measured this way on 2026-10-09: basis_set 6/6 correct; software 7/8
    before the name lists were tightened (`dirac` matched "Dirac-Fock",
    `ams` matched "Ames Cray"), 12/12 after, with one of the twelve resting on
    a reference-list citation rather than a methods-section sentence.
    """
    import random
    flagged = [r for r in records if field in r["completeness_missed"]]
    if not flagged:
        print("no rows flagged for %s" % field)
        return
    print("\n%d rows flagged for a missing %s; showing %d at random (seed %d)"
          % (len(flagged), field, min(n, len(flagged)), seed))
    print("score each by eye: does the paper state it, or is the match a "
          "collision?\n")
    for r in random.Random(seed).sample(flagged, min(n, len(flagged))):
        key = r["entry_id"].rsplit("-", 1)[0]
        path = TEXT_DIR / ("%s.txt" % key)
        text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8",
                                                  errors="ignore"))
        hit = None
        if field == "software":
            for c in CODES_PLAIN:
                i = text.lower().find(c)
                if i >= 0:
                    hit = (c, i, i + len(c))
                    break
            if hit is None:
                for pat in CODES_CASED:
                    m = re.search(pat, text)
                    if m:
                        hit = (m.group(0), m.start(), m.end())
                        break
        else:
            for pat in BASIS_PATTERNS:
                m = re.search(pat, text, re.I)
                if m:
                    hit = (m.group(0), m.start(), m.end())
                    break
        if hit:
            name, a, b = hit
            print("  %-16s [%s]" % (r["entry_id"], name))
            print("      ...%s..." % text[max(0, a - 90):b + 90])
        else:
            print("  %-16s [no evidence found - detector disagrees with "
                  "itself]" % r["entry_id"])


def table(records, label, warn=True):
    """Print Y / N / \\ proportions and net-Y-ratio, their Fig. 1 layout.

    `n` is every row in the cut; `scored` is Y+N, the rows the criterion could
    actually judge. The two diverge sharply here -- only 48% of rows still have
    their source text -- and net-Y-ratio is over `scored` alone, so a cut with
    few scored rows produces a confident-looking ratio from almost nothing.
    """
    n = len(records)
    print("\n%s  (n = %d rows)" % (label, n))
    print("  %-14s %7s %7s %7s %8s  %s"
          % ("criterion", "Y", "N", "\\", "scored", "net-Y-ratio"))
    for crit in ("completeness", "correctness", "obedience"):
        c = Counter(r[crit] for r in records)
        y, no, na = c.get("Y", 0), c.get("N", 0), c.get("\\", 0)
        scored = y + no
        net = ("%6.1f%%" % (100 * y / scored)) if scored else "     --"
        flag = ""
        if warn and scored and scored < 0.2 * n:
            flag = "  <- only %d rows scored; not comparable" % scored
        elif warn and not scored:
            flag = "  <- nothing scored"
        print("  %-14s %6.1f%% %6.1f%% %6.1f%% %8d  %s%s"
              % (crit, 100 * y / n, 100 * no / n, 100 * na / n, scored,
                 net, flag))


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--by-model", action="store_true",
                   help="cut the table by mining_model, as their Fig. 1 does "
                        "by LLM")
    p.add_argument("--explain", choices=("completeness", "correctness",
                                         "obedience"),
                   help="list the most common reasons for an N")
    p.add_argument("--min-rows", type=int, default=50,
                   help="smallest model cohort to report separately")
    p.add_argument("--validate", choices=("software", "basis_set"),
                   help="print completeness flags with their source evidence, "
                        "for hand scoring of the detector's precision")
    p.add_argument("--validate-n", type=int, default=12)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--report", type=Path, help="write per-row scores to CSV")
    args = p.parse_args()

    csv.field_size_limit(10 ** 9)
    with open(DB, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cache = {}
    gres = list(check_rows(rows, cache=cache))
    triage(gres, 4, 0.4)
    ground = {r["entry_id"]: r for r in gres}

    records = score(rows, cache, ground)
    with_text = sum(1 for r in records if r["completeness"] != "\\")
    print("Rubric of Shi, Rampal et al., Digital Discovery 2025, 4, 2676 "
          "(DOI 10.1039/d5dd00081e)")
    print("applied to database/aimdb.csv: %d rows, %d with local source text "
          "(%.0f%%)" % (len(rows), with_text, 100 * with_text / len(rows)))
    table(records, "ALL ROWS")

    if args.by_model:
        bym = defaultdict(list)
        for r in records:
            bym[r["mining_model"] or "(unstamped)"].append(r)
        print("\nNOTE: completeness and correctness need the paper's text, and"
              " it does not survive\nevenly across models -- share of each "
              "cohort's rows that can be scored at all:")
        for model, rs in sorted(bym.items(), key=lambda kv: -len(kv[1])):
            if len(rs) < args.min_rows:
                continue
            judged = sum(1 for r in rs if r["completeness"] != "\\")
            print("    %-22s %5.1f%%  (%d of %d rows)"
                  % (model, 100 * judged / len(rs), judged, len(rs)))
        print("Where that share is low the cut reflects which papers still "
              "have a text file,\nnot how well the model read them, and the "
              "scored rows are a biased subsample.\nObedience needs no source "
              "and is the one criterion comparable across models.")
        for model, rs in sorted(bym.items(), key=lambda kv: -len(kv[1])):
            if len(rs) >= args.min_rows:
                table(rs, "model: %s" % model)

    if args.validate:
        validate(records, args.validate, args.validate_n, args.seed)

    if args.explain:
        col = args.explain + ("_missed" if args.explain == "completeness"
                              else "_why")
        c = Counter()
        for r in records:
            if r[args.explain] == "N":
                for part in r[col].split("; "):
                    c[re.sub(r"\d+", "N", part)[:70]] += 1
        print("\nmost common reasons for N on %s:" % args.explain)
        for reason, n in c.most_common(15):
            print("   %5d  %s" % (n, reason))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0]))
            w.writeheader()
            w.writerows(records)
        print("\nwrote %s" % args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
