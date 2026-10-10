#!/usr/bin/env python3
"""Grounding check: does every number a row states actually appear in the paper?

A row is *grounded* when each numeric value in its prose can be found in the
extracted text of its source paper. A number that appears nowhere is either a
transcription slip or an invention, and both are worth knowing about. This is
the cheapest fabrication check available for `database/aimdb.csv`: no model, no
second read, and it covers every row whose `text/<key>.txt` survives on disk.

It is a SCREEN, not a verdict. Hand-adjudicating its alarms on 2026-10-09
turned up exactly one real data error and four source-side artefacts, so the
report separates the two rather than reporting a single number:

  * **review** — healthy text, and this row fails while its siblings pass. The
    row is the thing to re-read. These are the only rows worth a human.
  * **unverifiable** — the source text cannot support the check, for one of
    two measured reasons. Either the PDF's text layer lost its decimal points
    (`decimal-stripped`: W931703638 extracts 2,888 digits and zero decimals),
    or the values live in tables the extraction dropped while leaving the prose
    intact — visible as most of one paper's rows failing together
    (`source-wide`: 11 of W2397900523's 28 rows, whose cited table values are
    simply absent from a text that still carries ordinary prose decimals).
    Rows like these were read off rendered page images, which is correct
    practice and unverifiable here by construction.

Two further sources of false alarms are handled in the matcher rather than the
report: a row may legitimately round the paper's 192.74 to 192.7 (tier
`rounded`), or quote a value the text prints with trailing zeros (`trimmed`).
Derived values — a count or difference the extractor worked out from the
paper's own statements — are correct and absent from the text by definition;
such rows usually say so in `notes`, and the screen cannot know.

Only decimals are checked. Bare integers are far too common in prose ("the 3
lowest states", "a (12,11) space") to carry evidence, and matching them inflates
the located fraction without adding signal — the hand run that first found
these cases did count them, and two of its five alarms turned out to be rows
whose prose contains no decimal at all.

Calibration scores the detector against `cases.csv`, a small hand-adjudicated
set, so its behaviour is a measured number rather than an assumption; selftest
measures sensitivity by perturbing real rows. Re-run both after changing any
matching rule.

Usage, from the repository root:
    code/.venv/bin/python benchmark/check_grounding.py              # report
    code/.venv/bin/python benchmark/check_grounding.py --calibrate  # vs cases.csv
    code/.venv/bin/python benchmark/check_grounding.py --selftest   # sensitivity
    code/.venv/bin/python benchmark/check_grounding.py --entry W2055916038-a
"""
import argparse
import csv
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database" / "aimdb.csv"
TEXT_DIR = ROOT / "text"
CASES = Path(__file__).resolve().parent / "cases.csv"
DEFAULT_REPORT = ROOT / "logs" / "grounding_report.csv"

# Columns whose prose carries extracted numbers. `notes` is included because
# corrections, unit conversions and source checksums are recorded there — but
# its MD5 stamps are stripped first, or every hex digit becomes a claim.
PROSE_COLUMNS = ("electronic_structure_description", "Other",
                 "active_space_protocol", "method", "notes")

MD5 = re.compile(r"\b[0-9a-f]{32}\b")
DECIMAL = re.compile(r"(?<![\w.])-?\d+\.\d+(?![\w])")
DOI_LIKE = re.compile(r"10\.\d{4,9}/\S+")

# Decimal-density thresholds, set from the measured distribution over the 2,665
# local texts carrying at least 500 digits (2026-10-09): median 0.067,
# p25 0.041, p10 0.024, p5 0.016, p2 0.009. A text layer that lost its decimal
# points lands near zero, so `decimal-stripped` is drawn at the 2nd percentile
# and `decimal-poor` at the 10th — the latter is a caution, since a genuinely
# prose-heavy paper can sit there honestly.
STRIPPED_RATIO = 0.010
POOR_RATIO = 0.025
MIN_DIGITS = 200

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
         12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
         16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
         20: "twenty"}


