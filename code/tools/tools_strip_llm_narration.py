"""Remove the mining model's account of its own work from `notes`.

`notes` is for what the paper says and what a reader must know to trust the
row. It filled up instead with the extractor narrating itself — "GPT-5.6
comprehensively read all 17 pages of the complete local article, including
methods, active-space/system definitions, results, tables/figures, and
conclusions" — and with records of past bulk edits ("Full-database schema
audit (GPT-5.6, 2026-08-11): normalized verbose SOC/SS flags"). Neither is a
fact about the chemistry, and the edit records belong to
`logs/extractions.csv`, which already holds them.

Each rule matches one narrative shape and deletes only that span; anything the
sentence does not cover survives untouched. Two safeguards protect real
content that sits inside a narrative sentence:

  - a span is truncated at "; this ...", because a demonstrative there starts
    a genuine statement about the row (two rows read "...comprehensively
    reviewed the full source; this fragment is a distinct optimized
    CASSCF/CASPT2 species in the paper's thermochemical cycle");
  - an MD5 or a DOI inside a deleted span is re-appended, since a checksum of
    the source text and the location of a data deposit are both verification
    data, not narration. One row's only record of its figshare data DOI sat
    inside the sentence describing how the model had read it.

Deliberately kept: the Codex pull-request provenance, which records that a row
was mined outside this project's fetch pipeline, and every sentence naming
`claude-casscf/database/literature.csv`, which carries the QUEST export rule.

Usage, from code/:
    .venv/bin/python tools/tools_strip_llm_narration.py --dry-run [--limit N]
    .venv/bin/python tools/tools_strip_llm_narration.py --apply
"""

import argparse
import csv
import datetime as _dt
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
LOG = ROOT / "logs" / "extractions.csv"

MODEL = r"(?:GPT-?[\d.]+|Claude(?:-opus)?[\w.\-]*)"
# A period only ends a sentence when it is not part of a number, a DOI or a
# common abbreviation. Matching a bare "[^.]*\." instead cut straight through
# "DOI 10.1021/ct300414t.s001", truncating the DOI and stranding the rest of it
# mid-note.
SENT_END = (r"(?<!Fig)(?<!Figs)(?<!Tab)(?<!Ref)(?<!Refs)(?<!Eq)(?<!Eqs)(?<!vs)"
            r"(?<!cf)(?<!al)(?<!No)(?<!Nos)(?<!approx)\.(?!\d)(?=\s|$)")
BODY = rf"[^|]*?{SENT_END}\s*"
MD5 = re.compile(r"MD5\s+([0-9a-f]{32})", re.I)
DOI = re.compile(r"10\.\d{4,}/\S+?(?=[.,;)\]]?(?:\s|$))")
# A demonstrative after a semicolon starts a real statement, not more narration.
REAL_CLAUSE = re.compile(r";\s+th(?:is|ese)\s")

