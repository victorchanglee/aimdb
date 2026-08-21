"""Give a surviving paper the local text that sits under its duplicate's key.

`tools_resolve_duplicate_papers.py` keeps whichever key carries more rows. That
says nothing about which key was actually fetched, and usually the readable copy
is the one discarded: after the 2026-08-21 pass, 21 of the 49 removed rows had
local text while their survivor had none. Nothing was deleted -- `not_usable` is
an index status -- but a later audit checking a surviving row finds no source
and has no reason to look under the twin.

This copies the text (and links the PDF) across to the survivor's key and
records the move in `papers_index.csv`.

**The copy is not the same document.** One key is the preprint and the other the
published version; that is exactly why the two were mined separately and why
some rows disagree on an active space. So the copy is prefixed with a banner
naming the key and DOI it came from, and the survivor's `notes` already carries
the alternate DOI from the resolution pass. Never read the result as the
version of record without checking that banner.

Usage, from code/:
    .venv/bin/python tools/tools_repoint_duplicate_text.py --dry-run
    .venv/bin/python tools/tools_repoint_duplicate_text.py --apply
"""

import argparse
import csv
import datetime as _dt
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
INDEX = ROOT / "database" / "papers_index.csv"
QUARANTINE = ROOT / "logs" / "removed_rows.csv"
LOG = ROOT / "logs" / "extractions.csv"
TEXT = ROOT / "text"

BANNER = (
    "=== TEXT BORROWED FROM A DUPLICATE RECORD ===\n"
    "This file is NOT the text of {wkey} ({wdoi}).\n"
    "It is the text of {lkey} ({ldoi}), the other version of the same paper,\n"
    "whose rows were removed as duplicates on {when}. The two versions are a\n"
    "preprint and a published article and may differ; check anything you take\n"
    "from here against the version of record before trusting it.\n"
    "=============================================\n\n")


def _title(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def build_plan():
    csv.field_size_limit(10 ** 9)
    with QUARANTINE.open(newline="", encoding="utf-8") as fh:
        removed = [r for r in csv.DictReader(fh)
                   if "duplicate of the same paper" in r.get("removed_reason", "")]
    losers = defaultdict(list)
    for r in removed:
        losers[r["entry_id"].rsplit("-", 1)[0]].append(r)

    with INDEX.open(newline="", encoding="utf-8") as fh:
        index_rows = list(csv.DictReader(fh))
    by_key = {r["key"]: r for r in index_rows}
    by_title = defaultdict(list)
    for r in index_rows:
        by_title[_title(r["title"])].append(r)

    with DB.open(newline="", encoding="utf-8") as fh:
        db = defaultdict(list)
        for r in csv.DictReader(fh):
            db[r["entry_id"].rsplit("-", 1)[0]].append(r)

    def size(key):
        p = TEXT / f"{key}.txt"
        return p.stat().st_size if p.exists() else 0

    plan = []
    for lkey in losers:
        if lkey not in by_key:
            continue
        twins = [x for x in by_title[_title(by_key[lkey]["title"])]
                 if x["key"] != lkey and db.get(x["key"])]
        if not twins:
            continue
        wkey = twins[0]["key"]
        # Only when the survivor has nothing and the loser does.
        if size(wkey) or not size(lkey):
            continue
        pdf = next((p for p in (ROOT / "papers" / "mined" / f"{lkey}.pdf",
                                ROOT / "papers" / "pending" / f"{lkey}.pdf")
                    if p.exists()), None)
        plan.append({"loser": lkey, "winner": wkey, "pdf": pdf,
                     "ldoi": by_key[lkey]["doi"], "wdoi": by_key[wkey]["doi"],
                     "rows": len(db[wkey]), "bytes": size(lkey)})
    return plan, index_rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    plan, index_rows = build_plan()
    print(f"{len(plan)} papers to repoint; "
          f"{sum(p['rows'] for p in plan)} surviving rows become verifiable")
    for p in plan:
        print(f"   {p['loser']} -> {p['winner']}  {p['bytes']:7d} B  "
              f"survivor rows={p['rows']:2d}  pdf={'yes' if p['pdf'] else 'no'}")

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0
    if not plan:
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    by_key = {r["key"]: r for r in index_rows}
    written = linked = 0
    for p in plan:
        src = TEXT / f"{p['loser']}.txt"
        dest = TEXT / f"{p['winner']}.txt"
        banner = BANNER.format(wkey=p["winner"], wdoi=p["wdoi"],
                               lkey=p["loser"], ldoi=p["ldoi"], when=stamp[:10])
        dest.write_text(banner + src.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8")
        written += 1
        row = by_key.get(p["winner"])
        if row is not None:
            row["text_path"] = f"text/{p['winner']}.txt"
            row["updated"] = stamp
        if p["pdf"]:
            link = ROOT / "papers" / "mined" / f"{p['winner']}.pdf"
            if not link.exists():
                link.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(os.path.relpath(p["pdf"], link.parent), link)
                linked += 1
                if row is not None:
                    row["pdf_path"] = f"papers/mined/{p['winner']}.pdf"

    with INDEX.open(newline="", encoding="utf-8") as fh:
        fields = csv.DictReader(fh).fieldnames
    tmp = INDEX.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(index_rows)
    tmp.replace(INDEX)

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for p in plan:
            writer.writerow([
                stamp, p["winner"], p["wdoi"], "repoint_duplicate_text",
                f"text from {p['loser']} ({p['bytes']} bytes)",
                f"the surviving key had no local text; copied from its "
                f"duplicate {p['loser']} ({p['ldoi']}) with a banner saying so. "
                f"The two are a preprint and a published version and may differ"])
    print(f"\nwrote {written} text files, linked {linked} PDFs, "
          f"updated {written} index records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
