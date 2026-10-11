"""Paths and defaults, matching the layout in CLAUDE.md.

All paths are derived from this file's location so the project can be
moved or renamed without breaking anything.
"""
import re
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CODE_DIR.parent

DATABASE_DIR = PROJECT_ROOT / "database"
PAPERS_DIR = PROJECT_ROOT / "papers"
# Downloaded PDFs live in one of two queues: pending/ until the paper has been
# read and judged, then mined/. index.set_status() moves the file across
# automatically when a paper reaches one of MINED_STATUSES.
PAPERS_PENDING_DIR = PAPERS_DIR / "pending"
PAPERS_MINED_DIR = PAPERS_DIR / "mined"
SI_DIR = PAPERS_DIR / "si"
TEXT_DIR = PROJECT_ROOT / "text"
LOGS_DIR = PROJECT_ROOT / "logs"

LITERATURE_CSV = DATABASE_DIR / "aimdb.csv"
PAPERS_INDEX_CSV = DATABASE_DIR / "papers_index.csv"
EXTRACTIONS_LOG = LOGS_DIR / "extractions.csv"
# Community submissions from the website form, collected here for maintainer
# review — never auto-merged into aimdb.csv.
CONTRIBUTIONS_CSV = DATABASE_DIR / "contributions.csv"

OPENALEX_WORKS_URL = "https://api.openalex.org/works"

# Polite-pool identification for OpenAlex and publisher servers.
MAILTO = "victorchanglee@gmail.com"
USER_AGENT = f"casscf-literature-miner/0.1 (mailto:{MAILTO})"

# Seconds between consecutive HTTP requests.
REQUEST_INTERVAL = 1.0
# Refuse PDFs larger than this (broken links sometimes serve huge blobs).
MAX_PDF_BYTES = 80 * 1024 * 1024

# The LLM that performed the extraction. Stamped onto every
# new row by append_row() when the row doesn't already carry one. BUMP THIS
# whenever the mining model changes so provenance stays accurate; a session
# may also override per-row by passing "mining_model" in the add-row JSON.
CURRENT_MINING_MODEL = "claude-opus-5"

# How an entry was produced (provenance). Allowed values and the default used
# when a row omits "entry_type":
#   llm_mining     — extracted from the published literature by an LLM (default)
#   llm_reproduced — a calculation an LLM actually re-ran/reproduced
#   human          — entered by a human
ENTRY_TYPES = ("llm_mining", "llm_reproduced", "human")
DEFAULT_ENTRY_TYPE = "llm_mining"

# Version of the aimdb.csv schema, for consumers reading through
# mining_agent.query. BUMP THIS whenever LITERATURE_COLUMNS changes: the
# moment anything outside this repo depends on the column set, that set is a
# contract, and it has drifted once already (2026-07-28, see below).
# query.schema() also publishes a fingerprint derived from the column names,
# so a change that forgets this bump is still detectable downstream.
SCHEMA_VERSION = "2.0"

# aimdb.csv (formerly literature.csv) column order. Originally the first 30
# columns were identical to claude-casscf/database/literature.csv so rows
# could be merged directly; as of 2026-07-28 "ground_state_term" was merged into
# "low_lying_states_eV" (renamed "electronic_structure_description", with
# any ground-state-term text prefixed as "Ground term: ..."), so this
# schema has DIVERGED from claude-casscf until that project adopts the same
# change. "correlation_correction", "entry_type" and "mining_model" remain
# aimdb-only columns appended LAST.
LITERATURE_COLUMNS = [
    "entry_id", "structure_file", "structure_provenance", "compound_name",
    "system_class", "formula", "metal_center", "element",
    "metal_ox_state", "d_electron_count", "ligand_set", "point_group",
    "geometry_source", "method", "software", "basis_set",
    "relativistic_treatment", "soc_included", "ss_included",
    "active_space_nel", "active_space_norb",
    "active_space_orbital_description", "active_space_protocol",
    "multiplicities_studied", "nroots_per_mult", "ground_state_mult",
    "electronic_structure_description", "Other",
    "reference_short", "reference_doi", "year", "notes",
    "correlation_correction", "entry_type", "mining_model", "open_access",
    "date_added",
    "properties",
]

