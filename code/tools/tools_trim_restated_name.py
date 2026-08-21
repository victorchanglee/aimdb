"""Strip the row's own compound_name where it is restated at the head of a
prose segment.

`Other` and `electronic_structure_description` are often written as
pipe-separated segments, each opened with the compound the segment is about.
When that compound is the row's *own* `compound_name`, the prefix restates a
column the row already holds — the case CLAUDE.md rules out under "one prose
field, one job" and "not a restatement of a value another column already
holds". One row carried its name 112 times in a single cell.

Only the name itself is removed; any qualifier that follows it survives, so

    "2-nitroimidazole, S0 Franck-Condon minimum: Figure energy=0.00 eV"

becomes

    "S0 Franck-Condon minimum: Figure energy=0.00 eV"

and a segment naming a *different* species is never touched — that is data the
row would lose. Matching ignores punctuation and case but requires a word
boundary after the name, so a row for `N2` does not strip the head of an
`N2O5` segment.

Usage, from code/:
    .venv/bin/python tools/tools_trim_restated_name.py --dry-run [--limit N]
    .venv/bin/python tools/tools_trim_restated_name.py --apply
"""

import argparse
import csv
import datetime as _dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
LOG = ROOT / "logs" / "extractions.csv"

FIELDS = ("Other", "electronic_structure_description")
SEP = " | "
# Separators that may sit between the restated name and whatever qualifies it.
TRIM = " ,;:-–—()[]"
MIN_NAME = 3  # NO3, GeH, CdF: shorter than this matches too much to be safe


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def strip_name(head, name):
    """Return `head` minus a leading restatement of `name`, or None if `head`
    does not open with that name on a word boundary."""
    target = _norm(name)
    if len(target) < MIN_NAME:
        return None
    i = j = 0
    while i < len(head) and j < len(target):
        ch = head[i]
        if ch.isalnum():
            if ch.lower() != target[j]:
                return None
            j += 1
        i += 1
    if j < len(target):
        return None
    rest = head[i:]
    # The boundary test comes first: the name must have ended on a non-word
    # character, or it is only the prefix of a longer one ("N2" in "N2O5").
    if rest and rest[0].isalnum():
        return None
    # Only then discard the separators. The name's own punctuation counts as a
    # separator here, because _norm() dropped it and the match above therefore
    # stopped at the last alphanumeric: for "[Ir(ppy)2(bpy)]+" that is the y of
    # (bpy), so ")]+" is still sitting in `rest`. Left there it orphans the
    # segment as "+, state 1 ^1B ..." - 254 segments read that way once.
    return rest.lstrip(TRIM + "".join(c for c in name if not c.isalnum())).strip()


def trim_field(value, name):
    """Rewrite one field. Returns (new_value, segments_changed)."""
    if not value or not name:
        return value, 0
    out, changed = [], 0
    for seg in value.split(SEP):
        stripped = seg.strip()
        if not stripped or ":" not in stripped[:200]:
            out.append(seg)
            continue
        head, body = stripped.split(":", 1)
        if len(head) > 160:
            out.append(seg)
            continue
        rest = strip_name(head, name)
        if rest is None:
            out.append(seg)
            continue
        body = body.strip()
        new = f"{rest}: {body}" if rest else body
        if not new:
            changed += 1
            continue  # segment was nothing but the name
        out.append(new)
        changed += 1
    return SEP.join(s for s in out if s.strip()), changed


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=8,
                    help="examples to print in a dry run")
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    touched, segs, saved, shown = [], 0, 0, 0
    for r in rows:
        name = r["compound_name"].strip()
        edits = {}
        for f in FIELDS:
            new, n = trim_field(r[f], name)
            if n:
                edits[f] = (r[f], new)
                segs += n
                saved += len(r[f]) - len(new)
        if not edits:
            continue
        touched.append((r["entry_id"], edits))
        if args.dry_run and shown < args.limit:
            shown += 1
            print(f"--- {r['entry_id']}  ({name[:52]})")
            for f, (old, new) in edits.items():
                print(f"    {f}: {len(old)} -> {len(new)} chars")
                print(f"      before: {old[:150]}")
                print(f"      after : {new[:150]}")
        if args.apply:
            for f, (_old, new) in edits.items():
                r[f] = new

    print(f"\n{len(touched)} rows, {segs} segments, {saved} characters of "
          f"restated compound_name")

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
                stamp, eid, "", "trim_restated_name", what,
                "removed the row's own compound_name where it was restated at "
                "the head of a prose segment; qualifiers and segments naming "
                "other species left intact",
            ])
    print(f"wrote {DB} and logged {len(touched)} rows to {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
