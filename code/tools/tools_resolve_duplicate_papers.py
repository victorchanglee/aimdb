"""Resolve papers mined twice, once from the preprint and once from the journal.

The two versions carry genuinely different DOIs, so DOI dedup cannot see them
and `tools_dupfp.py` only catches the retitled case. This matches on the
*whole* normalized title: keying on a prefix pulls in series papers that share
a long stem ("...NEVPT2 I / II / III"), and the full title removed every one of
those false positives.

For each pair the survivor is whichever key carries more rows -- the preprint
was often mined more thoroughly than the published version -- and the journal
DOI wins a tie. The loser's rows are quarantined to `logs/removed_rows.csv`
before deletion, its index record becomes `not_usable` naming the survivor, and
the survivor's rows gain the alternate DOI in `notes` so the other citation is
not lost.

**A pair is only resolved when the survivor already covers every (nel,norb) the
loser holds.** Otherwise the "duplicate" carries data the survivor does not and
deleting it is not deduplication but loss: one pair here differed because the
published version reported six molecules -- AlCH2, CPP, CCO, CNN and both
cyanomethanimine isomers -- that the preprint pass never extracted. Those pairs
are reported and skipped, for a human to merge.

Usage, from code/:
    .venv/bin/python tools/tools_resolve_duplicate_papers.py --dry-run
    .venv/bin/python tools/tools_resolve_duplicate_papers.py --apply
"""

import argparse
import csv
import datetime as _dt
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
INDEX = ROOT / "database" / "papers_index.csv"
QUARANTINE = ROOT / "logs" / "removed_rows.csv"
LOG = ROOT / "logs" / "extractions.csv"

# DOI prefixes that identify a preprint server rather than a journal.
PREPRINT = re.compile(r"^10\.(26434|48550|21203|1101|20944|31219|33774)/", re.I)


