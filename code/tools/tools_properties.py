"""Populate the `properties` column from the prose already in each row.

`properties` is one packed field holding the measurable physical quantities a
row reports (config.LITERATURE_COLUMNS, SCHEMA_VERSION 2.0):

    D=-31.5 cm-1 calc; E/D=0.152 calc; D=-28.9 cm-1 exp; gz=19.86 calc

Entries are separated by "; ", each one `KEY=VALUE[ UNIT] SOURCE` with SOURCE
either `calc` (this row's own calculation) or `exp` (a measured value the paper
quotes). Keys and their canonical units:

    D      axial zero-field-splitting parameter, cm-1
    E/D    rhombicity, dimensionless, <= 1/3 by definition
    gz     axial g of the ground doublet (g_zz, g_par, g_eff), dimensionless
    Ueff   magnetisation-reversal barrier, cm-1

These are not new readings of the papers: they lift values the row's own prose
already states, so the numbers remain grounded in whatever the source said and
`benchmark/check_grounding.py` still covers them. What the field adds is that a
consumer can filter and sort on D or Ueff without parsing a sentence.

This replaced four dedicated columns (zfs_D_calc, zfs_ED_calc, zfs_D_exp,
zfs_ED_exp) on the day they were added, because they did not reach lanthanide
chemistry: a 4f ion has spin-orbit coupling far larger than its ligand field,
so papers report crystal-field parameters, doublet g-tensors and a relaxation
barrier rather than a spin-Hamiltonian D, and only 14 of 1,028 lanthanide rows
ever carried a ZFS value. A second quartet of columns for the crystal-field
quantities would have been followed by a third for hyperfine and a fourth for
exchange coupling, each one empty on the great majority of rows. One field that
names its own contents does not grow.

**Computed and experimental are tagged, never merged**, because a paper
reporting a property almost always reports both and conflating them would make
the database claim an ab initio result for a measured number. The decision is
made per clause and by the nearest marker before the value, never by a
character window: a 160-character window around a D routinely spans both a
computed and a measured statement, and 250 of 665 occurrences came out
ambiguous that way.

Units. D is cm-1 for most rows but not all: GHz, MHz, kHz, THz and K are
converted and the conversion is recorded. Magnetic field units (gauss, mT, T)
are REFUSED rather than converted, since D in gauss becomes cm-1 only through
g*mu_B for that species and a guessed g would be a fabricated number. Energy
units (eV, kcal, hartree) disqualify a D outright: one carrying them is a
different quantity, such as a pseudo-Jahn-Teller gap. Ueff is the one key that
REQUIRES an explicit unit -- the cm-1 default that is safe for D is what would
turn every reaction barrier in the corpus into a magnetic one.

Guards, because a bad value is worse than an empty one:
  * E/D is rhombic by definition and cannot exceed 1/3. Anything above 0.3334
    is reported, never stored.
  * gz cannot exceed 20.5: 2*J*g_J is 20 for Dy(III) and Ho(III), the largest
    of any trivalent lanthanide, so a larger number is not a doublet g.
    A gz whose nearest qualifier is "excited" is skipped -- the key means the
    GROUND doublet.
  * `barrier` alone is not enough for Ueff. Reaction barriers are everywhere in
    this corpus, so the bare word needs magnetic context in the same clause
    (magnetisation reversal, Orbach, SMM, blocking, effective barrier);
    Ueff/Ucal name themselves and do not.
  * A clause offering two different values for the same key and source (a
    range, or several methods in one sentence) contributes nothing and is
    listed, because a filter needs one number and picking one would be a guess.

Usage, from code/:
    .venv/bin/python tools/tools_properties.py --dry-run
    .venv/bin/python tools/tools_properties.py --sample 25
    .venv/bin/python tools/tools_properties.py --migrate   # one-off, see below
    .venv/bin/python tools/tools_properties.py --fill-only
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

# aimdb.csv ONLY, deliberately. database/aimdb_llm_reproduced.csv also has the
# four ZFS columns, but those hold values a reproducing agent COMPUTED and
# wrote directly -- they were never extracted from prose, and this tool lifts
# values out of prose. Pointing it at that file would find nothing to lift and
# --apply would blank all 97. That asymmetry is why the reproduced rows show a
# D on 100% of rows while the mined rows show one on 1.6%: a computed value is
# structured from birth, whereas a mined one survives only if the paper stated
# it in a sentence the text layer kept.
DB = ROOT / "database" / "aimdb.csv"
# --migrate also touches the reproduced CSV, which carries the same four legacy
# columns. EXTRACTION never does: those rows hold values a reproducing agent
# COMPUTED and wrote directly, never lifted from prose, so pointing the
# extractor at them would find nothing and --apply would blank all 97. That
# asymmetry is why reproduced rows show a D on 100% of rows and mined rows on
# 1.6%: a computed value is structured from birth, a mined one survives only if
# the paper stated it in a sentence the text layer kept.
DB_REPRODUCED = ROOT / "database" / "aimdb_llm_reproduced.csv"
PROSE = ("electronic_structure_description", "Other", "notes",
         "active_space_protocol")
COLUMN = "properties"
# The four columns `properties` replaced, in their original order. Kept so
# --migrate can fold them in and so a reader of this file can see what the
# packed keys correspond to.
LEGACY_COLUMNS = ("zfs_D_calc", "zfs_ED_calc", "zfs_D_exp", "zfs_ED_exp")
LEGACY_KEYS = {"zfs_D_calc": ("D", "calc"), "zfs_ED_calc": ("E/D", "calc"),
               "zfs_D_exp": ("D", "exp"), "zfs_ED_exp": ("E/D", "exp")}
# Canonical unit per key; "" means dimensionless.
KEYS = {"D": "cm-1", "E/D": "", "gz": "", "Ueff": "cm-1"}
# Entry order within the field, so the same row always serialises identically
# and a diff shows real changes only.
KEY_ORDER = ("D", "E/D", "gz", "Ueff")
SOURCE_ORDER = ("calc", "exp")

# Clause boundaries. Semicolons and pipes are the row-prose separators used
# throughout aimdb; a full stop followed by a capital ends a sentence. Splitting
# here is what keeps a computed value from inheriting an experimental context.
CLAUSE = re.compile(r"\s*[;|]\s*|(?<=[a-z0-9\)])\.\s+(?=[A-Z])"
                    r"|(?<=\d\s[KT])\.\s+(?=[A-Z])")

# "|D|" means the magnitude of D and is very common, but the pipe is also
# aimdb's prose separator, so CLAUSE would split "|D|: 2.72 GHz" into pieces
# holding either the D or the number but never both -- losing the value with
# no skip reason recorded. Normalise the bars to a word form before splitting.
ABSBARS = (
    (re.compile(r"\|\s*E\s*/\s*D\s*\|"), "E/D"),
    (re.compile(r"\|\s*D\s*\|"), "absD"),
    (re.compile(r"\|\s*E\s*\|"), "absE"),
)


def unbar(text):
    """Rewrite |D|, |E| and |E/D| so the clause splitter leaves them alone."""
    for pat, repl in ABSBARS:
        text = pat.sub(repl, text)
    return text

CALC = re.compile(
    r"calculat|comput|\bCASSCF\b|\bNEVPT|\bCASPT|\bRASSCF\b|ab initio|"
    r"predict|theoretic|RASSI|SINGLE_ANISO|\bDFT\b|\bMRCI\b|\bDMRG\b|"
    r"second-order-perturbation|\bQDPT\b|our (?:value|result)", re.I)
EXP = re.compile(
    # "expt"/"exptl" is how a table heading writes it, and the
    # unabbreviated "experiment" does not match either.
    r"experiment|\bexptl?\b|measured|\bEPR\b|\bESR\b|HFEPR|HF-ESR|magnetometr|"
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
    r"(?<!in )\b(?:absD|D)\b\s*(?:value|parameter)?s?\s*"
    r"(?:=|of|is|:)\s*(%s)(?![A-Za-z])" % NUM)
E_PAT = re.compile(
    r"\b(?:absE|E)\b\s*(?:=|of|is|:)\s*(%s)(?![A-Za-z])" % NUM)
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
# "Zero-field splitting D (cm-1), <label> <value>, ..., experiment <value>":
# a column heading followed by a labelled list, which is how a
# method-comparison paper reports D. The heading carries the unit, so the
# values that follow have none of their own.
D_LIST_HEAD = re.compile(
    r"\bD\s*[\(\[]\s*(cm[^)\]]*|GHz|MHz|K)\s*[)\]]\s*[,:]", re.I)
D_LIST_EXPT = re.compile(
    r"\bexperiment(?:al)?\s*[,:]?\s*([-+]?\d+(?:\.\d+)?)(?![A-Za-z])", re.I)

MULTI_D = re.compile(
    r"\b(?:absD|D)\b[^.;|]{0,12}(?:=|is|of|:)\s*%s%s\s*%s\s*%s"
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

# ---------------------------------------------------------------- gz, Ueff
# The axial g of a doublet, written g_z, g_zz, g_par, g_|| or g_eff. The
# anchor is case-sensitive on the subscript so that gx, gy, gxx, gyy, gavg,
# giso and gperp cannot match: those are the other tensor components, and
# storing one of them under `gz` would be a wrong number, not a missing one.
GZ_PAT = re.compile(
    r"\bg\s*[_ -]?\s*(?:zz|z|par|\|\|)\b\s*(?:=|of|is|:|~|value\s*(?:of)?)?"
    r"\s*([-+]?\d+(?:\.\d+)?)(?![A-Za-z0-9])")
# g_eff separately: it is the axial g for an Ising doublet, which is the sense
# meant here, but it is also used for an isotropic effective g, so it is only
# read when the clause is about a doublet.
GEFF_PAT = re.compile(
    r"\bg\s*[_ -]?\s*eff\b\s*(?:=|of|is|:|~)?\s*"
    r"([-+]?\d+(?:\.\d+)?)(?![A-Za-z0-9])", re.I)
DOUBLET = re.compile(r"doublet|\bKD\d|Ising|\bm_?J\b|Kramers", re.I)
# 2*J*g_J is 20.00 for Dy(III) and Ho(III), the largest of any trivalent
# lanthanide, so nothing above this is a doublet g.
MAX_GZ = 20.5
# An exchange-coupled g is a property of the coupled dimer, not of the ion,
# and a 3d-4f paper reports both. They differ by a factor of two or more, so
# putting either under `gz` when the other is also present would make the key
# mean two things.
EXCHANGE = re.compile(r"exchange[- ]coupled|coupled (?:ground )?doublet|"
                      r"\bPOLY_?ANISO\b|Lines (?:model|fit)", re.I)
# "excited" nearer the value than "ground" means the g belongs to an excited
# doublet, and this key means the ground one.
EXCITED = re.compile(r"\bexcited\b|\bKD[2-9]\b|\bsecond\b|\bthird\b", re.I)
GROUND = re.compile(r"\bground\b|\bKD1\b|\blowest\b", re.I)

# The magnetisation-reversal barrier. Ueff, Ucal and Ucalc name themselves.
UEFF_NAMED = re.compile(
    r"\bU\s*[_-]?\s*(?:eff|cal|calc)\b\s*(?:=|of|is|:|~)?\s*"
    r"([-+]?\d+(?:\.\d+)?)(?![A-Za-z0-9])", re.I)
# A bare "barrier" is not enough: reaction barriers are everywhere in this
# corpus and a torsional barrier in cm-1 looks exactly like a magnetic one.
UEFF_BARRIER = re.compile(
    r"\bbarrier\b[a-z \-]{0,20}?\s*(?:=|of|is|:|~|at)\s*"
    r"([-+]?\d+(?:\.\d+)?)(?![A-Za-z0-9])", re.I)
MAG_CONTEXT = re.compile(
    r"magneti[sz]ation|magnetic relaxation|Orbach|\bSMM\b|\bSIM\b|"
    r"single[- ](?:molecule|ion) magnet|blocking|spin[- ]reversal|"
    r"demagneti[sz]|effective barrier|anisotropy barrier|slow relaxation|"
    r"relaxation barrier|\bU_?eff\b|\bU_?cal", re.I)
# Observed magnetic behaviour, which is a measurement even when the sentence
# names no technique. Scoped to Ueff: the `calc` default is correct for D and
# changing it globally would disturb values that are already hand-scored.
UEFF_OBSERVED = re.compile(
    r"\b(?:shows?|showing|showed|exhibit\w*|display\w*|behaves?|"
    r"demonstrat\w*)\b[^.;|]{0,70}(?:slow (?:magnetic |magnetisation |"
    r"magnetization )?relaxation|single[- ]molecule magnet|\bSMM\b|"
    r"out[- ]of[- ]phase|hysteresis|blocking)"
    r"|field[- ]induced|under (?:an? )?(?:applied|dc|DC) field"
    r"|\bAC susceptibilit|Arrhenius|out[- ]of[- ]phase", re.I)

# The tallest barriers reported for any single-molecule magnet are around
# 2200 cm-1; 3000 leaves headroom without admitting an electronic excitation.
MAX_UEFF = 3000.0

# A second number straight after the first, joined by a separator: a range, or
# one value per complex. MULTI_D cannot be reused for this -- it is anchored on
# a literal "D" token and so matches nothing for a gz or a Ueff. Tested
# BEFORE the unit is read, since the unit sits between the value and any
# separator ("Ueff = 13.53 K and tau0 = ..." is one value, not two).
MULTI_TAIL = re.compile(r"^%s\s*%s\s*%s" % (UNC, SEP, NUM))

# Prose that exists to record a contradiction IN THE SOURCE. One of two
# contradictory numbers is not a fact about the compound, and which one the
# paper meant is exactly what the row is saying cannot be decided.
# The self-reference is required. A first attempt matched bare `disagree`,
# `inconsistent` and `mismatch`, which fired on 1,315 clauses -- almost all
# of them ordinary prose about a method disagreeing with experiment, which
# is a finding and not a defect. Requiring the clause to name the source
# (paper, abstract, conclusion, SI) or say `internally` brings it to 264.
CONFLICT = re.compile(
    r"(?:source|paper|article|abstract|manuscript|conclusion|SI\b|"
    r"supporting information)[^.;|]{0,40}\b(?:conflict|contradict|"
    r"inconsisten|irreconcil|two different (?:value|number))"
    r"|\b(?:conflict|contradict|inconsisten|irreconcil)\w*[^.;|]{0,40}"
    r"\b(?:source|paper|article|abstract|conclusion|manuscript|internally)"
    r"|\btwo (?:material numerical|conflicting|contradictory) "
    r"(?:conflict|value|number)"
    r"|cannot be reconciled", re.I)

GHZ_TO_CM = 0.0333564095
MHZ_TO_CM = 3.33564095e-5
KHZ_TO_CM = 3.33564095e-8
THZ_TO_CM = 33.3564095
# "D = x, against experimental y": a contrast word between the value and a
# later experimental marker puts the value on the computed side of the
# contrast. Without this the value is dropped as unassignable.
CONTRAST = re.compile(
    r"\b(?:against|versus|vs\.?|compared (?:with|to)|whereas|while|"
    r"in contrast (?:to|with)|relative to|cf\.)\b", re.I)
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

    Returns "cm-1"/"GHz"/"MHz"/"kHz"/"THz"/"K" for a usable unit, "" when none
    is stated (cm-1 is then assumed, as it is the convention throughout this
    corpus), or "bad" when the stated unit rules the value out as a ZFS
    parameter.

    An uncertainty in parentheses is stepped over first: "D = -178(1) MHz"
    otherwise reads as having no unit, and the cm-1 default then makes the
    value wrong by a factor of 30,000.
    """
    tail = clause[pos:pos + 40]
    skip = re.match(r"\s*\(\d+\)", tail)
    if skip:
        tail = tail[skip.end():]
    if re.match(r"\s*(?:cm\s*\^?-?1|cm-1|reciprocal centimet|per centimetre)",
                tail, re.I):
        return "cm-1"
    if re.match(r"\s*GHz", tail, re.I):
        return "GHz"
    if re.match(r"\s*MHz", tail, re.I):
        return "MHz"
    if re.match(r"\s*kHz", tail, re.I):
        return "kHz"
    if re.match(r"\s*THz", tail, re.I):
        return "THz"
    if re.match(r"\s*K\b", tail):
        return "K"
    if BAD_UNIT.match(tail):
        return "bad"
    return ""


