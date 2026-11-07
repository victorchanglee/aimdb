"""Check `electronic_structure_description` against its structured format.

The format (CLAUDE.md, user ruling 2026-11-06) is entries separated by "; ",
each `key=value[ unit] source[ method]`, with `source` `calc` or `exp` as in
`properties`. Keys: ground, character, E(<state>), gap(<A>-<B>),
barrier(<path>), f(<state>), occ(<orbital>), param(<name>), note.

`ground`, `character` and `note` hold words and need no source. The numeric
keys must carry a number (a range or ± is kept as printed) and a source.
D, E/D, g and Ueff are refused: they belong in `properties` only, an
excited state's value keyed with its state (gz@KD2).

Each row's `properties_add` (what a review adds to `properties`) is checked
strictly too: known keys, canonical units, no uncertainty in the value.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_esd_format.py                # summary over aimdb.csv
  .venv/bin/python tools/tools_esd_format.py --entry-id W123-a
  .venv/bin/python tools/tools_esd_format.py --rows file.json   # {rows:[...]} from a review pass
"""
import argparse
import csv
import json
import re
import sys

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config
from tools_properties import check_field as _prop_check  # noqa: E402

WORD_KEYS = {"ground", "character", "note"}
NUM_KEY = re.compile(r"^(E|gap|barrier|f|occ|param)\((.+)\)$")
PROPERTY_KEY = re.compile(r"^(D|E/D|g[xyz123]?|gperp|giso|Ueff)$")
NUMBER = re.compile(r"^[~<>≈]?\s*[-+−]?\d[\d.]*(?:\s*(?:±|\+/-)\s*\d[\d.]*)?(?:\s*(?:-|–|to)\s*[-+−]?\d[\d.]*)?")
SOURCES = ("calc", "exp")


def split_entries(text):
    """Split on '; ' outside parentheses (state labels may hold ';')."""
    out, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        c = text[i]
        depth += c in "([{"
        depth -= c in ")]}"
        if depth == 0 and text.startswith("; ", i):
            out.append(cur)
            cur = ""
            i += 2
            continue
        cur += c
        i += 1
    if cur.strip():
        out.append(cur)
    return [e.strip() for e in out if e.strip()]


def check_entry(entry):
    """Return None if the entry is well formed, else the reason."""
    if "=" not in entry:
        return "no key=value"
    key, value = entry.split("=", 1)
    key, value = key.strip(), value.strip()
    if PROPERTY_KEY.match(key) or re.match(r"^g[xyz123]?\(", key):
        return f"{key} belongs in properties (an excited state as gz@<state>)"
    if key in WORD_KEYS:
        return None if value else "empty value"
    m = NUM_KEY.match(key)
    if not m:
        return f"unknown key {key!r}"
    if not NUMBER.match(value):
        return "value is not a number"
    words = value.split()
    if not any(w in SOURCES for w in words):
        return "no source (calc/exp)"
    return None


def check(text):
    return [(e, r) for e in split_entries(text) for r in [check_entry(e)] if r]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entry-id")
    ap.add_argument("--rows", help="JSON {rows:[...]} to check instead of the database")
    ap.add_argument("--show", type=int, default=10, help="bad rows to print")
    a = ap.parse_args(argv)
    if a.rows:
        rows = json.load(open(a.rows, encoding="utf-8"))["rows"]
    else:
        rows = list(csv.DictReader(open(config.LITERATURE_CSV, newline="", encoding="utf-8")))
    if a.entry_id:
        rows = [r for r in rows if r["entry_id"] == a.entry_id]
    ok = bad = empty = 0
    shown = 0
    for r in rows:
        text = r.get("electronic_structure_description", "")
        perrs = [(e, "properties_add: " + why) for e, why in _prop_check(r.get("properties_add", ""))]
        if not text.strip() and not perrs:
            empty += 1
            continue
        errs = check(text) + perrs
        if errs:
            bad += 1
            if shown < a.show:
                shown += 1
                print(f"{r['entry_id']}:")
                for e, why in errs[:5]:
                    print(f"   {why}: {e[:120]}")
        else:
            ok += 1
    print(f"{ok} well formed, {bad} not, {empty} empty")
    return 1 if bad and (a.rows or a.entry_id) else 0


if __name__ == "__main__":
    sys.exit(main())
