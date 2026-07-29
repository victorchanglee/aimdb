"""Append validated rows to database/aimdb.csv.

The schema (column order included) was originally identical to
claude-casscf/database/literature.csv so mined rows could be merged into
the decision agent's reference database; as of 2026-07-28 that schema has
diverged (ground_state_term merged into electronic_structure_description —
see CLAUDE.md). Appending goes through here so a malformed dict can never
silently shift columns.
"""
import csv
import re

from . import config

# Detectors for the post-CASSCF dynamic-correlation correction applied to a
# result, matched (case-insensitively) against the `method` string. Ordered;
# all matches are reported. Bare "QDPT" is intentionally NOT a detector — it
# usually denotes spin-orbit quasi-degenerate PT (state mixing), not a
# correlation correction — whereas XMCQDPT2 is a genuine multireference PT2.
_CORRECTION_DETECTORS = [
    ("NEVPT2",   r"NEVPT"),
    ("CASPT2",   r"CASPT2"),
    ("RASPT2",   r"RASPT2"),
    ("CASPT3",   r"CASPT3|(?<![A-Z])PT3"),
    ("XMCQDPT2", r"XMCQDPT"),
    ("MRCI",     r"MRCI"),
    ("DDCI",     r"DDCI"),
    ("CIPSI",    r"CIPSI"),
    ("MRCC",     r"MRCC|MR-CC"),
]


def classify_correction(method):
    """Derive `correlation_correction` from a `method` string.

    Returns the name(s) of the dynamic-correlation correction(s) applied
    (e.g. "NEVPT2", "CASPT2; MRCI"), or "none" for a variational
    CASSCF/RASSCF/DMRG-only result. This is a restatement of the already-%
    extracted `method` field; an extractor may override it per row.
    """
    m = (method or "").upper()
    hits = [name for name, pat in _CORRECTION_DETECTORS if re.search(pat, m)]
    if not hits and re.search(r"PT2", m):   # generic +PT2 (e.g. ASCI+PT2)
        hits = ["PT2"]
    return "; ".join(dict.fromkeys(hits)) if hits else "none"


def ensure_header():
    config.ensure_layout()
    if not config.LITERATURE_CSV.exists():
        with open(config.LITERATURE_CSV, "w", newline="",
                  encoding="utf-8") as f:
            csv.writer(f).writerow(config.LITERATURE_COLUMNS)


def existing_entry_ids():
    if not config.LITERATURE_CSV.exists():
        return set()
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
        return {row["entry_id"] for row in csv.DictReader(f)}


def set_structure_file(entry_id, filename, note, provenance="ai_generated"):
    """Set structure_file/structure_provenance on an existing row and append
    to its notes — the one sanctioned in-place edit (user-directed structure
    generation)."""
    if provenance not in config.STRUCTURE_PROVENANCES:
        raise ValueError(f"bad provenance {provenance!r}, must be one of {config.STRUCTURE_PROVENANCES}")
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["entry_id"] == entry_id:
            row["structure_file"] = filename
            row["structure_provenance"] = provenance
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + note
            break
    else:
        raise ValueError(f"no row with entry_id {entry_id!r}")
    with open(config.LITERATURE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def ensure_contrib_header():
    config.CONTRIBUTIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not config.CONTRIBUTIONS_CSV.exists():
        with open(config.CONTRIBUTIONS_CSV, "w", newline="",
                  encoding="utf-8") as f:
            csv.writer(f).writerow(config.CONTRIB_COLUMNS)


def ingest_contributions(path):
    """Append rows from a website-submitted contribution CSV into
    database/contributions.csv (the maintainer's review queue). Unknown
    columns are ignored; missing ones default to empty. review_status
    defaults to 'pending'. Returns the number of rows appended."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        incoming = list(csv.DictReader(f))
    ensure_contrib_header()
    n = 0
    with open(config.CONTRIBUTIONS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.CONTRIB_COLUMNS)
        for src in incoming:
            row = {c: str(src.get(c, "") or "") for c in config.CONTRIB_COLUMNS}
            if not row.get("review_status"):
                row["review_status"] = "pending"
            writer.writerow(row)
            n += 1
    return n


def load_contributions():
    if not config.CONTRIBUTIONS_CSV.exists():
        return []
    with open(config.CONTRIBUTIONS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_row(fields):
    """Validate and append one row; raises ValueError on any problem."""
    unknown = set(fields) - set(config.LITERATURE_COLUMNS)
    if unknown:
        raise ValueError(f"unknown columns: {sorted(unknown)}")
    if not fields.get("entry_id"):
        raise ValueError("entry_id is required")
    if not fields.get("reference_doi"):
        raise ValueError(
            "reference_doi is required — a row without provenance is not "
            "addable (CLAUDE.md step 5)")
    if fields["entry_id"] in existing_entry_ids():
        raise ValueError(f"entry_id {fields['entry_id']!r} already exists")
    ensure_header()
    # Stamp the mining model automatically unless the caller set one.
    fields = {**fields}
    if not fields.get("mining_model"):
        fields["mining_model"] = config.CURRENT_MINING_MODEL
    # Derive the correlation correction from `method` unless the caller set it.
    if not fields.get("correlation_correction"):
        fields["correlation_correction"] = classify_correction(
            fields.get("method", ""))
    # Entry provenance: default to LLM mining, validate against the allowed set.
    if not fields.get("entry_type"):
        fields["entry_type"] = config.DEFAULT_ENTRY_TYPE
    elif fields["entry_type"] not in config.ENTRY_TYPES:
        raise ValueError(
            f"entry_type {fields['entry_type']!r} not in {config.ENTRY_TYPES}")
    row = {col: str(fields.get(col, "")) for col in config.LITERATURE_COLUMNS}
    with open(config.LITERATURE_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS).writerow(row)
    return row
