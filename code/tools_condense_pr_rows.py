#!/usr/bin/env python3
"""Condense over-split literature rows added by the current PR.

The database contribution rule is one row per chemical compound, not one row
per state, method, active-space choice, table cell, scan point, or reaction
path geometry.  This tool identifies the rows introduced by mining commit
``9ed7907``, builds conservative compound groups, and rewrites only those
rows.  Pre-existing and subsequently contributed rows are never changed.

Run without ``--apply`` to inspect the proposed counts.  Applying also appends
one audit record per retained/merged row to ``logs/extractions.csv``.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "aimdb.csv"
EXTRACTIONS = ROOT / "logs" / "extractions.csv"
BASE_SPEC = "9ed7907^:database/aimdb.csv"
SOURCE_SPEC = "9ed7907:database/aimdb.csv"
SOURCE_EXTRACTIONS_SPEC = "9ed7907:logs/extractions.csv"
MAIN_SPEC = "origin/main:database/aimdb.csv"
MAIN_EXTRACTIONS_SPEC = "origin/main:logs/extractions.csv"
AUDIT_MARKER = "GPT-5.6 full PR over-splitting correction (2026-08-17)"

METHOD = (
    r"(?:FOMO(?:-[A-Z0-9]+)?|SA\d*[- ]?CASSCF|CASSCF|CASPT2|"
    r"MS[- ]?CASPT2|XMS[- ]?CASPT2|MRCI(?:\+D)?|MRMP2|CASCI|"
    r"RASSCF|RASPT2|NEVPT2|QDPT|MCQDPT2|GMC[- ]?QDPT|SOCI|"
    r"ONIOM|CAS\([^)]*\))"
)

STRONG_COMMA_DESCRIPTOR = (
    r"(?:state\s*\d+|vertical\b|adiabatic\b|fluorescence\b|"
    r"absorption\b|ground[- ]state\b|excited[- ]state\b|relaxed\b|"
    r"Franck[- ]Condon\b|S\d(?:\b|/)|T\d(?:\b|/)|CAS(?:SCF|PT2|CI|\()|"
    r"MRCI\b|MRMP2\b|MS[- ]?CASPT2\b|ONIOM\b|active[- ]space\b|"
    r"large active space\b|compact[- ]space\b|basis\b|reference\b|"
    r"triplet\b|open-shell singlet\b|singlet\b|n-pi\*|pi-space\b|"
    r"pi/sigma-space\b|electronic state\b|excitation\b|"
    r"configuration-space\b|[0-9]+\^?[123]?[A-Z][A-Za-z0-9'\"]*\s+"
    r"(?:vertical|adiabatic|state))"
)

# Papers whose added rows are entirely table/state/path representations of a
# single chemical system.  Values are retained in the merged row's result
# fields; this changes row granularity, not source coverage.
ONE_COMPOUND = {
    "10.1063/1.4723808": "[Ir(ppy)2(bpy)]+",
    "10.1063/1.1290607": "NO3",
    "10.1021/jp961993j": "methylene",
    "10.1039/c5cp02446c": "azobenzene",
    "10.1021/ja982661q": "phenylnitrene",
    "10.1021/ja00031a014": "manganese pentacarbonyl hydride",
    "10.1021/jp201327w": "uracil",
    "10.1021/jp0537207": "9H-adenine",
    "10.1021/jz100196q": "anthracene-9,10-endoperoxide",
    "10.1021/jp9932766": "Co+ + propane reaction system",
    "10.1021/jp0633188": "acetylene + ozone reaction system",
    "10.1039/c0cp01827a": "phenalenone",
}

NONCOMPOUND_RE = re.compile(
    r"\b(?:transition state|transition structure|stationary point|"
    r"stationary structure|saddle point|inflection-region structure|"
    r"conical intersection|minimum-energy crossing|surface crossing|"
    r"singlet-triplet crossing|crossing point|crossing region|MECI|"
    r"PES point|path point|scan point|intrinsic reaction coordinate|"
    r"minimum-energy path|reaction coordinate|trajectory|potential-energy "
    r"grid|local potential-energy grid|dissociation curve|potential curve|"
    r"spectroscopic-constant curve|cross-section|dissociation limit|"
    r"asymptote|constrained structure|constrained biradical)\b|"
    r"\b(?:active[- ]space|basis[- ]set|compact[- ]space|reduced[- ]space) "
    r"(?:test|benchmark|comparison|check)\b|"
    r"\bTS(?:[-_:]?[0-9]|[-_:][A-Za-z]|[a-z]\b)|"
    r"\bCI(?:[0-9]|[-_][A-Za-z0-9])",
    re.IGNORECASE,
)

TOKEN_STOP = {
    "state", "ground", "excited", "vertical", "adiabatic", "minimum",
    "transition", "structure", "point", "path", "curve", "scan", "table",
    "casscf", "caspt2", "mrci", "mrmp2", "casci", "rasscf", "result",
    "reference", "calculation", "geometry", "energies", "energy", "singlet",
    "triplet", "quartet", "quintet", "electronic", "conical", "intersection",
}


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_base() -> list[dict[str, str]]:
    return load_git_csv(BASE_SPEC)[1]


def load_git_csv(spec: str) -> tuple[list[str], list[dict[str, str]]]:
    text = subprocess.check_output(["git", "show", spec], cwd=ROOT, text=True)
    reader = csv.DictReader(io.StringIO(text))
    fields = list(reader.fieldnames or [])
    rows = list(reader)
    return fields, rows


def special_identity(doi: str, name: str, formula: str) -> str | None:
    if doi in ONE_COMPOUND:
        return ONE_COMPOUND[doi]

    if doi == "10.1021/ja9727169":
        value = name.split(", ", 1)[0]
        value = value.replace("singlet propargylene HCCCH", "propargylene HCCCH")
        value = value.replace("HCCCH triplet propargylene", "propargylene HCCCH")
        return value

    if doi == "10.1063/1.458298":
        match = re.match(r"^(H2(?:Te|Po)\+?)", name)
        return match.group(1) if match else None

    if doi == "10.1063/1.452835":
        return "N2+"

    if doi == "10.1021/jp1019872":
        match = re.match(r"^(coumarin\s+(?:120|151))", name, re.IGNORECASE)
        return match.group(1) if match else None

    if doi == "10.1021/jp805173n":
        match = re.match(
            r"^(GeH[+-]?|bridged/bent Ge2H[+-]?)(?=\s|$)", name,
            re.IGNORECASE,
        )
        return match.group(1) if match else None

    if doi == "10.1039/c5cp03442f":
        if name.startswith("2-HEAQ·5H2O"):
            return "2-HEAQ·5H2O"
        if name.startswith("isolated 2-HEAQ"):
            return "isolated 2-HEAQ"

    if doi == "10.1063/1.469414":
        return formula or name

    if doi == "10.1039/a907834g":
        return formula or name

    if doi == "10.1063/1.4922352":
        lowered = name.casefold()
        identities = (
            ("f2 at", "F2"),
            ("no at", "NO"),
            ("nickel-acetylene", "nickel-acetylene complex"),
            ("nitrogen dioxide", "nitrogen dioxide"),
            ("ozone", "ozone"),
            ("nitrobenzene", "nitrobenzene"),
            ("phenoxy radical", "phenoxy radical"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity

    if doi == "10.1039/c3cp55020f":
        if name.startswith("aqueous (dA)5"):
            return "aqueous (dA)5"
        if name.startswith("9H-adenine monomer"):
            return "9H-adenine monomer"

    if doi == "10.1021/jp014289y":
        for value in (
            "benzene", "ethylene", "neutral GFP chromophore",
            "model retinal protonated Schiff base",
        ):
            if name.startswith(value):
                return value

    if doi == "10.1021/ja962576n":
        if "cyclooctadiene" in name:
            return "cyclooctadiene"
        if "divinylcyclobutane" in name:
            return "1,3-divinylcyclobutane"
        return "butadiene dimer excited-state system"

    if doi == "10.1039/c3ra47186a":
        match = re.match(
            r"^(N-(?:methyl|isopropyl) conjugated nitrone model [IVX]+)",
            name, re.IGNORECASE,
        )
        return match.group(1) if match else None

    if doi == "10.1021/jp909947c":
        model = re.search(
            r"Dronpa model chromophore, (?:anionic |zwitterionic |neutral |"
            r"cationic )?([AZNC](?:cis|trans))", name, re.IGNORECASE,
        )
        if model:
            return f"Dronpa model chromophore {model.group(1)}"
        protein = re.search(
            r"Dronpa (on|off)-state protein with ([AZN](?:cis|trans)) "
            r"chromophore", name, re.IGNORECASE,
        )
        if protein:
            return f"Dronpa {protein.group(1)}-state protein {protein.group(2)}"
        if "twisted intermediate NTI" in name:
            return "Dronpa neutral twisted intermediate NTI"

    if doi == "10.1021/jp060995t":
        for identity in (
            "2-methylpyrazine", "2,5-dimethylpyrazine",
            "2,6-dimethylpyrazine",
        ):
            if name.startswith(identity):
                return identity

    if doi == "10.1039/c2cp22341d":
        for prefix, identity in (
            ("trimethylamine", "trimethylamine N-oxide"),
            ("dimethylphenylamine", "dimethylphenylamine N-oxide"),
            ("methyl diphenylamine", "methyl diphenylamine N-oxide"),
            ("triphenylamine", "triphenylamine N-oxide"),
        ):
            if name.startswith(prefix):
                return identity

    if doi == "10.1063/1.3490480":
        lowered = name.casefold()
        identities = (
            ("weakly bound complex", "O2 + ethylene weakly bound complex"),
            ("peroxide biradical im1", "peroxide biradical IM1"),
            ("biradical im2", "biradical IM2"),
            ("im2-s", "biradical IM2"),
            ("biradical im3", "biradical IM3"),
            ("1,2-dioxetane", "1,2-dioxetane"),
            ("o2 singlet-triplet", "O2"),
            ("vinyl radical", "vinyl radical"),
            ("hydroperoxyl", "hydroperoxyl radical"),
            ("ethylene oxide", "ethylene oxide"),
            ("vinyl peroxide", "vinyl peroxide radical"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity
        if "biradical" in lowered:
            return "1,3-biradical intermediate"

    if doi == "10.1021/ja802666v":
        lowered = name.casefold()
        if "bis-allyl intermediate" in lowered:
            return "1a-to-2a bis-allyl intermediate"
        if "allyl-butadienyloxy intermediate" in lowered:
            return "1a-to-2a allyl-butadienyloxy intermediate"
        if lowered == "compound 1a" or name.startswith("1a "):
            return "compound 1a"
        if lowered == "compound 2a" or name.startswith("2a "):
            return "compound 2a"

    if doi == "10.1021/ja983480r":
        lowered = name.casefold()
        identities = (
            ("norbornene", "norbornene"),
            ("bicyclo[3.2.0]", "bicyclo[3.2.0]hept-2-ene"),
            ("bicyclo[4.1.0]", "bicyclo[4.1.0]hept-2-ene"),
            ("tricyclo[3.2.1.0", "tricyclo[3.2.1.0^3,7]heptane"),
            ("anti biradical", "anti biradical intermediate"),
            ("gauche-out biradical", "gauche-out biradical intermediate"),
            ("gauche-in biradical", "gauche-in biradical intermediate"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity

    if doi == "10.1021/ja953858a":
        lowered = name.casefold()
        identities = (
            ("formaldehyde carbonyl oxide", "formaldehyde carbonyl oxide"),
            ("methyldioxirane", "methyldioxirane"),
            ("syn acetaldehyde carbonyl oxide", "syn acetaldehyde carbonyl oxide"),
            ("anti acetaldehyde carbonyl oxide", "anti acetaldehyde carbonyl oxide"),
            ("acetaldehyde carbonyl oxide", "acetaldehyde carbonyl oxide"),
            ("dioxirane", "dioxirane"),
            ("hydroperoxyethylene", "cis hydroperoxyethylene"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity

    if doi == "10.1021/jp034391q":
        return "ethylene + peroxyformic acid epoxidation system"

    if doi == "10.1021/jo049542f":
        lowered = name.casefold()
        identities = (
            ("ethylene reference", "ethylene"),
            ("cyclopentyne reactant", "cyclopentyne"),
            ("cyclopentyne plus ethylene singlet biradical", "cyclopentyne + ethylene biradical"),
            ("cyclopentyne plus ethylene triplet biradical", "cyclopentyne + ethylene biradical"),
            ("cyclopentyne plus ethylene carbene", "cyclopentyne + ethylene carbene"),
            ("cyclopentyne-ethylene [2+2] cycloadduct", "cyclopentyne-ethylene cycloadduct"),
            ("benzyne reactant", "benzyne"),
            ("benzyne plus ethylene singlet biradical", "benzyne + ethylene biradical"),
            ("benzyne plus ethylene triplet biradical", "benzyne + ethylene biradical"),
            ("benzyne plus ethylene carbene", "benzyne + ethylene carbene"),
            ("benzocyclobutene", "benzocyclobutene"),
            ("acetylene plus ethylene", "acetylene + ethylene reaction system"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity

    if doi == "10.1021/jo026188h":
        lowered = name.casefold()
        identities = (
            ("ketene + formaldimine planar trans intermediate", "ketene + formaldimine trans intermediate"),
            ("ketene + formaldimine trans intermediate", "ketene + formaldimine trans intermediate"),
            ("ketene + formaldimine shallow gauche intermediate", "ketene + formaldimine gauche intermediate"),
            ("ketene + formaldimine gauche intermediate", "ketene + formaldimine gauche intermediate"),
            ("ketene + formaldimine parent β-lactam", "parent beta-lactam"),
            ("keteniminium cation + formaldimine trans intermediate", "keteniminium + formaldimine trans intermediate"),
            ("keteniminium + formaldimine trans intermediate", "keteniminium + formaldimine trans intermediate"),
            ("keteniminium cation + formaldimine cis/gauche intermediate", "keteniminium + formaldimine cis intermediate"),
            ("keteniminium + formaldimine cis intermediate", "keteniminium + formaldimine cis intermediate"),
            ("keteniminium cation + formaldimine ionic β-lactam", "ionic beta-lactam"),
            ("keteniminium cation reactant", "keteniminium cation"),
            ("ketene reactant", "ketene"),
        )
        for marker, identity in identities:
            if marker in lowered:
                return identity
        if lowered == "formaldimine":
            return "formaldimine"

    if doi == "10.1039/c4ra16375c":
        match = re.match(
            r"^((?:Z|E)-alpha-\(2-naphthyl\)-N-methylnitrone)",
            name, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        match = re.match(
            r"^(alpha-\(2-naphthyl\)-N-methyl oxaziridine Ox\d+)",
            name, re.IGNORECASE,
        )
        if match:
            return match.group(1)
        if name.startswith("alpha-(2-naphthyl)-N-methylnitrone"):
            return "alpha-(2-naphthyl)-N-methylnitrone"

    return None


def canonical_name(row: dict[str, str]) -> str:
    doi = compact(row["reference_doi"]).casefold()
    name = compact(row["compound_name"])
    formula = compact(row["formula"])
    special = special_identity(doi, name, formula)
    if special:
        return compact(special)

    value = name
    value = re.sub(
        r"\s+Table\s+(?:[IVXLCDM]+|S?\d+).*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:PES|path|scan)\s+point\s*\d*.*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:spectroscopic-constant|dissociation|potential(?:-energy)?)\s+"
        r"(?:curve|grid|scan).*$", "", value, flags=re.IGNORECASE,
    )
    value = re.sub(
        rf"\s+[—-]\s*{METHOD}.*$", "", value, flags=re.IGNORECASE
    )
    value = re.sub(
        rf"\s+at\s+{METHOD}.*$", "", value, flags=re.IGNORECASE
    )

    # Generated row names consistently use comma-space to separate the real
    # compound from a state/method descriptor; IUPAC locants use bare commas.
    parts = value.split(", ")
    if len(parts) > 1:
        cut = None
        for index in range(1, len(parts)):
            tail = ", ".join(parts[index:])
            if re.search(STRONG_COMMA_DESCRIPTOR, tail, re.IGNORECASE):
                cut = index
                break
        if cut is not None:
            value = ", ".join(parts[:cut])

    value = re.sub(
        rf"\s*\((?:{METHOD}|main Table|SI Table).*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:[0-9XabcE][^,]{0,35}\s+)?electronic state.*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:\d+)?(?:Pi|Sigma|Delta|Phi|A[0-9'\"]*|B[0-9'\"]*|"
        r"E[0-9'\"]*)\s+state.*$", "", value, flags=re.IGNORECASE,
    )
    if re.search(r"\b(?:CASSCF|CASPT2|MRCI|CASCI)\b", value, re.IGNORECASE):
        value = re.sub(r"\s+at\s+.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\s+\(?open-shell\s+singlet\)?\s*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+\(?(?:singlet|triplet|quartet|quintet)\)?\s*$", "", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:ground[- ]state|excited[- ]state)\s*"
        r"(?:EPR g tensor|minimum|reference|manifold)?\s*$", "", value,
        flags=re.IGNORECASE,
    )
    term = (
        r"(?:\d+\s+)?(?:\^?[123456])?(?:A|B|E)[0-9'\"]*|"
        r"(?:\^?[123456])?(?:Pi|Sigma|Delta|Phi)(?:_[A-Za-z0-9+\-]+)?"
    )
    value = re.sub(
        rf"\s+(?:(?:X|A'|second|bent|linear)\s+)?(?:{term})"
        r"(?:\s*\([^)]*\))?\s*$", "", value, flags=re.IGNORECASE,
    )
    value = re.sub(
        rf"\s+{METHOD}(?:\([^)]*\))?\s+"
        r"(?:result|reference|energies|benchmark).*$", "", value,
        flags=re.IGNORECASE,
    )
    return compact(value) or name


def group_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        compact(row["reference_doi"]).casefold(),
        canonical_name(row).casefold(),
        compact(row["formula"]).casefold(),
    )


def is_noncompound(row: dict[str, str]) -> bool:
    return bool(NONCOMPOUND_RE.search(compact(row["compound_name"])))


def identity_tokens(value: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", value.casefold()))
    return {token for token in tokens if token not in TOKEN_STOP and len(token) > 1}


def similarity(left: str, right: str) -> tuple[int, float]:
    a, b = identity_tokens(left), identity_tokens(right)
    overlap = len(a & b)
    union = len(a | b) or 1
    return overlap, overlap / union


def build_groups(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    initial: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        initial[group_key(row)].append(row)

    by_doi_formula: dict[tuple[str, str], list[tuple[tuple[str, str, str], list[dict[str, str]]]]] = defaultdict(list)
    for key, members in initial.items():
        by_doi_formula[(key[0], key[2])].append((key, members))

    final: list[list[dict[str, str]]] = []
    for _, entries in by_doi_formula.items():
        stable = [item for item in entries if not all(is_noncompound(r) for r in item[1])]
        transient = [item for item in entries if all(is_noncompound(r) for r in item[1])]
        if not transient:
            final.extend(members for _, members in stable)
            continue
        if not stable:
            # A paper/formula made only table/path/TS rows.  It still merits one
            # literature entry, but not one entry per sampled geometry.
            merged: list[dict[str, str]] = []
            for _, members in entries:
                merged.extend(members)
            final.append(merged)
            continue

        stable_members = [members for _, members in stable]
        stable_names = [canonical_name(members[0]) for members in stable_members]
        for key, members in transient:
            source_name = canonical_name(members[0])
            target_index = max(
                range(len(stable_members)),
                key=lambda index: similarity(source_name, stable_names[index]),
            )
            stable_members[target_index].extend(members)
        final.extend(stable_members)

    return final


def unique_values(rows: list[dict[str, str]], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = compact(row.get(field, ""))
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def representative_score(row: dict[str, str], canonical: str) -> tuple[int, ...]:
    name = compact(row["compound_name"])
    lower = name.casefold()
    method = row["method"].upper()
    filled = sum(bool(compact(value)) for value in row.values())
    return (
        int(not is_noncompound(row)),
        int(name.casefold() == canonical.casefold()),
        int("ground" in lower or "s0" in lower or "reactant" in lower),
        int("minimum" in lower),
        int(bool(compact(row["structure_file"]))),
        int("CASSCF" in method or "RASSCF" in method or "CASCI" in method),
        int(not any(word in lower for word in ("transition", "crossing", "path", "scan"))),
        filled,
        -len(name),
    )


def append_unique_sentence(base: str, addition: str) -> str:
    base, addition = compact(base), compact(addition)
    if not addition or addition in base:
        return base
    return f"{base}; {addition}" if base else addition


def labeled_merge(rows: list[dict[str, str]], field: str) -> str:
    pairs: list[str] = []
    seen: set[tuple[str, str]] = set()
    values = unique_values(rows, field)
    if len(values) == 1:
        return values[0]
    for row in rows:
        value = compact(row.get(field, ""))
        if not value:
            continue
        label = compact(row["compound_name"])
        key = (label, value)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(f"{label}: {value}")
    return " | ".join(pairs)


def merge_group(rows: list[dict[str, str]]) -> tuple[dict[str, str], list[dict[str, str]]]:
    if len(rows) == 1:
        return deepcopy(rows[0]), []
    identity_rows = [row for row in rows if not is_noncompound(row)] or rows
    canonical_counts = Counter(canonical_name(row) for row in identity_rows)
    canonical = canonical_counts.most_common(1)[0][0]
    representative = max(rows, key=lambda row: representative_score(row, canonical))
    merged = deepcopy(representative)
    merged["compound_name"] = canonical

    # Prefer a real ground-state/stable structure over a path/TS coordinate.
    structured = [
        row for row in rows
        if compact(row["structure_file"]) and not is_noncompound(row)
    ]
    if structured:
        structure_row = max(
            structured, key=lambda row: representative_score(row, canonical)
        )
        merged["structure_file"] = structure_row["structure_file"]
        merged["structure_provenance"] = structure_row["structure_provenance"]
    else:
        merged["structure_file"] = ""
        merged["structure_provenance"] = ""

    for field in (
        "method", "software", "basis_set", "relativistic_treatment",
        "active_space_orbital_description", "active_space_protocol",
        "multiplicities_studied", "nroots_per_mult", "point_group",
        "geometry_source", "correlation_correction",
    ):
        merged[field] = "; ".join(unique_values(rows, field))

    # These flags remain schema-valid yes/no values after condensation.
    for field in ("soc_included", "ss_included"):
        values = {value.casefold() for value in unique_values(rows, field)}
        if "yes" in values:
            merged[field] = "yes"
        elif "no" in values:
            merged[field] = "no"

    pairs = Counter(
        (compact(row["active_space_nel"]), compact(row["active_space_norb"]))
        for row in rows
        if compact(row["active_space_nel"]) or compact(row["active_space_norb"])
    )
    if pairs:
        primary_pair = max(
            pairs,
            key=lambda pair: (
                pair == (
                    compact(representative["active_space_nel"]),
                    compact(representative["active_space_norb"]),
                ),
                pairs[pair],
                pair,
            ),
        )
        merged["active_space_nel"], merged["active_space_norb"] = primary_pair
        if len(pairs) > 1:
            compared = ", ".join(
                f"({nel},{norb})" for nel, norb in sorted(pairs)
            )
            merged["active_space_protocol"] = append_unique_sentence(
                merged["active_space_protocol"],
                f"Source compared method/state-specific active spaces {compared}",
            )

    merged["electronic_structure_description"] = labeled_merge(
        rows, "electronic_structure_description"
    )
    merged["Other"] = labeled_merge(rows, "Other")

    source_notes = unique_values(rows, "notes")
    merged["notes"] = source_notes[0] if source_notes else ""
    merged["notes"] = append_unique_sentence(
        merged["notes"],
        f"{AUDIT_MARKER}: condensed {len(rows)} over-split source rows into "
        "one compound row; method, state, active-space, and numerical variants "
        "are retained in the merged fields",
    )

    removed = [row for row in rows if row["entry_id"] != merged["entry_id"]]
    return merged, removed


def append_logs(
    retained: list[tuple[dict[str, str], list[dict[str, str]]]],
    existing: list[dict[str, str]] | None = None,
) -> None:
    if existing is None:
        fields, existing = load_csv(EXTRACTIONS)
    else:
        fields, _ = load_git_csv(SOURCE_EXTRACTIONS_SPEC)
    if any(AUDIT_MARKER in row.get("reasoning", "") for row in existing):
        raise RuntimeError("condensation audit records already exist; refusing to append twice")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    additions: list[dict[str, str]] = []
    for survivor, removed in retained:
        if not removed:
            continue
        additions.append({
            "timestamp": now,
            "key": survivor["entry_id"],
            "doi": survivor["reference_doi"],
            "action": "condense-rows",
            "result": "retained",
            "reasoning": (
                f"{AUDIT_MARKER}: retained {survivor['entry_id']} as the one "
                f"compound-level row and merged {len(removed)} over-split "
                "method/state/table/path rows into its descriptive fields."
            ),
        })
        for row in removed:
            additions.append({
                "timestamp": now,
                "key": row["entry_id"],
                "doi": row["reference_doi"],
                "action": "deduplicate-row",
                "result": f"merged_into:{survivor['entry_id']}",
                "reasoning": (
                    f"{AUDIT_MARKER}: removed over-split row "
                    f"{row['entry_id']} ({compact(row['compound_name'])}); its "
                    "source-explicit method/state/active-space/results were "
                    f"preserved in {survivor['entry_id']}."
                ),
            })
    with EXTRACTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(additions)


def write_database(fields: list[str], rows: list[dict[str, str]]) -> None:
    with DATABASE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--from-head",
        action="store_true",
        help="rebuild from mining commit 9ed7907",
    )
    sources.add_argument(
        "--onto-main",
        action="store_true",
        help="apply the condensation to the current origin/main snapshot",
    )
    parser.add_argument("--show-groups", type=int, default=30)
    args = parser.parse_args()

    if args.onto_main:
        fields, current = load_git_csv(MAIN_SPEC)
        _, source_extractions = load_git_csv(MAIN_EXTRACTIONS_SPEC)
    elif args.from_head:
        fields, current = load_git_csv(SOURCE_SPEC)
        _, source_extractions = load_git_csv(SOURCE_EXTRACTIONS_SPEC)
    else:
        fields, current = load_csv(DATABASE)
        source_extractions = None
    base = load_base()
    base_ids = {row["entry_id"] for row in base}
    _, source = load_git_csv(SOURCE_SPEC)
    target_ids = {
        row["entry_id"] for row in source if row["entry_id"] not in base_ids
    }
    current_ids = {row["entry_id"] for row in current}
    missing_targets = target_ids - current_ids
    if (args.from_head or args.onto_main) and missing_targets:
        raise RuntimeError(
            f"source is missing {len(missing_targets)} mining-commit entries"
        )
    existing = [row for row in current if row["entry_id"] not in target_ids]
    added = [row for row in current if row["entry_id"] in target_ids]

    groups = build_groups(added)
    retained: list[tuple[dict[str, str], list[dict[str, str]]]] = [
        merge_group(group) for group in groups
    ]
    survivors = [row for row, _ in retained]
    removed_count = sum(len(removed) for _, removed in retained)
    affected_papers = len({
        row["reference_doi"] for row, removed in retained if removed
    })
    print(f"untouched rows: {len(existing)}")
    print(f"added rows before: {len(added)}")
    print(f"compound rows after: {len(survivors)}")
    print(f"rows condensed: {removed_count}")
    print(f"papers with condensation: {affected_papers}")
    print(f"total database rows after: {len(existing) + len(survivors)}")

    largest = sorted(
        ((len(removed) + 1, row, removed) for row, removed in retained if removed),
        reverse=True,
        key=lambda item: item[0],
    )
    for size, row, _ in largest[: args.show_groups]:
        print(
            f"{size:4d} -> 1  {row['reference_doi']}  "
            f"{row['compound_name']}  [{row['entry_id']}]"
        )

    if not args.apply:
        return
    append_logs(retained, source_extractions)
    write_database(fields, existing + survivors)
    print("applied database condensation and appended extraction audit records")


if __name__ == "__main__":
    main()
