"""Re-extract text with poppler's pdftotext where pypdf produced glyph codes.

Some publisher PDFs (older Elsevier/Springer files with embedded Type-1 fonts
that carry no ToUnicode map) come out of pypdf as runs of glyph names -
"/C65/C98/C115" instead of "Abs".  The words are unrecoverable to a reader and
the numbers are unrecoverable to the miner, so CLAUDE.md would have these
marked text_unreadable.  Poppler reads the same files correctly, so try it
before giving up.

Re-runnable: pass --key, or --all to sweep every text/*.txt whose glyph-code
density is above --threshold (default 0.30 of the file).  Rewrites
text/<key>.txt in place, prefixed with a banner recording the re-extraction.
"""
import argparse
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from mining_agent import config, index  # noqa: E402

GLYPH = re.compile(r"/C\d{1,3}")
BANNER = ("=== text re-extracted with poppler pdftotext -layout; the pypdf "
          "extraction for this PDF returned glyph codes (/C65/C98...) rather "
          "than characters ===\n\n")


def glyph_fraction(text):
    """Rough share of the file taken up by glyph-code runs."""
    if not text:
        return 0.0
    return 4 * len(GLYPH.findall(text)) / len(text)


def reextract(row, dry_run=False):
    key = row["key"]
    pdf = index.find_pdf(row)
    if pdf is None:
        return False, "no PDF on disk"
    dest = config.TEXT_DIR / f"{key}.txt"
    if dry_run:
        return True, f"would re-extract {pdf.name}"
    try:
        out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, f"pdftotext failed: {exc}"
    text = out.decode("utf-8", errors="replace")
    if len(text.strip()) < 500:
        return False, f"only {len(text.strip())} chars from pdftotext"
    if glyph_fraction(text) > 0.05:
        return False, "pdftotext output is still glyph-encoded"
    dest.write_text(BANNER + text, encoding="utf-8")
    index.log_extraction(key, row["doi"], "text", "text_ready",
                         "re-extracted with poppler pdftotext -layout; pypdf "
                         "output was glyph-encoded and unreadable")
    return True, str(dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", action="append", default=[],
                    help="index key to re-extract (repeatable)")
    ap.add_argument("--all", action="store_true",
                    help="sweep every text/*.txt above --threshold")
    ap.add_argument("--threshold", type=float, default=0.30,
                    help="glyph-code fraction above which --all re-extracts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not shutil.which("pdftotext"):
        sys.exit("pdftotext (poppler-utils) is not installed")

    rows = index.load()
    targets = []
    if args.key:
        for key in args.key:
            row = index.get(rows, key)
            if row is None:
                print(f"  ?  {key}: not in the index")
            else:
                targets.append(row)
    if args.all:
        for row in rows:
            path = config.TEXT_DIR / f"{row['key']}.txt"
            if not path.exists():
                continue
            frac = glyph_fraction(path.read_text(encoding="utf-8",
                                                 errors="replace"))
            if frac >= args.threshold:
                targets.append(row)

    seen, ordered = set(), []
    for row in targets:
        if row["key"] not in seen:
            seen.add(row["key"])
            ordered.append(row)

    ok = 0
    for row in ordered:
        good, detail = reextract(row, dry_run=args.dry_run)
        print(f"  {'ok ' if good else 'FAIL'} {row['key']}: {detail}")
        ok += good
    print(f"{ok}/{len(ordered)} re-extracted"
          f"{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
