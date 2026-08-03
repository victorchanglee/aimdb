"""Repair extracted text whose glyphs come out one-character-per-token.

Some PDFs — ACS peer-review watermarked manuscripts are the repeat offender —
position every glyph individually, so pypdf yields "T h i s  d o c u m e n t".
The text is complete but every regex in the reading pass misses it, and the
title-vs-text integrity scan flags it as a wrong-file download.

Detection: a line is letter-spaced when most of its whitespace-separated
tokens are single characters. Repair joins runs of single characters back into
words and collapses the doubled spaces that separated real words.

Usage:
  .venv/bin/python tools_despace.py --key W123          # rewrite in place
  .venv/bin/python tools_despace.py --scan              # list affected files
"""
import argparse
import re

from mining_agent import config, index


def is_spaced(text, sample=20000):
    """True when the text looks one-character-per-token."""
    lines = [ln for ln in text[:sample].splitlines() if len(ln) > 20]
    if not lines:
        return False
    spaced = 0
    for ln in lines:
        toks = ln.split()
        if not toks:
            continue
        if sum(1 for t in toks if len(t) == 1) / len(toks) > 0.6:
            spaced += 1
    return spaced / len(lines) > 0.5


def despace_line(line):
    if not line.strip():
        return line
    toks = line.split(" ")
    out, run = [], []
    for tok in toks:
        if len(tok) == 1 and tok.strip():
            run.append(tok)
        else:
            if run:
                out.append("".join(run))
                run = []
            # an empty token marks the doubled space between real words
            if tok:
                out.append(tok)
    if run:
        out.append("".join(run))
    return " ".join(out)


def despace(text):
    return "\n".join(despace_line(ln) for ln in text.splitlines())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--scan", action="store_true")
    args = ap.parse_args()

    if args.scan:
        rows = index.load()
        hits = []
        for r in rows:
            p = config.TEXT_DIR / f"{r['key']}.txt"
            if not p.exists():
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if is_spaced(t):
                hits.append((r["key"], r["status"], r["title"][:70]))
        for key, status, title in hits:
            print(f"  {key:12s} {status:18s} {title}")
        print(f"{len(hits)} letter-spaced text file(s)")
        return

    path = config.TEXT_DIR / f"{args.key}.txt"
    text = path.read_text(encoding="utf-8", errors="replace")
    if not is_spaced(text):
        print(f"{args.key}: not letter-spaced, left alone")
        return
    fixed = despace(text)
    path.write_text(fixed, encoding="utf-8")
    print(f"{args.key}: {len(text)} -> {len(fixed)} chars")
    print(re.sub(r"\s+", " ", fixed[:300]))


if __name__ == "__main__":
    main()
