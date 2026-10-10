"""Populate the zero-field-splitting columns from the prose already in each row.

Adds four columns (see config.LITERATURE_COLUMNS, SCHEMA_VERSION 1.2):

    zfs_D_calc   axial ZFS parameter D computed in this row's calculation, cm-1
    zfs_ED_calc  its rhombicity E/D, dimensionless
    zfs_D_exp    D the paper quotes from experiment, cm-1
    zfs_ED_exp   the experimental rhombicity

These are not new readings of the papers: they lift values the row's own prose
already states, so the numbers remain grounded in whatever the source said and
`benchmark/check_grounding.py` still covers them. What the columns add is that
a consumer can filter and sort on D without parsing a sentence.

**Computed and experimental are kept apart** because a ZFS paper almost always
reports both, and conflating them would make the database claim an ab initio
result for a measured number. 283 D-occurrences sit in a clause that is clearly
computational, 132 in one that is clearly experimental; the rest are decided by
clause, never by a character window, since a 160-character window around a D
value routinely spans both a computed and a measured statement and 250 of 665
occurrences came out ambiguous that way.

D is reported in cm-1 almost universally here; GHz and K are converted and the
conversion is recorded. E/D is taken as stated when the paper gives it, and
otherwise computed as |E/D| from a stated E and D -- arithmetic on two values
the row already holds, which CLAUDE.md permits.

Two guards, because a bad value is worse than an empty one:
  * E/D is rhombic by definition and cannot exceed 1/3. Anything above 0.3334
    is reported, never stored.
  * A clause offering two different D values for the same category (a range, or
    several methods in one sentence) is left empty and listed, because a filter
    needs one number and picking one would be a guess.

Usage, from code/:
    .venv/bin/python tools/tools_zfs_columns.py --dry-run
    .venv/bin/python tools/tools_zfs_columns.py --sample 25
    .venv/bin/python tools/tools_zfs_columns.py --apply
"""
import argparse
import csv
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from mining_agent import config  # noqa: E402

DB = ROOT / "database" / "aimdb.csv"
PROSE = ("electronic_structure_description", "Other", "notes",
         "active_space_protocol")
NEW_COLUMNS = ("zfs_D_calc", "zfs_ED_calc", "zfs_D_exp", "zfs_ED_exp")

# Clause boundaries. Semicolons and pipes are the row-prose separators used
# throughout aimdb; a full stop followed by a capital ends a sentence. Splitting
# here is what keeps a computed value from inheriting an experimental context.
CLAUSE = re.compile(r"\s*[;|]\s*|(?<=[a-z0-9\)])\.\s+(?=[A-Z])")

CALC = re.compile(
    r"calculat|comput|\bCASSCF\b|\bNEVPT|\bCASPT|\bRASSCF\b|ab initio|"
    r"predict|theoretic|RASSI|SINGLE_ANISO|\bDFT\b|\bMRCI\b|\bDMRG\b|"
    r"second-order-perturbation|\bQDPT\b|our (?:value|result)", re.I)
EXP = re.compile(
    r"experiment|measured|\bEPR\b|\bESR\b|HFEPR|HF-ESR|magnetometr|"
    r"\bINS\b|inelastic neutron|susceptibilit|M(?:o|ö)ssbauer|"
    r"fit(?:ted|ting)?\b|from the fit|observed|reported value|"
    r"far[- ]IR|torque magnetometr|Raman", re.I)
# Distinct measurement techniques. Two or more in one clause means the paper
# reports several experimental values, so none of them is "the" experiment.
TECHNIQUES = (r"\bEPR\b", r"\bESR\b", r"HFEPR|HF-ESR", r"magnetometr",
              r"\bINS\b|inelastic neutron", r"susceptibilit",
              r"M(?:o|ö)ssbauer", r"far[- ]IR", r"\bRaman\b",
              r"neutron diffract")

