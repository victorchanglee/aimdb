"""Fetch supplementary information in bulk, over the two sanctioned routes.

`python -m mining_agent si --key K` fetches one paper's SI from figshare
(ACS component DOIs, `<doi>.s001`...) or the PubMed Central OA package. This
tool runs that same code over every paper that needs it, so a structure or
gap-filling pass has the SI on disk before anyone starts reading. It downloads
nothing the single-paper command would not: only figshare's public API and
PMC's OA service are used, never a publisher site.

Selection, by default: every paper with at least one aimdb.csv row that has no
`structure_file`, whose `papers/si/<key>/` does not already hold a file. figshare
is tried only for ACS DOIs (10.1021), because the `<doi>.sNNN` component-DOI
convention is theirs; every other DOI goes straight to the PMC check. PMC ids
are resolved first in batches of 200 through the id converter, so a paper with
no PMC record costs one two-hundredth of a request rather than one.

Every PDF among the saved files is text-extracted to `text/<key>_si_<stem>.txt`,
exactly as the single-paper command does. Each attempt appends `si-fetch` to
logs/extractions.csv and a line to logs/si_batch.csv, which is what makes the
tool resumable: a key already in that file is skipped unless --retry is given.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_batch_si.py --dry-run        # count what would be tried
  .venv/bin/python tools/tools_batch_si.py                  # run
  .venv/bin/python tools/tools_batch_si.py --keys K1 K2     # just these keys
  .venv/bin/python tools/tools_batch_si.py --all-rows       # not only structureless rows
"""
import argparse
import csv
import datetime
import sys
import time

import requests

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, index, si

STATE = config.LOGS_DIR / "si_batch.csv"
PMC_IDS = config.LOGS_DIR / "pmc_ids.csv"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_state():
    done = {}
    if STATE.exists():
        with STATE.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                done[r["key"]] = r
    return done


def record_state(key, doi, route, result, files):
    new = not STATE.exists()
    with STATE.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "key", "doi", "route", "result", "files"])
        w.writerow([_now(), key, doi, route, result, files])


def candidate_keys(all_rows):
    with config.LITERATURE_CSV.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    keys = set()
    for r in rows:
        if all_rows or not (r.get("structure_file") or "").strip():
            keys.add(r["entry_id"].rsplit("-", 1)[0])
    return keys


def has_si_files(key):
    d = si.si_dir(key)
    return d.is_dir() and any(p.is_file() for p in d.iterdir())


def resolve_pmc_ids(dois):
    """Batch DOI -> PMCID through the id converter; cached in logs/pmc_ids.csv."""
    cache = {}
    if PMC_IDS.exists():
        with PMC_IDS.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cache[r["doi"]] = r["pmcid"]
    todo = [d for d in dois if d and d not in cache]
    session = si._session()
    for i in range(0, len(todo), 200):
        chunk = todo[i:i + 200]
        try:
            resp = session.get(si.IDCONV, params={
                "ids": ",".join(chunk), "format": "json",
                "tool": "casscf-miner", "email": config.MAILTO}, timeout=120)
        except requests.RequestException as exc:
            print(f"  idconv batch failed: {exc}", file=sys.stderr)
            time.sleep(10)
            continue
        time.sleep(config.REQUEST_INTERVAL)
        if resp.status_code != 200:
            print(f"  idconv HTTP {resp.status_code}", file=sys.stderr)
            time.sleep(10)
            continue
        seen = set()
        for rec in resp.json().get("records", []):
            d = (rec.get("requested-id") or rec.get("doi") or "").lower()
            cache[d] = rec.get("pmcid") or ""
            seen.add(d)
        for d in chunk:
            cache.setdefault(d, "")
        print(f"  idconv: {i + len(chunk)}/{len(todo)} DOIs screened", flush=True)
    with PMC_IDS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["doi", "pmcid"])
        for d in sorted(cache):
            w.writerow([d, cache[d]])
    return cache


def extract_pdf_text(key, path):
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        text = "\n\n".join(
            f"--- page {n} ---\n{page.extract_text() or ''}"
            for n, page in enumerate(reader.pages, 1))
    except Exception as exc:  # noqa: BLE001
        return f"text extraction failed: {exc}"
    dest = config.TEXT_DIR / f"{key}_si_{path.stem}.txt"
    dest.write_text(text, encoding="utf-8")
    return dest.name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keys", nargs="*", help="restrict to these index keys")
    ap.add_argument("--all-rows", action="store_true",
                    help="every paper with rows, not only those lacking a structure")
    ap.add_argument("--retry", action="store_true",
                    help="retry keys already recorded in logs/si_batch.csv")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=0, help="stop after this many attempts")
    args = ap.parse_args(argv)

    idx = {r["key"]: r for r in index.load()}
    keys = set(args.keys) if args.keys else candidate_keys(args.all_rows)
    done = load_state()
    todo = []
    for k in sorted(keys):
        row = idx.get(k)
        if row is None or not row.get("doi"):
            continue
        if has_si_files(k):
            continue
        if k in done and not args.retry:
            continue
        todo.append(row)
    acs = [r for r in todo if r["doi"].lower().startswith("10.1021/")]
    print(f"{len(keys)} papers selected, {len(todo)} to try "
          f"({len(acs)} ACS -> figshare first; all -> PMC screen)", flush=True)
    if args.dry_run:
        return 0

    pmc = resolve_pmc_ids(sorted({r["doi"].lower() for r in todo}))
    with_pmc = sum(1 for r in todo if pmc.get(r["doi"].lower()))
    print(f"PMC records found for {with_pmc} of {len(todo)} DOIs", flush=True)

    n = 0
    for row in todo:
        key, doi = row["key"], row["doi"]
        is_acs = doi.lower().startswith("10.1021/")
        pmcid = pmc.get(doi.lower(), "")
        if not is_acs and not pmcid:
            record_state(key, doi, "none", "no route", "")
            continue
        n += 1
        saved, route = [], ""
        try:
            if is_acs:
                route = "figshare"
                saved = si._fetch_figshare(row)
            if not saved and pmcid:
                route = "pmc"
                saved = si._fetch_pmc(row)
        except requests.RequestException as exc:
            record_state(key, doi, route, f"error: {exc}", "")
            print(f"  {key}: {route} error {exc}", file=sys.stderr, flush=True)
            time.sleep(15)
            continue
        names = []
        for p in saved:
            tag = p.name
            if p.suffix.lower() == ".pdf":
                tag += " -> " + extract_pdf_text(key, p)
            names.append(tag)
        result = f"{len(saved)} files"
        index.log_extraction(key, doi, "si-fetch", result,
                             (", ".join(p.name for p in saved) or "none found")
                             + f" [batch, route {route}]")
        record_state(key, doi, route, result, "; ".join(names))
        print(f"  {key} [{route}] {result}: {', '.join(names) or '-'}", flush=True)
        if args.max and n >= args.max:
            break
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
