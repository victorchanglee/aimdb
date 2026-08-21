"""Say a clause once per group of segments that share a head, not once each.

Where several pipe-separated segments open with the same head, a clause
repeated verbatim in all of them belongs to the head, not to any one segment.
The H2Te row carried each state's dipole and Mulliken populations again in
every segment for that state — 3,068 characters of one row.

The clause must appear in *every* segment of the group, the same rule
`tools_hoist_repeated_sentence.py` applies at field level and for the same
reason: a clause in only some of them is telling those apart, and collapsing
it would destroy which. The surviving copy stays on the group's first segment,
so nothing is reordered and no framing text is invented.

Usage, from code/:
    .venv/bin/python tools/tools_dedupe_within_head.py --dry-run [--limit N]
    .venv/bin/python tools/tools_dedupe_within_head.py --apply
"""

import argparse
import csv
import datetime as _dt
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
LOG = ROOT / "logs" / "extractions.csv"

FIELDS = ("Other", "electronic_structure_description")
SEP = " | "
MIN_CHARS = 25  # shorter clauses repeat innocently


def _clauses(body):
    return [c.strip() for c in body.split(";") if c.strip()]


def dedupe_field(value):
    """Returns (new_value, n_removed_clauses)."""
    segments = [s.strip() for s in value.split(SEP) if s.strip()]
    if len(segments) < 2:
        return value, 0

    groups = OrderedDict()
    for i, seg in enumerate(segments):
        if ":" not in seg[:200]:
            groups.setdefault(("__nohead__", i), []).append((i, seg))
            continue
        head, body = seg.split(":", 1)
        groups.setdefault(head.strip(), []).append((i, body.strip()))

    out, removed = dict(), 0
    for head, members in groups.items():
        if isinstance(head, tuple) or len(members) < 2:
            for i, body in members:
                out[i] = segments[i]
            continue
        counts = Counter()
        for _i, body in members:
            for clause in set(_clauses(body)):
                if len(clause) >= MIN_CHARS:
                    counts[clause] += 1
        shared = {c for c, n in counts.items() if n == len(members)}
        for pos, (i, body) in enumerate(members):
            if pos == 0 or not shared:
                out[i] = f"{head}: {body}"
                continue
            kept = []
            for clause in _clauses(body):
                if clause in shared:
                    removed += 1
                    continue
                kept.append(clause)
            text = "; ".join(kept).strip()
            # A segment reduced to nothing said only what the group already says.
            out[i] = f"{head}: {text}" if text else head

    return SEP.join(out[i] for i in sorted(out)), removed


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    touched, clauses, saved, shown = [], 0, 0, 0
    for r in rows:
        edits = {}
        for f in FIELDS:
            new, n = dedupe_field(r[f])
            if n:
                edits[f] = (r[f], new)
                clauses += n
                saved += len(r[f]) - len(new)
        if not edits:
            continue
        touched.append((r["entry_id"], edits))
        if args.dry_run and shown < args.limit:
            shown += 1
            print(f"--- {r['entry_id']}  ({r['compound_name'][:44]})")
            for f, (old, new) in edits.items():
                print(f"    {f}: {len(old)} -> {len(new)} chars")
        if args.apply:
            for f, (_old, new) in edits.items():
                r[f] = new

    print(f"\n{len(touched)} rows, {clauses} repeated clauses, {saved} characters")

    if args.dry_run:
        print("dry run - nothing written")
        return 0
    if not touched:
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(DB)

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for eid, edits in touched:
            what = "; ".join(f"{f} {len(o)}->{len(n)} chars"
                             for f, (o, n) in edits.items())
            writer.writerow([
                stamp, eid, "", "dedupe_within_head", what,
                "a clause repeated in every segment sharing a head now appears "
                "once, on the first of them; clauses present in only some "
                "segments were left alone",
            ])
    print(f"wrote {DB} and logged {len(touched)} rows to {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