NUM = r"[-+]?\d+(?:\.\d+)?"
# D = x, |D| = x, D of x, D value of x. Case-sensitive on the symbol: lowercase
# "d" is a shell label and "De" is a dissociation energy, both of which an
# re.I pattern swallowed in an earlier pass and inflated the ZFS count by 20%.
# "(?<!in )" keeps the Debye out: "dipole moments in D: 1A1 0.0" is a unit,
# not a parameter. "(?![A-Za-z])" stops a term symbol being read as a value --
# the 1 of "1A1" is not a number in this sense.
D_PAT = re.compile(
    r"(?<!in )(?:\|\s*D\s*\||\bD\b)\s*(?:value|parameter)?s?\s*"
    r"(?:=|of|is|:)\s*(%s)(?![A-Za-z])" % NUM)
E_PAT = re.compile(r"\bE\b\s*(?:=|of|is|:)\s*(%s)(?![A-Za-z])" % NUM)
ED_PAT = re.compile(
    r"\bE\s*/\s*D\b\s*(?:=|of|is|:)\s*(%s)(?![A-Za-z])" % NUM)
# A second number right after the first means a range or a list.
# A number may carry a parenthesised uncertainty -- 11.76(3) -- which sits
# between the value and whatever separates it from the next one.
# Any short parenthetical may sit between a value and its separator: a
# measurement uncertainty "(3)", or a method label "(CASSCF)".
UNC = r"(?:\s*\([^)]{0,24}\))?"
# En- and em-dashes are used for ranges as often as the ASCII hyphen here.
SEP = r"(?:,|/|-|–|—|to|and|then|against|versus|vs\.?)"
MULTI_D = re.compile(
    r"\bD\b[^.;|]{0,12}(?:=|is|of)\s*%s%s\s*%s\s*%s"
    % (NUM, UNC, SEP, NUM))
# "NEVPT2 improves it to -44.78" carries the value forward to another level of
# theory, so the clause states two computed D values and only the first is in
# "D = x" form. Which one this row reports cannot be decided from the clause.
CONTINUATION = re.compile(
    r"(?:improve|increas|decreas|chang|shift|rais|lower|reduc|correct|refin)"
    r"\w*\s+(?:it\s+|them\s+|this\s+)?to\s*[-+]?\d", re.I)
# A value offered as someone else's result is neither this row's calculation
# nor the paper's own measurement, so it must not land in either column.
# "D" is also the DMRG bond dimension, a basis-size parameter with nothing to
# do with magnetism; it is written exactly like the ZFS parameter.
BOND_DIM = re.compile(r"bond[- ]dimension\s*(?:of|=|:)?\s*$|"
                      r"bond[- ]dimension[^.;|]{0,12}$", re.I)
THIRD_PARTY = re.compile(
    r"literature value|reported (?:in|by) ref|for context|related (?:complex|"
    r"compound|system)|other (?:complex|compound)|previous(?:ly)? (?:report|"
    r"publish)|earlier (?:report|work)|by comparison with", re.I)
# Largest credible molecular ZFS D. Co(II) reaches ~100 cm-1 and lanthanide
# axial parameters a few hundred; 2800 cm-1 is a ligand-field or Racah
# parameter that happens to be written "D".
MAX_D = 1000.0

GHZ_TO_CM = 0.0333564095
MHZ_TO_CM = 3.33564095e-5
THZ_TO_CM = 33.3564095
K_TO_CM = 0.6950348
ED_MAX = 0.3334


# Units a ZFS parameter is never reported in. A "D" carrying one of these is
# a different quantity: an energy gap, a bond length, a dipole moment.
# Field units (G, mT, T) are deliberately here rather than converted: D in
# gauss becomes cm-1 only through g*mu_B for that species, so there is no
# constant factor and a guessed one would be a fabricated number.
BAD_UNIT = re.compile(
    r"\s*(?:eV|meV|kcal|kJ|hartree|a\.u\.|Ry\b|angstrom|Å|\bnm\b|\bpm\b|"
    r"\bppm\b|\bG\b|gauss|\bmT\b|\bT\b|tesla|Debye|\bD\b|degree|"
    r"\bdeg\b|%)", re.I)


