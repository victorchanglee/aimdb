#!/usr/bin/env python3
"""Build the static literature-browser site from database/aimdb.csv.

Reads ../database/aimdb.csv and writes docs/data.js, an embedded
`window.LIT = {...}` blob so index.html works when opened directly
(file://) with no web server. Re-run this whenever the CSV changes:

    python3 docs/build_site.py
"""
import csv
import json
import re
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV = HERE.parent / "database" / "aimdb.csv"
OUT = HERE / "data.js"

# Periodic-table symbols, used to pull real elements out of free-text
# metal_center / formula fields.
ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr
Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn
Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir
Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr""".split())

SYMBOL_RE = re.compile(r"[A-Z][a-z]?")


def elements_in(text):
    """Return the set of real element symbols appearing as tokens in text."""
    if not text:
        return set()
    return {t for t in SYMBOL_RE.findall(text) if t in ELEMENTS}


def main():
    with open(CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    out_rows = []
    for r in rows:
        row = {k: (r.get(k) or "").strip() for k in fields}
        # Elements to filter on come from the curated `element` column, which
        # is derived from metal_center and formula but masks ligand
        # abbreviations that elements_in() misreads as symbols (OAc -> Ac,
        # Por -> Po, Nor -> No, BArF -> Ar, the word Table -> Ta). Fall back to
        # deriving them here only if that column is absent, so this script
        # still works against a pre-36-column CSV.
        metal = row.get("metal_center", "")
        # "none" was emptied database-wide on 2026-08-20; the guard is kept so
        # the script still works against an older CSV.
        metals = sorted(elements_in(metal)) if metal.lower() != "none" else []
        row["_metals"] = metals
        if "element" in fields:
            row["_elements"] = row.get("element", "").split()
        else:
            formula_els = sorted(elements_in(row.get("formula", "")))
            row["_elements"] = sorted(set(metals) | set(formula_els))
        out_rows.append(row)

    payload = {
        "generated": datetime.date.today().isoformat(),
        "fields": fields,
        "rows": out_rows,
    }
    js = "window.LIT = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"Wrote {OUT} — {len(out_rows)} rows, {len(js)} bytes")


if __name__ == "__main__":
    main()
