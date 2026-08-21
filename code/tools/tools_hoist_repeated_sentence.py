"""Say a row's paper-level sentence once instead of once per segment.

`Other` and `electronic_structure_description` are often pipe-separated lists
with one segment per stationary point or state. Some rows repeat a statement
that is true of the whole paper inside *every* segment — one row restates
"The same 5SA-CASSCF(6,6)/6-31G level generated on-the-fly surfaces for 536
surface-hopping trajectories ..." 33 times. The repeated text is real content,
so the fix is to keep it, once, rather than to delete it: every copy is removed
from the individual segments and one verbatim copy is appended as the field's
last segment.

A sentence must recur in at least three segments to count. Two could be
coincidence — a genuine observation that happens to hold for two states — and
this tool never guesses; nothing is reworded and no framing text is invented.

Usage, from code/:
    .venv/bin/python tools/tools_hoist_repeated_sentence.py --dry-run [--limit N]
    .venv/bin/python tools/tools_hoist_repeated_sentence.py --apply
"""

import argparse
import csv
import datetime as _dt
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
LOG = ROOT / "logs" / "extractions.csv"

FIELDS = ("Other", "electronic_structure_description")
SEP = " | "
MIN_SEGMENTS = 3   # a sentence must recur in this many segments to be boilerplate
MIN_CHARS = 45     # shorter fragments repeat innocently


def _sentences(text):
    """Split on sentence-ending periods only.

    Not on semicolons: a semicolon joins clauses of one thought, and hoisting
    a single clause out of the middle leaves a dangling fragment behind. An
    early version split on both and reduced a segment to the orphan
    "dynamics used a 0.5 fs nuclear time step."
    """
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip()]


def _split_head(segment):
    """Separate a segment's "<label>:" head from its body.

    The head names the state or structure the segment is about and so differs
    from segment to segment; the boilerplate hides in the body behind it. A
    sentence carrying the head would never compare equal across segments, so
    the head is set aside before the comparison and restored afterwards.
    """
    m = re.match(r"^(.{1,160}?):\s*(.*)$", segment, re.S)
    if not m:
        return None, segment
    return m.group(1), m.group(2)


def hoist_field(value):
    """Returns (new_value, n_removed_copies, hoisted_sentences)."""
    segments = [s.strip() for s in value.split(SEP) if s.strip()]
    if len(segments) < MIN_SEGMENTS:
        return value, 0, []

    parts = [_split_head(seg) for seg in segments]

    counts = Counter()
    for _head, body in parts:
        for sentence in set(_sentences(body)):
            if len(sentence) >= MIN_CHARS:
                counts[sentence] += 1
    repeated = {s for s, n in counts.items() if n >= MIN_SEGMENTS}
    if not repeated:
        return value, 0, []

    # Keep the hoisted sentences in the order they first appear in the field.
    hoisted, removed, out = [], 0, []
    for head, body in parts:
        kept = []
        for sentence in _sentences(body):
            if sentence in repeated:
                removed += 1
                if sentence not in hoisted:
                    hoisted.append(sentence)
                continue
            kept.append(sentence)
        text = " ".join(kept).strip()
        if not text:
            # The segment was nothing but the boilerplate. Its head still names
            # a structure the paper treated, so keep the head by itself rather
            # than dropping the segment and that fact with it.
            if head:
                out.append(head)
            continue
        out.append(f"{head}: {text}" if head else text)

    out.extend(hoisted)
    removed -= len(hoisted)  # one copy of each survives
    return SEP.join(out), removed, hoisted


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=6)
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    touched, copies, saved, shown = [], 0, 0, 0
    for r in rows:
        edits = {}
        for f in FIELDS:
            new, n, hoisted = hoist_field(r[f])
            if n <= 0:
                continue
            edits[f] = (r[f], new, hoisted)
            copies += n
            saved += len(r[f]) - len(new)
        if not edits:
            continue
        touched.append((r["entry_id"], edits))
        if args.dry_run and shown < args.limit:
            shown += 1
            print(f"--- {r['entry_id']}  ({r['compound_name'][:48]})")
            for f, (old, new, hoisted) in edits.items():
                print(f"    {f}: {len(old)} -> {len(new)} chars")
                for s in hoisted:
                    print(f"      said once now: {s[:130]}")
        if args.apply:
            for f, (_old, new, _h) in edits.items():
                r[f] = new

    print(f"\n{len(touched)} rows, {copies} redundant copies removed, "
          f"{saved} characters")

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
                             for f, (o, n, _h) in edits.items())
            writer.writerow([
                stamp, eid, "", "hoist_repeated_sentence", what,
                "a paper-level sentence repeated in every segment now appears "
                "once, verbatim, as the field's last segment; no text reworded",
            ])
    print(f"wrote {DB} and logged {len(touched)} rows to {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
