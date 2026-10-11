"""Ask OpenAlex whether a preprint-cited row has a published version to cite.

The ruling is that "the peer review article should be the authors results".
Where a paper is indexed twice, `tools_resolve_duplicate_papers.py` resolves
it. This tool covers the case that tool cannot see: a row whose
`reference_doi` is a preprint and whose published version **is not in
papers_index.csv at all**, so no title match inside the index can find it.
Measured on 2026-10-11 that was 49 groups / 69 rows.

OpenAlex answers it directly. Every preprint record carries a `locations` list
and, usually, a `primary_location`; when the work has been published, one of
those locations is the journal version, and the preprint's own
`best_oa_location`/`ids` often names it. More reliably, OpenAlex links the two
records together, so this tool asks twice:

  1. the preprint's own record, for a `locations[].source` that is a journal
     rather than a repository, and for the `doi` of any linked version;
  2. failing that, a title search (`filter=title.search:...`) restricted to
     `type:article` and excluding preprint DOI prefixes, confirmed by
     comparing normalized titles for equality — the same whole-title test
     `tools_resolve_duplicate_papers.py` uses, because a prefix match pulls in
     series papers sharing a long stem.

A title search alone is not enough to act on, so a hit is only reported, never
written. Two papers can share a title (a thesis chapter and the article; part I
and part II of a series after truncation), and a published version with a
*changed* title — which happens often in review — will not be found by either
route. Expect this to resolve some of the 49, not all.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_find_published_version.py            # survey
  .venv/bin/python tools/tools_find_published_version.py --query    # ask OpenAlex
  .venv/bin/python tools/tools_find_published_version.py --query --csv out.csv

Nothing in database/ is modified. Acting on the output means running
`tools_oa.py --refresh --stamp` afterwards, since `open_access` is OpenAlex's
answer for whichever DOI the row cites.
"""
import argparse
import csv
import json
import sys
import time
from collections import defaultdict

import requests

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config
from tools.tools_resolve_duplicate_papers import _title, PREPRINT

API = "https://api.openalex.org/works"
# Answers are cached per preprint key so a killed or rate-limited run resumes
# instead of re-asking 136 groups. "failed" is never cached: it is the absence
# of an answer, and caching it would freeze a transient 429 into a finding.
CACHE = config.LOGS_DIR / "published_version_cache.json"
# Repository sources that are not a published version even when OpenAlex calls
# the location primary.
REPO = ("chemrxiv", "arxiv", "research square", "biorxiv", "ssrn", "preprints",
        "zenodo", "figshare", "osti", "hal", "europe pmc", "pubmed central",
        "semantic scholar", "datacite")


def norm_doi(doi):
    return (doi or "").strip().replace("https://doi.org/", "").lower()


def preprint_groups():
    """key -> (doi, [entry_ids]) for rows citing a preprint DOI."""
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    groups = defaultdict(lambda: ["", []])
    for r in rows:
        doi = norm_doi(r.get("reference_doi"))
        if not doi or not PREPRINT.match(doi):
            continue
        g = groups[r["entry_id"].split("-")[0]]
        g[0] = doi
        g[1].append(r["entry_id"])
    return dict(groups)


