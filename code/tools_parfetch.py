"""Parallel OA PDF fetcher for large candidate batches.

Same contract as `mining_agent fetch` — it only ever requests the OA URL
already recorded in the index row — but downloads run in a thread pool with
a per-host gate, and *all* index writes happen in one serial pass at the end.
The serial fetcher managed ~5 papers/min on batch 5 (1487 candidates ≈ 4.5 h),
almost all of it waiting on dead publisher links.

Usage:  .venv/bin/python tools_parfetch.py [--workers 8] [--max N]
"""
import argparse
import csv
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

from mining_agent import config, index

_host_gate = {}
_gate_lock = threading.Lock()
_host_last = defaultdict(float)

# Concurrency per host. doi.org is a redirector — its 313 URLs in batch 5 fan
# out to as many different publishers — so gating it like a single origin
# starved the pool and put the whole run back at the serial fetcher's pace.
HOST_LIMIT = 4
HOST_LIMIT_OVERRIDE = {"doi.org": 12, "dx.doi.org": 12}
HOST_SPACING = 0.5
TIMEOUT = 30


def _gate(url):
    host = urlparse(url).netloc.lower()
    with _gate_lock:
        sem = _host_gate.get(host)
        if sem is None:
            sem = threading.Semaphore(HOST_LIMIT_OVERRIDE.get(host,
                                                              HOST_LIMIT))
            _host_gate[host] = sem
    return host, sem


def download(row):
    """Returns (key, ok, detail). Writes the PDF, never the index."""
    url = row["oa_pdf_url"]
    if not url:
        return row["key"], False, "no OA URL in index"
    # Resume: a PDF already on disk was downloaded by an earlier run that was
    # killed before its single index-write pass. Don't re-request it.
    dest = config.PAPERS_PENDING_DIR / f"{row['key']}.pdf"
    if dest.exists() and dest.stat().st_size > 0:
        return row["key"], True, f"{dest.stat().st_size} bytes already on disk"
    host, sem = _gate(url)
    with sem:
        # keep at least REQUEST_INTERVAL between hits on the same host
        with _gate_lock:
            wait = _host_last[host] + HOST_SPACING - time.time()
            if wait > 0:
                time.sleep(wait)
            _host_last[host] = time.time()
        session = requests.Session()
        session.headers["User-Agent"] = config.USER_AGENT
        try:
            resp = session.get(url, timeout=TIMEOUT, stream=True,
                               allow_redirects=True)
            resp.raise_for_status()
            size, chunks = 0, []
            for chunk in resp.iter_content(chunk_size=1 << 16):
                size += len(chunk)
                if size > config.MAX_PDF_BYTES:
                    raise ValueError("response exceeds MAX_PDF_BYTES")
                chunks.append(chunk)
            body = b"".join(chunks)
            if not body.startswith(b"%PDF"):
                raise ValueError(
                    "response is not a PDF (probably an HTML landing page)")
            dest.write_bytes(body)
        except Exception as exc:  # noqa: BLE001 — any failure is terminal
            return row["key"], False, f"{type(exc).__name__}: {exc}"
        return row["key"], True, f"{size} bytes from {url}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()

    config.ensure_layout()
    rows = index.load()
    targets = [r for r in rows if r["status"] == "candidate"]
    if args.max:
        targets = targets[:args.max]
    print(f"{len(targets)} candidates, {args.workers} workers", flush=True)

    results = {}
    done = 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # as_completed, not map: map yields in submission order, so one slow
        # paper hides the progress of everything queued behind it.
        futures = [pool.submit(download, r) for r in targets]
        for fut in as_completed(futures):
            key, ok, detail = fut.result()
            results[key] = (ok, detail)
            done += 1
            if done % 50 == 0:
                n_ok = sum(1 for o, _ in results.values() if o)
                rate = done / (time.time() - started) * 60
                print(f"  {done}/{len(targets)}  fetched={n_ok}  "
                      f"{rate:.0f}/min", flush=True)

    # One serial write pass: index saved once, log appended once.
    by_key = {r["key"]: r for r in rows}
    log_rows = []
    now = index._now()
    n_ok = 0
    for key, (ok, detail) in results.items():
        row = by_key[key]
        row["status"] = "fetched" if ok else "fetch_failed"
        row["updated"] = now
        if ok:
            n_ok += 1
            row["pdf_path"] = config.rel_path(
                config.PAPERS_PENDING_DIR / f"{key}.pdf")
        log_rows.append([now, key, row["doi"], "fetch",
                         row["status"], detail])
    index.save(rows)
    with open(config.EXTRACTIONS_LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(log_rows)
    print(f"fetched {n_ok}, failed {len(results) - n_ok}")


if __name__ == "__main__":
    sys.exit(main())
