"""Append validated rows to database/literature.csv.

The schema (column order included) must stay identical to
claude-casscf/database/literature.csv so mined rows can be merged into
the decision agent's reference database. Appending goes through here so
a malformed dict can never silently shift columns.
"""
import csv

from . import config


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
    row = {col: str(fields.get(col, "")) for col in config.LITERATURE_COLUMNS}
    with open(config.LITERATURE_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS).writerow(row)
    return row