# "date_added" (added 2026-10-09, SCHEMA_VERSION 1.0 -> 1.1) is the UTC date
# the row entered the database, as dd/mm/yyyy (user-chosen format, 2026-10-09;
# note it does not sort lexicographically). It was backfilled from two
# sources and is NOT uniformly precise:
#   * 10,127 rows from the add-row timestamp in logs/extractions.csv, which is
#     exact to the second;
#   * 2,422 older rows, predating that logging, from the committer date of the
#     first commit whose database/aimdb.csv contained the entry_id. For those
#     the true addition can be anywhere between the previous commit and that
#     one, so treat the date as an upper bound.
# Cross-checking the 10,123 rows carrying both sources, exactly one disagrees
# once both are normalised to UTC: W4413906376-a logs an add-row on 2026-08-28
# but its entry_id already appears in a commit of 2026-08-11, which suggests an
# id reused after a removal. Everything else is consistent.
# add-row fills this automatically; see csvio.append_row.

# "year" is not one quantity. For an llm_mining row it is the source paper's
# publication year. For an llm_reproduced row it is the year the CALCULATION
# was performed (2026-10-10 sweep -> 2026, set by
# code/tools/tools_properties.py's sibling pass), because a result computed
# this year should not sort or filter as decade-old literature just because
# the compound was described then. The paper's own year stays available in
# reference_short, which states it on every reproduced row, and in
# papers_index.csv via reference_doi.

# "properties" (SCHEMA_VERSION 1.2 -> 2.0, 2026-10-10) holds the measurable
# physical quantities a row reports, as one packed field. It REPLACED four
# dedicated columns -- zfs_D_calc, zfs_ED_calc, zfs_D_exp, zfs_ED_exp -- which
# is why this is a major version bump rather than a minor one: a consumer
# reading those names will not find them. The migration was lossless and is
# reversible from tools/tools_properties.py --migrate.
#
# The four columns were added on 2026-10-10 and replaced the same day, for a
# reason worth recording. Lanthanides do not report a spin-Hamiltonian D at
# all: for a 4f ion spin-orbit coupling dominates the ligand field, so papers
# give crystal-field parameters, doublet g-tensors and a relaxation barrier
# instead. Of 1,028 lanthanide rows exactly 14 carried any ZFS value, so the
# dedicated columns simply did not reach that chemistry. Adding a second set
# for the crystal-field quantities would have worked once and then again for
# hyperfine, exchange coupling, quadrupole moments; every new observable a
# paper happens to report would be another schema bump and another always-empty
# column on the 95% of rows that do not report it. One field that names its own
# contents does not grow.
#
# FORMAT. Entries separated by "; ", each one
#
#     KEY=VALUE[ UNIT] SOURCE
#
# with SOURCE either "calc" (this row's own calculation) or "exp" (a measured
# value the paper quotes). UNIT is omitted when the quantity is dimensionless.
# Values are plain numbers, already converted to the canonical unit below.
#
#     D=-31.5 cm-1 calc; E/D=0.152 calc; D=-28.9 cm-1 exp; gz=19.86 calc
#
# Keys in use, with their canonical units:
#
#     D      axial zero-field-splitting parameter, cm-1
#     E/D    rhombicity, dimensionless, <= 1/3 by definition
#     gx gy gz   principal components of the Zeeman g tensor, dimensionless.
#                gz also absorbs g_par and, in a doublet context, g_eff --
#                both name the axial component. See the warning below.
#     gperp      the in-plane component, where a paper reports only g_perp
#     giso       isotropic or average g
#     Ueff   magnetisation-reversal barrier, cm-1
#
# The key list is open: a new quantity is a new key, not a new column. Keep it
# in step with KEYS in tools/tools_properties.py, which is the only writer, and
# with PROPS in docs/index.html, which is the only reader that filters on it.
#
# Why SOURCE is part of every entry rather than part of the key: a paper
# reporting a property almost always reports both a computed and a measured
# value, and a field that did not distinguish them would let the database
# assert an ab initio result for a number somebody measured.
#
# Populated by tools/tools_properties.py from the prose already in each row, so
# the values stay grounded in the source and benchmark/check_grounding.py still
# covers them. The tool is re-runnable and documents the false-positive classes
# that repeated hand-scoring found: a "D" that was a Debye unit or a DMRG bond
# dimension, a pseudo-Jahn-Teller gap in eV, a ligand-field parameter of
# 2800 cm-1, the D inside "E/D", a range written with an en-dash, a value
# belonging to another complex, a reaction barrier in kcal/mol read as a
# magnetic one, and a g_z belonging to an excited doublet. Where a clause
# offers more than one candidate the entry is OMITTED rather than guessed,
# which is why far fewer rows carry a value than mention the quantity.
#
#
# A WARNING about the g keys. gz is the z principal component of the Zeeman g
# tensor -- the same quantity as the familiar g factor, which is just its
# isotropic case -- but the SPIN it multiplies differs between rows, and the
# two senses are not comparable:
#
#   * true spin. g multiplies the real electron spin S in
#     H = mu_B B.g.S + D[Sz^2 - S(S+1)/3] + ..., and the values sit near the
#     free-electron 2.0023. This is what a 3d complex reports.
#   * effective, pseudospin-1/2. For a Kramers doublet the two states are
#     mapped onto a fictitious S = 1/2, and g then absorbs the orbital
#     moment: the ceiling is 2*g_J*|m_J|, which is 20.00 for Dy(III)
#     (g_J = 4/3, m_J = 15/2) and for Ho(III). A gz of 19.86 is NOT a tenfold
#     larger magnetic response than a gz of 2.0; it is the same physics
#     written in a different spin basis.
#
# So gz = 19.9 and gz = 2.0 must not be averaged, ranked or plotted on one
# axis without saying which convention each row uses. The split is visible in
# the data and tracks the block: of the 99 gz values extracted, the 69 above 4
# are 99% f-block, and 70% of the 30 at or below 4 are d-block. The convention
# is not stored as a separate key because the paper rarely states it in the
# sentence the value comes from, and inferring it from the magnitude would be
# exactly the kind of guess this database does not make.
# D is cm-1 throughout; GHz, MHz, kHz, THz and K are converted on the way in.
# Magnetic field units (gauss, mT, T) are refused rather than converted, since
# D in gauss becomes cm-1 only through g*mu_B for that species. E itself is not
# stored: E/D is the dimensionless measure consumers compare, and E is
# recoverable as E/D * D.

