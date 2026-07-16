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


def openalex_by_doi(doi):
    """Look up a single DOI; returns a candidate dict, or None if OpenAlex
    doesn't know the work. User-supplied DOIs are kept even without an OA
    URL (fetch will mark them fetch_failed, preserving the audit trail)."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    doi = doi.strip().replace("https://doi.org/", "")
    doi = doi.removeprefix("doi:").strip("/")
    resp = session.get(f"{config.OPENALEX_WORKS_URL}/https://doi.org/{doi}",
                       params={"mailto": config.MAILTO}, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    time.sleep(config.REQUEST_INTERVAL)
    hit = _to_candidate(resp.json(), require_url=False)
    if hit:
        hit["source"] = "doi-import"
    return hit


# Hosts that serve PDFs to scripted clients, best first. Publisher sites
# (pubs.acs.org, pubs.rsc.org, onlinelibrary.wiley.com) 403 or return HTML
# landing pages, which is what stranded 1276 papers on the first pass.
PREFERRED_HOSTS = ("arxiv.org", "pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
                   "chemrxiv.org", "europepmc.org")
BLOCKED_HOSTS = ("pubs.acs.org", "pubs.rsc.org", "onlinelibrary.wiley.com",
                 "www.science.org", "pubs.aip.org/aip/jcp/article-pdf")


def _host_rank(url):
    for i, h in enumerate(PREFERRED_HOSTS):
        if h in url:
            return i
    return len(PREFERRED_HOSTS) + (10 if any(b in url for b in BLOCKED_HOSTS) else 0)


def openalex_all_pdf_urls(doi):
    """Every OA pdf_url OpenAlex knows for this DOI, best-fetchable first.

    fetch() originally used only best_oa_location, which for paywalled-
    publisher-hosted OA is a URL that blocks scripts even though a
    repository copy exists.
    """
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    resp = session.get(f"{config.OPENALEX_WORKS_URL}/https://doi.org/{doi}",
                       params={"mailto": config.MAILTO,
                               "select": "locations,best_oa_location"},
                       timeout=60)
    time.sleep(config.REQUEST_INTERVAL)
    if resp.status_code != 200:
        return []
    payload = resp.json()
    urls = []
    for loc in (payload.get("locations") or []):
        u = loc.get("pdf_url")
        if u and u not in urls:
            urls.append(u)
    best = (payload.get("best_oa_location") or {}).get("pdf_url")
    if best and best not in urls:
        urls.append(best)
    return sorted(urls, key=_host_rank)


def openalex_by_dois(dois):
    """Batch lookup: returns (candidates, not_found_dois). Uses the works
    filter endpoint, 50 DOIs per request, so large user lists import in
    seconds-per-thousand rather than seconds-per-DOI."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    cleaned = []
    for doi in dois:
        doi = doi.strip().replace("https://doi.org/", "")
        doi = doi.removeprefix("doi:").strip("/")
        if doi:
            cleaned.append(doi)
    candidates, found_dois = [], set()
    for start in range(0, len(cleaned), 50):
        chunk = [d for d in cleaned[start:start + 50]
                 if "|" not in d and "," not in d]
        if not chunk:
            continue
        resp = session.get(config.OPENALEX_WORKS_URL, params={
            "filter": "doi:" + "|".join(chunk),
            "per-page": 50,
            "mailto": config.MAILTO,
            "select": "id,doi,display_name,publication_year,"
                      "best_oa_location,open_access",
        }, timeout=60)
        resp.raise_for_status()
        for work in resp.json().get("results", []):
            hit = _to_candidate(work, require_url=False)
            if hit:
                hit["source"] = "doi-import"
                candidates.append(hit)
                found_dois.add(hit["doi"].lower())
        time.sleep(config.REQUEST_INTERVAL)
    not_found = [d for d in cleaned if d.lower() not in found_dois]
    return candidates, not_found


def _to_candidate(work, require_url=True):
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if not doi:
        return None
    loc = work.get("best_oa_location") or {}
    pdf_url = loc.get("pdf_url") or ""
    if not pdf_url:
        # OA but no direct PDF link (e.g. HTML-only) — still indexable;
        # fetch will fail cleanly and mark it, keeping the audit trail.
        pdf_url = (work.get("open_access") or {}).get("oa_url") or ""
    if not pdf_url and require_url:
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
