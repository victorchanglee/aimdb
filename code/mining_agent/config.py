"""Paths and defaults, matching the layout in CLAUDE.md.

All paths are derived from this file's location so the project can be
moved or renamed without breaking anything.
"""
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CODE_DIR.parent

DATABASE_DIR = PROJECT_ROOT / "database"
PAPERS_DIR = PROJECT_ROOT / "papers"
TEXT_DIR = PROJECT_ROOT / "text"
LOGS_DIR = PROJECT_ROOT / "logs"

LITERATURE_CSV = DATABASE_DIR / "literature.csv"
PAPERS_INDEX_CSV = DATABASE_DIR / "papers_index.csv"
EXTRACTIONS_LOG = LOGS_DIR / "extractions.csv"

OPENALEX_WORKS_URL = "https://api.openalex.org/works"

# Polite-pool identification for OpenAlex and publisher servers.
MAILTO = "victorchanglee@gmail.com"
USER_AGENT = f"casscf-literature-miner/0.1 (mailto:{MAILTO})"

# Seconds between consecutive HTTP requests.
REQUEST_INTERVAL = 1.0
# Refuse PDFs larger than this (broken links sometimes serve huge blobs).
MAX_PDF_BYTES = 80 * 1024 * 1024

# The LLM (Claude model) that performed the extraction. Stamped onto every
# new row by append_row() when the row doesn't already carry one. BUMP THIS
# whenever the mining model changes so provenance stays accurate; a session
# may also override per-row by passing "mining_model" in the add-row JSON.
CURRENT_MINING_MODEL = "claude-opus-4-8"

# literature.csv column order. The first 30 columns are identical to
# claude-casscf/database/literature.csv so rows can be merged;
# "correlation_correction" and "mining_model" are aimdb-only columns appended
# LAST, so a merge into the decision agent's database can simply drop the
# trailing fields.
LITERATURE_COLUMNS = [
    "entry_id", "structure_file", "compound_name", "formula", "metal_center",
    "metal_ox_state", "d_electron_count", "ligand_set", "point_group",
    "geometry_source", "method", "software", "basis_set",
    "relativistic_treatment", "soc_included", "ss_included",
    "active_space_nel", "active_space_norb",
    "active_space_orbital_description", "active_space_protocol",
    "multiplicities_studied", "nroots_per_mult", "ground_state_mult",
    "ground_state_term", "low_lying_states_eV", "Other",
    "reference_short", "reference_doi", "year", "notes",
    "correlation_correction", "mining_model",
]

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


def ensure_layout():
    for d in (DATABASE_DIR, PAPERS_DIR, TEXT_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
