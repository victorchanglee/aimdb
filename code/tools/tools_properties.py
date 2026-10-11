"""Populate the `properties` column from the prose already in each row.

`properties` is one packed field holding the measurable physical quantities a
row reports (config.LITERATURE_COLUMNS, SCHEMA_VERSION 2.0):

    D=-31.5 cm-1 calc; E/D=0.152 calc; D=-28.9 cm-1 exp; gz=19.86 calc

Entries are separated by "; ", each one `KEY=VALUE[ UNIT] SOURCE` with SOURCE
either `calc` (this row's own calculation) or `exp` (a measured value the paper
quotes). Keys and their canonical units:

    D      axial zero-field-splitting parameter, cm-1
    E/D    rhombicity, dimensionless, <= 1/3 by definition
    gx gy gz   g-tensor components, dimensionless. gz absorbs g_par and (in
               a doublet context) g_eff, both of which name the axial value
    gperp      the in-plane component where a paper reports only g_perp
    giso       isotropic or average g
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


The g keys hold two conventions and the field does not distinguish them. gz is
the z principal component of the Zeeman g tensor either way, but for a 3d
complex it multiplies the real spin and lands near 2.0023, while for a Kramers
doublet it multiplies a fictitious S = 1/2 and absorbs the orbital moment,
with a ceiling of 2*g_J*|m_J| = 20.00 for Dy(III) and Ho(III). A gz of 19.86
is not a tenfold larger response than a gz of 2.0. Of the 99 gz values
extracted, the 69 above 4 are 99% f-block and 70% of the rest are d-block --
two populations, not a spread. The convention is not a separate key because
the sentence a value comes from rarely states it, and reading it off the
magnitude would be a guess.

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
  * no g component may exceed 20.5: 2*J*g_J is 20 for Dy(III) and Ho(III),
    the largest of any trivalent lanthanide. A component whose nearest
    qualifier is "excited" is skipped, and so is an exchange-coupled one --
    these keys mean the single-ion GROUND doublet.
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
# Canonical unit per key; "" means dimensionless. VARIES means the entry
# carries whatever unit the paper used, because no conversion is available --
# see the module docstring on A.
VARIES = None
KEYS = {"D": "cm-1", "E/D": "", "gx": "", "gy": "", "gz": "",
        "giso": "", "gperp": "", "Ueff": "cm-1", "A": VARIES}
# Crystal-field parameters are keyed B(k,q) and generated from the data, so
# they are matched by prefix rather than listed. All are cm-1.
B_PREFIX = "B("


def key_unit(key):
    """Canonical unit for a key, or VARIES when the entry carries its own."""
    if key.startswith(B_PREFIX):
        return "cm-1"
    return KEYS[key]
# Entry order within the field, so the same row always serialises identically
# and a diff shows real changes only.
KEY_ORDER = ("D", "E/D", "gx", "gy", "gz", "gperp", "giso", "A", "Ueff")


def key_rank(key):
    """Sort position for a key, so a row always serialises identically.

    B(k,q) keys are generated, so they sort after the fixed ones by (k, q)
    rather than appearing in KEY_ORDER.
    """
    if key in KEY_ORDER:
        return (0, KEY_ORDER.index(key), 0)
    if key.startswith(B_PREFIX):
        k, q = key[len(B_PREFIX):-1].split(",")
        return (1, int(k), int(q))
    return (2, 0, 0)
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
# A structure the paper invents to make a point is not the compound this row
# is about. "The hypothetical T-shaped model 1b, computed at CAS(3,12),
# inverts the picture entirely: negligible transverse anisotropy (gx 0.011,
# gy 0.013, gz 6.138)" describes a geometry that does not exist, and those
# numbers were being stored as the real complex's g tensor.
# Only words that actually mean "this structure is invented". A first version
# also matched `imaginary`, `idealised/idealized` and `artificially`, and fired
# on 1,673 clauses -- 1,380 of them on "imaginary frequency", a routine
# vibrational-analysis term, and 58 more on "idealized geometry", which is a
# symmetry-constrained model of the real compound rather than a different one.
HYPOTHETICAL = re.compile(
    r"\bhypothetical|\bfictitious|\bdoes not exist|\bnot a real\b", re.I)
THIRD_PARTY = re.compile(
    r"literature value|reported (?:in|by) ref|for context|related (?:complex|"
    r"compound|system)|other (?:complex|compound)|previous(?:ly)? (?:report|"
    r"publish)|earlier (?:report|work)|by comparison with", re.I)
# Largest credible molecular ZFS D. Co(II) reaches ~100 cm-1 and lanthanide
# axial parameters a few hundred; 2800 cm-1 is a ligand-field or Racah
# parameter that happens to be written "D".
MAX_D = 1000.0

# ---------------------------------------------------------------- gz, Ueff
# Any component of the g tensor. The label is captured so it can be
# normalised; longer alternatives come first so that `gzz` is not read as
# `gz` with a stray z, and `(?![A-Za-z])` stops `gx` matching inside a word.
# `||` is matched without a trailing \b, which would fail between a pipe and
# a space and is why the old axial-only pattern never actually caught "g||".
G_PAT = re.compile(
    r"\bg\s*[_ -]?\s*(zz|xx|yy|par|perp|iso|avg|av|eff|z|x|y|\|\|)"
    r"(?![A-Za-z])\s*(?:=|of|is|:|~|value\s*(?:of)?)?"
    # Chained equality: "gxx = gyy = 0.01" assigns one number to both
    # components, and is how EPR prose states an axial tensor. Without this
    # the first label in the chain finds "= g..." where it wants a number.
    r"((?:\s*[=:]\s*g\s*[_ -]?\s*(?:zz|xx|yy|z|x|y)(?![A-Za-z]))*)"
    r"\s*(?:=|:)?\s*([-+]?\d+(?:\.\d+)?)(?![A-Za-z0-9])")
# The labels inside a captured chain, so the value can be given to each of
# them. finditer does not overlap, so a chain consumed by one match is the
# only chance those labels get.
G_CHAIN = re.compile(r"g\s*[_ -]?\s*(zz|xx|yy|z|x|y)(?![A-Za-z])")
# Label -> key. g_parallel is the axial component by definition, so it shares
# gz rather than getting a key that would mean the same thing.
G_KEY = {"zz": "gz", "z": "gz", "par": "gz", "||": "gz",
         "xx": "gx", "x": "gx",
         "yy": "gy", "y": "gy",
         "iso": "giso", "avg": "giso", "av": "giso",
         "perp": "gperp"}
DOUBLET = re.compile(r"doublet|\bKD\d|Ising|\bm_?J\b|Kramers", re.I)
# 2*J*g_J is 20.00 for Dy(III) and Ho(III), the largest of any trivalent
# lanthanide, so nothing above this is a g at all -- and no ordinary
# transition-metal component comes near it either.
MAX_G = 20.5
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

# ------------------------------------------------- crystal field, hyperfine
# A crystal-field parameter with both indices and an explicit value. The two
# index orders in use -- B20 (k first) and B02 (q first) -- are told apart by
# the physics rather than by the paper's wording: see kq_of.
B_PAT = re.compile(
    r"\bB\s*[_^]?\s*\{?\s*(-?\d)\s*\}?\s*[_^(\[]?\s*\{?\s*(-?\d)"
    r"\s*\}?\s*[)\]}]?\s*(?:=|is|of|:)\s*([-+]?\d+(?:\.\d+)?)")
# A crystal-field parameter of a few thousand cm-1 is already extreme; beyond
# that the number is not a B(k,q).
MAX_B = 20000.0

# Hyperfine. The clause must SAY hyperfine, because the symbol A is unusable
# as an anchor on its own: across 111 clauses matching "A = <number>" with no
# mention of hyperfine, A was the Angstrom, the Arrhenius pre-exponential, a
# species label, an ABC2 parameter, and the ROTATIONAL CONSTANT A -- which one
# paper reports in MHz, the very unit hyperfine uses.
HYPERFINE = re.compile(r"hyperfine|\bHFI\b|\bHFC\b", re.I)
# `hfc` is not always hyperfine: in W4221104479 it is the ligand
# hexafluoroacetylacetonate, as in Ni(hfc)2(pic)2.
HFC_LIGAND = re.compile(r"\(hfc\)|hexafluoroacet|\bhfac\b", re.I)
# The rotational constant A, which collides in both symbol and unit.
ROT_CONST = re.compile(
    r"rotational constant|constants? A\b|\bA,\s*B,?\s*(?:and\s*)?C\b", re.I)
# Value and unit. "G" is matched last and deliberately word-bounded: it also
# ends a basis-set name, and "CAS(7,8)/6-31G*" otherwise reads as -31 G.
A_VAL = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(MHz|GHz|kHz|cm-1|mT|gauss|G)\b",
                   re.I)
BASIS_NEAR = re.compile(r"\d-\d+\+?G|cc-pV|def2|aug-cc|STO-3G|TZVP|QZVP", re.I)
# mu_B/h in MHz per gauss: A[MHz] = 1.399624 * g * A[G].
MHZ_PER_GAUSS = 1.399624
# A g stated in the same clause, for that conversion. Only giso/gz/gavg are
# used: the conversion needs the g that the quoted A belongs to, and a
# transverse component is not it.
G_FOR_A = re.compile(
    r"\bg\s*[_ -]?\s*(iso|avg|zz|z)\b\s*(?:=|of|is|:)?\s*"
    r"([-+]?\d+(?:\.\d+)?)", re.I)
# Which A label this is, so the right g is paired with it.
A_LABEL = re.compile(r"\bA\s*[_ -]?\s*(iso|avg|zz|z)\b", re.I)
MAX_A_MHZ = 20000.0

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
# A comparison word between a value and a later experimental marker puts the
# value on the COMPUTED side of the comparison. Agreement counts as much as
# contrast: "gx 3.625, gy 3.198, gz 0.723, in good agreement with experiment"
# states three computed numbers just as plainly as "against experiment" would,
# and without the agreement idioms here all three were dropped as
# unassignable.
CONTRAST = re.compile(
    r"\b(?:against|versus|vs\.?|compared (?:with|to)|whereas|while|"
    r"in contrast (?:to|with)|relative to|cf\.|"
    r"in (?:good |excellent |reasonable |close |fair )?agreement with|"
    r"agrees? (?:well )?with|consistent with|matching|reproduc\w+ the)\b",
    re.I)
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


def kq_of(a, b):
    """Resolve the two indices of a B parameter to (k, q), or None.

    Papers write both orders -- B20 for k=2,q=0 and B02 for the same thing --
    and B44 is identical either way while B46 is not. The physics settles it
    without reference to the paper's wording: k is 2, 4 or 6 and |q| <= k, so
    of the two possible readings exactly one is admissible. Where both are,
    the digits are equal and the readings agree.
    """
    ok = [(k, q) for k, q in ((a, b), (b, a))
          if k in (2, 4, 6) and abs(q) <= k]
    if not ok:
        return None
    if len(ok) == 2 and ok[0] != ok[1]:
        return None            # genuinely ambiguous; never reached in practice
    return ok[0]


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
            if HYPOTHETICAL.search(clause):
                skipped.append("clause describes a hypothetical structure")
                continue

            # --- g tensor -------------------------------------------
            cands = list(G_PAT.finditer(clause))
            if EXCHANGE.search(clause):
                if cands:
                    skipped.append("g is an exchange-coupled value, not a "
                                   "single-ion ground doublet")
                cands = []
            for m in cands:
                labels = [m.group(1).lower()] + [
                    g.lower() for g in G_CHAIN.findall(m.group(2) or "")]
                label = labels[0]
                if label == "eff":
                    # g_eff is the axial g for an Ising doublet and an
                    # isotropic effective g otherwise; only the first sense
                    # is identifiable from the clause.
                    if not DOUBLET.search(clause):
                        skipped.append("g_eff outside a doublet context is "
                                       "ambiguous between axial and isotropic")
                        continue
                    keys = ["gz"]
                else:
                    keys = [G_KEY[l] for l in labels]
                if not gz_is_ground(clause, m.start()):
                    skipped.append("%s belongs to an excited doublet"
                                   % "/".join(keys))
                    continue
                if MULTI_TAIL.match(clause[m.end():]):
                    skipped.append("%s is a range or a list" % "/".join(keys))
                    continue
                v = float(m.group(3))
                if not 0.0 <= v <= MAX_G:
                    skipped.append("%s = %g outside 0..%g"
                                   % ("/".join(keys), v, MAX_G))
                    continue
                kind = classify_at(clause, m.start())
                if kind:
                    for key in dict.fromkeys(keys):
                        found.setdefault((key, kind), []).append(
                            (round(v, 4), "stated"))

            # --- crystal field B(k,q) -------------------------------
            for m in B_PAT.finditer(clause):
                res = kq_of(int(m.group(1)), int(m.group(2)))
                if res is None:
                    continue
                if MULTI_TAIL.match(clause[m.end():]):
                    skipped.append("B(%d,%d) is a range or a list" % res)
                    continue
                v = float(m.group(3))
                if abs(v) > MAX_B:
                    skipped.append("B(%d,%d) = %g exceeds %g cm-1"
                                   % (res + (v, MAX_B)))
                    continue
                kind = classify_at(clause, m.start())
                if kind:
                    found.setdefault(("B(%d,%d)" % res, kind), []).append(
                        (round(v, 6), "cm-1"))

            # --- hyperfine A ----------------------------------------------
            if HYPERFINE.search(clause) and not HFC_LIGAND.search(clause) \
                    and not ROT_CONST.search(clause):
                # Pair the g with the A: an isotropic A takes giso/gavg, an
                # axial one takes gz/gzz. Taking simply the first g in the
                # clause picked gz for an A_iso.
                gs = {m.group(1).lower(): float(m.group(2))
                      for m in G_FOR_A.finditer(clause)}
                al = A_LABEL.search(clause)
                axial = bool(al) and al.group(1).lower() in ("z", "zz")
                order = (("zz", "z", "iso", "avg") if axial
                         else ("iso", "avg", "zz", "z"))
                g_here = next((gs[k] for k in order if k in gs), None)
                vals = list(A_VAL.finditer(clause))
                if len(vals) > 1:
                    # Several numbers in one hyperfine clause: a before/after
                    # pair ("cuts the HFC parameter from about 42 GHz to about
                    # 7 GHz"), or one per nucleus. Which is this row's A
                    # cannot be decided from the clause.
                    skipped.append("%d hyperfine values in one clause"
                                   % len(vals))
                    vals = []
                for m in vals:
                    unit = m.group(2)
                    u = unit.lower()
                    if u in ("g", "gauss", "mt") and BASIS_NEAR.search(clause):
                        # "CAS(7,8)/6-31G*" reads as -31 G.
                        skipped.append("A in gauss adjacent to a basis-set "
                                       "name; refused as a misread")
                        continue
                    v = float(m.group(1))
                    if u == "ghz":
                        v, unit = v * 1000.0, "MHz"
                    elif u == "khz":
                        v, unit = v / 1000.0, "MHz"
                    elif u == "cm-1":
                        v, unit = v / MHZ_TO_CM, "MHz"
                    elif u == "mhz":
                        unit = "MHz"
                    elif g_here is not None:
                        # Field units become a frequency only through
                        # g*mu_B, and only the paper's own g will do.
                        gauss = v * (10.0 if u == "mt" else 1.0)
                        v = gauss * g_here * MHZ_PER_GAUSS
                        unit = "MHz"
                        skipped.append("A converted from %s using the g of "
                                       "%g stated in the same clause" % (u, g_here))
                    else:
                        # No g anywhere, so no conversion is possible. Keep
                        # the paper's own unit rather than drop the value.
                        unit = "mT" if u == "mt" else "G"
                    if unit == "MHz" and abs(v) > MAX_A_MHZ:
                        skipped.append("A = %g MHz exceeds %g" % (v, MAX_A_MHZ))
                        continue
                    kind = classify_at(clause, m.start())
                    # A requires an explicit computational marker to count as
                    # computed. Unlike D, a hyperfine coupling in this corpus
                    # is an EPR observable far more often than a calculated
                    # one, and the "measured" that says so is routinely left
                    # behind in a neighbouring clause by the split.
                    if kind == "calc" and not CALC.search(clause[:m.start()]):
                        kind = "exp"
                        skipped.append("A taken as experimental: no "
                                       "computational marker precedes it")
                    if kind:
                        found.setdefault(("A", kind), []).append(
                            (round(v, 4), unit))

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
    """Serialise {(key, source): (value, unit)} to the packed field."""
    out = []
    for key, src in sorted(entries, key=lambda ks: (key_rank(ks[0]),
                                                    SOURCE_ORDER.index(ks[1]))):
        value, unit = entries[(key, src)]
        out.append("%s=%g%s %s" % (key, value, " " + unit if unit else "", src))
    return "; ".join(out)


def parse(field):
    """Inverse of fmt(): the packed field back to {(key, source): (value, unit)}.

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
        entries[(m.group(1), m.group(4))] = (float(m.group(2)), m.group(3))
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
        canonical = key_unit(name)
        # A key whose unit VARIES must compare value AND unit: 35.8 G and
        # 35.8 MHz are not the same number stated twice.
        distinct = ({(v, u) for v, u in vals} if canonical is VARIES
                    else {v for v, _ in vals})
        if len(distinct) > 1:
            skipped.append("%s (%s) disagrees across clauses: %s"
                           % (name, src, sorted(distinct, key=repr)))
            continue
        value, how = vals[0]
        if name == "E/D" and value > ED_MAX:
            skipped.append("E/D (%s) = %s exceeds the rhombic limit 1/3"
                           % (src, value))
            continue
        # For a fixed-unit key the extractor has already converted, so the
        # stored unit is the canonical one and `how` records where it came
        # from. For a VARIES key `how` IS the unit.
        entries[(name, src)] = (value, how if canonical is VARIES else canonical)
        if canonical is not VARIES and how in ("GHz", "MHz", "kHz", "THz", "K"):
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
                    key = LEGACY_KEYS[col]
                    entries[key] = (float(raw), key_unit(key[0]))
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
                    assert key in back and abs(back[key][0] - float(raw)) < 1e-9, (
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
    # Every key actually present, not just the fixed list: B(k,q) keys are
    # generated from the data and would otherwise never be reported.
    present = sorted({k.rsplit(" ", 1)[0] for k in counts}, key=key_rank)
    for key in present:
        for src in SOURCE_ORDER:
            n = counts.get("%s %s" % (key, src), 0)
            if n:
                print("   %-8s %-5s %5d rows" % (key, src, n))
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
