"""Read-only query layer over database/aimdb.csv.

Until now the only programmatic ways into the database were "read the whole
11 MB file" or `tools/tools_export.py`, which dumps the whole table minus the
QUEST rows. This module is the middle ground other code and agents need: a
filter over the structured columns that returns JSON-serialisable rows.

Two properties are deliberate and worth keeping.

**The QUEST boundary is enforced here, not remembered.** CLAUDE.md holds QUEST
out as a benchmark in claude-casscf/test/questdb/, and a 2026-08-03 bulk
refresh that forgot the rule carried 14 QUEST rows into literature.csv and had
to be reverted. `load()` and `find()` therefore drop QUEST-sourced rows by
default; a caller that genuinely wants them must pass include_quest=True and
say so. Rows that merely *mention* QUEST without being on the DOI list are
kept and counted, never silently dropped — same policy as tools_export.py,
whose DOI list now lives in config so the two cannot drift apart.

**A query's blind spots are reported, not hidden.** A filter can only match
rows whose field is filled, and coverage is uneven: `metal_center` is set on
38% of rows (most rows are organic, so that is not a defect), `formula` on
73%, `element` on 86%. A caller asking for iron complexes needs to be able to
tell "no such row" from "we have not extracted that field yet", so every
result carries a `blind_spots` block counting the rows each active filter
could never have matched.

Writes are deliberately absent. Appending goes through csvio.append_row, and
CLAUDE.md is explicit that extraction is judgement work ("You do the reading
and extraction"), so there is no coded path for an agent to add rows unread.
"""
import csv
import hashlib
import re
from datetime import date

from . import config

# Query keys that name a single symbol and must match whole tokens. `element`
# holds space-separated symbols ("Cl Zr"), so a substring test would match N
# inside Na and C inside Co.
_SYMBOL_RE = re.compile(r"[A-Z][a-z]?")

_cache = None


def _read():
    """Load and cache aimdb.csv. Callers get copies, never this list."""
    global _cache
    if _cache is None:
        with open(config.LITERATURE_CSV, newline="", encoding="utf-8") as f:
            _cache = list(csv.DictReader(f))
    return _cache


def schema():
    """Describe the contract a consumer is binding itself to.

    `version` is declared in config and must be bumped by hand when
    LITERATURE_COLUMNS changes; `columns_fingerprint` is derived from the
    column names themselves, so a schema change that forgets the bump is
    still detectable downstream. The schema has drifted once already — see
    the 2026-07-28 note in config.LITERATURE_COLUMNS.
    """
    joined = ",".join(config.LITERATURE_COLUMNS)
    return {
        "version": config.SCHEMA_VERSION,
        "columns": list(config.LITERATURE_COLUMNS),
        "columns_fingerprint": hashlib.sha256(joined.encode()).hexdigest()[:12],
        "system_classes": list(config.SYSTEM_CLASSES),
        "entry_types": list(config.ENTRY_TYPES),
        "open_access_values": list(config.OPEN_ACCESS_VALUES),
    }


def _is_quest(row):
    return (row.get("reference_doi") or "").strip().lower() in config.QUEST_DOIS


def _mentions_quest(row):
    return any(config.QUEST_TEXT.search(row.get(f) or "")
               for f in config.QUEST_SCAN_FIELDS)


def load(include_quest=False):
    """Every row, QUEST-sourced ones dropped unless explicitly included."""
    rows = _read()
    if include_quest:
        return [dict(r) for r in rows]
    return [dict(r) for r in rows if not _is_quest(r)]


def _tokens(value):
    """Element symbols in a cell, as whole tokens."""
    return set(_SYMBOL_RE.findall(value or ""))


def _ints(value):
    """Integers a cell offers a numeric filter.

    Most active_space_nel/norb cells are a bare number, but a few carry two
    results ("4; 6") and a few carry prose where the paper never printed a
    count. A multi-valued cell matches on either value; prose matches nothing
    and is counted as a blind spot instead.
    """
    out = []
    for part in re.split(r"[;,/]", value or ""):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _norm_doi(doi):
    doi = (doi or "").strip().lower()
    # Accept a pasted URL as well as a bare DOI.
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)


