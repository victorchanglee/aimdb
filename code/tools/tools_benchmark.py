"""Claim review: benchmark every paper's rows against the paper, fix, write back.

Every paper with rows goes through two agent passes before its rows count as
final (CLAUDE.md, step 5b):

  1. benchmark -- an agent that did not write the rows splits every field into
     atomic claims, labels each one supported / unsupported / bookkeeping
     against the paper and SI, and lists what the paper reports that the rows
     lack (omissions). Brief: benchmark/claim_review/bench_brief.md
  2. fix -- an agent verifies each benchmark item in the paper and writes the
     complete corrected row set plus a fix_log.
     Brief: benchmark/claim_review/fix_brief.md
  3. recheck -- a fresh agent benchmarks the FIXED rows the same way.
     Brief: benchmark/claim_review/recheck_brief.md
  4. target -- an agent acts only on what the recheck flags: every unsupported
     claim or contradiction is corrected or removed against the paper, and an
     omission is added only if found as printed. Nothing else changes.
     Brief: benchmark/claim_review/target_brief.md

This tool does the mechanical part around those passes:

  prepare   write batch files for the agents, to benchmark/work/<run>/.
            By default: papers whose rows were added on or after REVIEW_FROM
            (2026-10-31, the first intake after the rule) and that have no
            applied review.
            Papers mined before that are not re-reviewed (user ruling
            2026-10-30); name them with --keys to review one deliberately.
  score     precision/recall of the reviewed rows, from benchmark files
  apply     replace each paper's rows with the fix output. Old rows are
            quarantined verbatim to logs/removed_rows.csv; structure files,
            date_added and properties are carried to the new row describing
            the same species; every paper is logged to logs/extractions.csv
            and logs/benchmark_status.csv
  status    how many papers are reviewed, and what is left

Usage, from code/:
    .venv/bin/python tools/tools_benchmark.py prepare --run r001 --papers 50
    .venv/bin/python tools/tools_benchmark.py score --run r001
    .venv/bin/python tools/tools_benchmark.py apply --run r001 --dry-run
    .venv/bin/python tools/tools_benchmark.py apply --run r001
    .venv/bin/python tools/tools_benchmark.py status

A run directory holds, per batch NN: batch_NN.json (input), bench_NN.json,
fix_NN.json, recheck_NN.json and target_NN.json. `apply` writes target_NN's
rows and refuses a batch without one (--allow-no-target accepts fix_NN, for
runs made before the targeted pass existed). benchmark/work/ is gitignored: the files quote
the papers. The per-paper numbers are kept in logs/benchmark_status.csv.

`apply` refuses a paper whose fix output has a non-integer active space, an
unknown column or an invalid system_class, and changes nothing for it.
"""
import _bootstrap  # noqa: F401
import argparse
import csv
import datetime as _dt
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from mining_agent import config, csvio, index

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "aimdb.csv"
STRUCT = ROOT / "database" / "structures"
WORK = ROOT / "benchmark" / "work"
STATUS = ROOT / "logs" / "benchmark_status.csv"
QUARANTINE = ROOT / "logs" / "removed_rows.csv"

# Columns the agents read and write. Everything else is derived or bookkeeping
# and is kept by apply.
CONTENT = ["entry_id", "compound_name", "system_class", "formula", "metal_center",
           "metal_ox_state", "d_electron_count", "ligand_set", "point_group",
           "geometry_source", "method", "software", "basis_set",
           "relativistic_treatment", "soc_included", "ss_included",
           "active_space_nel", "active_space_norb", "active_space_orbital_description",
           "active_space_protocol", "multiplicities_studied", "nroots_per_mult",
           "ground_state_mult", "electronic_structure_description", "Other",
           "reference_short", "reference_doi", "year", "notes"]
REVIEW_FROM = (2026, 10, 31)  # rows added on/after this date need review (the 30/10 ZFS intake predates the rule)