def unit_of(clause, pos):
    """Unit for a value at `pos`, read from the text just after it.

    Returns "cm-1"/"GHz"/"K" for a usable unit, "" when none is stated (cm-1
    is then assumed, as it is the convention throughout this corpus), or
    "bad" when the stated unit rules the value out as a ZFS parameter.
    """
    tail = clause[pos:pos + 40]
    if re.match(r"\s*(?:cm\s*\^?-?1|cm-1|reciprocal centimet|per centimetre)",
                tail, re.I):
        return "cm-1"
    if re.match(r"\s*GHz", tail, re.I):
        return "GHz"
    if re.match(r"\s*MHz", tail, re.I):
        return "MHz"
    if re.match(r"\s*THz", tail, re.I):
        return "THz"
    if re.match(r"\s*K\b", tail):
        return "K"
    if BAD_UNIT.match(tail):
        return "bad"
    return ""


def to_cm(value, unit):
    """Value in cm-1, or None when the unit disqualifies it."""
    if unit in ("cm-1", ""):
        return value          # cm-1 is the overwhelming default in this corpus
    if unit == "GHz":
        return value * GHZ_TO_CM
    if unit == "MHz":
        return value * MHZ_TO_CM
    if unit == "THz":
        return value * THZ_TO_CM
    if unit == "K":
        return value * K_TO_CM
    return None               # "bad": not a ZFS parameter at all


def classify(clause):
    """Clause-level verdict, used only for the --sample display."""
    c, e = bool(CALC.search(clause)), bool(EXP.search(clause))
    if c and not e:
        return "calc"
    if e and not c:
        return "exp"
    return "both" if c else ""


def classify_at(clause, pos):
    """Whether the value at `pos` is computational or experimental.

    By the nearest marker BEFORE it, not by the clause as a whole: "CASSCF
    mean-field D_SS=0.053 cm-1 versus experimental D=0.047 cm-1" states one of
    each, and a clause-level verdict discards both. An unmarked value defaults
    to `calc`, since every aimdb row is a calculation and its bare numbers are
    its own unless the text says otherwise -- but only when the clause carries
    no experimental marker at all, so a measured value never inherits it.
    """
    head = clause[:pos]
    last_calc = max((m.end() for m in CALC.finditer(head)), default=-1)
    last_exp = max((m.end() for m in EXP.finditer(head)), default=-1)
    if last_calc < 0 and last_exp < 0:
        return "" if EXP.search(clause) else "calc"
    return "calc" if last_calc > last_exp else "exp"


