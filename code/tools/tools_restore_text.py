"""Restore `text/<key>.txt` for papers that carry rows but lost their text.

Half of aimdb's rows (6,522 of 12,541 on 2026-10-09) belong to papers whose
extracted text is no longer on disk, and nothing in `benchmark/` can judge
them: the grounding check skips them, and the correctness and completeness
criteria of `extraction_rubric.py` both score them `\\`. Restoring the text is
therefore the single largest expansion of the auditable database available, and
it adds no rows and changes no values.

Of 2,424 such papers, 1,824 still carry an `oa_pdf_url` in the index -- the
open-access location OpenAlex reported when they were first fetched -- so they
can be re-downloaded from the same source the pipeline used originally. 10 still
have a PDF on disk and need extraction only. The remaining ~590 have no
recorded OA location and cannot be recovered here.

**Why this is not `mining_agent text`.** That command calls
`index.set_status(key, "text_ready")`, which drags an already-read paper back
to an unread status and moves its PDF out of `papers/mined/`. Running it over
already-mined papers has corrupted statuses twice (2026-10-09, 13 papers), so
this tool extracts the text itself and preserves each paper's existing status,
passing it back unchanged so the PDF is still filed as mined. It never edits
`aimdb.csv`.

Only locations the API reported are downloaded, per CLAUDE.md -- no scraping,
no mirrors beyond what OpenAlex lists.

Takes an exclusive flock: two instances running together lose each other's
index updates, and cost 174 records on 2026-10-09.

Usage, from code/:
    .venv/bin/python tools/tools_restore_text.py --dry-run
    .venv/bin/python tools/tools_restore_text.py --max 25
    .venv/bin/python tools/tools_restore_text.py --key W2078010867
    .venv/bin/python tools/tools_restore_text.py --extract-only
"""
import argparse
import csv
import fcntl
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

import requests  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from mining_agent import config, fetch, index, search  # noqa: E402

DB = ROOT / "database" / "aimdb.csv"
MIN_CHARS = 500


def rowed_keys():
    """key -> number of aimdb rows, for every paper the database cites."""
    csv.field_size_limit(10 ** 9)
    counts = defaultdict(int)
    with DB.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            counts[row["entry_id"].rsplit("-", 1)[0]] += 1
    return counts


def targets(only_key=None):
    """Index rows for rowed papers whose text file is gone."""
    counts = rowed_keys()
    out = []
    for row in index.load():
        key = row["key"]
        if key not in counts:
            continue
        if only_key and key != only_key:
            continue
        if (config.TEXT_DIR / ("%s.txt" % key)).is_file():
            continue
        out.append((row, counts[key]))
    out.sort(key=lambda rc: -rc[1])     # most rows unlocked first
    return out


def extract(row):
    """Write text/<key>.txt from a PDF on disk, leaving status alone.

    Deliberately a copy of pdftext.extract_text's reading logic rather than a
    call to it: that function sets the paper's status to `text_ready` or
    `text_unreadable`, which is wrong for a paper that has already been read
    and judged. Here the status is passed back unchanged.
    """
    pdf_path = index.find_pdf(row)
    if pdf_path is None:
        return False, "no PDF on disk"
    dest = config.TEXT_DIR / ("%s.txt" % row["key"])
    try:
        reader = PdfReader(pdf_path)
        pages = ["--- page %d ---\n%s" % (n, page.extract_text() or "")
                 for n, page in enumerate(reader.pages, 1)]
        text = "\n\n".join(pages)
        if len(text.strip()) < MIN_CHARS:
            return False, ("only %d chars extracted - scanned or image PDF"
                           % len(text.strip()))
        dest.write_text(text, encoding="utf-8")
    except Exception as exc:                                  # noqa: BLE001
        return False, "%s: %s" % (type(exc).__name__, exc)
    # Same status back in: records text_path and refiles the PDF as mined
    # without moving the paper anywhere in the lifecycle.
    index.set_status(row["key"], row["status"],
                     text_path=config.rel_path(dest))
    return True, "%d pages -> %s" % (len(reader.pages), dest.name)


# A sweep of this size is dominated by links that no longer serve a PDF, and
# each one is paid for at the full timeout. 25 s is ample for a repository that
# is going to answer, and caps the cost of one that is not; 4 URLs per paper
# bounds the worst case at ~100 s instead of the ~10 min an unbounded list of
# dead publisher links would cost.
URL_TIMEOUT = 25
MAX_URLS_PER_PAPER = 4


