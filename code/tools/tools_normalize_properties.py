"""Bring `properties` entries to the strict grammar of tools_properties.check_field.

Review agents writing state- and method-tagged properties (2026-11-06) invented
spellings the parser and the site cannot read: contribution suffixes on the
key (`D(SOC)`), magnitude bars (`|E|[HFEPR]`), `=` inside a method tag
(`giso[Seff=1/2 gavg]`), spaces in a state label (`@minor S1 species`), keys
with no meaning in the schema (`gxy`, `Ucal`), and D or Ueff in GHz or K. Every
rewrite here is mechanical and keeps the number:

  D(SOC)[M] -> D[M SOC part]; (SSC)/(SS) -> SSC part; (contrib) -> contribution
  |X|[M]    -> X[M abs]   (|E/D| -> E/D: E/D is a magnitude by convention)
  `=` inside [...] -> space;  `|D|` inside [...] -> abs
  @state    -> spaces removed
  gxy -> gperp (the in-plane component of an axial tensor); Ucal -> Ueff[calc barrier]
  GHz, K    -> cm-1 (1 GHz = 0.0333564 cm-1, 1 K = 0.695035 cm-1), noted on the row

Anything still failing the strict check afterwards is printed, not guessed at.

Usage (from code/, with .venv/bin/python):
  .venv/bin/python tools/tools_normalize_properties.py --db [--apply]
  .venv/bin/python tools/tools_normalize_properties.py --rows FILE.json [--apply]   # properties_add
"""
import argparse
import csv
import json
import re
import sys

import _bootstrap  # noqa: F401  (puts code/ on sys.path)

from mining_agent import config, index
import tools_properties as tp

TO_CM = {"GHz": 1 / 29.9792458, "K": 0.695035}
SUFFIX = {"SOC": "SOC part", "SSC": "SSC part", "SS": "SSC part", "contrib": "contribution"}
ENTRY = re.compile(r"^(?P<key>.+?)=(?P<val>[-+]?\d+(?:\.\d+)?)(?:\s+(?P<unit>\S+))?\s+(?P<src>calc|exp)$")


def norm_key(key):
    state = ""
    if "@" in key:
        key, state = key.split("@", 1)
        state = re.sub(r"\s+", "", state)
    tags = []
    m = re.match(r"^(.*?)\[(.*)\]$", key)
    if m:
        key, inner = m.group(1), m.group(2)
        inner = inner.replace("|D|", "abs").replace("|E|", "abs E")
        tags.append(re.sub(r"\s*=\s*", " ", inner).strip())
    absval = False
    m = re.match(r"^\|(.+)\|$", key)
    if m:
        key, absval = m.group(1), True
    m = re.match(r"^(.+?)\((SOC|SSC|SS|contrib)\)$", key)
    if m:
        key = m.group(1)
        tags.append(SUFFIX[m.group(2)])
    if absval and key != "E/D":
        tags.append("abs")
    if key == "gxy":
        key = "gperp"
    if key == "Ucal":
        key = "Ueff"
        tags.append("calc barrier")
    tag = " ".join(t for t in tags if t)
    return key + (f"[{tag}]" if tag else "") + (f"@{state}" if state else "")


def norm_field(field):
    """Return (new_field, conversions) for a packed field."""
    out, conv = [], []
    for part in [p.strip() for p in (field or "").split(";") if p.strip()]:
        m = ENTRY.match(part)
        if not m:
            out.append(part)
            continue
        key, val, unit, src = norm_key(m["key"]), m["val"], m["unit"] or "", m["src"]
        if unit in TO_CM and tp.base_key(key) in ("D", "E", "Ueff"):
            new = float(val) * TO_CM[unit]
            conv.append(f"{key} {val} {unit} = {new:.4g} cm-1")
            val, unit = f"{new:.4g}", "cm-1"
        out.append(f"{key}={val}{' ' + unit if unit else ''} {src}")
    return "; ".join(out), conv


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--db", action="store_true")
    g.add_argument("--rows")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.db:
        rows = list(csv.DictReader(open(config.LITERATURE_CSV, newline="", encoding="utf-8")))
        col = "properties"
    else:
        doc = json.load(open(a.rows, encoding="utf-8"))
        rows, col = doc["rows"], "properties_add"
    changed = left = 0
    for r in rows:
        old = r.get(col, "") or ""
        if not old or not tp.check_field(old):
            continue
        new, conv = norm_field(old)
        if new != old:
            changed += 1
            r[col] = new
            if conv:
                note = "properties: " + "; ".join(conv) + " (unit conversion)"
                r["notes"] = (r["notes"] + "; " if r.get("notes") else "") + note
        rest = tp.check_field(new)
        if rest:
            left += 1
            print(f"{r['entry_id']}: still failing {rest[:3]}")
    print(f"{changed} rows rewritten, {left} still failing")
    if a.apply and changed:
        if a.db:
            with open(config.LITERATURE_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=config.LITERATURE_COLUMNS)
                w.writeheader()
                w.writerows(rows)
            index.log_extraction("properties", "", "properties", "normalized",
                                 f"{changed} rows: properties entries rewritten to the strict grammar "
                                 "(tools_normalize_properties.py)")
        else:
            json.dump(doc, open(a.rows, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
