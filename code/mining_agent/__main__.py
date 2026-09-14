"""CLI entry points for the mining loop — see CLAUDE.md for the policy.

Run from code/ with .venv/bin/python -m mining_agent <command>.
"""
import argparse
import csv
import json
import sys
from collections import Counter

from . import config, csvio, fetch, index, pdftext, query, search


def cmd_search(args):
    found = search.openalex_search(args.query, max_results=args.max,
                                   from_year=args.from_year)
    added = index.add_candidates(found)
    for row in added:
        index.log_extraction(row["key"], row["doi"], "search", "candidate",
                             f"query: {args.query!r}")
        print(f"  + {row['key']}  {row['year']}  {row['title'][:80]}")
    print(f"{len(found)} results, {len(added)} new candidates added")


def cmd_import(args):
    dois = _read_doi_column(args.csv)
    print(f"{len(dois)} DOIs in {args.csv}")
    found, not_found = search.openalex_by_dois(dois)
    for doi in not_found:
        print(f"  ? {doi}: not found in OpenAlex — skipped")
    added = index.add_candidates(found)
    for row in added:
        index.log_extraction(row["key"], row["doi"], "import", "candidate",
                             f"user DOI list: {args.csv}")
    n_no_url = sum(1 for r in added if not r["oa_pdf_url"])
    print(f"{len(added)} new candidates added "
          f"({n_no_url} without an OA URL), "
          f"{len(found) - len(added)} already indexed, "
          f"{len(not_found)} not found")


