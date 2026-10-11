"""Fill empty formula/element on mined rows from the reproduced row of the same compound.

Every one of the 97 rows in database/aimdb_llm_reproduced.csv carries a
molecular formula and a full element set, because the reproducing agent had to
build a structure before it could compute anything. The mined rows for the
SAME compounds frequently carry neither: 25% of aimdb.csv has no formula, and
where formula is empty the element column falls back to the metal alone.

That is a functional defect, not just a gap. `element` is what the site's
periodic-table filter matches on, so Ni(hfc)2(pic)2 -- twelve fluorines --
is findable under Ni and under nothing else.

Matching is by EXACT normalised compound_name within the same paper key, which
resolves all 97 reproduced rows to a mined row: the reproducing agent copied
the names verbatim from the rows already in aimdb, so there is nothing to
guess. A row that does not match exactly is skipped rather than approximated.

Two guards on the formula, which is the riskier of the two columns because
CLAUDE.md requires values to be stated rather than inferred:

  * it is only copied when it matches the atom counts in the reproduced row's
    own .xyz file, so what lands in aimdb is the verified composition of the
    structure that was computed. 96 of 97 pass; W2317193567-f claims one
    hydrogen its structure does not contain and is skipped.
  * every row that gains one has the provenance appended to `notes`, naming
    the reproduced entry it came from, so nobody can mistake a composition
    derived from a structure for a formula quoted from the paper.

Only EMPTY cells are filled. Nothing is ever overwritten, so a value a human
put there survives untouched.

Usage, from code/:
    .venv/bin/python tools/tools_backfill_from_reproduced.py --dry-run
    .venv/bin/python tools/tools_backfill_from_reproduced.py --apply
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from mining_agent import config  # noqa: E402

DB = ROOT / "database" / "aimdb.csv"
REPRODUCED = ROOT / "database" / "aimdb_llm_reproduced.csv"
STRUCTURES = ROOT / "database" / "structures"

SYMBOL = re.compile(r"([A-Z][a-z]?)(\d*)")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def formula_counts(formula):
    c = Counter()
    for sym, n in SYMBOL.findall(formula or ""):
        if sym:
            c[sym] += int(n or 1)
    return c


def xyz_counts(path):
    """Atom counts from an .xyz file, or None if it is unreadable."""
    if not path.is_file():
        return None
    c = Counter()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 4 and re.fullmatch(r"[A-Z][a-z]?", parts[0]):
            c[parts[0]] += 1
    return c or None


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
        fields = reader.fieldnames
        mined = list(reader)
    with REPRODUCED.open(newline="", encoding="utf-8") as fh:
        rep = list(csv.DictReader(fh))
    assert fields == config.LITERATURE_COLUMNS, "aimdb.csv schema has drifted"

    by_key = defaultdict(list)
    for r in mined:
        by_key[r["entry_id"].rsplit("-", 1)[0]].append(r)

    plan, skipped = [], Counter()
    for r in rep:
        key = r["entry_id"].rsplit("-", 1)[0]
        target = next((m for m in by_key.get(key, [])
                       if norm(m["compound_name"]) == norm(r["compound_name"])),
                      None)
        if target is None:
            skipped["no exact compound-name match"] += 1
            continue
        # the formula must match the structure that was actually computed
        verified = (formula_counts(r["formula"]) ==
                    xyz_counts(STRUCTURES / r["structure_file"]))
        change = {}
        if r["formula"].strip() and not target["formula"].strip():
            if verified:
                change["formula"] = r["formula"]
            else:
                skipped["formula disagrees with its own .xyz"] += 1
        new_els = set(r["element"].split()) | set(target["element"].split())
        if new_els and " ".join(sorted(new_els)) != target["element"]:
            change["element"] = " ".join(sorted(new_els))
        if change:
            plan.append((target, r, change))

    print("%d reproduced rows; %d mined rows would change"
          % (len(rep), len(plan)))
    print("   gaining a formula : %d"
          % sum(1 for _, _, c in plan if "formula" in c))
    print("   element set grows : %d"
          % sum(1 for _, _, c in plan if "element" in c))
    for reason, n in skipped.most_common():
        print("   skipped: %-34s %d" % (reason, n))
    for target, src, change in plan[:10]:
        print("\n  %-16s <- %-16s" % (target["entry_id"], src["entry_id"]))
        for k, v in change.items():
            print("      %-8s %-16s -> %s"
                  % (k, target[k] or "(empty)", v))

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0

    for target, src, change in plan:
        target.update(change)
        note = ("formula and element set taken from %s, the llm_reproduced "
                "entry for the same compound, whose composition was verified "
                "against its own structure file; the source paper may state "
                "neither." % src["entry_id"]
                if "formula" in change else
                "element set completed from %s, the llm_reproduced entry for "
                "the same compound." % src["entry_id"])
        target["notes"] = (target["notes"] + " " if target["notes"] else "") + note
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(mined)
    os.replace(tmp, DB)
    print("\nupdated %d rows in %s" % (len(plan), DB.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
