"""Save a coordinate block from a paper's text as the row's structure, verbatim.

`tools_find_coordinate_blocks.py` lists the blocks; a reader decides which
block is the geometry the row's calculation used. This tool does the copying:
it re-reads the block at the given line of `text/<file>`, writes
`database/structures/<entry_id>.xyz` with a VERBATIM provenance line, sets
`structure_file` and `structure_provenance` on the row, appends the note to
`notes`, and logs the edit — the same path `python -m mining_agent structure`
takes for a generated conformer, with the opposite provenance.

What is checked before anything is written:
  - the block's composition against the row's `formula`, when that formula
    is a plain one; a mismatch is refused unless --force, and the mismatch is
    then recorded in the note;
  - the row has no `structure_file` yet, unless --replace;
  - `--provenance` is `computational` or `experimental`, which is the reader's
    statement of how the paper obtained that geometry.

Several --line values write a multi-frame XYZ, for a row that stands for more
than one stationary point (a localized/delocalized pair, say). --bohr converts
the printed values to angstrom with 1 bohr = 0.529177210903 and says so in
the comment line; coordinates are otherwise copied as printed, with the
Unicode minus normalised to ASCII.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_save_coordinate_block.py --entry-id W123-a \\
      --file W123_si_001.txt --line 2578 --provenance computational \\
      --what "Table S7, 9HDAP ground state at MS(3)-CASPT2(10,9)/cc-pVDZ"
"""
import argparse
import re
import sys
from pathlib import Path
from collections import Counter

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, csvio, index
from tools_find_coordinate_blocks import LINE, atom_of, find_blocks, hill, parse_formula

BOHR = 0.529177210903


def block_at(path, line, min_atoms=2):
    for b in find_blocks(path, min_atoms):
        if b["line"] == line:
            return b
    near = [b["line"] for b in find_blocks(path, min_atoms) if abs(b["line"] - line) < 40]
    raise SystemExit(f"no block starts at line {line} of {path.name}; nearby blocks start at {near}")


def block_in_range(path, first, last):
    """Every coordinate line between two 1-based line numbers, as one frame:
    for a geometry the PDF text splits across a page break that the scanner
    could not join (a stray header line in the middle, say)."""
    lines = path.read_text(encoding="utf-8", errors="ignore").split("\n")  # grep numbering
    picked, atoms = [], []
    for i in range(first - 1, min(last, len(lines))):
        line = lines[i]
        m = LINE.match(line)
        sym = atom_of(m.group(1)) if m else None
        if not sym:
            # a species label printed on the first coordinate line
            # ("AmBO Am 0.223 ..."): in an explicit range, drop the label token
            # and keep the line, but only when what follows is a full coordinate line
            parts = line.split(None, 1)
            if len(parts) == 2 and atom_of(parts[0]) is None:
                m2 = LINE.match(parts[1])
                if m2 and atom_of(m2.group(1)):
                    print(f"  line {i + 1}: leading label {parts[0]!r} dropped", file=sys.stderr)
                    line, m, sym = parts[1], m2, atom_of(m2.group(1))
        if sym:
            picked.append(line)
            atoms.append(sym)
    if not atoms:
        raise SystemExit(f"no coordinate lines in {path.name} lines {first}-{last}")
    heading = [l.strip() for l in lines[max(0, first - 4):first - 1] if l.strip()]
    return {"line": first, "natoms": len(atoms), "formula": hill(Counter(atoms)),
            "heading": " | ".join(heading), "lines": picked}


_MINUS_MAP = {ord(c): "-" for c in "\u2212\u2010\u2011\u2012\u2013"}  # minus signs PDF text prints
_NUMTOK = re.compile(r"^[-\u2212]?(?:\d+\.\d*|\.\d+|\d+)$")


def suspicious(raw):
    """A coordinate line the PDF text has mangled: a digit run split by a
    space ("26.1 338842070"), a fourth numeric column, a coordinate with no
    decimal point, or a magnitude no molecule has. Such lines pass the atom
    count, so they must be refused here. Judged on what LINE itself parsed,
    so index, symbol, atomic-number and type columns are already accounted for."""
    m = LINE.match(raw)
    if not m:
        return "not a coordinate line"
    sym, x, y, z, trailing = m.groups()
    if trailing and _NUMTOK.match(trailing):
        return f"a fourth numeric column: {trailing}"
    for t in (x, y, z):
        t = re.sub("[\u2212\u2010\u2011\u2012\u2013]", "-", t).replace(" ", "")
        if "." not in t and t.strip("-") != "0":
            return f"coordinate without a decimal point: {t}"
        if abs(float(t)) > 500:
            return f"implausible magnitude: {t}"
    return ""


