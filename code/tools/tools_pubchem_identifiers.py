"""Resolve each row's compound in PubChem: standard identifiers, and a conformer.

Two things the database lacks, and that the same lookup supplies:

1. **A standard molecule identifier.** `compound_name` is free text and
   `formula` is filled on three rows in four, so the same molecule under two
   spellings cannot be matched, and a training split cannot keep benzene out
   of both halves. PubChem's name resolution returns the InChIKey, InChI and
   SMILES for any name it knows. They are written to
   `database/identifiers.csv`, one row per `entry_id`, a sidecar rather than
   new aimdb.csv columns, so the schema and its consumers are untouched until
   someone decides to merge them.

2. **A 3D structure** for rows that have none. These are PubChem's computed
   conformers for the *compound*, never the geometry the paper computed with;
   the file's comment line and the row's `structure_provenance=ai_generated`
   say so, exactly as `python -m mining_agent structure` does for one row.

The check that makes either safe to record is the formula. A name like
"the CNCCP isomer of NC3P" resolves to nothing, which is harmless; the danger
is a name that resolves to the *wrong* compound. So every hit's PubChem
formula is compared, element by element and ignoring charge, with the row's
`formula`. The status column records the outcome:

  match             PubChem composition equals the row's formula
  mismatch          it does not; identifiers are kept for the record, flagged,
                    and no structure is saved
  no_formula        the row has no formula to check against; identifiers are
                    kept and flagged unverified, and no structure is saved
  formula_unparsed  the row's formula is abbreviated ([Fe(TPP)Cl]) and cannot
                    be compared; treated like no_formula
  unresolved        PubChem knows none of the name variants tried

Only `match` rows get a conformer, and only a genuine 3D conformer (the 2D
depiction PubChem serves for molecules without one is not a geometry).

The name variants tried, in order: the name as written; without a leading
"the "; the part before " in its " / " (" / ","; and the IUPAC-looking last
clause after " of ". The first that resolves wins, and the variant used is
recorded. Every answer is cached in logs/pubchem_cache.json, so a rerun costs
nothing for names already asked.

aimdb.csv is not touched while the lookups run (hours, at PubChem's five
requests per second). Conformers are written to database/structures/ and the
row edits are queued in logs/pubchem_structure_edits.json; `--apply` writes
them to the rows in one pass, with a note and a logs/extractions.csv line each.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_pubchem_identifiers.py --dry-run
  .venv/bin/python tools/tools_pubchem_identifiers.py             # resolve + queue
  .venv/bin/python tools/tools_pubchem_identifiers.py --apply     # stamp queued structure_file edits
  .venv/bin/python tools/tools_pubchem_identifiers.py --no-structures   # identifiers only
"""
import argparse
import csv
import datetime
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, csvio, index, structures

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PROPS = "MolecularFormula,InChIKey,InChI,SMILES,ConnectivitySMILES,Charge,Title"
IDENTIFIERS = config.DATABASE_DIR / "identifiers.csv"
CACHE = config.LOGS_DIR / "pubchem_cache.json"
QUEUE = config.LOGS_DIR / "pubchem_structure_edits.json"
INTERVAL = 1.0   # PubChem also caps server time at 300 s/min, and a failed name lookup costs seconds
WORKERS = 1      # rows resolved concurrently; the limiter keeps the request rate
FAILED = object()  # a lookup that got no answer (throttled, network); never cached or recorded
# a name longer than this, or with more words, is a description and never resolves
MAX_QUERY_CHARS, MAX_QUERY_WORDS = 70, 8

ID_COLUMNS = ["entry_id", "compound_name", "query_used", "cid", "title",
              "molecular_formula", "formula_row", "status", "inchikey",
              "inchi", "smiles", "connectivity_smiles", "charge", "date"]

from tools_find_coordinate_blocks import parse_formula  # noqa: E402  (one parser for both tools)


_TRAILING = re.compile(
    r"\s+(?:diatomic molecule|parent molecule|molecule|molecules|diatomic|"
    r"monomer|in the gas phase|gas-phase|\(gas phase\))$", re.I)


