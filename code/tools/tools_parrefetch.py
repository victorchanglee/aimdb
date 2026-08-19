"""Parallel recovery pass over `fetch_failed` papers.

Same idea as `mining_agent refetch` — try every OA location OpenAlex knows,
repository mirrors before bot-blocking publisher sites, then fall back to
Europe PMC's JATS full text — but three things are different, and all three
matter at 1000+ papers:

  * **Locations are looked up in batches of 50** through the works filter
    endpoint instead of one request per DOI (21 requests instead of 1019).
  * Downloads run in a thread pool with the same per-host gate as
    `tools_parfetch`.
  * All index writes happen in one serial pass at the end, so the run can be
    killed at any point without a half-written `papers_index.csv`.

Usage:  .venv/bin/python tools/tools_parrefetch.py [--workers 24] [--max N]
"""
import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, europepmc, index, search
from tools_parfetch import _gate, HOST_SPACING, TIMEOUT, _gate_lock, _host_last


def batch_locations(dois, chunk=50):
    """{doi: [pdf_url, ...]} for every DOI, best-fetchable host first."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    out = {}
    for start in range(0, len(dois), chunk):
        piece = [d for d in dois[start:start + chunk]
                 if "|" not in d and "," not in d]
        if not piece:
            continue
        try:
            resp = session.get(config.OPENALEX_WORKS_URL, params={
                "filter": "doi:" + "|".join(piece),
                "per-page": chunk,
                "mailto": config.MAILTO,
                "select": "doi,locations,best_oa_location",
            }, timeout=90)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! locations lookup failed at {start}: {exc}", flush=True)
            time.sleep(5)
            continue
        for work in resp.json().get("results", []):
            doi = (work.get("doi") or "").replace("https://doi.org/", "").lower()
            urls = []
            for loc in (work.get("locations") or []):
                u = loc.get("pdf_url")
                if u and u not in urls:
                    urls.append(u)
            best = (work.get("best_oa_location") or {}).get("pdf_url")
            if best and best not in urls:
                urls.append(best)
            out[doi] = sorted(urls, key=search._host_rank)
        time.sleep(config.REQUEST_INTERVAL)
        if (start // chunk) % 5 == 0:
            print(f"  locations {start + len(piece)}/{len(dois)}", flush=True)
    return out


def _try_url(session, url, dest):
    host, sem = _gate(url)
    with sem:
        with _gate_lock:
            wait = _host_last[host] + HOST_SPACING - time.time()
            if wait > 0:
                time.sleep(wait)
            _host_last[host] = time.time()
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
                raise ValueError("not a PDF (probably an HTML landing page)")
            dest.write_bytes(body)
            return True, f"{size} bytes from {url}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


def recover(row, urls):
    """Returns (key, outcome, detail, extra) where outcome is one of
    'fetched' (PDF on disk), 'text_ready' (Europe PMC text), or ''."""
    key = row["key"]
    dest = config.PAPERS_PENDING_DIR / f"{key}.pdf"
    if dest.exists() and dest.stat().st_size > 0:
        return key, "fetched", "already on disk", ""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    details = []
    for url in urls[:6]:
        ok, detail = _try_url(session, url, dest)
        details.append(detail)
        if ok:
            return key, "fetched", detail, url
    # No fetchable PDF anywhere: Europe PMC serves OA full text as JATS XML
    # over a clean REST API, which is what the reading pass actually wants.
    try:
        text = europepmc.fulltext_to_text(row["doi"], session)
    except Exception as exc:  # noqa: BLE001
        text = None
        details.append(f"europepmc: {type(exc).__name__}: {exc}")
    if text and len(text) >= 800:
        path = config.TEXT_DIR / f"{key}.txt"
        path.write_text(text, encoding="utf-8")
        return (key, "text_ready", f"{len(text)} chars via Europe PMC",
                f"europepmc:fullTextXML:{row['doi']}")
    return key, "", (f"{len(urls)} PDF location(s) + Europe PMC tried; "
                     + " | ".join(details[:3])), ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()

    config.ensure_layout()
    rows = index.load()
    targets = [r for r in rows if r["status"] == "fetch_failed"]
    if args.max:
        targets = targets[:args.max]
    print(f"{len(targets)} fetch_failed papers", flush=True)

    locs = batch_locations([r["doi"] for r in targets])
    n_urls = sum(1 for r in targets if locs.get(r["doi"].lower()))
    print(f"{n_urls} have at least one OA PDF location", flush=True)

    results, done, started = {}, 0, time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(recover, r, locs.get(r["doi"].lower(), []))
                   for r in targets]
        for fut in as_completed(futures):
            key, outcome, detail, extra = fut.result()
            results[key] = (outcome, detail, extra)
            done += 1
            if done % 50 == 0:
                n_ok = sum(1 for o, _, _ in results.values() if o)
                rate = done / (time.time() - started) * 60
                print(f"  {done}/{len(targets)}  recovered={n_ok}  "
                      f"{rate:.0f}/min", flush=True)

    by_key = {r["key"]: r for r in rows}
    log_rows, now = [], index._now()
    n_pdf = n_text = 0
    for key, (outcome, detail, extra) in results.items():
        row = by_key[key]
        if outcome == "fetched":
            n_pdf += 1
            row["status"] = "fetched"
            row["pdf_path"] = config.rel_path(
                config.PAPERS_PENDING_DIR / f"{key}.pdf")
            if extra:
                row["oa_pdf_url"] = extra
        elif outcome == "text_ready":
            n_text += 1
            row["status"] = "text_ready"
            row["text_path"] = str(config.TEXT_DIR / f"{key}.txt")
            row["oa_pdf_url"] = extra
        else:
            continue  # stays fetch_failed
        row["updated"] = now
        log_rows.append([now, key, row["doi"], "refetch", row["status"],
                         detail])
    index.save(rows)
    with open(config.EXTRACTIONS_LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(log_rows)
    print(f"recovered {n_pdf} PDF(s) + {n_text} Europe PMC text(s), "
          f"{len(results) - n_pdf - n_text} still failed")


if __name__ == "__main__":
    sys.exit(main())