def _read_doi_column(path):
    """Accept a CSV with a doi column (any capitalization; extra columns
    ignored) or a headerless one-DOI-per-line file."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        sys.exit(f"{path} is empty")
    header = [c.strip().lower() for c in rows[0]]
    if "doi" in header:
        col = header.index("doi")
        body = rows[1:]
    elif "10." in rows[0][0]:
        col, body = 0, rows
    else:
        sys.exit(f"{path} has no 'doi' column and doesn't look like a "
                 "plain DOI list")
    dois, seen = [], set()
    for r in body:
        doi = r[col].strip() if col < len(r) else ""
        if doi and doi not in seen:
            dois.append(doi)
            seen.add(doi)
    return dois


def cmd_fetch(args):
    if args.key:
        row = index.get(index.load(), args.key)
        if row is None:
            sys.exit(f"no index entry {args.key!r}")
        ok, detail = fetch.fetch_one(row)
        print(("fetched: " if ok else "FAILED: ") + detail)
    else:
        ok, failed = fetch.fetch_candidates(max_papers=args.max)
        print(f"fetched {ok}, failed {failed}")


def cmd_refetch(args):
    ok, failed = fetch.refetch_failed(max_papers=args.max, only_key=args.key)
    print(f"recovered {ok}, still failed {failed}")


def cmd_text(args):
    rows = index.load()
    if args.key:
        targets = [r for r in rows if r["key"] == args.key]
        if not targets:
            sys.exit(f"no index entry {args.key!r}")
    else:
        targets = [r for r in rows if r["status"] == "fetched"]
    for row in targets:
        ok, detail = pdftext.extract_text(row)
        print(f"{row['key']}: " + ("ok " if ok else "FAILED ") + detail)


def cmd_add_row(args):
    with open(args.json, encoding="utf-8") as f:
        fields = json.load(f)
    row = csvio.append_row(fields)
    index.log_extraction(fields["entry_id"], fields["reference_doi"],
                         "add-row", "appended",
                         args.reasoning or "row added via add-row")
    print(f"appended {row['entry_id']} ({row['reference_doi']})")


def cmd_si(args):
    from pypdf import PdfReader

    from . import si
    saved = si.fetch_and_log(args.key)
    for p in saved:
        line = f"  {p.name} ({p.stat().st_size} bytes)"
        if p.suffix.lower() == ".pdf":
            try:
                reader = PdfReader(p)
                text = "\n\n".join(
                    f"--- page {n} ---\n{page.extract_text() or ''}"
                    for n, page in enumerate(reader.pages, 1))
                dest = config.TEXT_DIR / f"{args.key}_si_{p.stem}.txt"
                dest.write_text(text, encoding="utf-8")
                line += f" -> {dest.name}"
            except Exception as exc:  # noqa: BLE001
                line += f" (text extraction failed: {exc})"
        print(line)
    if not saved:
        print("no SI found via figshare or PMC")


def cmd_structure(args):
    from . import structures
    path, detail = structures.save_structure(args.entry_id, args.name)
    if path is None:
        print(f"FAILED: {detail}")
        sys.exit(1)
    csvio.set_structure_file(
        args.entry_id, path.name,
        f"structure_file is a generated PubChem conformer ({detail}), "
        "not the paper's geometry")
    index.log_extraction(args.entry_id, "", "structure", "generated",
                         f"{path.name} from PubChem name lookup {args.name!r}")
    print(f"saved {path.name} ({detail})")


def cmd_mark(args):
    row = index.set_status(args.key, args.status)
    index.log_extraction(args.key, row["doi"], "mark", args.status,
                         args.reasoning)
    print(f"{args.key} -> {args.status}")


def cmd_status(_args):
    rows = index.load()
    counts = Counter(r["status"] for r in rows)
    print(f"{len(rows)} papers indexed:")
    for status in sorted(counts):
        print(f"  {counts[status]:4d}  {status}")
    n_rows = max(0, len(csvio.existing_entry_ids()))
    print(f"{n_rows} rows in aimdb.csv")


def cmd_contributions(args):
    if args.add:
        n = csvio.ingest_contributions(args.add)
        print(f"ingested {n} row(s) from {args.add} "
              f"-> {config.CONTRIBUTIONS_CSV.name}")
    rows = csvio.load_contributions()
    by_status = Counter(r.get("review_status", "") or "pending" for r in rows)
    print(f"{len(rows)} contribution(s) in {config.CONTRIBUTIONS_CSV.name}:")
    for status in sorted(by_status):
        print(f"  {by_status[status]:4d}  {status}")
    if args.list:
        pending = [r for r in rows
                   if (r.get("review_status") or "pending") == "pending"]
        for r in pending:
            who = r.get("contributor_name") or "?"
            print(f"  - {r.get('compound_name','')[:50]!r}  "
                  f"DOI={r.get('reference_doi','') or '—'}  "
                  f"by {who} <{r.get('contributor_email','')}>  "
                  f"[{r.get('submitted_at','')}]")


def cmd_tidy(args):
    """Reconcile papers/pending/ and papers/mined/ with the index."""
    rows = index.load()
    moved = relinked = 0
    for row in rows:
        found = index.find_pdf(row)
        if found is None:
            continue
        if row["status"] in config.MINED_STATUSES:
            dest = index.move_to_mined(row)
            if dest is not None and str(dest) != str(found):
                moved += 1
                print(f"  -> mined/  {row['key']}  ({row['status']})")
            found = dest or found
        else:
            dest = index.move_to_pending(row)
            if dest is not None and str(dest) != str(found):
                moved += 1
                print(f"  -> pending/  {row['key']}  ({row['status']})")
            found = dest or found
        rel = config.rel_path(found)
        if rel != row["pdf_path"]:
            row["pdf_path"] = rel
            relinked += 1
    if moved or relinked:
        index.save(rows)
    n_pending = len(list(config.PAPERS_PENDING_DIR.glob("*.pdf")))
    n_mined = len(list(config.PAPERS_MINED_DIR.glob("*.pdf")))
    print(f"moved {moved} PDF(s) between the queues, repaired {relinked} path(s)")
    print(f"papers/pending: {n_pending} PDF(s)   papers/mined: {n_mined} PDF(s)")
    untracked = sorted(
        p.stem for p in config.PAPERS_PENDING_DIR.glob("*.pdf")
        if index.get(rows, p.stem) is None)
    if untracked:
        print(f"{len(untracked)} pending PDF(s) not in the index "
              f"(added by hand): {', '.join(untracked[:5])}"
              + (" ..." if len(untracked) > 5 else ""))


def cmd_show(args):
    row = index.get(index.load(), args.key)
    if row is None:
        sys.exit(f"no index entry {args.key!r}")
    for col in config.INDEX_COLUMNS:
        print(f"{col:12s} {row[col]}")


def _range(text):
    """--year-range 1990:2000, or a bare 1995 meaning 1995:1995."""
    lo, _, hi = text.partition(":")
    return (int(lo), int(hi or lo))


def cmd_query(args):
    if args.schema:
        print(json.dumps(query.schema(), indent=2))
        return
    spec = dict(
        entry_id=args.entry_id, doi=args.doi, element=args.element,
        metal=args.metal, system_class=args.system_class, formula=args.formula,
        compound=args.compound, method=args.method,
        correlation=args.correlation, software=args.software,
        open_access=args.open_access, nel=args.nel, norb=args.norb,
        nel_range=args.nel_range, norb_range=args.norb_range,
        year_range=args.year_range, has_space=args.has_space or None,
    )
    fields = args.fields.split(",") if args.fields else None
    try:
        if args.spaces:
            result = query.spaces_for(include_quest=args.include_quest, **spec)
        else:
            result = query.find(include_quest=args.include_quest,
                                limit=args.limit, offset=args.offset,
                                fields=fields, **spec)
    except ValueError as exc:
        sys.exit(str(exc))

    if args.format == "json":
        print(json.dumps(result, indent=2))
        return
    # tsv: the envelope on stderr so stdout stays a clean table to pipe.
    summary = (f"{result['count']} matched of {result['database']['rows_searched']} "
               f"searched ({result['database']['quest_rows_withheld']} QUEST withheld)")
    print(summary, file=sys.stderr)
    for name, spot in result.get("blind_spots", {}).items():
        print(f"  blind spot: {spot['rows_without_this_field']} rows have no "
              f"{spot['field']} and could not match", file=sys.stderr)
    if args.spaces:
        print("space\trows\texamples")
        for s in result["spaces"]:
            print(f"{s['space']}\t{s['rows']}\t{','.join(s['examples'])}")
        print(f"(no space recorded)\t{result['without_space']}\t",
              file=sys.stderr)
        return
    cols = fields or ["entry_id", "compound_name", "active_space_nel",
                      "active_space_norb", "reference_doi"]
    print("\t".join(cols))
    for row in result["rows"]:
        print("\t".join((row.get(c) or "").replace("\t", " ") for c in cols))


def main():
    parser = argparse.ArgumentParser(prog="mining_agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="query OpenAlex, add candidates")
    p.add_argument("--query", required=True)
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--from-year", type=int, default=None)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("import", help="add candidates from a user CSV "
                                      "with a doi column (or plain DOI list)")
    p.add_argument("--csv", required=True)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("fetch", help="download OA PDFs for candidates")
    p.add_argument("--key")
    p.add_argument("--max", type=int, default=5)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("refetch", help="retry fetch_failed papers against "
                                       "all OA locations (repository mirrors)")
    p.add_argument("--key")
    p.add_argument("--max", type=int, default=None)
    p.set_defaults(func=cmd_refetch)

    p = sub.add_parser("text", help="extract text from fetched PDFs")
    p.add_argument("--key")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("add-row", help="append a validated aimdb.csv row")
    p.add_argument("--json", required=True,
                   help="path to a JSON dict of schema fields")
    p.add_argument("--reasoning", default="")
    p.set_defaults(func=cmd_add_row)

    p = sub.add_parser("si", help="fetch supplementary information "
                                  "(figshare SI DOIs, then PMC OA package)")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_si)

    p = sub.add_parser("structure", help="save a generated PubChem 3D "
                                         "structure for an extracted row")
    p.add_argument("--entry-id", required=True)
    p.add_argument("--name", required=True,
                   help="compound name to resolve in PubChem")
    p.set_defaults(func=cmd_structure)

    p = sub.add_parser("mark", help="set a paper's index status")
    p.add_argument("--key", required=True)
    p.add_argument("--status", required=True,
                   choices=sorted(config.INDEX_STATUSES))
    p.add_argument("--reasoning", required=True)
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("status", help="index and database summary")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("contributions", help="review community submissions: "
                                             "ingest a downloaded form CSV and "
                                             "summarize the review queue")
    p.add_argument("--add", help="path to a contribution CSV from the website "
                                 "form to append to the review queue")
    p.add_argument("--list", action="store_true",
                   help="list pending contributions")
    p.set_defaults(func=cmd_contributions)

    p = sub.add_parser("tidy", help="reconcile papers/pending and papers/mined "
                                    "with the index (move read papers, repair "
                                    "stale paths)")
    p.set_defaults(func=cmd_tidy)

    p = sub.add_parser("show", help="print one index entry")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("query", help="read-only query over aimdb.csv "
                                     "(QUEST rows withheld by default)")
    p.add_argument("--entry-id", action="append")
    p.add_argument("--doi", action="append")
    p.add_argument("--element", action="append",
                   help="element symbol; repeat to require all of them")
    p.add_argument("--metal", action="append", help="metal_center symbol")
    p.add_argument("--system-class", action="append",
                   choices=sorted(config.SYSTEM_CLASSES))
    p.add_argument("--formula", action="append")
    p.add_argument("--compound", help="substring of compound_name")
    p.add_argument("--method", help="substring of method")
    p.add_argument("--correlation", help="substring of correlation_correction")
    p.add_argument("--software", help="substring of software")
    p.add_argument("--open-access", action="append",
                   choices=sorted(config.OPEN_ACCESS_VALUES))
    p.add_argument("--nel", type=int, action="append")
    p.add_argument("--norb", type=int, action="append")
    p.add_argument("--nel-range", type=_range, metavar="LO:HI")
    p.add_argument("--norb-range", type=_range, metavar="LO:HI")
    p.add_argument("--year-range", type=_range, metavar="LO:HI")
    p.add_argument("--has-space", action="store_true",
                   help="only rows carrying both nel and norb")
    p.add_argument("--spaces", action="store_true",
                   help="histogram the active spaces used instead of "
                        "listing rows")
    p.add_argument("--fields", help="comma-separated projection")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--include-quest", action="store_true",
                   help="include QUEST-sourced rows, which are withheld by "
                        "default (CLAUDE.md export boundary)")
    p.add_argument("--schema", action="store_true",
                   help="print the schema contract and exit")
    p.add_argument("--format", choices=("json", "tsv"), default="json")
    p.set_defaults(func=cmd_query)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