def ueff_unit(clause, pos):
    """Unit for a barrier at `pos`: "cm-1", "K", or "" when none is stated.

    Unlike D, a barrier with no stated unit is REFUSED rather than assumed to
    be cm-1. Energies in this corpus are quoted in kcal/mol far more often
    than in cm-1, so the assumption that is safe for a ZFS parameter would
    turn every unitless reaction barrier into a magnetic one.
    """
    tail = clause[pos:pos + 40]
    skip = re.match(r"\s*\(\d+\)", tail)
    if skip:
        tail = tail[skip.end():]
    if re.match(r"\s*(?:cm\s*\^?-?1|cm-1)", tail, re.I):
        return "cm-1"
    if re.match(r"\s*K\b", tail):
        return "K"
    return ""


def gz_is_ground(clause, pos):
    """Whether a g at `pos` belongs to the ground doublet.

    Decided by which qualifier sits nearer before it. An unqualified g is
    taken as the ground doublet, which is what a paper means when it reports
    one g without saying which -- but an "excited" closer than any "ground"
    overrides that.
    """
    head = clause[:pos]
    last_exc = max((m.end() for m in EXCITED.finditer(head)), default=-1)
    last_gnd = max((m.end() for m in GROUND.finditer(head)), default=-1)
    return last_gnd >= last_exc