# The QUEST export boundary (CLAUDE.md, "QUEST-sourced rows: keep here,
# filter on export"). QUEST is held out as a benchmark in
# claude-casscf/test/questdb/, so rows mined from a QUEST-series or
# QUEST-adjacent paper must not reach a database the decision agent reads.
# Enforced by tools/tools_export.py and by mining_agent.query, which both
# import this list — it used to live in the tool alone, and a 2026-08-03 bulk
# refresh that bypassed the tool carried 14 QUEST rows into literature.csv and
# had to be reverted. Keep in sync with the annotated list in CLAUDE.md.
QUEST_DOIS = {
    "10.1021/acs.jctc.8b01205",   # Reference Energies for Double Excitations
    "10.48550/arxiv.2409.00302",  # QUEST#4X
    "10.1063/5.0095887",          # CASPT3 benchmark (QUEST-adjacent)
    "10.1002/wcms.1517",          # QUESTDB, the database paper itself
    "10.1021/acs.jctc.9b01216",   # QUEST#3, Mountaineering Strategy
    "10.1021/acs.jctc.4c00410",   # Double Excitations: Improvement and Extension
    "10.1021/acs.jctc.3c01080",   # Transition metal compounds (QUEST-TM)
    "10.1021/acs.jctc.1c01197",   # CASPT2 vs NEVPT2 assessment (QUEST-adjacent)
}

# A row mentioning QUEST outside the known DOIs is reported, never dropped —
# a paper mined without being added to the list above shows up this way.
QUEST_TEXT = re.compile(r"\bquest\b", re.I)
QUEST_SCAN_FIELDS = ("reference_short", "notes", "compound_name",
                     "active_space_protocol")