def text_health(text):
    """Classify a paper's text by how many of its decimals survived extraction.

    A text layer that lost its decimal points cannot support a grounding check
    at all, and saying so is more useful than reporting its rows as ungrounded.
    """
    digits = len(re.findall(r"\d", text))
    decimals = len(re.findall(r"\d+\.\d+", text))
    if digits < MIN_DIGITS:
        return "sparse", digits, decimals
    ratio = decimals / digits
    if ratio < STRIPPED_RATIO:
        return "decimal-stripped", digits, decimals
    if ratio < POOR_RATIO:
        return "decimal-poor", digits, decimals
    return "ok", digits, decimals


def locate(value, text):
    """Return the tier at which `value` is found in `text`, or '' if absent.

    Tiers, strongest first: `exact`; `trimmed` (the text prints trailing
    zeros); `rounded` (the text carries more precision than the row quoted);
    `worded` (a small integer spelled out).
    """
    bare = value.lstrip("-")
    if value in text or bare in text:
        return "exact"
    trimmed = bare.rstrip("0").rstrip(".")
    if trimmed and trimmed != bare and trimmed in text:
        return "trimmed"
    if "." in bare:
        head, tail = bare.split(".", 1)
        if tail:
            wider = re.compile(r"(?<![\w.])%s\.%s\d(?![\w])"
                               % (re.escape(head), re.escape(tail)))
            if wider.search(text):
                return "rounded"
    try:
        as_int = int(float(bare))
        if float(bare) == as_int and as_int in WORDS:
            if re.search(r"\b%s\b" % WORDS[as_int], text, re.I):
                return "worded"
    except ValueError:
        pass
    return ""


def claims(row):
    """The distinct numeric claims a row makes, with known noise removed."""
    blob = " ".join(MD5.sub("", row.get(c, "")) for c in PROSE_COLUMNS)
    blob = DOI_LIKE.sub(" ", blob)
    return sorted(set(DECIMAL.findall(blob)))


def load_text(key, cache):
    """Normalised text plus health for one paper key, or None if absent."""
    if key not in cache:
        path = TEXT_DIR / ("%s.txt" % key)
        if not path.is_file():
            cache[key] = None
        else:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            cache[key] = (re.sub(r"[ \t]+", " ", raw),) + text_health(raw)
    return cache[key]


def check_rows(rows, want=None, cache=None):
    """One result dict per checkable row that makes a numeric claim.

    A row is checkable when its paper's text is on disk; a row whose prose
    holds no decimal is skipped, since there is nothing to ground.
    """
    cache = {} if cache is None else cache
    for row in rows:
        entry = row["entry_id"]
        if want is not None and entry not in want:
            continue
        loaded = load_text(entry.rsplit("-", 1)[0], cache)
        if loaded is None:
            continue
        text, health, digits, decimals = loaded
        values = claims(row)
        if not values:
            continue
        tiers = {v: locate(v, text) for v in values}
        found = [v for v, t in tiers.items() if t]
        yield {
            "entry_id": entry,
            "paper": entry.rsplit("-", 1)[0],
            "values": len(values),
            "located": len(found),
            "rate": round(len(found) / len(values), 3),
            "text_health": health,
            "text_digits": digits,
            "text_decimals": decimals,
            "triage": "",
            "missing": "; ".join(v for v, t in tiers.items() if not t)[:300],
        }


