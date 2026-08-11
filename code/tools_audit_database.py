#!/usr/bin/env python3
"""Generate a row-level completeness and source-evidence audit for AIMdb.

This is deliberately an audit, not an extractor: it never fills database
fields.  When a recovered source map is supplied, it checks whether each
numeric active-space pair can be located in the mapped full text and records
the source-matching strength.  Human/LLM rereads and corrections remain in
logs/extractions.csv.

Usage:
  python3 code/tools_audit_database.py \
      --source-map /tmp/aimdb_full_audit_source_map.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database/aimdb.csv"
INDEX = ROOT / "database/papers_index.csv"
OUTPUT = ROOT / "logs/full_database_audit.csv"
QUEUE = ROOT / "logs/second_read_queue.csv"
EXTRACTIONS = ROOT / "logs/extractions.csv"

CORE_FIELDS = (
    "active_space_nel",
    "active_space_norb",
    "active_space_orbital_description",
    "basis_set",
    "software",
)
SUBSTANTIVE_FIELDS = (
    "compound_name", "system_class", "formula", "metal_center",
    "metal_ox_state", "d_electron_count", "ligand_set", "point_group",
    "geometry_source", "method", "software", "basis_set",
    "relativistic_treatment", "soc_included", "ss_included",
    "active_space_nel", "active_space_norb",
    "active_space_orbital_description", "active_space_protocol",
    "multiplicities_studied", "nroots_per_mult", "ground_state_mult",
    "electronic_structure_description", "Other", "correlation_correction",
)
VALID_SYSTEM_CLASSES = {"atom", "molecule", "solid-state"}
VALID_ENTRY_TYPES = {"llm_mining", "llm_reproduced", "human"}
VALID_OA = {"yes", "no", "unknown"}
AUDIT_FIELDS = (
    "audited_on", "entry_id", "reference_doi", "mining_model",
    "documented_read_depth", "source_status", "source_match_method",
    "source_match_confidence", "active_pair_text_evidence",
    "filled_substantive_fields", "missing_core_fields", "schema_issues",
    "audit_action",
)
QUEUE_FIELDS = (
    "tier", "key", "doi", "title", "status", "rows", "rows_with_gaps",
    "priority_score", "missing_nel", "missing_norb",
    "missing_orbital_description", "missing_basis_set", "missing_software",
    "mining_model", "text_available", "si_fetched",
)


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def source_map(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    _, rows = load_csv(path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        doi = row.get("doi", "").strip().lower()
        if doi:
            grouped[doi].append(row)

    def rank(row: dict[str, str]) -> tuple[int, int, float, int]:
        text_path = Path(row.get("text_path", ""))
        size = text_path.stat().st_size if text_path.is_file() else 0
        return (
            row.get("method") in {"doi", "index_key"},
            row.get("confidence") == "high",
            float(row.get("title_score") or 0),
            size,
        )

    return {doi: max(candidates, key=rank) for doi, candidates in grouped.items()}


def numeric(value: str) -> int | None:
    return int(value) if value.strip().isdigit() else None


def pair_evidence(row: dict[str, str], source: dict[str, str] | None) -> str:
    nel = numeric(row["active_space_nel"])
    norb = numeric(row["active_space_norb"])
    if nel is None or norb is None:
        return "not_applicable" if not row["active_space_nel"].strip() and not row["active_space_norb"].strip() else "symbolic_or_partial"
    if source is None:
        return "source_unavailable"
    path = Path(source.get("text_path", ""))
    if not path.is_file():
        return "source_unavailable"
    text = path.read_text(encoding="utf-8", errors="ignore")
    patterns = (
        rf"\(\s*{nel}\s*[,;/]\s*{norb}\s*\)",
        rf"\b{nel}\s*(?:e|electrons?)\s*[,;/ ]+\s*{norb}\s*(?:o|orbitals?)\b",
        rf"\b{nel}\s+(?:active\s+)?electrons?\b.{{0,100}}\b{norb}\s+(?:active\s+)?orbitals?\b",
        rf"\b{norb}\s+(?:active\s+)?orbitals?\b.{{0,100}}\b{nel}\s+(?:active\s+)?electrons?\b",
    )
    return "located" if any(re.search(pattern, text, re.I | re.S) for pattern in patterns) else "not_machine_located"


def source_status(source: dict[str, str] | None) -> str:
    if source is None:
        return "unavailable"
    if source.get("method") in {"doi", "index_key"}:
        return "exact_doi_text"
    if source.get("method") == "title":
        return "title_matched_text"
    return "mapped_text"


def row_issues(row: dict[str, str], duplicate_ids: set[str]) -> list[str]:
    issues = []
    if row["entry_id"] in duplicate_ids:
        issues.append("duplicate_entry_id")
    if not row["reference_doi"].strip():
        issues.append("missing_doi")
    if row["system_class"] not in VALID_SYSTEM_CLASSES:
        issues.append("invalid_system_class")
    if row["entry_type"] not in VALID_ENTRY_TYPES:
        issues.append("invalid_entry_type")
    if row["open_access"] not in VALID_OA:
        issues.append("invalid_open_access")
    if bool(row["structure_file"].strip()) != bool(row["structure_provenance"].strip()):
        issues.append("structure_provenance_mismatch")
    if row["soc_included"].strip().lower() not in {"", "yes", "no"}:
        issues.append("noncanonical_soc_flag")
    if row["ss_included"].strip().lower() not in {"", "yes", "no"}:
        issues.append("noncanonical_ss_flag")
    if bool(row["active_space_nel"].strip()) != bool(row["active_space_norb"].strip()):
        issues.append("partial_active_pair")
    return issues


def documented_depth(row: dict[str, str]) -> str:
    notes = row["notes"].lower()
    if "full-database source audit (gpt-5.6, 2026-08-11)" in notes:
        return "comprehensive_source_reread_2026-08-11"
    if "comprehensively reviewed supplied full text" in notes or "comprehensive main-text review" in notes:
        return "comprehensive_read_documented"
    if "mined from oa text" in notes or "full text" in notes or "re-read" in notes or "reread" in notes:
        return "source_read_documented"
    return "not_documented"


def queue_tier(rows: list[dict[str, str]], source: dict[str, str] | None) -> str:
    if any(not row["active_space_nel"].strip() or not row["active_space_norb"].strip() for row in rows):
        return "A-active-space"
    if any(not row["active_space_orbital_description"].strip() or not row["basis_set"].strip() for row in rows):
        return "B-basis-orbitals" if source else "C-refetch"
    return "D-software-only" if source else "C-refetch"


def decision_reasoning(row: dict[str, str]) -> str:
    return (
        "GPT-5.6 full-database audit; audited_on=" + row["audited_on"]
        + "; documented_read_depth=" + row["documented_read_depth"]
        + "; source_status=" + row["source_status"]
        + "; source_match=" + (row["source_match_method"] or "none")
        + "/" + (row["source_match_confidence"] or "none")
        + "; active_pair_evidence=" + row["active_pair_text_evidence"]
        + "; filled_substantive_fields=" + row["filled_substantive_fields"]
        + "; missing_core_fields=" + (row["missing_core_fields"] or "none")
        + "; schema_issues=" + (row["schema_issues"] or "none") + "."
    )


def append_extraction_trail(audit: list[dict[str, str]]) -> int:
    """Append one checkable audit decision for every database entry."""
    with EXTRACTIONS.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        previous = list(reader)
    required = {"timestamp", "key", "doi", "action", "result", "reasoning"}
    if not required.issubset(fields):
        raise ValueError(f"unexpected extraction-log columns: {fields}")
    prior_base = {
        row["key"]: row
        for row in previous
        if row["action"] == "full_database_row_audit"
        and "audited_on=2026-08-11" in row["reasoning"]
    }
    reconciliation_prefix = "Supersedes the earlier same-day row audit after rebuilding the complete source map; "
    exact_seen = {
        (row["key"], row["result"], row["reasoning"].removeprefix(reconciliation_prefix))
        for row in previous
        if row["action"] in {"full_database_row_audit", "full_database_row_audit_reconciliation"}
    }
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    pending = []
    for row in audit:
        entry_id = row["entry_id"]
        reasoning = decision_reasoning(row)
        signature = (entry_id, row["audit_action"], reasoning)
        if signature in exact_seen:
            continue
        action = "full_database_row_audit_reconciliation" if entry_id in prior_base else "full_database_row_audit"
        if action.endswith("reconciliation"):
            reasoning = reconciliation_prefix + reasoning
        pending.append({
            "timestamp": now,
            "key": entry_id,
            "doi": row["reference_doi"],
            "action": action,
            "result": row["audit_action"],
            "reasoning": reasoning,
        })
    if pending:
        with EXTRACTIONS.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writerows(pending)
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-map", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--queue", type=Path, default=QUEUE)
    parser.add_argument(
        "--append-extraction-trail",
        action="store_true",
        help="append one full_database_row_audit decision per database entry",
    )
    args = parser.parse_args()

    _, rows = load_csv(DB)
    _, index_rows = load_csv(INDEX)
    sources = source_map(args.source_map)
    id_counts = Counter(row["entry_id"] for row in rows)
    duplicate_ids = {entry_id for entry_id, count in id_counts.items() if count > 1}
    index_by_doi = {row["doi"].strip().lower(): row for row in index_rows}

    audit = []
    for row in rows:
        doi = row["reference_doi"].strip().lower()
        source = sources.get(doi)
        missing_core = [field for field in CORE_FIELDS if not row[field].strip()]
        issues = row_issues(row, duplicate_ids)
        evidence = pair_evidence(row, source)
        depth = documented_depth(row)
        if "2026-08-11" in depth:
            action = "corrected_or_enriched_from_comprehensive_reread"
        elif issues:
            action = "schema_followup"
        elif source_status(source) == "exact_doi_text" and evidence in {"located", "not_applicable"} and not missing_core:
            action = "source_evidence_and_completeness_pass"
        elif source is None:
            action = "source_recovery_needed"
        else:
            action = "manual_source_reread_needed"
        audit.append({
            "audited_on": "2026-08-11", "entry_id": row["entry_id"],
            "reference_doi": row["reference_doi"], "mining_model": row["mining_model"],
            "documented_read_depth": depth, "source_status": source_status(source),
            "source_match_method": source.get("method", "") if source else "",
            "source_match_confidence": source.get("confidence", "") if source else "",
            "active_pair_text_evidence": evidence,
            "filled_substantive_fields": str(sum(bool(row[field].strip()) for field in SUBSTANTIVE_FIELDS)),
            "missing_core_fields": ";".join(missing_core),
            "schema_issues": ";".join(issues), "audit_action": action,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(audit)

    by_doi: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if any(not row[field].strip() for field in CORE_FIELDS):
            by_doi[row["reference_doi"].strip().lower()].append(row)
    queue = []
    weights = {"active_space_nel": 6, "active_space_norb": 6, "active_space_orbital_description": 4, "basis_set": 3, "software": 1}
    for doi, gap_rows in by_doi.items():
        all_rows = [row for row in rows if row["reference_doi"].strip().lower() == doi]
        index_row = index_by_doi.get(doi, {})
        missing = {field: sum(not row[field].strip() for row in gap_rows) for field in CORE_FIELDS}
        source = sources.get(doi)
        key = index_row.get("key") or gap_rows[0]["entry_id"].rsplit("-", 1)[0]
        queue.append({
            "tier": queue_tier(gap_rows, source), "key": key, "doi": gap_rows[0]["reference_doi"],
            "title": index_row.get("title") or gap_rows[0]["reference_short"],
            "status": index_row.get("status", ""), "rows": str(len(all_rows)),
            "rows_with_gaps": str(len(gap_rows)),
            "priority_score": str(sum(weights[field] * count for field, count in missing.items())),
            "missing_nel": str(missing["active_space_nel"]),
            "missing_norb": str(missing["active_space_norb"]),
            "missing_orbital_description": str(missing["active_space_orbital_description"]),
            "missing_basis_set": str(missing["basis_set"]),
            "missing_software": str(missing["software"]),
            "mining_model": gap_rows[0]["mining_model"],
            "text_available": "yes" if source else "no",
            "si_fetched": "yes" if index_row.get("si_status") == "fetched" else "no",
        })
    tier_order = {"A-active-space": 0, "B-basis-orbitals": 1, "D-software-only": 2, "C-refetch": 3}
    queue.sort(key=lambda row: (tier_order[row["tier"]], -int(row["priority_score"]), row["doi"]))
    with args.queue.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(queue)

    appended = append_extraction_trail(audit) if args.append_extraction_trail else 0

    source_counts = Counter(row["source_status"] for row in audit)
    action_counts = Counter(row["audit_action"] for row in audit)
    print(f"audited {len(audit)} rows across {len({row['reference_doi'].lower() for row in rows})} papers")
    print("sources:", dict(sorted(source_counts.items())))
    print("actions:", dict(sorted(action_counts.items())))
    print(f"wrote {args.output}")
    print(f"wrote {args.queue} ({len(queue)} papers)")
    if args.append_extraction_trail:
        print(f"appended {appended} row-level decisions to {EXTRACTIONS}")


if __name__ == "__main__":
    main()
