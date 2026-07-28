"""papers_index.csv — one row per candidate paper, deduplicated by DOI.

The index is the mining loop's state file: every paper the agent has ever
seen is here with its lifecycle status, so searches never re-surface work
that was already judged.
"""
import csv
from datetime import datetime, timezone

from . import config


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    if not config.PAPERS_INDEX_CSV.exists():
        return []
    with open(config.PAPERS_INDEX_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(rows):
    config.ensure_layout()
    with open(config.PAPERS_INDEX_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def get(rows, key):
    for row in rows:
        if row["key"] == key:
            return row
    return None


def add_candidates(found):
    """Merge search results into the index; returns the newly added rows."""
    rows = load()
    known_dois = {r["doi"] for r in rows if r["doi"]}
    known_keys = {r["key"] for r in rows}
    added = []
    for hit in found:
        if not hit.get("doi") or hit["doi"] in known_dois:
            continue
        if hit["key"] in known_keys:
            continue
        row = {
            "key": hit["key"],
            "doi": hit["doi"],
            "title": hit.get("title", ""),
            "year": hit.get("year", ""),
            "oa_pdf_url": hit.get("oa_pdf_url", ""),
            "source": hit.get("source", "openalex"),
            "status": "candidate",
            "pdf_path": "",
            "text_path": "",
            "updated": _now(),
        }
        rows.append(row)
        added.append(row)
        known_dois.add(hit["doi"])
        known_keys.add(hit["key"])
    if added:
        save(rows)
    return added


def find_pdf(row):
    """Locate a row's PDF on disk, wherever it currently sits.

    Prefers the recorded pdf_path, then papers/pending/<key>.pdf, then
    papers/mined/<key>.pdf (and the legacy flat papers/<key>.pdf), so the
    index self-heals after files are moved by hand.
    """
    candidates = []
    if row.get("pdf_path"):
        candidates.append(config.abs_path(row["pdf_path"]))
    name = f"{row['key']}.pdf"
    candidates += [config.PAPERS_PENDING_DIR / name,
                   config.PAPERS_MINED_DIR / name,
                   config.PAPERS_DIR / name]
    for path in candidates:
        if path and path.exists():
            return path
    return None


def move_to_mined(row):
    """Move a read paper's PDF into papers/mined/ and return the new path
    (or None if there is no file to move). Idempotent."""
    src = find_pdf(row)
    if src is None:
        return None
    dest = config.PAPERS_MINED_DIR / f"{row['key']}.pdf"
    if src.resolve() == dest.resolve():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    return dest


def set_status(key, status, **fields):
    if status not in config.INDEX_STATUSES:
        raise ValueError(f"unknown status {status!r}")
    rows = load()
    row = get(rows, key)
    if row is None:
        raise KeyError(f"no index entry with key {key!r}")
    row["status"] = status
    row["updated"] = _now()
    for name, value in fields.items():
        if name not in config.INDEX_COLUMNS:
            raise ValueError(f"unknown index column {name!r}")
        row[name] = value
    # A paper that has been read moves out of the pending queue.
    if status in config.MINED_STATUSES:
        moved = move_to_mined(row)
        if moved is not None:
            row["pdf_path"] = config.rel_path(moved)
    save(rows)
    return row


def log_extraction(key, doi, action, result, reasoning):
    config.ensure_layout()
    new_file = not config.EXTRACTIONS_LOG.exists()
    with open(config.EXTRACTIONS_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(
                ["timestamp", "key", "doi", "action", "result", "reasoning"])
        writer.writerow([_now(), key, doi, action, result, reasoning])