def triage(results, min_values, threshold, source_wide=0.6):
    """Fill in each result's `triage`, and return the flagged rows.

    `review` means the row is the suspect: its paper's text is healthy and its
    siblings ground fine. `unverifiable` means the source cannot answer —
    either the text layer is damaged, or most of the paper's rows fail
    together, which points at tables the extraction dropped rather than at a
    row-by-row transcription problem.
    """
    flagged = [r for r in results
               if r["values"] >= min_values and r["rate"] < threshold]
    per_paper, flagged_per_paper = {}, {}
    for r in results:
        per_paper[r["paper"]] = per_paper.get(r["paper"], 0) + 1
    for r in flagged:
        flagged_per_paper[r["paper"]] = flagged_per_paper.get(r["paper"], 0) + 1
    for r in results:
        r["paper_rows"] = per_paper[r["paper"]]
        r["paper_rows_flagged"] = flagged_per_paper.get(r["paper"], 0)
    for r in flagged:
        wide = (r["paper_rows"] >= 2
                and r["paper_rows_flagged"] / r["paper_rows"] >= source_wide)
        if r["text_health"] in ("decimal-stripped", "sparse"):
            r["triage"] = "unverifiable-text-damaged"
        elif wide:
            r["triage"] = "unverifiable-source-wide"
        elif r["text_health"] == "decimal-poor":
            r["triage"] = "review-weak-text"
        else:
            r["triage"] = "review"
    return flagged


def load_rows():
    with open(DB, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_report(args):
    results = list(check_rows(load_rows(),
                              want={args.entry} if args.entry else None))
    if not results:
        print("nothing to check: no local text, or no decimal in the prose")
        return 0
    flagged = triage(results, args.min_values, args.threshold)
    values = sum(r["values"] for r in results)
    located = sum(r["located"] for r in results)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    fields = ["entry_id", "paper", "values", "located", "rate", "triage",
              "text_health", "text_digits", "text_decimals", "paper_rows",
              "paper_rows_flagged", "missing"]
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(results, key=lambda r: (r["rate"], -r["values"])))

    print("rows checked      : %d  (of the rows with local text and a decimal)"
          % len(results))
    print("numeric claims    : %d" % values)
    print("located in source : %d  (%.1f%%)"
          % (located, 100 * located / values))
    print("flagged (>=%d claims, <%.0f%% located): %d"
          % (args.min_values, 100 * args.threshold, len(flagged)))
    buckets = {}
    for r in flagged:
        buckets[r["triage"]] = buckets.get(r["triage"], 0) + 1
    for name in ("review", "review-weak-text", "unverifiable-source-wide",
                 "unverifiable-text-damaged"):
        if buckets.get(name):
            print("    %-26s %d" % (name, buckets[name]))
    print("wrote %s" % args.report)

    worth_reading = sorted((r for r in flagged if r["triage"].startswith("review")),
                           key=lambda r: (r["rate"], -r["values"]))
    if worth_reading:
        print("\nrows to re-read (healthy text, isolated failure):")
        for r in worth_reading[:args.show]:
            print("   %-16s %2d/%-3d  %s"
                  % (r["entry_id"], r["located"], r["values"],
                     r["missing"][:84]))
    return 0


def run_calibration(args):
    """Compare the detector against the hand-adjudicated cases.

    `cases.csv` records what a human concluded about each row AND what the
    detector is expected to do with it today, which are not the same thing: a
    row whose error has since been corrected should now pass.
    """
    if not CASES.is_file():
        print("no %s to calibrate against" % CASES, file=sys.stderr)
        return 1
    with open(CASES, newline="", encoding="utf-8") as f:
        cases = [c for c in csv.DictReader(f)
                 if c["entry_id"] and not c["entry_id"].startswith("#")]
    rows = load_rows()
    present = {r["entry_id"] for r in rows}
    # The source-wide rule asks what fraction of a PAPER's rows fail, so every
    # sibling of a case row has to be checked too — scoring the case rows
    # alone would make any two-row paper look source-wide by construction.
    papers = {c["entry_id"].rsplit("-", 1)[0] for c in cases}
    want = {r["entry_id"] for r in rows
            if r["entry_id"].rsplit("-", 1)[0] in papers}
    results = {r["entry_id"]: r for r in check_rows(rows, want=want)}
    triage(list(results.values()), args.min_values, args.threshold)

    agreed = 0
    print("%-16s %-14s %-14s %-14s %s"
          % ("entry_id", "label", "expected", "observed", ""))
    for c in cases:
        entry = c["entry_id"]
        if entry not in present:
            observed = "row-gone"
        elif entry not in results:
            observed = "no-claims"
        else:
            r = results[entry]
            observed = r["triage"] or "pass"
            if observed.startswith("unverifiable"):
                observed = "unverifiable"
            elif observed.startswith("review"):
                observed = "flag"
        ok = observed == c["expect"]
        agreed += ok
        print("%-16s %-14s %-14s %-14s %s"
              % (entry, c["label"], c["expect"], observed,
                 "ok" if ok else "MISMATCH <-"))
    print("\n%d/%d cases behave as adjudicated" % (agreed, len(cases)))
    print("A mismatch means either the matcher changed or the row did; read "
          "the case note before \"fixing\" the detector.")
    return 0