def added_on_or_after(row, start=REVIEW_FROM):
    """date_added is dd/mm/yyyy; an unparseable date counts as old."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", (row.get("date_added") or "").strip())
    return bool(m) and (int(m[3]), int(m[2]), int(m[1])) >= start


STATUS_COLS = ["key", "doi", "run", "benchmarked_at", "claims_supported",
               "claims_unsupported", "bookkeeping", "omissions", "precision", "recall",
               "fixes", "added", "removed", "benchmark_rejected",
               "recheck_supported", "recheck_unsupported", "recheck_omissions",
               "target_fixed", "target_added", "target_removed", "target_rejected",
               "rows_before", "rows_after", "decision", "applied_at"]


def now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def read_db():
    with DB.open(newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames, list(rd)


def key_of(entry_id):
    return entry_id.rsplit("-", 1)[0]


def read_status():
    if not STATUS.exists():
        return {}
    with STATUS.open(newline="", encoding="utf-8") as fh:
        return {r["key"]: r for r in csv.DictReader(fh)}


def write_status(st):
    tmp = STATUS.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STATUS_COLS, restval="")
        w.writeheader()
        for k in sorted(st):
            w.writerow({c: st[k].get(c, "") for c in STATUS_COLS})
    tmp.replace(STATUS)


def paper_files(key, idx_row):
    si = sorted(str(Path(p).relative_to(ROOT)) for p in glob.glob(str(ROOT / "text" / f"{key}_si_*.txt")))
    sidir = ROOT / "papers" / "si" / key
    if sidir.is_dir():
        si += sorted(str(p.relative_to(ROOT)) for p in sidir.rglob("*") if p.is_file()
                     and p.suffix.lower() in (".pdf", ".txt", ".docx", ".xyz", ".csv"))
    text = ROOT / "text" / f"{key}.txt"
    return {"text": f"text/{key}.txt" if text.exists() else "",
            "pdf": idx_row.get("pdf_path", ""), "si": si}


# ---------------------------------------------------------------- prepare
def cmd_prepare(a):
    _, rows = read_db()
    idx = {r["key"]: r for r in index.load()}
    by = defaultdict(list)
    for r in rows:
        by[key_of(r["entry_id"])].append(r)
    supplied = {}
    if a.rows_from:  # candidate rows from elsewhere replace the database rows as the rows under review
        for r in json.loads(Path(a.rows_from).read_text())["rows"]:
            supplied.setdefault(key_of(r["entry_id"]), []).append(r)
    extra = json.loads(Path(a.instructions).read_text()) if a.instructions else {}
    if a.keys:
        keys = [k.strip() for k in Path(a.keys).read_text().split() if k.strip()] \
            if Path(a.keys).exists() else a.keys.split(",")
    else:
        done = {k for k, s in read_status().items() if s.get("applied_at")}
        new = {k for k, rs in by.items() if any(added_on_or_after(r) for r in rs)}
        keys = sorted(k for k in new if k not in done)[: a.papers]
    out = WORK / a.run
    out.mkdir(parents=True, exist_ok=True)
    papers = []
    for k in keys:
        ir = idx.get(k, {})
        cur = supplied.get(k, by.get(k, []))
        p = {"key": k, "doi": (by[k][0]["reference_doi"] if by.get(k) else ir.get("doi", "")),
             "title": ir.get("title", ""), **paper_files(k, ir),
             "rows": [{c: r.get(c, "") for c in CONTENT if r.get(c, "") not in ("", None)} for r in cur]}
        if supplied and by.get(k):
            p["previous_rows"] = [{c: r.get(c, "") for c in CONTENT if r.get(c, "")} for r in by[k]]
        if k in extra:
            p["instructions"] = extra[k]
        papers.append(p)
    n = 0
    for i in range(0, len(papers), a.batch_size):
        n += 1
        (out / f"batch_{n:02d}.json").write_text(json.dumps({"run": a.run, "papers": papers[i:i + a.batch_size]}, indent=1))
    print(f"{len(papers)} papers in {n} batches under {out.relative_to(ROOT)}")
    print("agents, per batch: bench_brief.md -> bench_NN.json; fix_brief.md -> fix_NN.json; "
          "recheck_brief.md -> recheck_NN.json; target_brief.md -> target_NN.json")


# ---------------------------------------------------------------- score
def bench_counts(p):
    c = Counter(x.get("label", "") for x in p.get("claims", []))
    c["omission"] = len(p.get("omissions", []))
    return c


def metrics(c):
    tp, fp, fn = c["supported"], c["unsupported"], c["omission"]
    return (tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None)


def load_run(run, kind):
    papers, rows, log = {}, [], []
    for f in sorted(glob.glob(str(WORK / run / f"{kind}_*.json"))):
        d = json.loads(Path(f).read_text())
        papers.update(d.get("papers", {}))
        rows += d.get("rows", [])
        log += d.get("fix_log", [])
    return papers, rows, log


def cmd_score(a):
    papers, _, _ = load_run(a.run, a.stage)
    tot = Counter()
    for k, p in papers.items():
        tot.update(bench_counts(p))
    p_, r_ = metrics(tot)
    print(f"{len(papers)} papers: supported {tot['supported']}, unsupported {tot['unsupported']}, "
          f"bookkeeping {tot['not_a_paper_claim']}, omissions {tot['omission']}")
    if p_ is not None:
        print(f"precision {p_:.3f}  recall {r_:.3f}  "
              f"({'first-pass rows, before the fix' if a.stage == 'bench' else 'fixed rows, before the targeted pass'})")
    byf = defaultdict(Counter)
    for p in papers.values():
        for x in p.get("claims", []):
            byf[x.get("field", "")][x.get("label", "")] += 1
        for x in p.get("omissions", []):
            byf[x.get("field", "")]["omission"] += 1
    for f, c in sorted(byf.items(), key=lambda kv: -(kv[1]["unsupported"] + kv[1]["omission"]))[:12]:
        print(f"  {f:34s} unsupported {c['unsupported']:4d}  omitted {c['omission']:4d}")


# ---------------------------------------------------------------- apply
def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match(old, new):
    """Pair old rows with new rows describing the same species. Returns {new_index: old_row}.

    The fix agent's own `continues` field decides first; a database row that
    several new rows continue (a merged row the fix split) pairs with none of
    them, since its structure file can describe only one. Name/formula
    heuristics then pair what is left, and only when the pairing is unique.
    """
    pairs, used_o, used_n = {}, set(), set()
    pos = {o["entry_id"]: j for j, o in enumerate(old)}
    cont = Counter(n.get("continues") for n in new if n.get("continues"))
    for i, n in enumerate(new):
        c = n.get("continues")
        if c in pos and cont[c] == 1:
            pairs[i] = old[pos[c]]
            used_o.add(pos[c])
            used_n.add(i)
    used_o |= {pos[c] for c in cont if c in pos and cont[c] > 1}
    used_n |= {i for i, n in enumerate(new) if n.get("continues") in pos}

    def take(test):
        for i, n in enumerate(new):
            if i in used_n:
                continue
            cands = [j for j, o in enumerate(old) if j not in used_o and test(o, n)]
            if len(cands) == 1 and sum(1 for i2, n2 in enumerate(new)
                                       if i2 not in used_n and test(old[cands[0]], n2)) == 1:
                pairs[i] = old[cands[0]]
                used_o.add(cands[0])
                used_n.add(i)

    sp = lambda r: (r.get("active_space_nel", ""), r.get("active_space_norb", ""))
    take(lambda o, n: norm(o["compound_name"]) == norm(n.get("compound_name")) and sp(o) == sp(n))
    take(lambda o, n: norm(o["compound_name"]) == norm(n.get("compound_name")))
    take(lambda o, n: bool(o.get("formula")) and o.get("formula") == n.get("formula") and sp(o) == sp(n))
    return pairs


def validate(r):
    errs = []
    extra = set(r) - set(CONTENT) - {"continues"}
    if extra:
        errs.append(f"unknown columns {sorted(extra)}")
    for c in ("active_space_nel", "active_space_norb"):
        v = str(r.get(c, "")).strip()
        if v and not re.fullmatch(r"\d+", v):
            errs.append(f"{c}={v!r} is not an integer")
    if r.get("system_class") and r["system_class"] not in config.SYSTEM_CLASSES:
        errs.append(f"system_class={r['system_class']!r}")
    if not r.get("compound_name"):
        errs.append("empty compound_name")
    return errs


def quarantine(rows, reason, stamp, fieldnames):
    qfields = fieldnames + ["removed_reason", "removed_at"]
    existing, old_fields = [], qfields
    if QUARANTINE.exists():
        with QUARANTINE.open(newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            old_fields = rd.fieldnames or qfields
            existing = list(rd)
    fields = old_fields + [c for c in qfields if c not in old_fields]
    out = [{**r, "removed_reason": reason(r), "removed_at": stamp} for r in rows]
    if fields == old_fields and QUARANTINE.exists():
        with QUARANTINE.open("a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=fields, restval="").writerows(out)
    else:
        with QUARANTINE.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, restval="")
            w.writeheader()
            w.writerows(existing + out)


def cmd_apply(a):
    fieldnames, rows = read_db()
    fixes, frows, flog, refused = {}, [], [], []
    for bf in sorted(glob.glob(str(WORK / a.run / "batch_*.json"))):
        nn = Path(bf).stem.split("_", 1)[1]
        tgt, fix = WORK / a.run / f"target_{nn}.json", WORK / a.run / f"fix_{nn}.json"
        src = tgt if tgt.exists() else (fix if a.allow_no_target and fix.exists() else None)
        if src is None:
            keys = [p["key"] for p in json.loads(Path(bf).read_text())["papers"]]
            why = "no target output (run recheck + target, or pass --allow-no-target)" \
                if fix.exists() else "no fix output"
            refused += [(k, f"batch {nn}: {why}") for k in keys]
            continue
        d = json.loads(src.read_text())
        fixes.update(d.get("papers", {}))
        frows += d.get("rows", [])
        flog += d.get("fix_log", [])
    bench, _, _ = load_run(a.run, "bench")
    recheck, _, _ = load_run(a.run, "recheck")
    _, _, tlog = load_run(a.run, "target")
    tlogs = defaultdict(list)
    for x in tlog:
        tlogs[x.get("key", "")].append(x)
    if a.only:
        keep_keys = set(a.only.split(","))
        fixes = {k: v for k, v in fixes.items() if k in keep_keys}
    newrows = defaultdict(list)
    for r in frows:
        newrows[key_of(r.get("entry_id", "") or "?")].append(r)
    logs = defaultdict(list)
    for x in load_run(a.run, "fix")[2]:
        logs[x.get("key", "")].append(x)
    by = defaultdict(list)
    for r in rows:
        by[key_of(r["entry_id"])].append(r)
    idx = {r["key"]: r for r in index.load()}
    st = read_status()
    stamp = now()
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%d/%m/%Y")

    replaced, removed_all, renames, report = {}, [], [], []
    for k, dec in sorted(fixes.items()):
        if st.get(k, {}).get("run") == a.run and st[k].get("applied_at") and not a.reapply:
            refused.append((k, f"already applied from run {a.run} (pass --reapply to replace again)"))
            continue
        old = by.get(k, [])
        doi = old[0]["reference_doi"] if old else idx.get(k, {}).get("doi", "")
        decision = (dec.get("decision") or "").strip()
        new = newrows.get(k, [])
        if decision != "usable" and new:
            refused.append((k, f"decision {decision!r} but {len(new)} rows"))
            continue
        errs = [f"{r.get('entry_id')}: {e}" for r in new for e in validate(r)]
        if decision == "usable" and not new:
            errs.append("usable but no rows")
        if errs:
            refused.append((k, "; ".join(errs[:4])))
            continue
        # entry_ids: keep the agent's when unique and well formed, else reassign
        ids, seen = [], set()
        for r in new:
            e = r.get("entry_id", "")
            ok = re.fullmatch(re.escape(k) + r"-[a-z]{1,3}", e or "") and e not in seen
            ids.append(e if ok else None)
            seen.add(e)
        free = (f"{k}-{s}" for s in _suffixes() if f"{k}-{s}" not in seen)
        for i, r in enumerate(new):
            r["entry_id"] = ids[i] or next(free)
        pairs = match(old, new)
        out = []
        for i, r in enumerate(new):
            o = pairs.get(i, {})
            row = {c: "" for c in fieldnames}
            row.update({c: str(r.get(c, "") or "") for c in CONTENT})
            row["reference_doi"] = doi
            row["correlation_correction"] = csvio.classify_correction(row["method"])
            row["entry_type"] = config.DEFAULT_ENTRY_TYPE
            row["mining_model"] = config.CURRENT_MINING_MODEL
            row["open_access"] = old[0].get("open_access", "") if old else ""
            row["date_added"] = o.get("date_added") or today
            if o:
                row["properties"] = o.get("properties", "")
                if o.get("formula", "") == row["formula"] and o.get("metal_center", "") == row["metal_center"]:
                    row["element"] = o.get("element", "")
                if o.get("structure_file"):
                    row["structure_file"] = o["structure_file"]
                    row["structure_provenance"] = o.get("structure_provenance", "")
                    want = f"{row['entry_id']}.xyz"
                    if o["structure_file"] != want:
                        renames.append((row, o["structure_file"], want))
            out.append(row)
        paired = {o["entry_id"] for o in pairs.values()}
        orphan = [o["entry_id"] for o in old if o.get("structure_file") and o["entry_id"] not in paired]
        dates = {o["entry_id"]: o.get("date_added", "") for o in old}
        for i, r in enumerate(new):  # a split row keeps the date its species entered the database
            if i not in pairs and dates.get(r.get("continues")):
                out[i]["date_added"] = dates[r["continues"]]
        replaced[k] = out
        removed_all += old
        b = bench.get(k, {})
        c = bench_counts(b) if b else Counter()
        p_, r_ = metrics(c) if b else (None, None)
        acts = Counter(x.get("action") for x in logs[k])
        tacts = Counter(x.get("action") for x in tlogs[k])
        rc = bench_counts(recheck[k]) if k in recheck else Counter()
        st[k] = {"key": k, "doi": doi, "run": a.run, "benchmarked_at": stamp if b else "",
                 "claims_supported": c["supported"], "claims_unsupported": c["unsupported"],
                 "bookkeeping": c["not_a_paper_claim"], "omissions": c["omission"],
                 "precision": f"{p_:.3f}" if p_ is not None else "",
                 "recall": f"{r_:.3f}" if r_ is not None else "",
                 "fixes": acts["fixed"], "added": acts["added"], "removed": acts["removed"],
                 "benchmark_rejected": acts["kept_benchmark_wrong"],
                 "recheck_supported": rc["supported"] if k in recheck else "",
                 "recheck_unsupported": rc["unsupported"] if k in recheck else "",
                 "recheck_omissions": rc["omission"] if k in recheck else "",
                 "target_fixed": tacts["fixed"] if k in recheck else "",
                 "target_added": tacts["added"] if k in recheck else "",
                 "target_removed": tacts["removed"] if k in recheck else "",
                 "target_rejected": tacts["kept_benchmark_wrong"] if k in recheck else "",
                 "rows_before": len(old), "rows_after": len(out), "decision": decision,
                 "applied_at": stamp}
        report.append((k, len(old), len(out), len(pairs), orphan, decision, dec.get("reason", "")))

    for k, why in refused:
        print(f"REFUSED {k}: {why}")
    for k, nb, na, nm, orphan, decision, reason in report:
        line = f"{k}: rows {nb} -> {na} ({nm} matched)"
        if decision != "usable":
            line += f"  NOT USABLE: {reason[:100]}"
        if na < nb:
            line += "  FEWER ROWS: check nothing was dropped"
        if orphan:
            line += f"  structure left with quarantined row: {orphan}"
        print(line)
    print(f"{len(replaced)} papers to apply, {len(refused)} refused, {len(renames)} structure renames")
    if a.dry_run:
        print("dry run - nothing written")
        return 0

    # Structure files follow their row's new entry_id, in two phases so a swap
    # cannot overwrite. A destination that exists and is not itself moving away
    # (an unmatched old row's file, kept with its quarantined row) is never
    # overwritten: the row then keeps pointing at the old filename.
    moving = {src for _, src, _ in renames}
    tmp = []
    for row, src, dst in renames:
        if not (STRUCT / src).exists() or ((STRUCT / dst).exists() and dst not in moving):
            continue
        t = STRUCT / (dst + ".renaming")
        (STRUCT / src).rename(t)
        tmp.append((t, STRUCT / dst))
        row["structure_file"] = dst
    for t, d in tmp:
        t.rename(d)

    quarantine(removed_all, lambda r: f"replaced by claim-reviewed rewrite (run {a.run}); "
               f"see logs/benchmark_status.csv", stamp, fieldnames)
    out_rows, written = [], set()
    for r in rows:
        k = key_of(r["entry_id"])
        if k in replaced:
            if k not in written:
                out_rows += replaced[k]
                written.add(k)
            continue
        out_rows.append(r)
    for k in replaced:
        if k not in written:
            out_rows += replaced[k]
    t = DB.with_suffix(".csv.tmp")
    with t.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    t.replace(DB)
    write_status(st)
    for k, nb, na, nm, orphan, decision, reason in report:
        s = st[k]
        index.log_extraction(
            k, s["doi"], "claim_review", f"rows {nb} -> {na}; {decision}",
            f"run {a.run}: benchmark found {s['claims_unsupported']} unsupported of "
            f"{int(s['claims_supported'] or 0) + int(s['claims_unsupported'] or 0)} claims and "
            f"{s['omissions']} omissions; fix pass {s['fixes']} fixed, {s['added']} added, "
            f"{s['removed']} removed, {s['benchmark_rejected']} benchmark items rejected after checking "
            f"the paper."
            + (f" Recheck of the fixed rows found {s['recheck_unsupported']} unsupported claims and "
               f"{s['recheck_omissions']} omissions; targeted pass {s['target_fixed']} fixed, "
               f"{s['target_added']} added, {s['target_removed']} removed, "
               f"{s['target_rejected']} rejected." if s.get('recheck_unsupported') != "" else
               " No recheck/targeted pass (run predates it).")
            + " Old rows quarantined to logs/removed_rows.csv."
            + (f" Not usable: {reason}" if decision != "usable" else ""))
        if decision != "usable" and idx.get(k, {}).get("status") != "not_usable":
            index.set_status(k, "not_usable")
        elif decision == "usable" and idx.get(k, {}).get("status") not in ("extracted", "extracted_partial"):
            # a newly mined paper, or one now usable (e.g. its SI arrived): its rows are final
            index.set_status(k, "extracted")
    print(f"applied; quarantined {len(removed_all)} old rows. Next, from code/: "
          "tools/tools_fill_element.py --apply; tools/tools_properties.py --fill-only")
    return 0


def _suffixes():
    import itertools
    import string
    for n in (1, 2, 3):
        for t in itertools.product(string.ascii_lowercase, repeat=n):
            yield "".join(t)


# ---------------------------------------------------------------- status
def cmd_status(_a):
    _, rows = read_db()
    keys = {key_of(r["entry_id"]) for r in rows}
    st = read_status()
    done = {k for k, s in st.items() if s.get("applied_at")}
    new = {key_of(r["entry_id"]) for r in rows if added_on_or_after(r)}
    print(f"papers with rows: {len(keys)}; claim-reviewed: {len(done & keys)}; "
          f"mined since {REVIEW_FROM[0]}-{REVIEW_FROM[1]:02d}-{REVIEW_FROM[2]:02d} and awaiting review: "
          f"{len(new - done)}; mined before and not re-reviewed by policy: {len(keys - new - done)}")
    c = Counter()
    for k in done:
        c["sup"] += int(st[k]["claims_supported"] or 0)
        c["uns"] += int(st[k]["claims_unsupported"] or 0)
        c["om"] += int(st[k]["omissions"] or 0)
    if c["sup"]:
        print(f"before the fix pass, reviewed rows had precision {c['sup'] / (c['sup'] + c['uns']):.3f}, "
              f"recall {c['sup'] / (c['sup'] + c['om']):.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--run", required=True)
    p.add_argument("--papers", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--keys", help="comma-separated keys, or a file of keys")
    p.add_argument("--rows-from", help="JSON {rows:[...]} of candidate rows to review instead of the database rows; "
                                       "the database rows are then passed as previous_rows")
    p.add_argument("--instructions", help="JSON {key: text} of per-paper decisions for the agents")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("score")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", choices=["bench", "recheck"], default="bench")
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("apply")
    p.add_argument("--run", required=True)
    p.add_argument("--only", help="comma-separated keys")
    p.add_argument("--reapply", action="store_true",
                   help="replace rows of papers this run already applied")
    p.add_argument("--allow-no-target", action="store_true",
                   help="apply fix_NN where no target_NN exists (runs made before the targeted pass)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)
    a = ap.parse_args(argv)
    return a.func(a) or 0


if __name__ == "__main__":
    sys.exit(main())