def extract(row):
    """Return ({column: value}, [notes about what was skipped])."""
    found = {k: [] for k in ("D_calc", "ED_calc", "D_exp", "ED_exp")}
    skipped = []
    for col in PROSE:
        text = row[col]
        if not text:
            continue
        for clause in CLAUSE.split(text):
            if not clause or not re.search(r"\bD\b|\bE\s*/\s*D\b", clause):
                continue
            if THIRD_PARTY.search(clause):
                if D_PAT.search(clause):
                    skipped.append("value belongs to another paper")
                continue
            if MULTI_D.search(clause):
                skipped.append("several D values in one clause")
                continue
            if CONTINUATION.search(clause):
                skipped.append("clause carries D forward to another level of "
                               "theory")
                continue
            # Several techniques in one clause means several experimental
            # values; none of them is the paper's experimental D for this row.
            n_tech = sum(1 for t in TECHNIQUES if re.search(t, clause, re.I))
            # The D inside "E/D" is not a D. Blank each E/D out, keeping the
            # clause the same length so offsets still locate the markers.
            masked = ED_PAT.sub(lambda m: " " * len(m.group(0)), clause)
            # EVERY D in the clause, not just the first: a clause commonly
            # states a computed and a measured value, and taking only the
            # leading one both loses data and mislabels it.
            for m in D_PAT.finditer(masked):
                if BOND_DIM.search(clause[max(0, m.start() - 48):m.start()]):
                    skipped.append("D is a DMRG bond dimension")
                    continue
                kind = classify_at(clause, m.start())
                unit = unit_of(clause, m.end())
                val = to_cm(float(m.group(1)), unit)
                if not kind:
                    skipped.append("D value not assignable to calc or exp")
                elif kind == "exp" and n_tech > 1:
                    skipped.append("clause reports %d techniques; no single "
                                   "experimental D" % n_tech)
                elif val is None:
                    skipped.append("D in %s is not a ZFS parameter"
                                   % unit_of(clause, m.end()))
                elif abs(val) > MAX_D:
                    skipped.append("D = %g exceeds %g cm-1, not a ZFS "
                                   "parameter" % (val, MAX_D))
                else:
                    found["D_" + kind].append((round(val, 6), unit))
                    if not unit:
                        skipped.append("D unit absent, assumed cm-1")
            # E/D as stated wins over E/D derived from a stated E and D.
            stated = list(ED_PAT.finditer(clause))
            for m in stated:
                kind = classify_at(clause, m.start())
                if kind == "exp" and n_tech > 1:
                    continue
                if kind:
                    found["ED_" + kind].append((abs(float(m.group(1))), "stated"))
            if not stated:
                ds = list(D_PAT.finditer(masked))
                for me in E_PAT.finditer(clause):
                    # Pair an E with the D nearest it in the same clause.
                    near = [d for d in ds if float(d.group(1)) != 0]
                    if not near:
                        break
                    md = min(near, key=lambda d: abs(d.start() - me.start()))
                    kind = classify_at(clause, me.start())
                    if kind == "exp" and n_tech > 1:
                        continue
                    if kind and abs(float(md.group(1))) <= MAX_D:
                        ratio = abs(float(me.group(1)) / float(md.group(1)))
                        found["ED_" + kind].append((round(ratio, 4), "derived"))

    out, units = {}, []
    for key, vals in found.items():
        if not vals:
            continue
        distinct = {v for v, _ in vals}
        if len(distinct) > 1:
            skipped.append("%s disagrees across clauses: %s"
                           % (key, sorted(distinct)))
            continue
        value, how = vals[0]
        if key.startswith("ED") and value > ED_MAX:
            skipped.append("%s = %s exceeds the rhombic limit 1/3" % (key, value))
            continue
        out["zfs_" + key] = ("%g" % value)
        if how in ("GHz", "K"):
            units.append("%s converted from %s" % (key, how))
        if how == "derived":
            units.append("%s derived as |E/D|" % key)
    return out, skipped + units


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--sample", type=int, metavar="N",
                      help="print N extractions with their source clause, "
                           "for hand checking before --apply")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    results = [(r, *extract(r)) for r in rows]
    filled = [(r, v, n) for r, v, n in results if v]
    counts = Counter(k for _, v, _ in results for k in v)
    notes = Counter(n.split(":")[0].split(" =")[0] for _, _, ns in results
                    for n in ns)

    print("%d rows; %d gained at least one ZFS value" % (len(rows), len(filled)))
    for col in NEW_COLUMNS:
        print("   %-12s %4d rows" % (col, counts.get(col, 0)))
    print("\nskipped / annotated:")
    for reason, n in notes.most_common(10):
        print("   %4d  %s" % (n, reason))

    if args.sample:
        print("\n--- %d samples for hand checking ---" % args.sample)
        for r, vals, _ in random.Random(args.seed).sample(
                filled, min(args.sample, len(filled))):
            print("\n%s  ->  %s" % (r["entry_id"], vals))
            for col in PROSE:
                for clause in CLAUSE.split(r[col]):
                    if D_PAT.search(clause or "") or ED_PAT.search(clause or ""):
                        print("    [%s] %s" % (classify(clause) or "?",
                                               clause.strip()[:200]))
        return 0

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0

    if "zfs_D_calc" not in fields:
        fields = list(fields) + list(NEW_COLUMNS)
    for r, vals, _ in results:
        # Reset before writing, never merge: a value this run no longer
        # extracts must disappear, or the file stops reflecting the rules.
        for col in NEW_COLUMNS:
            r[col] = ""
        r.update(vals)
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, DB)
    print("\nwrote %d rows with %d columns" % (len(rows), len(fields)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