# Each filter is (row -> bool) built from the caller's value, paired with a
# test for "this row could never have matched" so blind spots can be counted.
def _build_filters(spec):
    filters = {}

    def add(name, match, usable):
        filters[name] = (match, usable)

    if spec.get("entry_id"):
        want = {e.strip() for e in _as_list(spec["entry_id"])}
        add("entry_id", lambda r: r["entry_id"] in want,
            lambda r: bool(r["entry_id"]))
    if spec.get("doi"):
        want = {_norm_doi(d) for d in _as_list(spec["doi"])}
        add("doi", lambda r: _norm_doi(r["reference_doi"]) in want,
            lambda r: bool(r["reference_doi"].strip()))
    if spec.get("element"):
        want = {e.strip() for e in _as_list(spec["element"])}
        add("element", lambda r: want <= _tokens(r["element"]),
            lambda r: bool(r["element"].strip()))
    if spec.get("metal"):
        want = {m.strip() for m in _as_list(spec["metal"])}
        # metal_center is mostly a bare symbol but 249 distinct values include
        # prose ("Fe/Mo (7 Fe + 1 Mo cluster)", "An (actinide)"), so match any
        # requested symbol appearing as a token.
        add("metal", lambda r: bool(want & _tokens(r["metal_center"])),
            lambda r: bool(r["metal_center"].strip()))
    if spec.get("system_class"):
        want = {c.strip() for c in _as_list(spec["system_class"])}
        add("system_class", lambda r: r["system_class"] in want,
            lambda r: bool(r["system_class"].strip()))
    if spec.get("formula"):
        want = [f.strip().lower() for f in _as_list(spec["formula"])]
        add("formula",
            lambda r: any(w == r["formula"].strip().lower() for w in want),
            lambda r: bool(r["formula"].strip()))
    if spec.get("compound"):
        needle = spec["compound"].lower()
        add("compound", lambda r: needle in r["compound_name"].lower(),
            lambda r: bool(r["compound_name"].strip()))
    if spec.get("method"):
        needle = spec["method"].lower()
        add("method", lambda r: needle in r["method"].lower(),
            lambda r: bool(r["method"].strip()))
    if spec.get("correlation"):
        needle = spec["correlation"].lower()
        add("correlation",
            lambda r: needle in r["correlation_correction"].lower(),
            lambda r: bool(r["correlation_correction"].strip()))
    if spec.get("software"):
        needle = spec["software"].lower()
        add("software", lambda r: needle in r["software"].lower(),
            lambda r: bool(r["software"].strip()))
    if spec.get("open_access"):
        want = {v.strip() for v in _as_list(spec["open_access"])}
        add("open_access", lambda r: r["open_access"] in want,
            lambda r: bool(r["open_access"].strip()))

    for key, col in (("nel", "active_space_nel"), ("norb", "active_space_norb")):
        if spec.get(key) is not None:
            want = {int(v) for v in _as_list(spec[key])}
            add(key, lambda r, c=col, w=want: bool(w & set(_ints(r[c]))),
                lambda r, c=col: bool(_ints(r[c])))
        rng = spec.get(f"{key}_range")
        if rng:
            lo, hi = rng
            add(f"{key}_range",
                lambda r, c=col, lo=lo, hi=hi:
                    any(lo <= v <= hi for v in _ints(r[c])),
                lambda r, c=col: bool(_ints(r[c])))

    if spec.get("year_range"):
        lo, hi = spec["year_range"]
        add("year_range",
            lambda r, lo=lo, hi=hi: bool(_ints(r["year"])) and
                lo <= _ints(r["year"])[0] <= hi,
            lambda r: bool(_ints(r["year"])))
    if spec.get("has_space"):
        add("has_space",
            lambda r: bool(_ints(r["active_space_nel"]))
                      and bool(_ints(r["active_space_norb"])),
            lambda r: True)
    return filters