def name_variants(name):
    """(variant, is_whole_name) pairs to try, in order. A variant cut out of
    the name is a fragment: it may resolve to a different compound, so a row
    with no formula to check against accepts only whole-name hits."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = name.replace("—", " - ").replace("–", " - ")
    out = []

    def add(v, whole):
        v = v.strip(" .;:-")
        if (v and len(v) <= MAX_QUERY_CHARS and len(v.split()) <= MAX_QUERY_WORDS
                and v.lower() not in {o.lower() for o, _ in out}):
            out.append((v, whole))

    base = re.sub(r"^(the|a|an)\s+", "", name, flags=re.I)
    add(name, True)
    add(base, True)
    add(_TRAILING.sub("", base), True)
    # a trailing formula token ("all-trans octatetraene C8H10") is a label, not the name
    m = re.match(r"^(.*?)\s+([A-Z][A-Za-z0-9+\-]*)$", base)
    if m and parse_formula(m.group(2)):
        add(m.group(1), True)
    # cut at a descriptive clause; a comma between digits (1,2,3-triazole) is not one
    seps = [re.escape(x) for x in (" in its ", " in the ", " (", ";", " - ", " at ",
                                   " with ", " on the ", " on ", " from ")]
    seps.append(r"(?<!\d),(?!\d)")
    for sep in seps:
        parts = re.split(sep, base, maxsplit=1)
        if len(parts) == 2:
            add(_TRAILING.sub("", parts[0]), False)
    m = re.search(r"\bof\s+([^,;()]+)$", base)
    if m:
        add(m.group(1), False)
    return out[:6]


class PubChem:
    """Thread-safe client: one session per thread, one rate limiter for all."""

    def __init__(self):
        self.local = threading.local()
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.cooldown_until = 0.0  # set on a 429: PubChem blocks a client for minutes
        self.cache = {}
        if CACHE.exists():
            self.cache = json.loads(CACHE.read_text(encoding="utf-8"))

    @property
    def session(self):
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
            self.local.session.headers["User-Agent"] = config.USER_AGENT
        return self.local.session

    def save_cache(self):
        with self.lock:
            CACHE.write_text(json.dumps(self.cache, indent=0), encoding="utf-8")

    def _wait_turn(self):
        with self.lock:
            now = time.monotonic()
            delay = max(self.last_request + INTERVAL, self.cooldown_until) - now
            self.last_request = max(now, self.last_request + INTERVAL, self.cooldown_until)
        if delay > 0:
            time.sleep(delay)

    def _get(self, url, **params):
        for attempt in range(5):
            self._wait_turn()
            try:
                resp = self.session.get(url, params=params or None, timeout=30)
            except requests.RequestException as exc:
                print(f"  network error {exc}; backing off", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code in (429, 503):
                pause = 300 * (attempt + 1)  # a 429 block lasts minutes; probing extends it
                print(f"  HTTP {resp.status_code}; pausing {pause}s", file=sys.stderr, flush=True)
                with self.lock:
                    self.cooldown_until = max(self.cooldown_until, time.monotonic() + pause)
                time.sleep(pause)
                continue
            return resp
        return None

    def properties(self, name):
        key = "p:" + name.lower()
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        resp = self._get(f"{PUG}/compound/name/{requests.utils.quote(name)}"
                         f"/property/{PROPS}/JSON")
        result = None
        if resp is None:
            return FAILED  # do not cache a transport failure
        if resp.status_code == 200:
            props = resp.json().get("PropertyTable", {}).get("Properties", [])
            if props:
                result = props[0]
        with self.lock:
            self.cache[key] = result
        return result

    def sdf3d(self, cid):
        resp = self._get(f"{PUG}/compound/cid/{cid}/SDF", record_type="3d")
        if resp is None or resp.status_code != 200:
            return None
        return resp.text


def load_identifiers():
    rows = {}
    if IDENTIFIERS.exists():
        with IDENTIFIERS.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows[r["entry_id"]] = r
    return rows


def write_identifiers(rows):
    tmp = IDENTIFIERS.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ID_COLUMNS)
        w.writeheader()
        for eid in sorted(rows):
            w.writerow({c: rows[eid].get(c, "") for c in ID_COLUMNS})
    tmp.replace(IDENTIFIERS)


def load_queue():
    if QUEUE.exists():
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    return []


def save_queue(q):
    QUEUE.write_text(json.dumps(q, indent=1), encoding="utf-8")


def resolve(args):
    with config.LITERATURE_CSV.open(newline="", encoding="utf-8") as fh:
        db = list(csv.DictReader(fh))
    ids = load_identifiers()
    queue = load_queue()
    queued = {e["entry_id"] for e in queue}
    targets = [r for r in db
               if r.get("system_class") == "molecule"
               and (r.get("compound_name") or "").strip()
               and (args.redo or r["entry_id"] not in ids)]
    if args.keys:
        targets = [r for r in targets if r["entry_id"] in set(args.keys)]
    if args.max:
        targets = targets[:args.max]
    print(f"{len(targets)} rows to resolve ({len(ids)} already in identifiers.csv)",
          flush=True)
    if args.dry_run:
        return 0

    pc = PubChem()
    today = datetime.date.today().isoformat()
    tally = {}

    def resolve_row(r):
        eid = r["entry_id"]
        rec = {"entry_id": eid, "compound_name": r["compound_name"],
               "formula_row": r.get("formula", ""), "date": today}
        hit, used = None, ""
        has_formula = parse_formula(r.get("formula")) is not None
        for v, is_whole in name_variants(r["compound_name"]):
            if not is_whole and not has_formula:
                continue  # a fragment hit cannot be checked; do not record it
            hit = pc.properties(v)
            if hit is FAILED:
                rec["status"] = "deferred"  # PubChem gave no answer; try again on a rerun
                return rec, None
            if hit:
                used = v
                break
        if not hit:
            rec["status"] = "unresolved"
            return rec, None
        rec.update({
            "query_used": used, "cid": hit.get("CID", ""),
            "title": hit.get("Title", ""),
            "molecular_formula": hit.get("MolecularFormula", ""),
            "inchikey": hit.get("InChIKey", ""), "inchi": hit.get("InChI", ""),
            "smiles": hit.get("SMILES", ""),
            "connectivity_smiles": hit.get("ConnectivitySMILES", ""),
            "charge": hit.get("Charge", "")})
        row_f = parse_formula(r.get("formula"))
        pc_f = parse_formula(hit.get("MolecularFormula"))
        if not (r.get("formula") or "").strip():
            rec["status"] = "no_formula"
        elif row_f is None or pc_f is None:
            rec["status"] = "formula_unparsed"
        elif row_f == pc_f:
            rec["status"] = "match"
        else:
            rec["status"] = "mismatch"
        entry = None
        if (rec["status"] == "match" and not args.no_structures
                and not (r.get("structure_file") or "").strip()
                and eid not in queued):
            sdf = pc.sdf3d(hit["CID"])
            parsed = structures._sdf_to_xyz(sdf, used, "3D conformer") if sdf else None
            if sdf is None:
                rec["status"] = "match(3d lookup deferred)"  # rerun fetches it
            if parsed:
                xyz, cid = parsed
                dest = config.DATABASE_DIR / "structures" / f"{eid}.xyz"
                if not dest.exists():
                    dest.write_text(xyz)
                    entry = {"entry_id": eid, "file": dest.name, "cid": cid,
                             "query": used, "formula": hit.get("MolecularFormula", "")}
                    rec["status"] = "match+3d"
            else:
                rec["status"] = "match(no 3d conformer)"
        return rec, entry

    n = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(resolve_row, r) for r in targets]
        for fut in as_completed(futures):
            rec, entry = fut.result()
            if rec["status"] != "deferred":
                ids[rec["entry_id"]] = rec
            if entry:
                queue.append(entry)
                queued.add(entry["entry_id"])
            tally[rec["status"]] = tally.get(rec["status"], 0) + 1
            n += 1
            if n % 50 == 0 or n == len(targets):
                write_identifiers(ids)
                save_queue(queue)
                pc.save_cache()
                print(f"  {n}/{len(targets)}  " +
                      "  ".join(f"{k}={v}" for k, v in sorted(tally.items())), flush=True)
    write_identifiers(ids)
    save_queue(queue)
    pc.save_cache()
    print("done:", tally, flush=True)
    return 0


def apply(args):
    queue = load_queue()
    if not queue:
        print("nothing queued")
        return 0
    with config.LITERATURE_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols, db = reader.fieldnames, list(reader)
    by_id = {r["entry_id"]: r for r in db}
    applied, kept = [], []
    for e in queue:
        row = by_id.get(e["entry_id"])
        dest = config.DATABASE_DIR / "structures" / e["file"]
        if row is None or not dest.exists():
            kept.append(e)
            continue
        if (row.get("structure_file") or "").strip():
            continue  # someone gave it a real geometry meanwhile; drop the queue entry
        row["structure_file"] = csvio.normalize_structure_filename(e["file"])
        row["structure_provenance"] = "ai_generated"
        note = (f"structure_file is a generated PubChem conformer (CID {e['cid']}, "
                f"name lookup {e['query']!r}, composition {e['formula']} checked "
                f"against the row's formula), not the paper's geometry")
        row["notes"] = (row["notes"] + "; " if row["notes"] else "") + note
        applied.append(e)
    if args.dry_run:
        print(f"would apply {len(applied)}, keep {len(kept)} queued")
        return 0
    tmp = config.LITERATURE_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(db)
    tmp.replace(config.LITERATURE_CSV)
    for e in applied:
        index.log_extraction(e["entry_id"], by_id[e["entry_id"]].get("reference_doi", ""),
                             "structure", "generated",
                             f"{e['file']} from PubChem name lookup {e['query']!r} "
                             f"(CID {e['cid']}; formula {e['formula']} matches row) [batch]")
    save_queue(kept)
    print(f"applied {len(applied)} structure_file edits; {len(kept)} left queued")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write queued structure_file edits into aimdb.csv")
    ap.add_argument("--no-structures", action="store_true",
                    help="identifiers only; fetch no conformers")
    ap.add_argument("--redo", action="store_true",
                    help="re-resolve rows already in identifiers.csv")
    ap.add_argument("--keys", nargs="*", help="restrict to these entry_ids")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return apply(args) if args.apply else resolve(args)


if __name__ == "__main__":
    raise SystemExit(main())
