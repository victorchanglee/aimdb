"""Save one data block of a paper's CIF as the row's structure, verbatim.

A CIF is an allowed structure format (user ruling 2026-11-05). Most ZFS and
magnetism papers compute on the X-ray structure and deposit it as a CIF, not
as a coordinate table, so this is the only route to the geometry their
calculation used. The block is copied byte-for-byte from `data_<name>` up to
the next `data_` line, minus any embedded reflection data (`_shelx_hkl_file`,
`_shelx_fab_file`, `_refln_` loops: diffraction intensities, not structure), under two `#` comment lines giving its provenance, to
`database/structures/<entry_id>.cif`. The row gets `structure_file`,
`structure_provenance=experimental`, a note, and a log entry.

What is checked before anything is written:
  - the block exists and has an atom-site loop (a `publication_text` or
    `global` block carries no coordinates and is refused);
  - the block's `_chemical_formula_sum` is printed in the note, so a reader
    can see that it is the crystal formula (salt, solvate) and not the row's
    molecule;
  - the row has no `structure_file` yet, unless --replace.

Which block belongs to which row is a reading decision, made from the
block's formula, name and CCDC number against the row; --batch applies a
reviewed JSON list of {"entry_id", "cif", "block", "what"} decisions.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_save_cif_block.py --entry-id W123-a \\
      --cif ../papers/si/W123/x_si_002.cif --block complex1 --what "complex 1"
  .venv/bin/python tools/tools_save_cif_block.py --batch decisions.json
"""
import argparse
import csv
import json
import re
from pathlib import Path

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, csvio, index


def cif_block(text, name):
    for part in re.split(r"(?m)^(?=data_)", text):
        m = re.match(r"data_(\S+)", part)
        if m and m.group(1) == name:
            return part
    return None


REFLECTIONS = re.compile(
    r"(?ms)^_shelx_(?:hkl|fab)_file\s*\n;.*?^;[ \t]*\n"      # embedded hkl/fab text fields
    r"|^loop_\s*\n(?:_refln_\S*[^\n]*\n)+(?:(?!loop_|_|data_|#)[^\n]*\n)*")  # _refln loop + rows


def strip_reflections(block):
    """Drop embedded reflection data (diffraction intensities, not structure)."""
    out, n = REFLECTIONS.subn("", block)
    return out, n


def tag(block, name):
    m = re.search(r"(?m)^_" + re.escape(name) + r"\s+(.+)$", block)
    return m.group(1).strip().strip("'\"") if m else ""


def save(entry_id, cif, block_name, what, replace=False, dry_run=False):
    rows = {r["entry_id"]: r for r in csv.DictReader(open(config.LITERATURE_CSV, newline="", encoding="utf-8"))}
    row = rows.get(entry_id)
    if row is None:
        raise SystemExit(f"no row {entry_id}")
    if row.get("structure_file") and not replace:
        raise SystemExit(f"{entry_id} already has {row['structure_file']} (use --replace)")
    path = Path(cif)
    block = cif_block(path.read_text(encoding="utf-8", errors="replace"), block_name)
    if block is None:
        raise SystemExit(f"no data_{block_name} in {path}")
    if "_atom_site_fract_x" not in block and "_atom_site_Cartn_x" not in block:
        raise SystemExit(f"data_{block_name} has no atom-site coordinates")
    block, nref = strip_reflections(block)
    ccdc = tag(block, "database_code_depnum_ccdc_archive")
    fsum = tag(block, "chemical_formula_sum")
    dest = config.DATABASE_DIR / "structures" / f"{entry_id}.cif"
    m = re.match(r"cod_(\d+)\.cif$", path.name)
    c = re.match(r"ccdc_(\d+)\.cif$", path.name)
    origin = (f"Crystallography Open Database entry COD {m.group(1)} (https://www.crystallography.net/cod/{m.group(1)}.cif), deposited with {row.get('reference_doi','')}"
              if m else
              f"CCDC deposition {c.group(1)} (CCDC Access Structures, downloaded by the user), cited in {row.get('reference_doi','')}"
              if c else f"the paper's SI file {path.name}")
    head = (f"# VERBATIM data block data_{block_name} from {origin}{' ' + ccdc if ccdc else ''}\n"
            f"# {what}; crystal formula {fsum or 'not printed'}. Experimental (X-ray) structure, not optimised."
            f"{' Embedded reflection data omitted.' if nref else ''}\n")
    note = (f"structure_file {dest.name} is CIF data block '{block_name}'"
            f"{' (' + ccdc + ')' if ccdc else ''} copied verbatim from {origin}"
            f"{' (embedded reflection data omitted)' if nref else ''}; "
            f"crystal formula {fsum or 'not printed'} (the crystal, including any counter-ions and solvent)"
            f"{'. Match: ' + what if what else ''}")
    if dry_run:
        print(f"would write {dest.name}: {len(block)} chars; {note}")
        return
    dest.write_text(head + block, encoding="utf-8")
    csvio.set_structure_file(entry_id, dest.name, note, provenance="experimental")
    index.log_extraction(entry_id, row.get("reference_doi", ""), "structure", "verbatim_cif",
                         f"{dest.name} from {path.name} data_{block_name}: {what}")
    print(f"saved {dest.name} ({fsum})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entry-id"); ap.add_argument("--cif"); ap.add_argument("--block")
    ap.add_argument("--what", default="")
    ap.add_argument("--batch", help="JSON list of {entry_id, cif, block, what}")
    ap.add_argument("--replace", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    jobs = json.load(open(a.batch)) if a.batch else [{"entry_id": a.entry_id, "cif": a.cif, "block": a.block, "what": a.what}]
    for j in jobs:
        save(j["entry_id"], j["cif"], j["block"], j.get("what", ""), a.replace, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