def extract_magnetic(row):
    """gz and Ueff entries from the row's prose: {(key, source): [(val, how)]}."""
    found, skipped = {}, []
    for col in PROSE:
        text = row[col]
        if not text:
            continue
        for clause in CLAUSE.split(unbar(text)):
            if not clause:
                continue
            if THIRD_PARTY.search(clause):
                continue
            if CONFLICT.search(clause):
                skipped.append("clause records a conflict in the source")
                continue

            # --- gz -------------------------------------------------------
            cands = list(GZ_PAT.finditer(clause))
            if DOUBLET.search(clause):
                cands += list(GEFF_PAT.finditer(clause))
            vals = []
            if EXCHANGE.search(clause):
                if cands:
                    skipped.append("gz is an exchange-coupled value, not a "
                                   "single-ion ground doublet")
                cands = []
            for m in cands:
                if not gz_is_ground(clause, m.start()):
                    skipped.append("gz belongs to an excited doublet")
                    continue
                if MULTI_TAIL.match(clause[m.end():]):
                    skipped.append("gz is a range or a list")
                    continue
                v = float(m.group(1))
                if not 0.0 <= v <= MAX_GZ:
                    skipped.append("gz = %g outside 0..%g" % (v, MAX_GZ))
                    continue
                kind = classify_at(clause, m.start())
                if kind:
                    vals.append((kind, round(v, 4)))
            # Several g values in one clause are the x/y/z components of one
            # tensor or several complexes; the pattern only matches axial
            # labels, so two distinct ones mean two systems, not two axes.
            for kind, v in vals:
                found.setdefault(("gz", kind), []).append((v, "stated"))

            # --- Ueff -----------------------------------------------------
            named = list(UEFF_NAMED.finditer(clause))
            bare = ([] if named or not MAG_CONTEXT.search(clause)
                    else list(UEFF_BARRIER.finditer(clause)))
            for m in named + bare:
                if MULTI_TAIL.match(clause[m.end():]):
                    skipped.append("Ueff is a range or a list")
                    continue
                unit = ueff_unit(clause, m.end())
                if not unit:
                    skipped.append("barrier has no cm-1 or K unit; refused")
                    continue
                v = float(m.group(1)) * (K_TO_CM if unit == "K" else 1.0)
                if not 0.0 < v <= MAX_UEFF:
                    skipped.append("Ueff = %g outside 0..%g cm-1"
                                   % (v, MAX_UEFF))
                    continue
                kind = classify_at(clause, m.start())
                # An unmarked barrier in a clause describing observed magnetic
                # behaviour is experimental, not this row's calculation. Only
                # when no computational marker precedes the value: "SINGLE_ANISO
                # gives Ucal = 877 cm-1 for a compound showing SMM behaviour"
                # is still a computed number.
                if kind == "calc" and UEFF_OBSERVED.search(clause) \
                        and not CALC.search(clause[:m.start()]):
                    kind = "exp"
                if kind:
                    found.setdefault(("Ueff", kind), []).append(
                        (round(v, 4), unit))
    return found, skipped