def frame_lines(block, bohr):
    out = []
    for raw in block["lines"]:
        why = suspicious(raw)
        if why:
            raise SystemExit(f"refusing a mangled coordinate line ({why}): {raw.strip()!r}")
        m = LINE.match(raw)
        sym = atom_of(m.group(1))
        xyz = [float(v.translate(_MINUS_MAP).replace(" ", "")) for v in m.groups()[1:4]]
        if bohr:
            xyz = [v * BOHR for v in xyz]
            out.append(f"{sym:2s}  {xyz[0]:14.8f} {xyz[1]:14.8f} {xyz[2]:14.8f}")
        else:
            vals = [v.translate(_MINUS_MAP).replace(" ", "") for v in m.groups()[1:4]]
            out.append(f"{sym:2s}  {vals[0]:>16s} {vals[1]:>16s} {vals[2]:>16s}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", help="JSON list of decisions, each with the keys of the "
                                    "options below (entry_id, file, line or range, provenance, "
                                    "what, frame_labels, bohr, force, replace); applied in order")
    ap.add_argument("--entry-id")
    ap.add_argument("--file", help="name of the file under text/")
    ap.add_argument("--line", type=int, nargs="*", default=[],
                    help="first line of the block (1-based, as the scanner reports)")
    ap.add_argument("--range", type=int, nargs="+", default=[], metavar="N",
                    help="FIRST LAST pairs: every coordinate line in that span is one frame")
    ap.add_argument("--provenance", choices=("computational", "experimental"))
    ap.add_argument("--what",
                    help="what the paper says the block is: table number, species, state, level")
    ap.add_argument("--frame-labels", nargs="*", help="one label per --line for a multi-frame file")
    ap.add_argument("--bohr", action="store_true", help="source prints bohr; convert to angstrom")
    ap.add_argument("--force", action="store_true", help="save despite a formula mismatch")
    ap.add_argument("--replace", action="store_true", help="overwrite an existing structure_file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.batch:
        import json
        decisions = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        ok, failed = 0, []
        for d in decisions:
            argv2 = ["--entry-id", d["entry_id"], "--file", d["file"],
                     "--provenance", d["provenance"], "--what", d["what"]]
            for key in ("line", "range"):
                if d.get(key):
                    argv2 += [f"--{key}"] + [str(v) for v in d[key]]
            if d.get("frame_labels"):
                argv2 += ["--frame-labels"] + list(d["frame_labels"])
            for flag in ("bohr", "force", "replace", "dry_run"):
                if d.get(flag) or (flag == "dry_run" and args.dry_run):
                    argv2.append("--" + flag.replace("_", "-"))
            try:
                main(argv2)
                ok += 1
            except SystemExit as exc:
                failed.append((d["entry_id"], str(exc)))
                print(f"  FAILED {d['entry_id']}: {exc}", file=sys.stderr)
        print(f"batch: {ok} saved, {len(failed)} failed")
        return 1 if failed else 0
    if not (args.entry_id and args.file and args.provenance and args.what):
        raise SystemExit("--entry-id, --file, --provenance and --what are required (or --batch)")

    import csv
    with config.LITERATURE_CSV.open(newline="", encoding="utf-8") as fh:
        rows = {r["entry_id"]: r for r in csv.DictReader(fh)}
    row = rows.get(args.entry_id)
    if row is None:
        raise SystemExit(f"no row {args.entry_id}")
    if row["structure_file"] and not args.replace:
        raise SystemExit(f"{args.entry_id} already has structure_file={row['structure_file']}; use --replace")

    path = config.TEXT_DIR / args.file
    if not path.exists():
        raise SystemExit(f"{path} does not exist")
    if len(args.range) % 2:
        raise SystemExit("--range takes FIRST LAST pairs")
    spans = [(l, None) for l in args.line] + [(args.range[i], args.range[i + 1])
                                              for i in range(0, len(args.range), 2)]
    if not spans:
        raise SystemExit("give --line or --range")
    labels = args.frame_labels or [args.what] * len(spans)
    if len(labels) != len(spans):
        raise SystemExit("--frame-labels must match the frames one for one")

    frames, mismatch = [], []
    row_formula = parse_formula(row.get("formula"))
    for (line, last), label in zip(spans, labels):
        b = block_at(path, line) if last is None else block_in_range(path, line, last)
        comp = parse_formula(b["formula"])
        if row_formula is not None and comp != row_formula:
            mismatch.append(f"block at line {line} is {b['formula']}, row formula {row['formula']}")
        unit = f"converted from bohr to angstrom with 1 bohr = {BOHR}" if args.bohr else "angstrom as printed"
        where = f"line {line}" if last is None else f"lines {line}-{last}"
        comment = (f"{row['compound_name'][:80]} | VERBATIM coordinates from {args.file} {where}"
                   f" ({label}) | {unit} | NOT a generated structure")
        frames.append(f"{b['natoms']}\n{comment}\n" + "\n".join(frame_lines(b, args.bohr)) + "\n")
        print(f"  line {line}: {b['natoms']} atoms, {b['formula']}; heading: {b['heading'][:100]}")
    if mismatch and not args.force:
        raise SystemExit("formula mismatch, not saved (use --force to record it anyway):\n  " + "\n  ".join(mismatch))

    dest = config.DATABASE_DIR / "structures" / f"{args.entry_id}.xyz"
    note = (f"structure_file holds the paper's own coordinates, copied verbatim from the local text "
            f"({args.file}, {'; '.join(f'line {l}' if e is None else f'lines {l}-{e}' for l, e in spans)}): {args.what}."
            + (" Bohr-to-angstrom conversion applied." if args.bohr else "")
            + (f" Composition check: {'; '.join(mismatch)}." if mismatch else ""))
    if args.dry_run:
        print(f"would write {dest.name} ({len(frames)} frame(s)) and set structure_provenance={args.provenance}")
        print("note:", note)
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(frames), encoding="utf-8")
    csvio.set_structure_file(args.entry_id, dest.name, note, provenance=args.provenance)
    index.log_extraction(args.entry_id, row.get("reference_doi", ""), "structure", "verbatim",
                         f"{dest.name} copied from {args.file} "
                         f"{'; '.join(f'line {l}' if e is None else f'lines {l}-{e}' for l, e in spans)}: {args.what}")
    print(f"saved {dest.name}; {args.entry_id} structure_provenance={args.provenance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