def download(row, session):
    """Fetch the PDF from the OA locations the API reports. True on success."""
    dest = config.PAPERS_PENDING_DIR / ("%s.pdf" % row["key"])
    urls = []
    if row.get("oa_pdf_url", "").strip():
        urls.append(row["oa_pdf_url"].strip())
    try:
        urls += [u for u in search.openalex_all_pdf_urls(row["doi"])
                 if u not in urls]
    except Exception:                                         # noqa: BLE001
        pass
    # Repository copies answer far more often than publisher pages, so try
    # them first: the ordering decides what the URL cap throws away.
    urls.sort(key=lambda u: 0 if any(
        h in u.lower() for h in ("arxiv", "ncbi.nlm.nih", "europepmc",
                                 "chemrxiv", "hal.", "osti.gov", "zenodo",
                                 "core.ac.uk", "dspace", "diva-portal",
                                 "handle.net", "repository", "biorxiv")) else 1)
    for url in urls[:MAX_URLS_PER_PAPER]:
        try:
            ok, _ = fetch._try_url(session, url, dest, timeout=URL_TIMEOUT)
        except Exception:                                     # noqa: BLE001
            ok = False
        if ok:
            index.set_status(row["key"], row["status"],
                             pdf_path=config.rel_path(dest))
            return True
        time.sleep(config.REQUEST_INTERVAL)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be attempted and stop")
    ap.add_argument("--max", type=int, help="stop after this many papers")
    ap.add_argument("--key", help="just this paper")
    ap.add_argument("--extract-only", action="store_true",
                    help="never download; only extract PDFs already on disk")
    args = ap.parse_args(argv)

    # One writer at a time. Every set_status is a load-mutate-save over the
    # whole index, so a second instance silently drops the first's updates; on
    # 2026-10-09 two overlapping runs cost 174 index records, recovered from a
    # backup and git. flock releases on exit or kill, so there is no stale
    # lock to clean up after a crash.
    lock_path = ROOT / "logs" / ".restore_text.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another tools_restore_text.py is already running (%s); "
                 "wait for it or kill it, and verify it is gone before "
                 "starting another" % lock_path)

    todo = targets(args.key)
    on_disk = [(r, n) for r, n in todo if index.find_pdf(r) is not None]
    fetchable = [(r, n) for r, n in todo
                 if index.find_pdf(r) is None and r.get("oa_pdf_url", "").strip()]
    hopeless = len(todo) - len(on_disk) - len(fetchable)
    print("%d rowed papers have no local text (%d rows behind them)"
          % (len(todo), sum(n for _, n in todo)))
    print("  PDF already on disk, extract only : %d  (%d rows)"
          % (len(on_disk), sum(n for _, n in on_disk)))
    print("  re-downloadable from a recorded OA url: %d  (%d rows)"
          % (len(fetchable), sum(n for _, n in fetchable)))
    print("  no PDF and no OA url, needs supplying : %d" % hopeless)
    if args.dry_run:
        print("\ndry run - nothing fetched or written")
        return 0

    queue = on_disk + ([] if args.extract_only else fetchable)
    if args.max:
        queue = queue[:args.max]
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    done = failed = 0
    for row, nrows in queue:
        if index.find_pdf(row) is None:
            if not download(row, session):
                failed += 1
                index.log_extraction(row["key"], row["doi"], "restore-text",
                                     "download_failed",
                                     "no OA location served a PDF")
                print("  %-14s DOWNLOAD FAILED" % row["key"])
                continue
            time.sleep(config.REQUEST_INTERVAL)
        ok, detail = extract(row)
        if ok:
            done += 1
            index.log_extraction(
                row["key"], row["doi"], "restore-text", "text_restored",
                "re-extracted text for a paper already marked %s, unlocking "
                "%d row(s) for audit; status left unchanged"
                % (row["status"], nrows))
        else:
            failed += 1
            index.log_extraction(row["key"], row["doi"], "restore-text",
                                 "extract_failed", detail)
        print("  %-14s %-5s %s" % (row["key"], "ok" if ok else "FAIL", detail))
    print("\nrestored %d, failed %d" % (done, failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
