"""Order the reading queue — never a substitute for reading it.

Prints one line per `text/<key>.txt`: which multireference methods are named,
how many active-space-shaped `(n,m)` pairs appear, and whether the paper talks
about an active space in prose. Use it to decide *what to read first*, never
to decide `not_usable` — an empty hit count is not evidence of absence
(active spaces hide in a dozen prose forms, and often only in the SI).

Two traps this avoids, both of which caused real false negatives:
  * a `CAS ?\\(` pattern misses `CASSCF(n,m)` — match the method names in full;
  * some extracted text decodes as binary and silently yields nothing under
    grep — read with errors="replace".

Usage:
  .venv/bin/python tools_triage.py                 # all text_ready papers
  .venv/bin/python tools_triage.py --key W123 ...  # specific keys
  .venv/bin/python tools_triage.py --sort          # best candidates first
"""
import argparse
import re

from mining_agent import config, index

METHODS = ("CASSCF", "RASSCF", "CASPT2", "RASPT2", "NEVPT2", "MRCI", "MRCISD",
           "DMRG", "CASCI", "MCSCF", "XMS-CASPT2", "SA-CASSCF", "MC-PDFT",
           "CASPT2/", "QD-NEVPT2", "SC-NEVPT2", "MRPT2", "CASSI")
# (n,m) written any of the usual ways: CASSCF(10,10), CAS(10e,10o), (12e,11o)
PAIR = re.compile(r"\(\s*\d{1,2}\s*(?:e|el|electrons?)?\s*[,/]\s*"
                  r"\d{1,2}\s*(?:o|orb|orbitals?)?\s*\)", re.I)
PROSE = re.compile(r"active space|active orbital|reference space|"
                   r"electrons? in \w* ?\d* ?orbitals", re.I)


def scan(key):
    path = config.TEXT_DIR / f"{key}.txt"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [m for m in METHODS if m.lower() in text.lower()]
    return {
        "key": key,
        "chars": len(text),
        "methods": found,
        "pairs": len(PAIR.findall(text)),
        "prose": len(PROSE.findall(text)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", nargs="*")
    ap.add_argument("--sort", action="store_true",
                    help="most promising first, instead of index order")
    args = ap.parse_args()

    rows = index.load()
    keys = args.key or [r["key"] for r in rows if r["status"] == "text_ready"]
    titles = {r["key"]: r["title"] for r in rows}

    hits = [h for h in (scan(k) for k in keys) if h]
    if args.sort:
        hits.sort(key=lambda h: (bool(h["methods"]), h["pairs"], h["prose"]),
                  reverse=True)
    for h in hits:
        print(f"{h['key']:12s} {h['chars']:7d}c  pairs={h['pairs']:<3d} "
              f"prose={h['prose']:<3d} {','.join(h['methods'][:4]) or '-':40s} "
              f"{titles.get(h['key'], '')[:70]}")
    n_meth = sum(1 for h in hits if h["methods"])
    print(f"\n{len(hits)} text files, {n_meth} name a multireference method")


if __name__ == "__main__":
    main()
