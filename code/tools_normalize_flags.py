#!/usr/bin/env python3
"""Normalize verbose SOC/SS flags while preserving their evidence text."""

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database/aimdb.csv"
LOG = ROOT / "logs/extractions.csv"
NOTE = "Full-database schema audit (GPT-5.6, 2026-08-11): normalized verbose SOC/SS flags to yes/no and retained the original wording in Other."


def normalized(value: str, column: str) -> str:
    low = value.strip().lower()
    if low in {"", "yes", "no"}:
        return low
    if low.startswith("yes"):
        return "yes"
    if low.startswith("no"):
        return "no"
    if column == "soc_included" and low.startswith("spin-orbit couplings computed"):
        return "yes"
    if column == "soc_included" and low.startswith("computed and found negligible"):
        return "no"
    raise ValueError(f"cannot normalize {column}: {value!r}")


with DB.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    fields = list(reader.fieldnames or [])
    rows = list(reader)

changed = defaultdict(list)
for row in rows:
    details = []
    for column, label in (("soc_included", "SOC detail"), ("ss_included", "SS detail")):
        original = row[column].strip()
        canonical = normalized(original, column)
        if original and original.lower() != canonical:
            details.append(f"{label}: {original}")
            row[column] = canonical
    if not details:
        continue
    for detail in details:
        if detail not in row["Other"]:
            row["Other"] = (row["Other"].rstrip(" ;") + "; " + detail).strip(" ;")
    if NOTE not in row["notes"]:
        row["notes"] = (row["notes"].rstrip() + " " + NOTE).strip()
    changed[row["reference_doi"]].append(row["entry_id"])

with DB.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

with LOG.open(newline="", encoding="utf-8") as handle:
    log_reader = csv.DictReader(handle)
    log_fields = list(log_reader.fieldnames or [])
    logs = list(log_reader)
seen = {(row["doi"].lower(), row["action"]) for row in logs}
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
for doi, ids in sorted(changed.items()):
    if (doi.lower(), "full_database_schema_audit") in seen:
        continue
    logs.append({
        "timestamp": now, "key": ids[0].rsplit("-", 1)[0], "doi": doi,
        "action": "full_database_schema_audit",
        "result": f"normalized SOC/SS flags in {len(ids)} row(s)",
        "reasoning": "Canonicalized the flag columns to yes/no; retained each source-specific explanation verbatim in Other.",
    })
with LOG.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=log_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(logs)

print(f"normalized {sum(map(len, changed.values()))} rows across {len(changed)} papers")