def _as_list(value):
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def find(include_quest=False, limit=None, offset=0, fields=None, **spec):
    """Filter the database and return a result envelope.

    Filters (all optional, all combined with AND; list values are OR'd within
    a filter): entry_id, doi, element, metal, system_class, formula,
    compound, method, correlation, software, open_access, nel, norb,
    nel_range, norb_range, year_range, has_space.
    """
    spec = {k: v for k, v in spec.items() if v not in (None, "", [], ())}
    unknown = set(spec) - _FILTER_KEYS
    if unknown:
        raise ValueError(f"unknown filter(s): {sorted(unknown)}; "
                         f"known: {sorted(_FILTER_KEYS)}")
    if fields:
        bad = set(fields) - set(config.LITERATURE_COLUMNS)
        if bad:
            raise ValueError(f"unknown field(s): {sorted(bad)}")

    all_rows = _read()
    quest_rows = [r for r in all_rows if _is_quest(r)]
    rows = all_rows if include_quest else [r for r in all_rows
                                           if not _is_quest(r)]

    filters = _build_filters(spec)
    matched = [r for r in rows
               if all(match(r) for match, _ in filters.values())]

    # What each active filter could never have matched, so a caller can tell
    # an empty result from an unextracted field.
    blind = {}
    for name, (_, usable) in filters.items():
        missing = sum(1 for r in rows if not usable(r))
        if missing:
            blind[name] = {
                "field": _FILTER_FIELDS.get(name, name),
                "rows_without_this_field": missing,
                "of_rows_searched": len(rows),
            }

    page = matched[offset:] if limit is None else matched[offset:offset + limit]
    if fields:
        page = [{k: r[k] for k in fields} for r in page]
    else:
        page = [dict(r) for r in page]

    return {
        "schema": schema(),
        "generated": date.fromtimestamp(
            config.LITERATURE_CSV.stat().st_mtime).isoformat(),
        "database": {
            "rows_total": len(all_rows),
            "rows_searched": len(rows),
            "quest_rows_withheld": 0 if include_quest else len(quest_rows),
            "quest_mentions_kept": sum(1 for r in rows if _mentions_quest(r)),
        },
        "query": {**spec, "include_quest": include_quest,
                  "limit": limit, "offset": offset},
        "count": len(matched),
        "returned": len(page),
        "blind_spots": blind,
        "rows": page,
    }


_FILTER_KEYS = {
    "entry_id", "doi", "element", "metal", "system_class", "formula",
    "compound", "method", "correlation", "software", "open_access",
    "nel", "norb", "nel_range", "norb_range", "year_range", "has_space",
}

# The column each filter reads, so a blind spot names the field a caller
# would have to go and fill rather than the filter they happened to use.
_FILTER_FIELDS = {
    "doi": "reference_doi", "metal": "metal_center",
    "compound": "compound_name", "correlation": "correlation_correction",
    "nel": "active_space_nel", "norb": "active_space_norb",
    "nel_range": "active_space_nel", "norb_range": "active_space_norb",
    "year_range": "year",
}


def get(entry_id, include_quest=False):
    """One row by entry_id, or None.

    None means no such row. A row that exists but has not had a field
    extracted comes back with that field empty — the two are different
    answers and a caller should treat them differently.
    """
    for row in _read():
        if row["entry_id"] == entry_id:
            if _is_quest(row) and not include_quest:
                return None
            return dict(row)
    return None


def spaces_for(include_quest=False, **spec):
    """Active spaces used for the matching rows, most common first.

    The database's central question — "what active space has been used for
    this system" — as a histogram rather than a row dump. Rows whose nel or
    norb was never printed in the paper are counted in `without_space`.
    """
    result = find(include_quest=include_quest, **spec)
    counts, without = {}, 0
    for row in result["rows"]:
        nel, norb = _ints(row["active_space_nel"]), _ints(row["active_space_norb"])
        if not nel or not norb:
            without += 1
            continue
        key = f"({nel[0]},{norb[0]})"
        entry = counts.setdefault(key, {"space": key, "rows": 0, "examples": []})
        entry["rows"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(row["entry_id"])
    result["spaces"] = sorted(counts.values(), key=lambda d: -d["rows"])
    result["without_space"] = without
    del result["rows"]
    return result