def run_selftest(args):
    """Measure sensitivity by corrupting real rows and re-checking them.

    `cases.csv` holds no row that both fails the check and is genuinely wrong —
    the one real error found on 2026-10-09 was corrected, so it now passes.
    Perturbing a digit in a fully grounded row supplies that missing half of
    the calibration: a detector that cannot see an injected wrong number cannot
    see a transcribed one either.
    """
    rng = random.Random(args.seed)
    cache = {}
    results = [r for r in check_rows(load_rows(), cache=cache)
               if r["rate"] == 1.0 and r["values"] >= args.min_values
               and r["text_health"] == "ok"]
    if not results:
        print("no fully grounded rows to perturb")
        return 1
    sample = rng.sample(results, min(args.n, len(results)))
    rows = {r["entry_id"]: r for r in load_rows()}

    caught, tested, skipped = 0, 0, 0
    for res in sample:
        row = dict(rows[res["entry_id"]])
        text = cache[res["paper"]][0]
        target = rng.choice(claims(row))
        # Bump the last digit, keeping the value's shape, until the result is
        # one the paper does not happen to contain anyway.
        for bump in range(1, 10):
            fake = target[:-1] + str((int(target[-1]) + bump) % 10)
            if fake != target and not locate(fake, text):
                break
        else:
            skipped += 1   # every neighbour of this value is in the paper too
            continue
        # Substring replacement would corrupt 11.25 while targeting 1.2, so
        # the edit is anchored the same way the extractor's own regex is.
        anchored = re.compile(r"(?<![\w.])%s(?![\w])" % re.escape(target))
        for col in PROSE_COLUMNS:
            if row.get(col):
                row[col] = anchored.sub(fake, row[col])
        after = claims(row)
        if fake not in after:
            skipped += 1   # the edit did not take (value only inside a word)
            continue
        tested += 1
        hit = not locate(fake, text)
        caught += hit
        if args.verbose or not hit:
            print("   %-16s %-9s -> %-9s  %s"
                  % (res["entry_id"], target, fake,
                     "caught" if hit else "MISSED"))
    print("\ninjected one wrong decimal into %d grounded rows; detected %d "
          "(%.0f%%)" % (tested, caught, 100 * caught / max(tested, 1)))
    if skipped:
        print("%d rows skipped: no neighbouring value absent from the paper, "
              "or the edit did not take." % skipped)
    print("This is sensitivity to a single altered digit, not to a whole "
          "fabricated row — a row-level threshold of <%.0f%% located needs "
          "several such errors before it flags the row itself."
          % (100 * args.threshold))
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--calibrate", action="store_true",
                      help="compare the detector against benchmark/cases.csv")
    mode.add_argument("--selftest", action="store_true",
                      help="perturb grounded rows and measure detection")
    p.add_argument("--entry", help="report on a single entry_id")
    p.add_argument("--min-values", type=int, default=4,
                   help="minimum numeric claims before a row can be flagged")
    p.add_argument("--threshold", type=float, default=0.4,
                   help="flag a row locating less than this fraction")
    p.add_argument("--show", type=int, default=20,
                   help="how many rows to print")
    p.add_argument("--n", type=int, default=40, help="selftest sample size")
    p.add_argument("--seed", type=int, default=0, help="selftest seed")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = p.parse_args()
    if args.calibrate:
        return run_calibration(args)
    if args.selftest:
        return run_selftest(args)
    return run_report(args)


if __name__ == "__main__":
    sys.exit(main())
