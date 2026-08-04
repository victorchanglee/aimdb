"""Ask OpenAlex whether each aimdb.csv DOI is open access, and stamp the answer.

Adds/refreshes the `open_access` column of database/aimdb.csv: `yes` / `no` /
`unknown` (OpenAlex has no record of that DOI). The full OpenAlex answer —
oa_status (gold/hybrid/green/bronze/closed) and the best OA URL — is kept in
logs/oa_status.csv, one row per DOI, so the boolean can be rebuilt or audited
without re-querying.

DOIs are looked up 50 at a time with the `doi:a|b|...` OR filter; anything the
batch doesn't return is retried as a single-work lookup before being called
unknown (batch misses happen for DOIs OpenAlex has stored in a different
normalized form).

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools_oa.py --refresh      # query OpenAlex, rewrite logs/oa_status.csv
  .venv/bin/python tools_oa.py --stamp        # write the column from logs/oa_status.csv
  .venv/bin/python tools_oa.py --refresh --stamp
"""
import argparse
import csv
import datetime
import os
import sys
import time

import requests

from mining_agent import config

OA_STATUS_CSV = config.LOGS_DIR / "oa_status.csv"
OA_COLUMNS = ["doi", "open_access", "oa_status", "oa_url", "openalex_id",
              "checked"]
BATCH = 50


def norm(doi):
    """Bare lowercase DOI, the form OpenAlex indexes."""
    doi = (doi or "").strip().replace("https://doi.org/", "")
    return doi.removeprefix("doi:").strip("/").lower()


def aimdb_dois():
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen = {}
    for r in rows:
        d = norm(r.get("reference_doi"))
        if d:
            seen.setdefault(d, 0)
            seen[d] += 1
    return seen


def record(work, checked):
    oa = work.get("open_access") or {}
    loc = work.get("best_oa_location") or {}
    return {
        "doi": norm(work.get("doi")),
        "open_access": "yes" if oa.get("is_oa") else "no",
        "oa_status": oa.get("oa_status") or "",
        "oa_url": loc.get("pdf_url") or loc.get("landing_page_url") or "",
        "openalex_id": (work.get("id") or "").rsplit("/", 1)[-1],
        "checked": checked,
    }


def refresh(dois):
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    checked = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    select = "id,doi,open_access,best_oa_location"
    found = {}

    ordered = sorted(dois)
    for i in range(0, len(ordered), BATCH):
        chunk = ordered[i:i + BATCH]
        resp = session.get(config.OPENALEX_WORKS_URL, params={
            "filter": "doi:" + "|".join(chunk),
            "per-page": BATCH,
            "select": select,
            "mailto": config.MAILTO,
        }, timeout=60)
        resp.raise_for_status()
        for work in resp.json().get("results", []):
            rec = record(work, checked)
            if rec["doi"]:
                found[rec["doi"]] = rec
        print(f"  batch {i // BATCH + 1}: {len(found)}/{len(ordered)} resolved",
              file=sys.stderr)
        time.sleep(config.REQUEST_INTERVAL)

    missing = [d for d in ordered if d not in found]
    print(f"retrying {len(missing)} unresolved DOIs one at a time",
          file=sys.stderr)
    for doi in missing:
        resp = session.get(
            f"{config.OPENALEX_WORKS_URL}/https://doi.org/{doi}",
            params={"select": select, "mailto": config.MAILTO}, timeout=60)
        time.sleep(config.REQUEST_INTERVAL)
        if resp.status_code == 404:
            found[doi] = {"doi": doi, "open_access": "unknown",
                          "oa_status": "", "oa_url": "", "openalex_id": "",
                          "checked": checked}
            continue
        resp.raise_for_status()
        rec = record(resp.json(), checked)
        # OpenAlex may echo a different canonical DOI; key by what we asked for.
        rec["doi"] = doi
        found[doi] = rec

    with open(OA_STATUS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OA_COLUMNS)
        w.writeheader()
        for doi in ordered:
            w.writerow(found[doi])
    print(f"wrote {OA_STATUS_CSV} ({len(found)} DOIs)", file=sys.stderr)
    return found


def load_oa_status():
    with open(OA_STATUS_CSV, newline="", encoding="utf-8") as f:
        return {r["doi"]: r for r in csv.DictReader(f)}


def stamp():
    """Rewrite aimdb.csv with the open_access column filled from oa_status.csv."""
    status = load_oa_status()
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    counts = {}
    for r in rows:
        rec = status.get(norm(r.get("reference_doi")))
        value = rec["open_access"] if rec else "unknown"
        r["open_access"] = value
        counts[value] = counts.get(value, 0) + 1

    tmp = str(config.LITERATURE_CSV) + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") or "" for c in config.LITERATURE_COLUMNS})
    os.replace(tmp, config.LITERATURE_CSV)
    print(f"stamped {len(rows)} rows: {counts}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="query OpenAlex and rewrite logs/oa_status.csv")
    ap.add_argument("--stamp", action="store_true",
                    help="write aimdb.csv's open_access column from that file")
    args = ap.parse_args()
    if not (args.refresh or args.stamp):
        ap.error("pass --refresh, --stamp, or both")

    if args.refresh:
        dois = aimdb_dois()
        print(f"{sum(dois.values())} rows / {len(dois)} unique DOIs",
              file=sys.stderr)
        refresh(dois)
    if args.stamp:
        stamp()


if __name__ == "__main__":
    main()