# system_class: what kind of system the row describes, so consumers can filter
# (it sits next to compound_name, since it describes the compound itself)
# without the mining policy deciding for them (user decision 2026-08-07: the
# database excludes nothing by system size or class).
#   atom         — a single atom or atomic ion
#   molecule     — any bound species of two or more atoms, isolated/gas-phase
#                  or in solution; diatomics included (user decision
#                  2026-08-10: O2 and N2 are molecules, so the former
#                  `diatomic` value was merged into this one and the 221 rows
#                  carrying it were relabelled)
#   cluster-model — a finite cluster standing in for a larger system: an
#                  embedded or bare cluster cut from a solid, a surface/
#                  adsorbate cluster, an enzyme active-site model, a QM/MM QM
#                  region. Added 2026-08-14; 419 rows moved here, 403 of them
#                  from solid-state. Displayed as "Cluster model" on the site.
#   solid-state  — a site in a host lattice or a bulk solid treated as
#                  EXTENDED (periodic/PBC). A finite cluster standing in for
#                  such a system is `cluster-model`, not `solid-state`.
SYSTEM_CLASSES = ("atom", "molecule", "cluster-model", "solid-state")

# open_access: is reference_doi open access according to OpenAlex?
#   yes / no  — OpenAlex's open_access.is_oa for that DOI
#   unknown   — OpenAlex has no record of that DOI
#   (empty)   — not checked yet; a freshly added row until tools_oa.py --stamp
# Refreshed in bulk by code/tools_oa.py, which also keeps the full answer
# (oa_status gold/hybrid/green/bronze/closed, best OA URL) in logs/oa_status.csv.
# Not a property of the calculation — it is access metadata about the source,
# so it goes last and claude-casscf merges drop it alongside mining_model.
OPEN_ACCESS_VALUES = ("yes", "no", "unknown")

# d_electron_count: the open-shell valence count of the metal centre, for the
# d block AND the f block, always written with its shell — 3d7, 4d9, 5d6,
# 4f9, 5f2 (never bare "d7", "f9" or "7"). The shell follows from
# metal_center: Sc-Zn 3d, Y-Cd 4d, Hf-Hg 5d, La-Lu 4f, Ac-Lr 5f; the count is
# the group valence electron count minus the oxidation state. Empty for
# main-group centres. The name is historical (schema parity with
# claude-casscf); the website labels the column "d/f electron count".

# structure_provenance: how the coordinates in structure_file were obtained.
#   computational  — geometry the paper itself computed/optimized (DFT, etc.)
#   experimental    — geometry the paper took from X-ray/neutron/other measurement
#   ai_generated    — a PubChem conformer stand-in, NOT the paper's real geometry
# Empty when structure_file is empty. structures.save_structure() (the only
# coded path) always writes "ai_generated"; the VERBATIM-from-SI path is
# manual (see CLAUDE.md) and must set this explicitly per paper.
STRUCTURE_PROVENANCES = ("computational", "experimental", "ai_generated")

# contributions.csv schema: review metadata first, then the full literature
# schema (so an approved contribution promotes straight into aimdb.csv).
# The website form emits exactly these columns.
CONTRIB_META_COLUMNS = [
    "submitted_at", "contributor_name", "contributor_email", "review_status",
]
CONTRIB_COLUMNS = CONTRIB_META_COLUMNS + LITERATURE_COLUMNS

INDEX_COLUMNS = [
    "key", "doi", "title", "year", "oa_pdf_url", "source",
    "status", "pdf_path", "text_path", "updated",
]

# Lifecycle: candidate -> fetched -> text_ready -> extracted /
# extracted_partial / not_usable, with fetch_failed / text_unreadable as
# terminal error states (retryable by explicit --key).
INDEX_STATUSES = {
    "candidate", "fetched", "fetch_failed", "text_ready",
    "text_unreadable", "extracted", "extracted_partial", "not_usable",
}

# Statuses meaning "this paper has been read and judged" — whatever the
# verdict. Reaching one of these moves the PDF from papers/pending/ to
# papers/mined/, so pending/ always shows exactly the work still to do.
MINED_STATUSES = {
    "extracted", "extracted_partial", "not_usable", "text_unreadable",
}


def ensure_layout():
    for d in (DATABASE_DIR, PAPERS_DIR, PAPERS_PENDING_DIR, PAPERS_MINED_DIR,
              TEXT_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def rel_path(path):
    """Store paths relative to PROJECT_ROOT so renaming or moving the project
    never invalidates the index (absolute paths did break on the 2026-07-28
    rename)."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def abs_path(stored):
    """Resolve a stored (relative or legacy-absolute) path against the
    project root."""
    if not stored:
        return None
    path = Path(stored)
    return path if path.is_absolute() else PROJECT_ROOT / path
