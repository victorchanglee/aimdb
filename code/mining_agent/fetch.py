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
