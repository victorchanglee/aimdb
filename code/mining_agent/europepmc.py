"""Europe PMC full-text recovery for papers stranded behind publisher
bot-blocks.

For any DOI that Europe PMC has in its OA full-text set, this fetches the
JATS XML over a clean HTTPS REST API (no bot interstitial, no FTP) and
renders it to plain text directly. That skips the PDF entirely — which is
fine, since text is what the extraction pass actually reads, and JATS text
is cleaner than pypdf output (no column-shredding).
"""
import re
import time

import requests

from . import config, index

REST = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = config.USER_AGENT
    return s


def find_pmcid(doi, session=None):
    """Resolve a DOI to a PMCID via the Europe PMC search API, or None."""
    session = session or _session()
    resp = session.get(f"{REST}/search",
                       params={"query": f'DOI:"{doi}"', "format": "json",
                               "resultType": "lite"}, timeout=60)
    time.sleep(config.REQUEST_INTERVAL)
    if resp.status_code != 200:
        return None
    for r in resp.json().get("resultList", {}).get("result", []):
        if r.get("pmcid") and r.get("isOpenAccess") == "Y":
            return r["pmcid"]
    return None


def fulltext_to_text(doi, session=None):
    """Return plain text of the OA full text for a DOI, or None."""
    session = session or _session()
    pmcid = find_pmcid(doi, session)
    if not pmcid:
        return None
    resp = session.get(f"{REST}/{pmcid}/fullTextXML", timeout=90)
    time.sleep(config.REQUEST_INTERVAL)
    if resp.status_code != 200 or "<article" not in resp.text:
        return None
    return _jats_to_text(resp.text)


def _jats_to_text(xml):
    # Drop the reference list and figure/table graphics, keep body prose.
    xml = re.sub(r"<ref-list.*?</ref-list>", " ", xml, flags=re.S)
    xml = re.sub(r"<xref[^>]*>.*?</xref>", " ", xml, flags=re.S)
    # Preserve paragraph/section/title/formula boundaries as newlines.
    xml = re.sub(r"</(p|sec|title|td|tr|caption|disp-formula|label)>",
                 "\n", xml, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", xml)
    text = (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&#x2013;", "-")
                .replace("&#x2212;", "-"))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def recover_text(row, session=None):
    """Fetch full text for a fetch_failed row via Europe PMC; on success
    write text/<key>.txt and set status text_ready. Returns (ok, detail)."""
    text = fulltext_to_text(row["doi"], session)
    if not text or len(text) < 800:
        return False, "no Europe PMC OA full text"
    dest = config.TEXT_DIR / f"{row['key']}.txt"
    dest.write_text(text, encoding="utf-8")
    index.set_status(row["key"], "text_ready", text_path=str(dest),
                     oa_pdf_url=f"europepmc:fullTextXML:{row['doi']}")
    index.log_extraction(row["key"], row["doi"], "europepmc", "text_ready",
                         f"{len(text)} chars of JATS full text")
    return True, f"{len(text)} chars via Europe PMC"