def fmt(entries):
    """Serialise {(key, source): value} to the packed field."""
    out = []
    for key in KEY_ORDER:
        for src in SOURCE_ORDER:
            if (key, src) not in entries:
                continue
            unit = KEYS[key]
            out.append("%s=%g%s %s" % (key, entries[(key, src)],
                                       " " + unit if unit else "", src))
    return "; ".join(out)


def parse(field):
    """Inverse of fmt(): the packed field back to {(key, source): value}.

    Used by --migrate to verify the fold was lossless, and available to any
    consumer that would rather not write this twice.
    """
    entries = {}
    for part in field.split(";"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(.+?)=([-+]?\d+(?:\.\d+)?)\s*(.*?)\s*(calc|exp)$",
                     part)
        if not m:
            raise ValueError("unparseable properties entry: %r" % part)
        entries[(m.group(1), m.group(4))] = float(m.group(2))
    return entries


def to_cm(value, unit):
    """Value in cm-1, or None when the unit disqualifies it."""
    if unit in ("cm-1", ""):
        return value          # cm-1 is the overwhelming default in this corpus
    if unit == "GHz":
        return value * GHZ_TO_CM
    if unit == "MHz":
        return value * MHZ_TO_CM
    if unit == "kHz":
        return value * KHZ_TO_CM
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
        nxt = EXP.search(clause, pos)
        if nxt is None:
            return "calc"
        # The only marker follows the value. If a contrast word separates
        # them -- "D = 0.0821 ... against experimental 0.1229" -- the value
        # sits on the computed side of the contrast.
        if CONTRAST.search(clause, pos, nxt.start()):
            return "calc"
        return ""
    return "calc" if last_calc > last_exp else "exp"


