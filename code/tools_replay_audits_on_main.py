#!/usr/bin/env python3
"""Replay a clean local AIMDB audit delta onto a newer main branch.

The old base and audited CSVs are supplied explicitly.  A field is replayed only
when the current row still contains the old-base value (or already contains the
audited value).  Any genuine three-way conflict aborts before either repository
CSV is written.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "aimdb.csv"
EXTRACTIONS = ROOT / "logs" / "extractions.csv"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def by_entry_id(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {row["entry_id"]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("duplicate entry_id encountered")
    return result


def log_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["key"],
        row["doi"].casefold(),
        row["action"],
        row["result"],
        row["reasoning"],
    )


def append_logs(rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    # origin/main uses LF for this file; preserve that convention.
    with EXTRACTIONS.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-db", type=Path, required=True)
    parser.add_argument("--audited-db", type=Path, required=True)
    parser.add_argument("--base-log", type=Path, required=True)
    parser.add_argument("--audited-log", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    base_fields, base_rows = read_csv(args.base_db)
    audited_fields, audited_rows = read_csv(args.audited_db)
    current_fields, current_rows = read_csv(DATABASE)
    if base_fields != audited_fields or base_fields != current_fields:
        raise RuntimeError("database schemas differ")

    base = by_entry_id(base_rows)
    audited = by_entry_id(audited_rows)
    current = by_entry_id(current_rows)
    if set(base) != set(audited):
        raise RuntimeError("the audited snapshot added or removed database rows")

    changed_rows = 0
    changed_cells = 0
    already_cells = 0
    conflicts: list[tuple[str, str, str, str, str]] = []
    for entry_id in base:
        local_changes = {
            field: audited[entry_id][field]
            for field in base_fields
            if audited[entry_id][field] != base[entry_id][field]
        }
        if not local_changes:
            continue
        changed_rows += 1
        if entry_id not in current:
            conflicts.append((entry_id, "entry_id", "present", "present", "missing"))
            continue
        for field, audited_value in local_changes.items():
            base_value = base[entry_id][field]
            current_value = current[entry_id][field]
            if current_value == audited_value:
                already_cells += 1
            elif current_value == base_value:
                current[entry_id][field] = audited_value
                changed_cells += 1
            else:
                conflicts.append((entry_id, field, base_value, audited_value, current_value))

    base_log_fields, base_logs = read_csv(args.base_log)
    audited_log_fields, audited_logs = read_csv(args.audited_log)
    current_log_fields, current_logs = read_csv(EXTRACTIONS)
    if base_log_fields != audited_log_fields or base_log_fields != current_log_fields:
        raise RuntimeError("extraction-log schemas differ")
    if audited_logs[: len(base_logs)] != base_logs:
        raise RuntimeError("audited extraction log is not a pure append to its base")
    local_log_additions = audited_logs[len(base_logs) :]
    if len({log_key(row) for row in local_log_additions}) != len(local_log_additions):
        raise RuntimeError("duplicate records inside local extraction-log additions")
    current_keys = {log_key(row) for row in current_logs}
    logs_to_append = [row for row in local_log_additions if log_key(row) not in current_keys]

    print(f"locally audited rows: {changed_rows}")
    print(f"field cells to replay: {changed_cells}")
    print(f"field cells already present: {already_cells}")
    print(f"three-way conflicts: {len(conflicts)}")
    print(f"local extraction records: {len(local_log_additions)}")
    print(f"extraction records to append: {len(logs_to_append)}")
    if conflicts:
        for conflict in conflicts[:20]:
            entry_id, field, old, audited_value, current_value = conflict
            print(f"CONFLICT {entry_id} {field}: base={old!r} audited={audited_value!r} current={current_value!r}")
        raise RuntimeError("reconciliation conflicts found; no files written")
    if not args.apply:
        return

    # Preserve origin/main row order while taking values from the reconciled map.
    with DATABASE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=current_fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(current[row["entry_id"]] for row in current_rows)
    append_logs(logs_to_append, current_log_fields)
    print("reconciliation applied")


if __name__ == "__main__":
    main()
