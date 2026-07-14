"""OpenAlex works search, filtered to open-access papers with a PDF URL.

https://docs.openalex.org/api-entities/works — no API key needed; the
mailto param puts us in the polite pool. `search=` matches title,
abstract, and (where indexed) full text, so a query like
"CASSCF transition metal complex" surfaces papers whose methods section
mentions CASSCF even if the title doesn't.
"""
import time

import requests

from . import config


def openalex_search(query, max_results=25, from_year=None):
    """Return a list of candidate dicts: key, doi, title, year, oa_pdf_url."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    filters = ["open_access.is_oa:true"]
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")

    found = []
    cursor = "*"
    while len(found) < max_results and cursor:
        params = {
            "search": query,
            "filter": ",".join(filters),
            "per-page": min(50, max_results),
            "cursor": cursor,
            "mailto": config.MAILTO,
            "select": "id,doi,display_name,publication_year,"
                      "best_oa_location,open_access",
        }
        resp = session.get(config.OPENALEX_WORKS_URL, params=params,
                           timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        for work in payload.get("results", []):
            hit = _to_candidate(work)
            if hit:
                found.append(hit)
                if len(found) >= max_results:
                    break
        cursor = payload.get("meta", {}).get("next_cursor")
        time.sleep(config.REQUEST_INTERVAL)
    return found


def _to_candidate(work):
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if not doi:
        return None
    loc = work.get("best_oa_location") or {}
    pdf_url = loc.get("pdf_url") or ""
    if not pdf_url:
        # OA but no direct PDF link (e.g. HTML-only) — still indexable;
        # fetch will fail cleanly and mark it, keeping the audit trail.
        pdf_url = (work.get("open_access") or {}).get("oa_url") or ""
    if not pdf_url:
        return None
    # OpenAlex id like https://openalex.org/W2741809807 -> W2741809807
    key = (work.get("id") or "").rsplit("/", 1)[-1]
    if not key:
        return None
    return {
        "key": key,
        "doi": doi,
        "title": work.get("display_name") or "",
        "year": work.get("publication_year") or "",
        "oa_pdf_url": pdf_url,
        "source": "openalex",
    }
