"""Supplementary-information fetching, two publisher-sanctioned routes:

1. PubMed Central OA packages: for papers with a PMC ID, the OA service
   hands out a tarball containing the article plus all SI files.
2. figshare: ACS (and some others) deposit SI under component DOIs like
   <doi>.s001, all hosted on figshare, whose API allows direct downloads.

Files land in papers/si/<key>/; PDFs among them can then be text-extracted
with pdftext for the extraction pass. SI is copyrighted content like the
papers themselves — papers/ is gitignored and must stay that way.
"""
import io
import tarfile
import time
import xml.etree.ElementTree as ET

import requests

from . import config, index

IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
OA_FCGI = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
FIGSHARE = "https://api.figshare.com/v2/articles"

# SI payloads worth keeping (skip article nxml/graphics).
KEEP_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".csv",
            ".txt", ".cif", ".xyz", ".mol", ".sdf"}
MAX_SI_BYTES = 200 * 1024 * 1024


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = config.USER_AGENT
    return s


def si_dir(key):
    return config.PAPERS_DIR / "si" / key


def fetch_si(row):
    """Try figshare then PMC for one index row; returns list of saved paths."""
    saved = _fetch_figshare(row)
    if not saved:
        saved = _fetch_pmc(row)
    return saved


def _fetch_figshare(row):
    session = _session()
    saved = []
    misses = 0
    for n in range(1, 10):
        doi = f"{row['doi']}.s{n:03d}"
        resp = session.get(FIGSHARE, params={"doi": doi}, timeout=60)
        time.sleep(config.REQUEST_INTERVAL)
        if resp.status_code != 200 or not resp.json():
            misses += 1
            if misses >= 2:
                break
            continue
        misses = 0
        for art in resp.json():
            detail = session.get(f"{FIGSHARE}/{art['id']}", timeout=60)
            time.sleep(config.REQUEST_INTERVAL)
            if detail.status_code != 200:
                continue
            for f in detail.json().get("files", []):
                if f.get("size", 0) > MAX_SI_BYTES or not f.get("download_url"):
                    continue
                dest = si_dir(row["key"]) / f["name"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                blob = session.get(f["download_url"], timeout=300)
                time.sleep(config.REQUEST_INTERVAL)
                if blob.status_code == 200:
                    dest.write_bytes(blob.content)
                    saved.append(dest)
    return saved


def _fetch_pmc(row):
    session = _session()
    resp = session.get(IDCONV, params={"ids": row["doi"], "format": "json",
                                       "tool": "casscf-miner",
                                       "email": config.MAILTO}, timeout=60)
    time.sleep(config.REQUEST_INTERVAL)
    if resp.status_code != 200:
        return []
    recs = resp.json().get("records", [])
    pmcid = recs[0].get("pmcid") if recs else None
    if not pmcid:
        return []
    resp = session.get(OA_FCGI, params={"id": pmcid}, timeout=60)
    time.sleep(config.REQUEST_INTERVAL)
    if resp.status_code != 200:
        return []
    href = None
    for link in ET.fromstring(resp.text).iter("link"):
        if link.get("format") == "tgz":
            href = link.get("href")
    if not href:
        return []
    href = href.replace("ftp://ftp.ncbi.nlm.nih.gov/", "https://ftp.ncbi.nlm.nih.gov/")
    blob = session.get(href, timeout=600)
    if blob.status_code != 200 or len(blob.content) > MAX_SI_BYTES:
        return []
    saved = []
    with tarfile.open(fileobj=io.BytesIO(blob.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name.rsplit("/", 1)[-1]
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if not member.isfile() or ext not in KEEP_EXT:
                continue
            dest = si_dir(row["key"]) / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(member)
            if f:
                dest.write_bytes(f.read())
                saved.append(dest)
    return saved


def fetch_and_log(key):
    row = index.get(index.load(), key)
    if row is None:
        raise KeyError(f"no index entry {key!r}")
    saved = fetch_si(row)
    names = ", ".join(p.name for p in saved) or "none found"
    index.log_extraction(key, row["doi"], "si-fetch",
                         f"{len(saved)} files", names)
    return saved
