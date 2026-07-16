"""Download open-access PDFs for indexed candidates.

Only URLs that came from the search API's OA metadata are ever fetched —
this module takes the URL from the index row, never discovers its own.
"""
import time

import requests

from . import config, index


def fetch_one(row, session=None):
    """Download row's PDF; returns (ok, detail). Updates the index."""
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = config.USER_AGENT
    url = row["oa_pdf_url"]
    if not url:
        index.set_status(row["key"], "fetch_failed")
        return False, "no OA URL in index"
    dest = config.PAPERS_DIR / f"{row['key']}.pdf"
    try:
        resp = session.get(url, timeout=120, stream=True,
                           allow_redirects=True)
        resp.raise_for_status()
        size = 0
        chunks = []
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
    except Exception as exc:  # noqa: BLE001 — any failure is terminal here
        index.set_status(row["key"], "fetch_failed")
        index.log_extraction(row["key"], row["doi"], "fetch", "fetch_failed",
                             f"{type(exc).__name__}: {exc}")
        return False, str(exc)
    index.set_status(row["key"], "fetched", pdf_path=str(dest))
    index.log_extraction(row["key"], row["doi"], "fetch", "fetched",
                         f"{size} bytes from {url}")
    return True, str(dest)


def _try_url(session, url, dest):
    """Download one URL to dest; returns (ok, detail)."""
    try:
        resp = session.get(url, timeout=120, stream=True, allow_redirects=True)
        resp.raise_for_status()
        size = 0
        chunks = []
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


def refetch_failed(max_papers=None, only_key=None):
    """Retry fetch_failed rows against every OA location OpenAlex knows,
    preferring repository mirrors over blocked publisher sites.

    Returns (n_recovered, n_still_failed).
    """
    from . import search
    config.ensure_layout()
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    rows = [r for r in index.load()
            if r["status"] == "fetch_failed"
            and (only_key is None or r["key"] == only_key)]
    if max_papers:
        rows = rows[:max_papers]
    from . import europepmc
    ok = failed = 0
    for row in rows:
        # A transient network error on any single paper must not abort a
        # multi-hour sweep of thousands — isolate each paper.
        try:
            recovered, detail = _refetch_one(row, session, europepmc)
        except Exception as exc:  # noqa: BLE001
            recovered, detail = False, f"{type(exc).__name__}: {exc}"
            index.log_extraction(row["key"], row["doi"], "refetch", "error",
                                 detail)
        if recovered:
            ok += 1
        else:
            failed += 1
    return ok, failed


def _refetch_one(row, session, europepmc):
    """Recover one fetch_failed row; returns (recovered, detail)."""
    urls = search.openalex_all_pdf_urls(row["doi"])
    dest = config.PAPERS_DIR / f"{row['key']}.pdf"
    details = []
    for url in urls:
        success, detail = _try_url(session, url, dest)
        details.append(detail)
        time.sleep(config.REQUEST_INTERVAL)
        if success:
            index.set_status(row["key"], "fetched", pdf_path=str(dest),
                             oa_pdf_url=url)
            index.log_extraction(row["key"], row["doi"], "refetch",
                                 "fetched", detail)
            return True, detail
    # No fetchable PDF anywhere. Europe PMC serves the OA full text as JATS
    # XML over clean HTTPS (bypasses publisher bot-blocks and FTP-only PMC
    # packages), yielding text_ready directly and skipping the PDF.
    success, detail = europepmc.recover_text(row, session)
    details.append(detail)
    if success:
        return True, detail
    index.log_extraction(
        row["key"], row["doi"], "refetch", "still_failed",
        f"{len(urls)} PDF location(s) + Europe PMC tried; "
        + " | ".join(details[:3]))
    return False, detail


def fetch_candidates(max_papers=5):
    """Fetch up to max_papers candidates; returns (n_ok, n_failed)."""
    config.ensure_layout()
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    ok = failed = 0
    for row in index.load():
        if ok + failed >= max_papers:
            break
        if row["status"] != "candidate":
            continue
        success, _ = fetch_one(row, session)
        ok += success
        failed += not success
        time.sleep(config.REQUEST_INTERVAL)
    return ok, failed