def extract(row):
    """Return ({column: value}, [notes about what was skipped])."""
    found = {k: [] for k in ("D_calc", "ED_calc", "D_exp", "ED_exp")}
    skipped = []
    for col in PROSE:
        text = row[col]
        if not text:
            continue
        text = unbar(text)
        for clause in CLAUSE.split(text):
            # absD/absE are what unbar() leaves behind; "\bD\b" does not
            # match the D inside absD, and this guard silently dropped
            # every |D| clause until it did.
            if not clause or not re.search(
                    r"\b(?:absD|D)\b|\b(?:absE|E)\s*/\s*D\b", clause):
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
            # A unit-headed labelled list: take the one value labelled
            # `experiment`, and leave the method-labelled ones alone -- the
            # row's `method` field spans all of them, so none is "the"
            # computed value for this row.
            head = D_LIST_HEAD.search(clause)
            if head:
                me = D_LIST_EXPT.search(clause, head.end())
                if me:
                    unit = {"ghz": "GHz", "mhz": "MHz", "k": "K"}.get(
                        head.group(1).strip().lower(), "cm-1")
                    val = to_cm(float(me.group(1)), unit)
                    if val is not None:
                        found["D_exp"].append((round(val, 6), unit))
                        skipped.append("D read from a unit-headed labelled "
                                       "list; the method-labelled values were "
                                       "left for the row's method field")
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

    mag, mag_skipped = extract_magnetic(row)
    for key, vals in mag.items():
        found.setdefault(key, []).extend(vals)
    skipped += mag_skipped

    entries, units = {}, []
    for key, vals in found.items():
        if not vals:
            continue
        # Legacy keys arrive from the D/E/D pass as "D_calc" strings; the
        # magnetic pass already uses (key, source) tuples.
        if isinstance(key, str):
            name, src = key.rsplit("_", 1)
            name = {"D": "D", "ED": "E/D"}[name]
            key = (name, src)
        name, src = key
        distinct = {v for v, _ in vals}
        if len(distinct) > 1:
            skipped.append("%s (%s) disagrees across clauses: %s"
                           % (name, src, sorted(distinct)))
            continue
        value, how = vals[0]
        if name == "E/D" and value > ED_MAX:
            skipped.append("E/D (%s) = %s exceeds the rhombic limit 1/3"
                           % (src, value))
            continue
        entries[(name, src)] = value
        if how in ("GHz", "MHz", "kHz", "THz", "K"):
            units.append("%s (%s) converted from %s" % (name, src, how))
        if how == "derived":
            units.append("E/D (%s) derived as |E/D|" % src)
    return entries, skipped + units


