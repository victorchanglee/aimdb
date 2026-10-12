"""Find Cartesian coordinate blocks in the local text, and pair them with rows.

A paper's real geometry lives in a coordinate table, almost always in the SI
and occasionally in the main text. This tool finds every such block in
`text/<key>*.txt` (article and `_si_` files alike) and reports, per block, the
atom count, the composition it implies, the heading lines printed just above
it, and which of the paper's rows have a `formula` of the same composition.
It writes nothing to the database: pairing a block with a row is a reading
decision, because an SI prints every stationary point, every conformer and
every DFT comparison geometry, and only one of them is the one the row's
calculation used. The report is the worklist for that reading.

A block is a run of at least `--min-atoms` consecutive lines of the form
`<symbol or atomic number> <x> <y> <z>` (an optional leading index is
allowed). Lines with fewer than three decimals are not counted, which keeps
tables of bond lengths out. Blocks whose composition matches no row of the
paper are still reported, since the row's formula may be abbreviated or empty.

Output: logs/coordinate_blocks.csv with one line per block, and a summary of
how many papers with structureless rows have at least one block.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_find_coordinate_blocks.py
  .venv/bin/python tools/tools_find_coordinate_blocks.py --keys W123 W456
  .venv/bin/python tools/tools_find_coordinate_blocks.py --show W123   # print the blocks
"""
import argparse
import csv
import re
import sys
from collections import Counter

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

OUT = config.LOGS_DIR / "coordinate_blocks.csv"

SYMBOLS = """H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co
Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe
Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl
Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr""".split()
Z = {s: i + 1 for i, s in enumerate(SYMBOLS)}

_MINUS = "-\u2212\u2010\u2011\u2012\u2013"  # PDF text prints minus as any of these
_NUM = rf"(?:[{_MINUS}]?\s?\d+(?:\.\d*)?|[{_MINUS}]?\s?\.\d+)"
# an optional nuclear-charge column after the symbol ("C  6.0  x y z", GAMESS
# and some Molpro listings) is skipped; it is recognised by its ".0" ending
# ... and Gaussian's "center  atomic-number  atomic-type  x y z" carries a bare
# integer type column (usually 0); either is consumed only when exactly three
# numbers follow it, so "C 0 1.2 3.4" still reads x = 0
LINE = re.compile(
    r"^\s*(?:\d{1,4}\s+)?([A-Z][a-z]?|\d{1,3})(?:\d{0,2})?\s+"
    rf"(?:(?:\d{{1,3}}\.0|\d{{1,2}})\s+(?={_NUM}\s+{_NUM}\s+{_NUM}\s*$))?"
    rf"({_NUM})\s+({_NUM})\s+({_NUM})\s*(\S*)\s*$")
_PRECISE = re.compile(r"\d\.\d{3,}")


def precise(line):
    """At least two of a coordinate line's numbers carry three decimals or
    are an exact zero; a table of charges or exponents rarely does, while an
    exact 0. in a symmetric geometry legitimately happens."""
    exact_zero = len(re.findall(r"(?<![\d.])[-−]?0\.?(?![\d])", line))
    return len(_PRECISE.findall(line)) + exact_zero >= 2


def atom_of(token):
    if token.isdigit():
        z = int(token)
        return SYMBOLS[z - 1] if 0 < z <= len(SYMBOLS) else None
    return token if token in Z else None


def hill(counts):
    parts = []
    if "C" in counts:
        parts.append(("C", counts["C"]))
        if "H" in counts:
            parts.append(("H", counts["H"]))
        rest = sorted(k for k in counts if k not in ("C", "H"))
    else:
        rest = sorted(counts)
    parts += [(k, counts[k]) for k in rest]
    return "".join(f"{k}{n if n > 1 else ''}" for k, n in parts)


def parse_formula(text):
    """Element counts for a plain formula, charge ignored; None when the
    string is not one. A bare trailing sign is a charge and the digits before
    it stoichiometry (N2+ is the N2 cation); a charge with its own digits must
    be marked, ^2+ or (2+). A single symbol with digits and a bare sign
    (Cu2+: the ion, or the diatomic cation?) is ambiguous and returns None."""
    s = (text or "").strip().replace("−", "-")
    s = re.sub(r"\^\(?\d*[+-]\)?$|\(\d*[+-]\)$", "", s).strip()
    signed = bool(re.search(r"[+-]$", s))
    s = re.sub(r"[+-]+$", "", s).strip()
    s = re.sub(r"^\[|\]$", "", s)
    if signed and re.fullmatch(r"[A-Z][a-z]?\d+", s):
        return None
    if not re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", s):
        return None
    counts = Counter()
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", s):
        if el not in Z:
            return None
        counts[el] += int(n) if n else 1
    return dict(counts)


NOISE = re.compile(
    r"^\s*$|^--- page \d+ ---$|^\s*Downloaded from\b|^\s*S-?\d{1,3}\s*$|^\s*\d{1,4}\s*$"
    r"|^\s*Page \d+ of \d+\s*$|^\s*Supporting Information\s*$", re.I)
