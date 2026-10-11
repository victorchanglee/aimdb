"""Cross-reference an external ZFS extraction against aimdb, per compound.

The ZFS project at ../zfs mined 782 papers for spin-Hamiltonian D and E,
emitting one row per (compound, determination). Where it overlaps aimdb it is a
SECOND INDEPENDENT READING of the same papers, which makes it useful for one
thing aimdb cannot do for itself: naming the compounds a class-named row is
hiding.

The worked example, and the reason this exists. For 10.1039/c5dt00600g the ZFS
extraction lists NINE own-work CASSCF/NEVPT2 determinations across eight
distinct complexes -- [Ni(L5A)] through [Ni(L5F)], [Ni(L3A)(L2)] and
[Ni(L3B)(L2)] at two nickel sites -- each with its own D and E/D at CAS(8,5)/
ZORA/def2-TZVP. aimdb has ONE row for that paper, class-named "pentacoordinate
mononuclear Ni(II) Schiff-base complexes [Ni(L5)]", carrying a single
D = -64 cm-1. Seven compounds and their anisotropies are absent, and the one
stored D matches none of the eight exactly ([Ni(L5E)] at -63.2 is nearest).

WHAT IT DOES NOT CLAIM. A compound listed here as missing is a lead, not a
defect: the two projects name compounds differently and the token overlap used
to pair them is crude, so a "missing" compound may simply be the same species
under another name. And a zfs row is only counted when the value is the paper's
OWN -- rows whose evidence quote carries a bracketed citation, "quoted", "from
ref" or "literature" are dropped, because aimdb records a paper's own
calculations and not the values it cites.

Usage, from code/:
  .venv/bin/python tools/tools_crossref_zfs_project.py ../../zfs/zfs_database.csv
  .venv/bin/python tools/tools_crossref_zfs_project.py <csv> --min-missing 2
"""
import argparse
import csv
import re
from collections import defaultdict

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

csv.field_size_limit(10 ** 9)

MULTIREF = re.compile(
    r"CASSCF|RASSCF|CASPT2|NEVPT2|DMRG|MRCI|CASCI|RASPT2|MC-?PDFT|"
    r"SINGLE_ANISO|POLY_ANISO|complete active space", re.I)
# A value the paper quotes rather than computes. aimdb records own work only.
QUOTED = re.compile(r"\[\d+\]|\bquoted\b|\bfrom ref\b|\bliterature\b", re.I)
STOP = {"the", "and", "complex", "complexes", "with", "ion", "ions", "type",
        "site", "sites", "model", "models", "series", "compound", "compounds"}


def norm_doi(d):
    return (d or "").strip().lower().replace("https://doi.org/", "").rstrip("/")


def tokens(s):
    return {t for t in re.findall(r"[A-Za-z0-9()\[\]]{3,}", (s or "").lower())
            if t not in STOP}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("zfs_csv", help="path to the ZFS project's zfs_database.csv")
    ap.add_argument("--min-missing", type=int, default=1,
                    help="only report papers with at least this many unpaired "
                         "compounds (default 1)")
    args = ap.parse_args(argv)

    with open(args.zfs_csv, newline="", encoding="utf-8") as fh:
        zrows = list(csv.DictReader(fh))
    with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as fh:
        arows = list(csv.DictReader(fh))

    # zfs: own-work multireference computed determinations, by paper
    z = defaultdict(dict)
    for r in zrows:
        if (r.get("determination") or "") != "computed":
            continue
        if not MULTIREF.search("%s %s" % (r.get("method") or "",
                                          r.get("method_class") or "")):
            continue
        if QUOTED.search("%s %s" % (r.get("evidence_quote") or "",
                                    r.get("notes") or "")):
            continue
        name = (r.get("compound_name") or r.get("compound_label") or "").strip()
        if name:
            z[norm_doi(r.get("doi"))][name] = (r.get("D_cm-1") or "",
                                               r.get("E_over_D") or "")

    a = defaultdict(list)
    for r in arows:
        a[norm_doi(r["reference_doi"])].append(r)

    shared = sorted(set(z) & set(a), key=lambda d: -len(z[d]))
    print("ZFS papers with own-work multireference rows : %d" % len(z))
    print("   of those, also cited by an aimdb row      : %d" % len(shared))
    print()
    flagged = 0
    for d in shared:
        anames = [r["compound_name"] for r in a[d]]
        missing = [c for c in z[d]
                   if not any(tokens(c) & tokens(x) for x in anames)]
        if len(missing) < args.min_missing:
            continue
        flagged += 1
        print("=" * 94)
        print("%s" % d)
        print("   zfs names %d compound(s); aimdb has %d row(s)"
              % (len(z[d]), len(a[d])))
        for r in a[d]:
            print("   aimdb  %-16s %s" % (r["entry_id"], r["compound_name"][:62]))
        for c in sorted(missing):
            dv, ed = z[d][c]
            print("   zfs    %-16s %-40s D=%-9s E/D=%s" % ("", c[:40], dv, ed))
    print()
    print("%d shared paper(s) where zfs names a compound aimdb may not cover."
          % flagged)
    print("A LEAD, not a defect: the two projects name compounds differently "
          "and the pairing is by token overlap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