def migrate():
    """Fold the four legacy columns into `properties` and drop them.

    Lossless by construction and checked as such: every legacy cell must come
    back out of parse() with the same value, and the four columns must be gone
    from the header afterwards. Run once per file; a file already migrated is
    reported and left alone, so this is safe to re-run.
    """
    for path in (DB, DB_REPRODUCED):
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fields = list(reader.fieldnames)
            rows = list(reader)
        if not any(c in fields for c in LEGACY_COLUMNS):
            print("%s: already migrated, %d rows" % (path.name, len(rows)))
            continue

        moved = carried = 0
        for r in rows:
            entries = {}
            for col in LEGACY_COLUMNS:
                raw = (r.get(col) or "").strip()
                if raw:
                    entries[LEGACY_KEYS[col]] = float(raw)
                    moved += 1
            existing = (r.get(COLUMN) or "").strip()
            if existing:
                # Nothing writes `properties` before this runs, but if a row
                # somehow holds both, the legacy columns lose: they are the
                # thing being retired.
                entries = {**parse(existing), **entries}
                carried += 1
            r[COLUMN] = fmt(entries)
            # Verify this row survived the fold before the old cells go.
            back = parse(r[COLUMN])
            for col in LEGACY_COLUMNS:
                raw = (r.get(col) or "").strip()
                if raw:
                    key = LEGACY_KEYS[col]
                    assert key in back and abs(back[key] - float(raw)) < 1e-9, (
                        "%s: %s lost %s=%s" % (path.name, r["entry_id"], col, raw))
            for col in LEGACY_COLUMNS:
                r.pop(col, None)

        fields = [c for c in fields if c not in LEGACY_COLUMNS]
        if COLUMN not in fields:
            fields.append(COLUMN)
        tmp = path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)
        n = sum(1 for r in rows if r[COLUMN])
        print("%s: %d legacy values -> %d rows carrying `properties`; "
              "%d columns (%d dropped)%s"
              % (path.name, moved, n, len(fields), len(LEGACY_COLUMNS),
                 ", %d rows already had entries" % carried if carried else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true",
                      help="reset all four columns and rewrite them from "
                           "prose. DISCARDS hand-curated values, including "
                           "the deliberate blanks on rows whose computed D "
                           "changes sign between geometries -- see "
                           "--fill-only")
    mode.add_argument("--fill-only", action="store_true",
                      help="write a column only where it is currently empty; "
                           "never overwrite. The safe mode after hand-mining")
    mode.add_argument("--migrate", action="store_true",
                      help="one-off: fold the four legacy zfs_* columns into "
                           "`properties` and drop them, in both CSVs. "
                           "Verifies the fold round-trips before writing")
    mode.add_argument("--sample", type=int, metavar="N",
                      help="print N extractions with their source clause, "
                           "for hand checking before --apply")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    if args.migrate:
        return migrate()

    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    results = [(r, *extract(r)) for r in rows]
    filled = [(r, v, n) for r, v, n in results if v]
    counts = Counter("%s %s" % (k, src) for _, v, _ in results
                     for k, src in v)
    notes = Counter(n.split(":")[0].split(" =")[0] for _, _, ns in results
                    for n in ns)

    print("%d rows; %d gained at least one property" % (len(rows), len(filled)))
    for key in KEY_ORDER:
        for src in SOURCE_ORDER:
            n = counts.get("%s %s" % (key, src), 0)
            if n:
                print("   %-6s %-5s %5d rows" % (key, src, n))
    print("\nskipped / annotated:")
    for reason, n in notes.most_common(12):
        print("   %5d  %s" % (n, reason))

    if args.sample:
        print("\n--- %d samples for hand checking ---" % args.sample)
        for r, vals, _ in random.Random(args.seed).sample(
                filled, min(args.sample, len(filled))):
            print("\n%s  ->  %s" % (r["entry_id"], fmt(vals)))
            for col in PROSE:
                for clause in CLAUSE.split(r[col]):
                    if D_PAT.search(clause or "") or ED_PAT.search(clause or ""):
                        print("    [%s] %s" % (classify(clause) or "?",
                                               clause.strip()[:200]))
        return 0

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0

    if COLUMN not in fields:
        fields = list(fields) + [COLUMN]
    written = kept = 0
    for r, entries, _ in results:
        packed = fmt(entries)
        r.setdefault(COLUMN, "")
        if args.fill_only:
            # Merge per KEY, not per cell. A row already stating a D has a
            # non-empty cell, and a cell-level test would then refuse the gz
            # the same prose offers. Existing keys are never overwritten:
            # whatever is there was written by an earlier run or curated by
            # hand, and the tool cannot tell which.
            have = parse(r[COLUMN]) if r[COLUMN].strip() else {}
            added = {k: v for k, v in entries.items() if k not in have}
            kept += len(have)
            if added:
                r[COLUMN] = fmt({**have, **added})
                written += len(added)
        else:
            # Reset before writing, never merge: a value this run no longer
            # extracts must disappear, or the file stops reflecting the rules.
            r[COLUMN] = packed
            if packed:
                written += 1
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, DB)
    print("\nwrote %d rows with %d columns (%d %s)"
          % (len(rows), len(fields), written,
             "entr%s added, %d existing left untouched"
             % ("y" if written == 1 else "ies", kept) if args.fill_only
             else "`properties` cell(s) written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