MAX_NOISE = 4  # a page break in an extracted PDF is at most this many junk lines
HEADER = re.compile(
    r"^(Center|Number|Atom\b|ATOM\b|-{3,}|Standard orientation|Input orientation|"
    r"Z-Matrix orientation|Coordinates|x\s*y\s*z|X\s*Y\s*Z|centre no\.|E\s*[=(]|"
    r"Energy|SCF Done|Charge\s*=|\d+\s*$|Cartesian|Symbol|Type|Atomic|No\.)", re.I)


def find_blocks(path, min_atoms):
    """Runs of coordinate lines, joined across page-break noise. Each block
    carries the atom list, the raw lines (noise removed) and a heading."""
    # split on newline only, so a reported line number is what `sed -n` and
    # `grep -n` show; splitlines() also breaks on form feeds and Unicode
    # separators, which 231 of the text files contain
    lines = path.read_text(encoding="utf-8", errors="ignore").split("\n")
    blocks, run, start, pending = [], [], None, []
    for i, line in enumerate(lines):
        m = LINE.match(line)
        sym = atom_of(m.group(1)) if m else None
        if sym:
            if not run:
                start = i
            run.append((i, sym))
            pending = []
            continue
        if run and NOISE.match(line) and len(pending) < MAX_NOISE:
            pending.append(i)
            continue
        if len(run) >= min_atoms:
            blocks.append((start, run))
        run, pending = [], []
    if len(run) >= min_atoms:
        blocks.append((start, run))
    out = []
    for start, run in blocks:
        if sum(precise(lines[i]) for i, _ in run) < 0.6 * len(run):
            continue  # a table of numbers that happens to start with a symbol
        atoms = [s for _, s in run]
        heading = [l.strip() for l in lines[max(0, start - 6):start] if l.strip()]
        heading = [h for h in heading if not LINE.match(h) and not NOISE.match(h)][-3:]
        # the species label usually sits above a program's own column header
        # (Gaussian's "Center Atomic ... Coordinates"), so look further back
        # for the nearest line that is neither header nor coordinates
        label = ""
        for j in range(start - 1, max(-1, start - 14), -1):
            t = lines[j].strip()
            if (t and not LINE.match(t) and not NOISE.match(t)
                    and not HEADER.match(t)):
                label = t
                break
        counts = Counter(atoms)
        plausible = (len(counts) <= 6 and len(atoms) >= 2 and
                     (len(atoms) >= 6 or re.search(
                         r"coord|geometr|xyz|angstr|bohr|structure|optimi|\bÅ\b",
                         " ".join(heading), re.I) is not None))
        out.append({"line": start + 1, "natoms": len(atoms),
                    "formula": hill(counts), "heading": " | ".join(heading),
                    "label": label,
                    "plausible": plausible, "atoms": atoms,
                    "lines": [lines[i] for i, _ in run],
                    "spans_pages": any("--- page" in lines[j]
                                       for j in range(start, run[-1][0]))})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--min-atoms", type=int, default=3)
    ap.add_argument("--show", help="print every block of this key")
    args = ap.parse_args(argv)

    with config.LITERATURE_CSV.open(newline="", encoding="utf-8") as fh:
        db = list(csv.DictReader(fh))
    by_key = {}
    for r in db:
        by_key.setdefault(r["entry_id"].rsplit("-", 1)[0], []).append(r)

    if args.show:
        for path in sorted(config.TEXT_DIR.glob(f"{args.show}*.txt")):
            for b in find_blocks(path, args.min_atoms):
                print(f"== {path.name} line {b['line']} {b['natoms']} atoms {b['formula']}")
                print("   label:  ", b["label"])
                print("   heading:", b["heading"])
                for l in b["lines"][:4]:
                    print("   ", l.strip())
                if b["natoms"] > 4:
                    print("    ...")
        return 0

    keys = args.keys or sorted(by_key)
    records, papers_hit, papers_hit_structureless = [], 0, 0
    for key in keys:
        rows = by_key.get(key, [])
        files = sorted(config.TEXT_DIR.glob(f"{key}*.txt"))
        found = False
        for path in files:
            for b in find_blocks(path, args.min_atoms):
                found = True
                comp = parse_formula(b["formula"])
                matches = [r["entry_id"] for r in rows
                           if parse_formula(r.get("formula")) == comp]
                unfilled = [e for e in matches
                            if not next(r for r in rows if r["entry_id"] == e)["structure_file"]]
                records.append({
                    "key": key, "file": path.name, "line": b["line"],
                    "natoms": b["natoms"], "formula": b["formula"],
                    "plausible": "yes" if b["plausible"] else "",
                    "spans_pages": "yes" if b["spans_pages"] else "",
                    "heading": b["heading"][:300],
                    "label": b["label"][:200],
                    "rows_same_formula": " ".join(matches),
                    "rows_same_formula_no_structure": " ".join(unfilled),
                    "rows_in_paper": len(rows),
                    "rows_without_structure": sum(1 for r in rows if not r["structure_file"]),
                })
        if found:
            papers_hit += 1
            if any(not r["structure_file"] for r in rows):
                papers_hit_structureless += 1
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0].keys()) if records else ["key"])
        w.writeheader()
        w.writerows(records)
    print(f"{len(records)} blocks in {papers_hit} papers "
          f"({papers_hit_structureless} with at least one structureless row); "
          f"{sum(1 for r in records if r['rows_same_formula_no_structure'])} blocks "
          f"match a structureless row's formula -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