RULES = [
    ("read-all-pages", re.compile(
        rf"{MODEL} (?:comprehensive(?:ly)? )?(?:audit|reread|read)[^:.]*\([^)]*\):"
        rf"\s*(?:re-?read|read|reviewed|inspected|full|comprehensive)\b{BODY}", re.I)),
    ("comprehensively-read", re.compile(
        rf"{MODEL} comprehensively (?:read|reviewed){BODY}", re.I)),
    ("comprehensively-mined", re.compile(
        rf"Comprehensively mined by {MODEL} (?:on [\d-]+ )?from{BODY}", re.I)),
    ("full-paper-read", re.compile(
        rf"Comprehensive (?:full-paper|source|main-text) read by {MODEL} "
        rf"on [\d-]+:{BODY}", re.I)),
    ("no-local-si", re.compile(
        r"No separate local supporting-information file was available; "
        r"unsupported SI-only details (?:remain|were left) blank\.\s*", re.I)),
    ("audit-summary-lbl", re.compile(r"Audit summary:\s*")),
    ("full-db-source", re.compile(
        rf"Full-database source audit \({MODEL},[^)]*\):{BODY}", re.I)),
    ("full-db-schema", re.compile(
        rf"Full-database schema audit \({MODEL},[^)]*\):{BODY}", re.I)),
    ("dup-audit", re.compile(
        rf"Database-wide duplicate audit \({MODEL},[^)]*\):{BODY}", re.I)),
    ("one-row-audit", re.compile(
        rf"(?:[\d-]+\s+)?{MODEL} database-wide one-row-per-compound audit:"
        rf"{BODY}", re.I)),
    ("field-rich", re.compile(rf"Field-rich {MODEL} audit added{BODY}", re.I)),
    ("main-text-si-review", re.compile(
        rf"{MODEL} comprehensive main-text and SI review[.;]\s*", re.I)),
    ("read-of-all-pages", re.compile(
        rf"Comprehensive {MODEL} read of all {BODY}", re.I)),
    ("dup-audit-correction", re.compile(
        rf"Database-wide duplicate audit correction \({MODEL},[^)]*\):{BODY}", re.I)),
    # Keep the fact that the DOI was canonicalized; drop who did it and when.
    ("reviewed-by-attribution", re.compile(
        rf"\s+and reviewed by {MODEL} on [\d-]+(?=\.)", re.I)),
    # Long tail of one-off "read all N pages" phrasings. The terminator must be
    # a period followed by a capital (or the end), so the cut never lands inside
    # "Fig. 4" or partway through a DOI.
    ("pages-read-longtail", re.compile(
        rf"{MODEL} [^.;|]*\bpages?\b[^;|]*?(?:\.(?=\s+[A-Z])|\.\s*$|;)\s*", re.I)),
    ("prior-note-lbl", re.compile(r"Prior structured note retained:\s*")),
    ("mined-from-oa", re.compile(
        r"Mined from OA text(?:\s*\([^)]*\))? by claude-casscf-data_mining\.\s*")),
    ("over-splitting", re.compile(
        rf"{MODEL} full PR over-splitting correction \([^)]*\):[^.|]*"
        rf"(?:\.|(?=\s*\|)|$)\s*", re.I)),
    ("manually-mined", re.compile(rf"Manually mined by {MODEL} from{BODY}", re.I)),
]


def _tidy(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[;,.|\s]+", "", text)
    text = re.sub(r"\s*\|\s*(?:\|\s*)+", " | ", text)
    return re.sub(r"^\|\s*|\s*\|$", "", text).strip()


def clean(notes, reference_doi=""):
    """Returns (cleaned_notes, {rule: hits})."""
    text, hits = notes, Counter()
    for name, pattern in RULES:
        while True:
            m = pattern.search(text)
            if not m:
                break
            span = m.group(0)
            # Never swallow a real statement that follows a semicolon.
            cut = REAL_CLAUSE.search(span)
            if cut:
                span = span[:cut.start()]
                if not span.strip():
                    break
            remaining = text.replace(span, "", 1)
            keep = ""
            for digest in MD5.findall(span):
                if digest not in remaining:
                    keep += f" Source-text MD5 {digest}."
            for doi in DOI.findall(span):
                doi = doi.rstrip(".,;)]")
                if doi and doi not in remaining and doi != reference_doi.strip():
                    keep += f" Data DOI {doi}."
            start = m.start()
            text = text[:start] + keep + " " + text[start + len(span):]
            hits[name] += 1
    return _tidy(text), hits


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args(argv)

    csv.field_size_limit(10 ** 9)
    with DB.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    touched, totals, saved, shown = [], Counter(), 0, 0
    for r in rows:
        new, hits = clean(r["notes"], r.get("reference_doi", ""))
        if new == r["notes"]:
            continue
        touched.append((r["entry_id"], r["notes"], new))
        totals.update(hits)
        saved += len(r["notes"]) - len(new)
        if args.dry_run and shown < args.limit:
            shown += 1
            print(f"--- {r['entry_id']}  ({len(r['notes'])} -> {len(new)} chars)")
            print(f"    before: {r['notes'][:190]}")
            print(f"    after : {new[:190] or '(empty)'}")
        if args.apply:
            r["notes"] = new

    print(f"\n{len(touched)} rows, {saved} characters of narration")
    for name, _ in RULES:
        if totals[name]:
            print(f"    {name:22s} {totals[name]:6d}")

    if args.dry_run:
        print("dry run - nothing written")
        return 0
    if not touched:
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    tmp = DB.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(DB)

    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for eid, old, new in touched:
            writer.writerow([
                stamp, eid, "", "strip_llm_narration",
                f"notes {len(old)}->{len(new)} chars",
                "removed the mining model's account of its own reading and "
                "records of past bulk edits; statements about the paper, "
                "source checksums and contribution provenance left in place",
            ])
    print(f"wrote {DB} and logged {len(touched)} rows to {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
