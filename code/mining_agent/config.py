"""Paths and defaults, matching the layout in CLAUDE.md.

All paths are derived from this file's location so the project can be
moved or renamed without breaking anything.
"""
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
    "system_class", "formula", "metal_center",
    "metal_ox_state", "d_electron_count", "ligand_set", "point_group",
    "geometry_source", "method", "software", "basis_set",
    "relativistic_treatment", "soc_included", "ss_included",
    "active_space_nel", "active_space_norb",
    "active_space_orbital_description", "active_space_protocol",
    "multiplicities_studied", "nroots_per_mult", "ground_state_mult",
    "electronic_structure_description", "Other",
    "reference_short", "reference_doi", "year", "notes",
    "correlation_correction", "entry_type", "mining_model", "open_access",
]

# system_class: what kind of system the row describes, so consumers can filter
# (it sits next to compound_name, since it describes the compound itself)
# without the mining policy deciding for them (user decision 2026-08-07: the
# database excludes nothing by system size or class).
#   atom         — a single atom or atomic ion
#   diatomic     — a two-atom species, metal dimers included
#   molecule     — three or more atoms, isolated/gas-phase or in solution
#   solid-state  — a site in a host lattice, a surface/adsorbate model or a
#                  bulk solid, however it is modelled (embedded cluster,
#                  bare cluster, periodic); wins over the size-based values
SYSTEM_CLASSES = ("atom", "diatomic", "molecule", "solid-state")

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