def _title(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _space(r):
    return (r["active_space_nel"].strip(), r["active_space_norb"].strip())


def build_plan(index_rows, db_rows):
    by_key = defaultdict(list)
    for r in db_rows:
        by_key[r["entry_id"].rsplit("-", 1)[0]].append(r)

    by_title = defaultdict(list)
    for r in index_rows:
        if r.get("title"):
            by_title[_title(r["title"])].append(r)

    resolved, skipped = [], []
    for members in by_title.values():
        live = [m for m in members if by_key.get(m["key"])]
        if len(live) < 2 or len({m["doi"].lower() for m in live}) < 2:
            continue
        pre = [m for m in live if PREPRINT.match(m["doi"])]
        journal = [m for m in live if not PREPRINT.match(m["doi"])]
        if not (pre and journal):
            continue
        n_pre = sum(len(by_key[m["key"]]) for m in pre)
        n_journal = sum(len(by_key[m["key"]]) for m in journal)
        winner, loser = ((pre, journal) if n_pre > n_journal
                         else (journal, pre))  # tie: the journal version wins

        won = Counter(_space(r) for m in winner for r in by_key[m["key"]])
        lost = Counter(_space(r) for m in loser for r in by_key[m["key"]])
        # A row with no active space holds nothing the survivor can lack; it is
        # the bare summary row the published version often got.
        lost.pop(("", ""), None)
        uncovered = lost - won

        entry = {
            "title": live[0]["title"],
            "winner": winner, "loser": loser,
            "winner_rows": [r for m in winner for r in by_key[m["key"]]],
            "loser_rows": [r for m in loser for r in by_key[m["key"]]],
            "uncovered": uncovered,
        }
        (skipped if uncovered else resolved).append(entry)
    return resolved, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        db_fields = reader.fieldnames
        db_rows = list(reader)
    with INDEX.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        index_fields = reader.fieldnames
        index_rows = list(reader)

    resolved, skipped = build_plan(index_rows, db_rows)
    drop = {r["entry_id"] for e in resolved for r in e["loser_rows"]}

    print(f"{len(resolved) + len(skipped)} preprint/journal pairs")
    print(f"  resolvable (survivor covers every space): {len(resolved)}"
          f"  -> {len(drop)} rows removed")
    print(f"  skipped (loser holds a space the survivor lacks): {len(skipped)}"
          f"  -> {sum(len(e['loser_rows']) for e in skipped)} rows kept\n")
    for e in skipped:
        u = {f"({a},{b})": n for (a, b), n in e["uncovered"].items()}
        print(f"  SKIP {e['title'][:58]}")
        print(f"       keep {[m['key'] for m in e['winner']]} "
              f"({len(e['winner_rows'])}), loser "
              f"{[m['key'] for m in e['loser']]} ({len(e['loser_rows'])}) "
              f"holds {u}")

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0
    if not resolved:
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    removed = [r for r in db_rows if r["entry_id"] in drop]

    # Quarantine before deleting, reconciling a narrower existing header.
    qfields = db_fields + ["removed_reason", "removed_at"]
    existing = []
    if QUARANTINE.exists():
        with QUARANTINE.open(newline="", encoding="utf-8") as fh:
            qreader = csv.DictReader(fh)
            old_fields = qreader.fieldnames or []
            existing = list(qreader)
        if old_fields != qfields:
            qfields = old_fields + [c for c in qfields if c not in old_fields]
        else:
            existing = None
    reason = {}
    for e in resolved:
        survivor = ", ".join(m["doi"] for m in e["winner"])
        for r in e["loser_rows"]:
            reason[r["entry_id"]] = (
                f"duplicate of the same paper under {survivor}; this row came "
                f"from the other version of record")
    out_rows = [{**r, "removed_reason": reason[r["entry_id"]],
                 "removed_at": stamp} for r in removed]
    mode_ = "a" if existing is None else "w"
    with QUARANTINE.open(mode_, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=qfields, restval="")
        if mode_ == "w":
            writer.writeheader()
            writer.writerows(existing)
        writer.writerows(out_rows)

    # The survivor keeps the other citation.
    noted = 0
    for e in resolved:
        alt = ", ".join(m["doi"] for m in e["loser"])
        note = (f" The same paper is also indexed under {alt}; its duplicate "
                f"rows were removed {stamp[:10]}.")
        for r in e["winner_rows"]:
            if alt not in r["notes"]:
                r["notes"] = (r["notes"].rstrip() + note).strip()
                noted += 1

    keep = [r for r in db_rows if r["entry_id"] not in drop]
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=db_fields)
        writer.writeheader()
        writer.writerows(keep)
    tmp.replace(DB)

    # The loser's index record stops being a mining target.
    loser_keys = {}
    for e in resolved:
        survivor = ", ".join(m["key"] for m in e["winner"])
        for m in e["loser"]:
            loser_keys[m["key"]] = survivor
    marked = 0
    for r in index_rows:
        if r["key"] in loser_keys:
            r["status"] = "not_usable"
            r["updated"] = stamp
            marked += 1
    tmp = INDEX.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=index_fields)
        writer.writeheader()
        writer.writerows(index_rows)
    tmp.replace(INDEX)

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for r in removed:
            writer.writerow([
                stamp, r["entry_id"], r.get("reference_doi", ""),
                "resolve_duplicate_paper", "removed",
                reason[r["entry_id"]] + "; full row preserved in "
                "logs/removed_rows.csv"])
        for key, survivor in loser_keys.items():
            writer.writerow([
                stamp, key, "", "resolve_duplicate_paper", "not_usable",
                f"preprint/journal duplicate of {survivor}; its rows were "
                f"removed and the surviving rows carry both DOIs"])

    print(f"\nremoved {len(removed)} rows, quarantined to {QUARANTINE.name}")
    print(f"annotated {noted} surviving rows with the alternate DOI")
    print(f"marked {marked} index records not_usable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
