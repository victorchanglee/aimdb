"""Export the computed-ZFS molecules with fewer than 100 atoms.

A row counts as a computed-ZFS molecule when its `properties` holds a computed D
(any method tag). Its atom count is taken, in this order, from:

  1. the row's `formula`, when every symbol in it is an element (an abbreviated
     formula such as Co(SPh)4 or Fe(TPP)Cl cannot be counted and is skipped);
  2. the structure file: an .xyz file's first frame, or a CIF's
     `_chemical_formula_sum`. A CIF formula is the crystal's formula unit,
     counter-ions and solvent included, so it is an upper bound on the
     molecule: below 100 it settles the question, at 100 or more it does not.

--single-metal keeps only molecular complexes (system_class molecule) whose
metal_center is one d/f-block element and whose readable composition holds
exactly one d/f metal atom. A CIF with several (Z' > 1, or a metal counter-ion)
cannot settle it and goes to undetermined.

Rows whose count cannot be settled are listed in a third file, so nothing is
dropped silently.

Writes, under --out (default exports/zfs_lt100/):
  structures/<file>              copies of the structure files of molecules < 100 atoms
  with_structure.csv             one line per row in structures/
  without_structure.csv          rows < 100 atoms that have no structure file
  undetermined.csv               rows whose atom count could not be settled

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_export_small_zfs.py [--limit 100] [--out ../exports/zfs_lt100]
"""
import argparse
import csv
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config
import tools_properties as tp

ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn
Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm
Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu
Am Cm Bk Cf Es Fm Md No Lr""".split())
STRUCT = config.DATABASE_DIR / "structures"
# d- and f-block metals: what "single-metal complex" counts
DF = set("""Sc Ti V Cr Mn Fe Co Ni Cu Zn Y Zr Nb Mo Tc Ru Rh Pd Ag Cd Hf Ta W Re Os Ir Pt Au Hg
La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr""".split())


def count_formula(formula):
    """Atom count of a formula whose every symbol is an element, else None.

    Handles nested () and [] with multipliers and a trailing charge
    ("[Co(NCS)4]2-", "C6H6", "Ni(H2O)6^2+"); refuses abbreviations.
    """
    f = re.sub(r"\s+\d*[+-]$", "", (formula or "").strip())   # "C44H26N4O12S4 4-"
    if not f or " " in f or "." in f or "·" in f:
        return None
    f = re.sub(r"\^?\d*[+-]$|\(\d*[+-]\)$", "", f)   # trailing charge
    pos = 0

    def group(close):
        nonlocal pos
        total = Counter()
        while pos < len(f):
            c = f[pos]
            if c in "([":
                pos += 1
                inner = group(")" if c == "(" else "]")
                if inner is None:
                    return None
                n = num()
                for k, v in inner.items():
                    total[k] += v * n
            elif c in ")]":
                if c != close:
                    return None
                pos += 1
                return total
            else:
                m = re.match(r"[A-Z][a-z]?", f[pos:])
                if not m or m.group(0) not in ELEMENTS:
                    return None
                pos += len(m.group(0))
                total[m.group(0)] += num()
        return total if close is None else None

    def num():
        nonlocal pos
        m = re.match(r"\d+", f[pos:])
        if not m:
            return 1
        pos += len(m.group(0))
        return int(m.group(0))

    out = group(None)
    return out or None


def count_xyz(path):
    """Composition of the first frame of an .xyz file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        n = int(lines[0].split()[0])
        body = lines[2:2 + n]
    except (IndexError, ValueError):
        body = lines
    comp = Counter(m.group(1) for l in body for m in [re.match(r"^\s*([A-Z][a-z]?)\s+-?\d", l)] if m)
    return comp or None


def count_cif(path):
    m = re.search(r"(?m)^_chemical_formula_sum\s+['\"]?([^'\"\n]+)", path.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    comp = Counter()
    for sym, k in re.findall(r"([A-Z][a-z]?)\s*(\d*\.?\d*)", m.group(1)):
        comp[sym] += float(k) if k else 1
    return comp or None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--single-metal", action="store_true",
                    help="only molecular complexes with exactly one d/f metal atom")
    ap.add_argument("--out", default=str(config.PROJECT_ROOT / "exports" / "zfs_lt100")
                    if hasattr(config, "PROJECT_ROOT") else "../exports/zfs_lt100")
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "structures").mkdir(parents=True, exist_ok=True)
    cols = ["entry_id", "compound_name", "formula", "metal_center", "atoms", "atoms_from",
            "structure_file", "structure_provenance", "active_space_nel", "active_space_norb",
            "properties", "reference_doi"]
    ws, wo, und = [], [], []
    for r in csv.DictReader(open(config.LITERATURE_CSV, newline="", encoding="utf-8")):
        p = tp.parse(r["properties"]) if r["properties"] else {}
        if not any(tp.base_key(k) == "D" and s == "calc" for k, s in p):
            continue
        # single-metal molecular complex: one d/f metal named, a molecule (not a
        # cluster model or solid), and -- where a composition can be read --
        # exactly one d/f metal atom in it
        if a.single_metal and (r["system_class"] != "molecule" or r["metal_center"].strip() not in DF):
            continue
        # a coordination polymer ({...}n): its structure file is the extended
        # crystal, not the mononuclear model the calculation cut from it
        if a.single_metal and re.search(r"\}\s*n\b|polymer", r["compound_name"], re.I):
            continue
        sf = r["structure_file"]
        comp, src, bound = count_formula(r["formula"]), "formula", False
        if comp is None and sf and sf.endswith(".xyz"):
            comp, src = count_xyz(STRUCT / sf), "xyz file"
        elif comp is None and sf and sf.endswith(".cif"):
            comp, src, bound = count_cif(STRUCT / sf), "CIF formula unit (upper bound)", True
        row = {c: r.get(c, "") for c in cols}
        n = int(round(sum(comp.values()))) if comp else None
        nmet = sum(v for k, v in comp.items() if k in DF) if comp else None
        if a.single_metal and comp and nmet != 1 and not (bound and nmet > 1 and n is not None):
            continue  # a polynuclear formula or file
        if comp is None or (bound and (n >= a.limit or nmet != 1)):
            row["atoms"], row["atoms_from"] = "", ""
            und.append(row)
            continue
        row["atoms"], row["atoms_from"] = n, src
        if n < a.limit:
            if sf:
                shutil.copy2(STRUCT / sf, out / "structures" / sf)
                ws.append(row)
            else:
                wo.append(row)
    for name, rows in (("with_structure.csv", ws), ("without_structure.csv", wo), ("undetermined.csv", und)):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    print(f"< {a.limit} atoms: {len(ws)} with a structure (copied), {len(wo)} without; "
          f"{len(und)} undetermined -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