def indexed_titles():
    """normalized title -> [index rows], for deciding what is already known."""
    out = defaultdict(list)
    with open(config.PAPERS_INDEX_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = _title(r.get("title", ""))
            if len(t) > 25:
                out[t].append(r)
    return out


def is_journal(loc):
    src = (loc or {}).get("source") or {}
    name = (src.get("display_name") or "").lower()
    if not name or any(w in name for w in REPO):
        return False
    return src.get("type") in (None, "journal", "book series", "conference")


def ask(session, params):
    """One OpenAlex query, or None, or "failed". Never raises.

    Pacing matters more here than in `tools_oa.py`, which asks the cheap `doi:`
    filter 50 DOIs at a time. `title.search` is a full-text query and OpenAlex
    rate-limits it far harder: the first run of this tool paced at 0.12 s
    between groups and spent twenty-five minutes collecting 429s, because a
    2/4/6/8/10-second retry ladder just re-hits the limit five times and gives
    up. So the backoff starts at 5 s and doubles, `Retry-After` is honoured
    when the server sends it, and callers wait a whole second between groups.
    """
    delay = 5.0
    for _ in range(6):
        try:
            resp = session.get(API, params=dict(params, mailto=config.MAILTO),
                               timeout=60)
        except requests.RequestException:
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code == 429 or resp.status_code >= 500:
            try:
                wait = max(float(resp.headers.get("Retry-After")), delay)
            except (TypeError, ValueError):
                wait = delay
            time.sleep(min(wait, 120.0))
            delay *= 2
            continue
        if not resp.ok:
            return None
        try:
            return resp.json()
        except ValueError:
            return None
    return "failed"


SELECT = "id,doi,title,display_name,type,publication_year,locations," \
         "primary_location,best_oa_location"


def published_for(session, doi, title, title_search=True):
    """(doi, year, title, how) for the published version, None if OpenAlex has
    none, or "failed" if it never answered — a distinction that matters,
    because "no published version" is a finding and a dropped request is not.

    The two routes fail independently. On 2026-10-11 the `doi:` filter answered
    normally while `title.search` returned 503 for every query, search being a
    separate backend; a tool that treats one dead route as a dead tool reports
    136 failures and learns nothing. So route 1 is always tried, and when route
    2 is unavailable the result is "partial" — route 1 found nothing AND the
    confirming search could not run, which is weaker than a real negative.
    """
    rec = ask(session, {"filter": "doi:" + doi, "select": SELECT,
                        "per-page": 1})
    if rec == "failed":
        return "failed"
    results = (rec or {}).get("results") or []
    if results:
        w = results[0]
        for loc in (w.get("locations") or []):
            ldoi = norm_doi((loc.get("source") or {}).get("doi")
                            or loc.get("landing_page_url", ""))
            if is_journal(loc) and ldoi and not PREPRINT.match(ldoi):
                return (ldoi, w.get("publication_year"),
                        w.get("display_name") or "", "linked-location")

    if not title_search:
        return "partial"
    want = _title(title)
    hits = ask(session, {
        "filter": "title.search:%s,type:article" % title[:180],
        "select": SELECT, "per-page": 25})
    if hits == "failed":
        return "partial"
    for w in (hits or {}).get("results") or []:
        wdoi = norm_doi(w.get("doi"))
        if not wdoi or PREPRINT.match(wdoi) or wdoi == doi:
            continue
        if _title(w.get("display_name") or w.get("title") or "") != want:
            continue
        if not any(is_journal(loc) for loc in (w.get("locations") or [])):
            continue
        return (wdoi, w.get("publication_year"),
                w.get("display_name") or "", "title-match")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="store_true",
                    help="ask OpenAlex; without it, only survey what is local")
    ap.add_argument("--csv", help="write the findings to this path")
    ap.add_argument("--limit", type=int, help="stop after N groups")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore logs/published_version_cache.json and re-ask")
    args = ap.parse_args(argv)

    groups = preprint_groups()
    by_title = indexed_titles()
    index = {}
    with open(config.PAPERS_INDEX_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            index[r["key"]] = r

    # A group is only this tool's business if the index holds no journal twin.
    todo = []
    for key, (doi, entries) in sorted(groups.items()):
        rec = index.get(key, {})
        title = rec.get("title", "")
        twins = [m for m in by_title.get(_title(title), [])
                 if m["key"] != key and not PREPRINT.match(m.get("doi") or "")]
        if twins:
            continue
        todo.append((key, doi, title, len(entries)))

    print("%d row group(s) cite a preprint; %d have no journal twin in the "
          "index" % (len(groups), len(todo)), file=sys.stderr)
    print("%d row(s) affected" % sum(n for _, _, _, n in todo), file=sys.stderr)
    if not args.query:
        for key, doi, title, n in todo:
            print("  %-14s %-34s %2d row(s)  %s" % (key, doi, n, title[:62]))
        return 0

    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    cache = {}
    if CACHE.exists() and not args.no_cache:
        cache = json.loads(CACHE.read_text())
        print("resuming: %d key(s) already answered" % len(cache),
              file=sys.stderr)
    # One probe decides whether route 2 is worth attempting at all. Without
    # it, a dead search backend costs the full backoff ladder 136 times over.
    probe = ask(session, {"filter": "title.search:ethylene,type:article",
                          "select": "id", "per-page": 1})
    title_search = probe != "failed"
    if not title_search:
        print("title.search is not answering; running the linked-location "
              "route only. Groups it cannot settle are reported PARTIAL, not "
              "negative — re-run when search is back.", file=sys.stderr)

    found, missing, failed, partial = [], [], [], []
    for i, (key, doi, title, n) in enumerate(todo, 1):
        if args.limit and i > args.limit:
            break
        if key in cache:
            hit = tuple(cache[key]) if cache[key] else None
        else:
            hit = (published_for(session, doi, title, title_search)
                   if title else None)
            if hit not in ("failed", "partial"):
                cache[key] = list(hit) if hit else None
                CACHE.write_text(json.dumps(cache, indent=0))
        if hit == "failed":
            failed.append((key, doi, n, title))
            print("  ERROR   %-14s %2d row(s)  %s  (OpenAlex did not answer)"
                  % (key, n, doi))
        elif hit == "partial":
            partial.append((key, doi, n, title))
            print("  partial %-14s %2d row(s)  %s  (no linked journal "
                  "location; title search unavailable)" % (key, n, doi))
        elif hit:
            found.append((key, doi, n, hit))
            print("  FOUND   %-14s %2d row(s)  %s  <- %s (%s, %s)"
                  % (key, n, doi, hit[0], hit[1], hit[3]))
        else:
            missing.append((key, doi, n, title))
            print("  none    %-14s %2d row(s)  %s" % (key, n, doi))
        sys.stdout.flush()
        time.sleep(1.0)

    print("\n%d group(s) have a published version in OpenAlex (%d rows); "
          "%d do not (%d rows)"
          % (len(found), sum(f[2] for f in found),
             len(missing), sum(m[2] for m in missing)), file=sys.stderr)
    if partial:
        print("%d group(s) (%d rows) have no journal location linked from the "
              "preprint record, which is suggestive and not conclusive: the "
              "confirming title search could not run. Re-run when it can."
              % (len(partial), sum(f[2] for f in partial)), file=sys.stderr)
    if failed:
        print("%d group(s) (%d rows) got no answer at all and are UNDECIDED, "
              "not negative: re-run to settle them."
              % (len(failed), sum(f[2] for f in failed)), file=sys.stderr)
    print("Nothing was written. These are candidates for re-attribution, not "
          "decisions: confirm each before pointing rows at it.", file=sys.stderr)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["key", "preprint_doi", "rows", "published_doi",
                        "published_year", "published_title", "how"])
            for key, doi, n, hit in found:
                w.writerow([key, doi, n, hit[0], hit[1], hit[2], hit[3]])
        print("wrote %s" % args.csv, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
