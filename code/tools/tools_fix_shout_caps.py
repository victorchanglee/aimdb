"""Lower-case ordinary English words that were written mid-sentence in capitals.

Some prose fields shout: "IT WAS found that THE energies OF THE ground state
changed FOR NO more than 1200 PER centimetre", "cannot BE better than THE
basis'S ability TO represent them", "kcal/MOL". The capitals carry no
information - they are an artifact of the writing model, concentrated in the
`claude-opus-5` rows - and they make a field look corrupted.

Only a fixed list of common English words is touched, and only mid-sentence.
Chemistry is left alone by construction: `A`, `NO` and `SO` are never in the
list because they are an irreducible representation, nitric oxide and
spin-orbit; a word followed by a capital or digit is skipped, so `NO3` and
`BE2` cannot match; and the deliberate greppable markers named in CLAUDE.md
are masked out before anything is replaced.

A capitalised word at the start of a sentence is left alone - there the
capital is correct, or at worst harmless.

Usage, from code/:
    .venv/bin/python tools/tools_fix_shout_caps.py --dry-run [--limit N]
    .venv/bin/python tools/tools_fix_shout_caps.py --apply
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

FIELDS = ("Other", "electronic_structure_description", "notes",
          "active_space_protocol")

# Deliberately absent: A, NO, SO, AT, IN, ON, IT, AS, BY, OR - each is a real
# chemical token somewhere (irrep, nitric oxide, spin-orbit, astatine, indium,
# iridium/osmium pairs in formulas). The list is words that carry no chemical
# meaning standing alone.
WORDS = ["THE", "AN", "IS", "WAS", "WERE", "ARE", "BE", "NOT", "OF", "FOR",
         "PER", "AND", "BUT", "THAT", "THIS", "THESE", "WITH", "FROM", "TO",
         "ALL", "ITS", "HAS", "HAVE", "HAD", "WHICH", "WHEN", "THAN", "BOTH",
         "EACH", "ONE", "TWO", "THREE", "MUCH", "MORE", "ONLY", "SAME", "OWN",
         "MOL"]
WORD_RE = re.compile(rf"^[(\[\"']*(?:{'|'.join(WORDS)})[)\]\"',.;:!?]*$")

# Markers that are meant to be capitals. CLAUDE.md requires the first one to
# stay greppable, so it must survive verbatim.
PROTECTED = ["ACTIVE SPACE IS HARDWARE-LIMITED", "MODEL CAVEAT"]
_SENTINEL = "\x00%d\x00"
_SENT_END = ".!?|:;"


def fix(text):
    """Returns (new_text, n_replacements).

    Works on whole whitespace-delimited tokens. A word only counts when it
    stands alone: "HS-IS" keeps its IS, because there it means intermediate
    spin rather than the verb, and "TWO-STATE" is left whole rather than
    half-lowered into "two-STATE".
    """
    if not text:
        return text, 0
    masked, marks = text, []
    for i, marker in enumerate(PROTECTED):
        if marker in masked:
            masked = masked.replace(marker, _SENTINEL % i)
            marks.append(i)

    out, last, n = [], 0, 0
    for m in re.finditer(r"\S+", masked):
        token = m.group(0)
        if not WORD_RE.match(token):
            continue
        prev = masked[:m.start()].rstrip()
        # Start of the field, or of a sentence / segment / clause label.
        if not prev or prev[-1] in _SENT_END:
            continue
        out.append(masked[last:m.start()])
        out.append(token.lower())
        last = m.end()
        n += 1
    out.append(masked[last:])
    result = "".join(out)

    for i in marks:
        result = result.replace(_SENTINEL % i, PROTECTED[i])
    return result, n


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

    touched, total, shown, per_word = [], 0, 0, Counter()
    for r in rows:
        edits, n_row = {}, 0
        for f in FIELDS:
            new, n = fix(r[f])
            if n:
                edits[f] = new
                n_row += n
        if not edits:
            continue
        total += n_row
        touched.append((r["entry_id"], n_row))
        if args.dry_run and shown < args.limit:
            shown += 1
            f = next(iter(edits))
            old = r[f]
            i = next((k for k in range(len(old)) if old[k:k + 1].isupper()
                      and old[k:] != edits[f][k:]), 0)
            print(f"--- {r['entry_id']} ({r['mining_model']}) {n_row} fixes in {f}")
            print(f"    before: ...{old[max(0, i - 60):i + 90]}")
            print(f"    after : ...{edits[f][max(0, i - 60):i + 90]}")
        if args.apply:
            for f, new in edits.items():
                r[f] = new

    print(f"\n{len(touched)} rows, {total} capitalised words lowered")

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
        for eid, n in touched:
            writer.writerow([
                stamp, eid, "", "fix_shout_caps", f"{n} words lowered",
                "mid-sentence capitals on ordinary English words lowered; "
                "chemical tokens and the greppable CLAUDE.md markers untouched",
            ])
    print(f"wrote {DB} and logged {len(touched)} rows to {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
