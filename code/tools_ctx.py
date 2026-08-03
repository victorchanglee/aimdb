"""Print the regions of an extracted paper that decide the schema fields.

The reading pass needs the computational-details prose, not the whole 80k-char
text. This pulls windows around active-space, method, software, state-energy
and geometry mentions, merges overlapping windows, and prints them in document
order so a paper can be judged from ~4-8k chars instead of 80k.

It is a *reading aid*: what it prints is the paper's own words, and anything
it does not surface is still the paper's to state. Never conclude
`not_usable` from a quiet output — open the full text (and the SI) first.

Usage:
  .venv/bin/python tools_ctx.py --key W123 [--win 700] [--pat EXTRA_REGEX]
  .venv/bin/python tools_ctx.py --key W123 --si       # include SI text files
"""
import argparse
import re

from mining_agent import config

DEFAULT = (
    r"active space|active orbital|reference space|CASSCF|RASSCF|CASPT2|"
    r"RASPT2|NEVPT2|MRCI|DMRG|CASCI|MCSCF|MC-PDFT|state-averag|state averag|"
    r"\(\s*\d{1,2}\s*(?:e|el)?\s*[,/]\s*\d{1,2}\s*(?:o|orb)?\s*\)|"
    r"MOLCAS|ORCA|MOLPRO|Gaussian ?\d|Q-Chem|BAGEL|PySCF|Dalton|GAMESS|"
    r"NWChem|Turbomole|COLUMBUS|zero-field splitting|spin-orbit|"
    r"vertical excitation|adiabatic excitation|roots?\b"
)


def windows(text, pattern, win):
    spans = []
    for m in re.finditer(pattern, text, re.I):
        spans.append((max(0, m.start() - win), min(len(text), m.end() + win)))
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for lo, hi in spans[1:]:
        if lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--win", type=int, default=700)
    ap.add_argument("--pat", default=None, help="regex to use instead of the "
                                                "default field-bearing one")
    ap.add_argument("--si", action="store_true", help="also scan SI text")
    ap.add_argument("--max-chars", type=int, default=20000)
    args = ap.parse_args()

    paths = [config.TEXT_DIR / f"{args.key}.txt"]
    if args.si:
        paths += sorted(config.TEXT_DIR.glob(f"{args.key}_si_*.txt"))
    pattern = args.pat or DEFAULT

    total = 0
    for path in paths:
        if not path.exists():
            print(f"[missing {path.name}]")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        merged = windows(text, pattern, args.win)
        print(f"=== {path.name}  ({len(text)} chars, "
              f"{len(merged)} region(s)) ===")
        for lo, hi in merged:
            if total >= args.max_chars:
                print(f"... [truncated at --max-chars={args.max_chars}]")
                return
            chunk = re.sub(r"\s+", " ", text[lo:hi]).strip()
            total += len(chunk)
            print(f"\n--[{lo}:{hi}]--\n{chunk}")


if __name__ == "__main__":
    main()
