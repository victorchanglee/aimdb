"""Check that a rewrite of a batch's rows lost no number and no active space.

A conversion to the structured `electronic_structure_description` format, or a
fold of an active-space ladder, must move numbers, never drop them. The 2026-11-06
pilot dropped 438 numbers in 35 papers before this check existed. For each paper
it compares the numbers (two or more significant digits) and the (nel,norb)
pairs in the batch's rows against those in the output rows plus the database
`properties` column, and lists what is missing.

Normalisation: trailing zeros are ignored (2.00 = 2), thin spaces inside a
number are removed (37 093.6 = 37093.6). What remains can still be a false
alarm (a range rewritten as its printed members), so every hit is read.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_check_conversion.py --batch ../benchmark/work/RUN/batch_01.json \\
      --rows ../benchmark/work/RUN/target_01.json
"""
import argparse
import collections
import csv
import json
import re
import sys

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config

OLD_FIELDS = ("electronic_structure_description", "active_space_protocol", "Other",
              "active_space_orbital_description")
NEW_FIELDS = ("electronic_structure_description", "active_space_protocol", "Other", "notes",
              "method", "active_space_orbital_description", "geometry_source",
              "nroots_per_mult", "multiplicities_studied", "properties_add")
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
PAIR = re.compile(r"\(\s*(\d+)\s*e?\s*[,/]\s*(\d+)\s*o?\s*\)")


def nums(text):
    text = (text or "").replace(" ", "").replace(" ", "")
    out = set()
    for x in NUM.findall(text):
        x = x.lstrip("-")
        if len(x.replace(".", "")) < 2:
            continue
        if "." in x:
            x = x.rstrip("0").rstrip(".")
        if x in ("", "0"):
            continue  # a zero carries no information a reader could lose
        out.add(x)
    return out


THOUSANDS = re.compile(r"(?<![\d.])\d{1,3}(?: \d{3})+(?![\d.])")


def joined(text):
    """Numbers with a thousands space read as one ("57 945" -> 57945), and
    the fragments that reading accounts for. Both readings are tried because a
    space can also separate two numbers ("2Delta5/2 175")."""
    whole, frags = set(), set()
    for m in THOUSANDS.finditer(text or ""):
        whole.add(m.group(0).replace(" ", ""))
        frags |= {p for p in m.group(0).split(" ") if len(p) >= 2}
    return whole, frags


def pairs(text):
    return set(PAIR.findall(text or ""))


def key(entry_id):
    return entry_id.rsplit("-", 1)[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--batch", required=True)
    ap.add_argument("--rows", required=True)
    a = ap.parse_args(argv)
    old_n, old_p = collections.defaultdict(set), collections.defaultdict(set)
    old_w, old_f, new_j = (collections.defaultdict(set) for _ in range(3))
    for p in json.load(open(a.batch, encoding="utf-8"))["papers"]:
        for r in p.get("rows", []):
            for f in OLD_FIELDS:
                old_n[p["key"]] |= nums(r.get(f, ""))
                w, fr = joined(r.get(f, ""))
                old_w[p["key"]] |= w
                old_f[p["key"]] |= fr
                old_p[p["key"]] |= pairs(r.get(f, ""))
            if r.get("active_space_nel") and r.get("active_space_norb"):
                old_p[p["key"]].add((r["active_space_nel"], r["active_space_norb"]))
    new_n, new_p = collections.defaultdict(set), collections.defaultdict(set)
    for r in json.load(open(a.rows, encoding="utf-8"))["rows"]:
        k = key(r["entry_id"])
        for f in NEW_FIELDS:
            new_n[k] |= nums(r.get(f, ""))
            new_j[k] |= joined(r.get(f, ""))[0]
            new_p[k] |= pairs(r.get(f, ""))
        if r.get("active_space_nel") and r.get("active_space_norb"):
            new_p[k].add((r["active_space_nel"], r["active_space_norb"]))
    keys = set(old_n) | set(old_p)
    for r in csv.DictReader(open(config.LITERATURE_CSV, newline="", encoding="utf-8")):
        if key(r["entry_id"]) in keys:
            new_n[key(r["entry_id"])] |= nums(r.get("properties", ""))
    bad = 0
    for k in sorted(keys):
        ln = sorted(x for x in old_n[k] - new_n[k] - new_j[k]
                    if not (x in old_f[k] and old_w[k] & (new_n[k] | new_j[k])))
        lp = sorted(old_p[k] - new_p[k])
        if ln or lp:
            bad += 1
            print(f"{k}: numbers missing {ln}" + (f"; spaces missing {lp}" if lp else ""))
    print(f"{len(keys) - bad} papers complete, {bad} with something missing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
