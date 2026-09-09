"""Fill the derived `element` column in database/aimdb.csv.

`element` is not read from the paper and is not written by `add-row`: it is
the union of the element symbols in `metal_center` and in `formula`, space
separated and alphabetical, and it exists so the site's periodic-table filter
has something to match on. Rows appended by `add-row` therefore arrive with
it empty and this closes the gap after an intake.

By default only EMPTY cells are filled, so a curated value is never
overwritten. `--regenerate` recomputes every row from its current
`metal_center` and `formula`, which is the right thing to do only after those
two columns have actually changed.

A bare `[A-Z][a-z]?` scan misreads several common ligand abbreviations as
symbols, so those are masked out before the scan: OAc/SAc/HOAc would give
actinium, Por polonium, Nor nobelium, BArF argon, CmH2m curium, and the word
Table tantalum. Genuine entries survive, because the masks are whole-token
patterns that the real formulae (PoCl6(2-), XeH+, NoO, Ta2, AcCO,
Co2O37W10^6-) do not match.

Usage, from code/:
  .venv/bin/python tools/tools_fill_element.py            # dry run
  .venv/bin/python tools/tools_fill_element.py --apply
  .venv/bin/python tools/tools_fill_element.py --regenerate --apply
"""
import argparse
import csv
import re

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, index

ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr
Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn
Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir
Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr""".split())

SYMBOL_RE = re.compile(r"[A-Z][a-z]?")

# Ligand abbreviations and stray words a bare symbol scan misreads. Order
# matters only in that longer patterns must come first (HOAc before OAc).
MASKS = re.compile(r"HOAc|OAc|SAc|BArF|Table|Por|Nor|C[a-z]?mH2m")


def elements_in(text):
    if not text:
        return set()
    return {t for t in SYMBOL_RE.findall(MASKS.sub(" ", text)) if t in ELEMENTS}


def derive(row):
    metal = (row.get("metal_center") or "").strip()
    metals = elements_in(metal) if metal.lower() != "none" else set()
    return " ".join(sorted(metals | elements_in(row.get("formula") or "")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--regenerate", action="store_true",
                    help="recompute every row, not only the ones with an "
                         "empty element cell")
    args = ap.parse_args()

    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    changed = []
    for row in rows:
        current = (row.get("element") or "").strip()
        if current and not args.regenerate:
            continue
        new = derive(row)
        if new != current:
            changed.append((row["entry_id"], current, new))
            row["element"] = new

    for entry_id, old, new in changed[:20]:
        print(f"  {entry_id}: {old!r} -> {new!r}")
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")
    print(f"{len(changed)} row(s) would change" if not args.apply
          else f"{len(changed)} row(s) changed")

    if args.apply and changed:
        with open(config.LITERATURE_CSV, "w", newline="",
                  encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        index.log_extraction(
            "", "", "fill_element", f"{len(changed)} rows",
            "derived the `element` column from metal_center and formula for "
            + ("every row (--regenerate)" if args.regenerate
               else "rows whose element cell was empty")
            + "; ligand-abbreviation masks applied (OAc/SAc/HOAc, Por, Nor, "
              "BArF, CmH2m, the word Table)")


if __name__ == "__main__":
    main()
