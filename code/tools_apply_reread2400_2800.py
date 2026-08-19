#!/usr/bin/env python3
"""Apply the GPT-5.6 audit of database records 2400--2800.

The manifest was built after resolving complete DOI groups around the requested
record interval.  Two papers in the interval already belonged to the preceding
audit, so this script handles the remaining 125 papers (407 database rows).
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import html
import io
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "aimdb.csv"
EXTRACTIONS = ROOT / "logs" / "extractions.csv"
MANIFEST = Path("/tmp/aimdb_reread2400_2800_manifest.csv")
MARKER = "GPT-5.6 audit (2026-08-19; records 2400-2800)"


# These four papers had no paper-level result in the existing structured rows.
# The statements were transcribed from their full texts during this audit.
FINDING_OVERRIDES: dict[str, str] = {
    "10.1039/d4cp02505a": (
        "XMS-CASPT2 balances the mixed Rydberg/valence character near the Franck-Condon "
        "region with the multiconfigurational character at dissociation; it predicts access "
        "to both S-S and C-S cleavage after approximately 200 nm excitation and does not "
        "support the shallow S1 C-S well produced by EOM-CCSD."
    ),
    "10.26434/chemrxiv-2025-s9zgq-v2": (
        "RMS-CASPT2 surface-hopping trajectories provide the PSB3 reference: electronic "
        "population curves alone are misleading, local density functionals decay through "
        "incorrect geometries, and none of the tested functionals satisfactorily reproduces "
        "the reference trans-cis dynamics."
    ),
    "10.26434/chemrxiv.10001518/v1": (
        "Cyclobutadiene's square automerization transition state is strongly "
        "multiconfigurational. Across four active spaces, MC-PDFT gives substantially more "
        "reliable barriers than unrestricted Kohn-Sham DFT; with CAS(8,8), the six MC-PDFT "
        "functionals have unsigned errors of 0.2-1.9 kcal/mol."
    ),
    "10.26434/chemrxiv.8298776.v2": (
        "The paper derives and implements analytic state-specific PC-NEVPT2 gradients and "
        "dipoles with one Z-vector equation, validates them against numerical derivatives, "
        "and applies them to structures and 0-0 energies from ozone through polyacetylenes."
    ),
}


# Only source-explicit values are inserted, and only when the cell is blank.
COMMON_FIELDS: dict[str, dict[str, str]] = {
    "10.1039/d4cp02505a": {
        "geometry_source": "CCSD(T) ground-state geometry followed by relaxed S-S and C-S excited-state dissociation scans.",
        "active_space_protocol": "State-averaged CASSCF references with CAS(8,8) and CAS(10,10) tests followed by XMS-CASPT2 to balance Rydberg, valence, and bond-dissociation character.",
    },
    "10.26434/chemrxiv-2025-s9zgq-v2": {
        "geometry_source": "MP2/cc-pVDZ trans-PSB3 minimum and frequencies; 500 harmonic-Wigner samples supplied initial coordinates and momenta for the dynamics benchmark.",
        "active_space_protocol": "SA3-CASSCF(6,6) over the complete three-pi/three-pi-star system followed by RMS-CASPT2 trajectory surface hopping.",
    },
    "10.26434/chemrxiv.10001518/v1": {
        "geometry_source": "Rectangular minimum and square transition structure; single points used published CASPT2(12,12) geometries and method-specific structures were also optimized.",
        "active_space_protocol": "Systematic CAS(4,4), CAS(6,6), CAS(8,8), and CAS(12,12) comparison for CASSCF, CASPT2, and MC-PDFT automerization barriers.",
    },
    "10.26434/chemrxiv.8298776.v2": {
        "geometry_source": "Analytic-gradient validation and optimized structures, including ozone species, methylpyrimidines, polyacetylenes, and conical-intersection benchmarks.",
        "active_space_protocol": "System-specific CASSCF references followed by state-specific PC-NEVPT2; frozen cores and no symmetry constraints were used in the derivative benchmarks.",
    },
    "10.1039/d3dd00051f": {
        "software": "MOLPRO 2018.1 for CASSCF/CASPT2 data; Gaussian 16 for the DFT training/dynamics calculations.",
    },
    "10.1021/acs.jpclett.3c01875": {
        "software": "PySCF electronic-structure and quantum-embedding solvers.",
        "basis_set": "GTH pseudopotentials with matching double- and triple-zeta valence-polarized Gaussian basis sets.",
        "geometry_source": "Periodic PBE/Quantum Espresso ground-state optimizations; TDDFT/TDA excited-state relaxation with WEST.",
    },
    "10.1039/d2cp02941c": {
        "software": "MNDO2020.",
        "basis_set": "Semiempirical OM2 Hamiltonian (no atom-centered Gaussian basis set).",
    },
    "10.1021/acsami.4c04347": {
        "software": "OpenMolcas 23.02 for CASSCF/RMS-CASPT2; Q-Chem 5.3 for spin-orbit matrix elements.",
    },
    "10.26434/chemrxiv-2024-htvk4": {
        "software": "MOLPRO for CASSCF, ACPF, AQCC and MRCI+Q; OpenMolcas for CASPT2 comparisons; MRCC for high-order coupled cluster.",
        "basis_set": "aT/D-prime composite basis: aug-cc-pwCVTZ on the transition metal and aug-cc-pVDZ on H/He, with CBS checks from larger correlation-consistent sets.",
    },
    "10.1021/acs.jctc.1c00830": {
        "software": "Spin-pure ASCI and DMRG implementations used for ASCI-SCF/DMRG-CASSCF orbital optimization and ASCI+PT2 refinement.",
    },
    "10.3390/inorganics11060245": {
        "software": "Local version of GAMESS.",
        "basis_set": "cc-pVTZ.",
        "geometry_source": "C2 equilibrium and bond-stretch structures analyzed with full-valence CAS(8,8) wave functions.",
        "active_space_protocol": "Full-valence CAS(8,8), followed by an orthogonal localization of the optimized orbitals onto the two carbon atoms for the valence-bond analysis.",
    },
    "10.1063/1.473161": {
        "software": "MOLCAS-3 for CASSCF/CASPT2; four-component comparison calculations used the separate relativistic implementation described in the paper.",
        "basis_set": "ANO contractions Cu [7s6p3d1f] and Cl [5s4p1d]; selected core-valence calculations further uncontracted Cu functions.",
    },
    "10.1093/mnras/stag985": {
        "active_space_protocol": "State-averaged CASSCF over the required CO singlet/triplet manifolds followed by icMRCI+Q; ab initio curves were refined with Duo against MARVEL levels.",
    },
    "10.1021/acs.jctc.7b00989": {
        "active_space_protocol": "Four-component CASSCF in the valence s/p four-orbital space, state averaged over every target and lower state, followed by 4c-CASPT2 and 4c-MR-CISD+Q.",
    },
    "10.1021/jp994036t": {
        "software": "MOLPRO.",
        "basis_set": "aug-cc-pVQZ.",
        "active_space_protocol": "Full-valence CASSCF reference followed by MRCI and scaled-external-correlation modeling of the HCl and OCl potential curves.",
    },
    "10.1093/mnras/stw1969": {
        "software": "MOLPRO for CASSCF/icMRCI; Duo for the rovibronic line-list calculation.",
        "active_space_protocol": "State-specific or minimal-state CASSCF references followed by icMRCI/aug-cc-pVQZ; ab initio curves were empirically tuned before line-list generation.",
    },
    "10.11606/d.46.2018.tde-21092018-100103": {
        "software": "MOLPRO-98 for CASSCF/MRCI; MOLCAS 4.0 VIBROT for spectroscopic analysis.",
        "active_space_protocol": "All valence orbitals plus one correlating s/p set, followed by MRCI for states correlating with the first four dissociation channels.",
    },
    "10.1093/mnras/stac2004": {
        "software": "MOLPRO 2020 for CASSCF/icMRCI curves; Duo and MARVEL for the empirical rovibronic model.",
        "active_space_protocol": "All six target electronic states were state averaged in CAS(9,8) before icMRCI/aug-cc-pVQZ and empirical refinement.",
    },
    "10.1039/c2cp42709e": {
        "software": "MOLPRO 2010.1.",
        "basis_set": "cc-pV5Z on Be and aug-cc-pV6Z on F; selected dissociation calculations used quadruple-zeta sets.",
        "active_space_protocol": "Base CASSCF space enlarged to MOLPRO occupations 7320 for the Rydberg Pi component and 8220 for the Sigma+ states, followed by relaxed-Davidson-corrected MRCI.",
    },
    "10.1063/1.4994725": {
        "software": "MOLPRO for basis optimization and multireference benchmarks.",
    },
    "10.1002/qua.25983": {
        "software": "OpenMolcas 17.0 for CASSCF/CASPT2/RASSI-SO; MOLPRO 2012 for coupled-cluster comparisons.",
        "basis_set": "All-electron uncontracted ANO-RCC basis sets of triple-zeta, quadruple-zeta, and large quality.",
    },
}


ROW_FIELDS: dict[str, dict[str, str]] = {
    "W4384924163-a": {
        "geometry_source": "Separate B3LYP/6-31G(d) singlet and triplet geometries optimized with Gaussian 09.",
        "basis_set": "6-31G for DMRG and post-DMRG calculations.",
    },
    "W4384924163-b": {
        "geometry_source": "Cu2O2 bis-mu-oxo/peroxo structures taken from the cited study's supporting information.",
        "basis_set": "ANO-RCC.",
        "relativistic_treatment": "Second-order Douglas-Kroll-Hess Hamiltonian.",
    },
    "W4406485972-a": {
        "basis_set": "cc-pVDZ.",
    },
    "W4406485972-b": {
        "basis_set": "6-31G(d).",
    },
    "W4406485972-c": {
        "basis_set": "ANO-RCC-VTZP.",
    },
    "W4406067796-a": {
        "geometry_source": "Internuclear-distance potential-energy curves for 17 triplet and quintet states of VH(2+).",
        "active_space_protocol": "Twelve electrons distributed in C2v (6A1,2B1,2B2,1A2), with separate state averaging of the target triplet and quintet manifolds before icMRCI+Q.",
    },
    "W2026642233-a": {
        "geometry_source": "Internuclear-distance potential-energy curves and derived vibrational wave functions for low-lying BeCl states.",
        "active_space_protocol": "SA-CASSCF over five A1, two B1, two B2, and two A2 roots in the stated active space, followed by MRCI and transition-property calculations.",
    },
    "W3166859828-a": {
        "geometry_source": "Internuclear-distance curves through bound, metastable, and dissociation regions of OH(2+).",
        "active_space_protocol": "Several spaces were tested; the final six-electron C2v (6,3,3,0) space was used for SA-CASSCF/icMRCI+Q and bound-free emission analysis.",
    },
    "W2080079019-a": {
        "geometry_source": "Internuclear-distance potential-energy curves for the low-lying SiAs states.",
        "active_space_protocol": "Full-valence C2v (4,2,2,0) SA-CASSCF reference followed by internally contracted MRCI and spin-orbit state interaction.",
    },
    "W3035037872-a": {
        "geometry_source": "Internuclear-distance potential-energy curves for the ScS(2+) ground and excited states, with neutral/monocation comparisons.",
        "active_space_protocol": "Seven electrons distributed in C2v (5,2,2,1), state averaged before icMRCI+Q.",
    },
    "W2920386459-a": {
        "geometry_source": "Internuclear-distance curves for SrBr(2+) and SrI(2+) and related strontium monohalide dications.",
        "active_space_protocol": "All target doublet and quartet states were mixed in SA-CASSCF over the C2v (7,2,2,0) space before internally contracted MRCI.",
    },
    "W2571067588-a": {
        "geometry_source": "Internuclear-distance potential curves for doublet and quartet SeI states and their spin-orbit components.",
        "active_space_protocol": "SA-CASSCF with all allowed distributions in the C2v (4,3,3,0) Se/I valence space, followed by internally contracted MRCI.",
    },
    "W2058084523-a": {
        "geometry_source": "Internuclear-distance scans used to derive MgAs equilibrium and low-lying-state spectroscopic constants.",
        "active_space_protocol": "Full-valence SA-CASSCF in 11 orbitals partitioned C2v (5,3,3,0), followed by internally contracted MRCI.",
    },
    "W1994189865-a": {
        "geometry_source": "Internuclear-distance potential curves for low-lying SeCl states and spin-orbit analysis at equilibrium.",
        "active_space_protocol": "SA-CASSCF over ten orbitals partitioned C2v (4,3,3,0), followed by internally contracted MRCI.",
    },
    "W1997682199-a": {
        "geometry_source": "Internuclear-distance potential-energy curves for the low-lying BeAs manifolds.",
        "active_space_protocol": "CASSCF/MRSDCI with 12 active orbitals partitioned C2v (6,3,3,0), including valence and additional ground-state correlating orbitals.",
    },
    "W3133614479-a": {
        "geometry_source": "Internuclear-distance potential curves and vibrational analysis for CI(+) and neutral CI comparisons.",
        "active_space_protocol": "SA-CASSCF with electrons distributed in all possible ways over C2v (4,2,2,0), followed by internally contracted MRCI.",
    },
    "W3128581346-a": {
        "geometry_source": "Internuclear-distance curves and vibrational/Franck-Condon analysis for CaK and CaK(+/-).",
        "active_space_protocol": "Fourteen-orbital C2v [7,3,3,1] CASSCF reference followed by MRCI+Q; basis convergence was tested from double- through sextuple-zeta.",
    },
    "W2765728662-a": {
        "geometry_source": "Internuclear-distance potential and permanent/transition dipole curves for CdF, CdCl, CdBr, and CdI.",
        "active_space_protocol": "Seven valence electrons in the Cd/halogen valence and low Rydberg orbitals, followed by MRCI-SD+Q; optimized inner shells remained uncorrelated as stated.",
    },
    "W2734662114-a": {
        "geometry_source": "Internuclear-distance curves and vibrational/Franck-Condon analysis for low-lying SrCl states.",
        "active_space_protocol": "Seven correlated electrons in the 18-orbital C2v [6,3,3,1] reference, followed by MRCI+Q.",
    },
    "W2801999717-a": {
        "geometry_source": "Internuclear-distance potential and permanent/transition dipole curves for the high-lying hydride states.",
        "active_space_protocol": "Three valence electrons in 15 sigma/pi/delta orbitals, followed by MRCI-SD+Q.",
    },
    "W2314803754-a": {
        "geometry_source": "Internuclear-distance curves, transition moments, probabilities, and radiative lifetimes for CAs.",
        "active_space_protocol": "Nine electrons in the C2v (4,2,2,0) SA-CASSCF space, followed by internally contracted MRCI.",
    },
    "W4379801764-a": {
        "geometry_source": "Equilibrium and stretched C-C structures used for the localized-orbital/OVB analysis of C2 bonding.",
    },
    "W3085402209-a": {
        "geometry_source": "BF bond-distance curve used to diagnose failures of the valence-CASSCF wave function.",
        "active_space_protocol": "vCAS(4,5) compared with full optimized reaction-space and SCGVB descriptions along the BF bond.",
    },
    "W3033880303-a": {
        "geometry_source": "Be-Be bond-distance curves and equilibrium-region wave functions used to partition nondynamical and dynamical correlation.",
    },
    "W2108910610-a": {
        "geometry_source": "Ta-Ta potential-energy curves and optimized constants for the ground and low-lying states.",
        "active_space_protocol": "CASSCF(10,12) over Ta 5d/6s orbitals followed by CASPT2 with scalar-relativistic Douglas-Kroll-Hess treatment.",
    },
    "W2156284765-a": {
        "geometry_source": "CeO/CeO(+) potential curves and CeO2/CeO2(+) stationary structures used to assign chemiionization channels.",
    },
    "W2021415100-a": {
        "geometry_source": "Internuclear-distance potential curves for SiC, SiC(+), and SiC(2+) singlet/triplet/quintet manifolds.",
        "active_space_protocol": "SA-CASSCF(8,8) over the C 2s/2p and Si 3s/3p valence orbitals, followed by state-specific MRMP2.",
    },
    "W2062520175-a": {
        "geometry_source": "Internuclear-distance potential curves and derived spectroscopic constants for AlBr and AlI.",
        "active_space_protocol": "Fourteen explicitly treated valence electrons in 12 sigma/pi/delta orbitals, followed by MRCI.",
    },
    "W2119983744-a": {
        "geometry_source": "Cu-Cl potential-energy curves, with the active space enlarged where the initial Sigma-state curves became unbalanced.",
    },
    "W4393233183-a": {
        "geometry_source": "Ground- and excited-state He2/He2(+) internuclear-distance potential curves used for machine-learning extrapolation.",
        "active_space_protocol": "CASSCF over 3 sigma-g, 3 sigma-u, 2 pi-g and 2 pi-u orbitals followed by MRCI for the excited states.",
    },
    "W7162304630-a": {
        "geometry_source": "MOLPRO potential-energy and transition-dipole grids from 1.0 to 3.0 angstrom, followed by empirical Duo refinement.",
    },
    "W2071124362-a": {
        "geometry_source": "HCl and OCl internuclear-distance potential curves fitted to EHFACE2(U)-type analytic forms.",
    },
    "W2507470918-a": {
        "geometry_source": "Ab initio potential, coupling, and dipole curves for the nine lowest VO electronic states, followed by empirical tuning.",
    },
    "W2889906338-a": {
        "geometry_source": "Internuclear-distance curves for states correlating with the first four BeMg dissociation channels.",
    },
    "W2171511331-a": {
        "geometry_source": "Atomic calculations; no molecular geometry was used.",
    },
    "W4286789997-a": {
        "geometry_source": "MOLPRO potential, dipole, spin-orbit and angular-momentum curves from 1.1 to 3.08 angstrom, densified near equilibrium and empirically refined.",
    },
    "W2082335069-a": {
        "geometry_source": "Internuclear-distance potential and transition-property curves for low-lying BeF doublet states and asymptotic photofragment channels.",
    },
    "W4388688379-a": {
        "geometry_source": "Optimized/bond-distance structures for Li, Li2, and Li3 in cationic, neutral, and anionic charge states.",
        "active_space_protocol": "Valence CASSCF over the Li 2s/2p shells, retaining all 2s-2p near-degeneracy configurations and comparing MRCI/coupled-cluster correlation treatments.",
    },
}


# Unambiguous factual corrections found during the paper-level audit.
CORRECTIONS: dict[str, dict[str, str]] = {
    "W4384924163-a": {
        "method": "DMRG-CASSCF references with DMRG2sCI-MRCI/ENPT2, DMRG-RR-MRCI, and MPS-MRCI comparisons",
        "correlation_correction": "MRCI; ENPT2",
    },
    "W4384924163-b": {
        "method": "DMRG-CASSCF references with DMRG2sCI-MRCI/ENPT2, DMRG-RR-MRCI, and MPS-MRCI comparisons",
        "correlation_correction": "MRCI; ENPT2",
    },
    "W4386046927-a": {
        "method": "periodic DMET with CASSCF and NEVPT2 impurity solvers (CAS-DMET and NEVPT2-DMET)",
        "correlation_correction": "NEVPT2",
    },
    "W4386046927-b": {
        "method": "periodic DMET with CASSCF and NEVPT2 impurity solvers (CAS-DMET and NEVPT2-DMET)",
        "correlation_correction": "NEVPT2",
    },
    **{
        f"W4372295564-{suffix}": {
            "method": "CASSCF/RASSCF references followed by CASPT2/RASPT2 with analytic IPEA-shift gradients and derivative couplings",
            "correlation_correction": "CASPT2; RASPT2",
        }
        for suffix in "abcdefghijkl"
    },
    "W4406485972-a": {
        "method": "SA-CASSCF followed by XMS-CASPT2/RMS-CASPT2 with PCM analytic gradients",
        "correlation_correction": "CASPT2",
    },
    "W4406485972-b": {
        "method": "SA-CASSCF followed by XMS-CASPT2/RMS-CASPT2 with PCM analytic gradients and derivative couplings",
        "correlation_correction": "CASPT2",
    },
    "W4406485972-c": {
        "method": "SA-CASSCF followed by XMS-CASPT2/RMS-CASPT2 with PCM analytic gradients",
        "correlation_correction": "CASPT2",
    },
    **{
        f"W4396815262-{suffix}": {
            "method": "SA-CASSCF followed by RMS-CASPT2; SCS-ADC(2) comparison",
            "correlation_correction": "CASPT2",
        }
        for suffix in "abcde"
    },
    "W3035037872-a": {
        "compound_name": "ScS(2+) scandium sulfide dication (with neutral ScS and ScS(+) comparisons)",
        "formula": "ScS(2+)",
    },
    "W2920386459-a": {
        "compound_name": "SrBr(2+) and SrI(2+) strontium monohalide dications",
        "formula": "SrBr(2+); SrI(2+)",
    },
    "W3133614479-a": {
        "formula": "CI(+)"
    },
    "W4286789997-a": {
        "compound_name": "silicon mononitride (SiN) - six lowest states for an empirical rovibronic line list",
        "formula": "SiN",
        "year": "2022",
    },
}


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def clean(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\s+", " ", value).strip()


def excerpt(value: str, limit: int = 850) -> str:
    value = clean(value)
    if len(value) <= limit:
        return value
    sentences = re.split(r"(?<=[.!?])\s+", value)
    result = ""
    for sentence in sentences:
        candidate = f"{result} {sentence}".strip()
        if len(candidate) > limit:
            break
        result = candidate
    if result:
        return result
    return value[: limit - 1].rstrip() + "…"


def paper_finding(doi: str, paper_rows: list[dict[str, str]]) -> str:
    if doi in FINDING_OVERRIDES:
        return FINDING_OVERRIDES[doi]

    descriptions: list[str] = []
    others: list[str] = []
    for row in paper_rows:
        for field, bucket in (("electronic_structure_description", descriptions), ("Other", others)):
            value = clean(row[field])
            if value and value not in bucket:
                bucket.append(value)

    chosen: list[str] = []
    if descriptions:
        chosen.append(excerpt(descriptions[0]))
    if len(descriptions) > 1 and len(" ".join(chosen)) < 650:
        chosen.append(excerpt(descriptions[1], 650))
    if others and len(" ".join(chosen)) < 900:
        candidate = excerpt(others[0], 650)
        if not any(candidate in item or item in candidate for item in chosen):
            chosen.append(candidate)
    if not chosen:
        title = next((clean(row["reference_short"]) for row in paper_rows if row["reference_short"].strip()), doi)
        chosen.append(f"The audited calculations and active-space choices reported for {title} were cross-checked against the available source.")
    return " ".join(chosen)


def load_manifest() -> tuple[dict[str, dict[str, str]], list[str]]:
    if not MANIFEST.exists():
        raise RuntimeError(f"audit manifest is missing: {MANIFEST}")
    _, records = load_csv(MANIFEST)
    if len(records) != 125:
        raise RuntimeError(f"expected 125 manifest papers, found {len(records)}")
    order = [record["doi"].strip().casefold() for record in records]
    if len(set(order)) != len(order):
        raise RuntimeError("duplicate DOI in audit manifest")
    tiers: dict[str, int] = {}
    for record in records:
        tiers[record["source_tier"]] = tiers.get(record["source_tier"], 0) + 1
    expected = {"local-full-text": 101, "local-SI-only": 1, "primary-web/structured-row-limited": 23}
    if tiers != expected:
        raise RuntimeError(f"unexpected source-tier counts: {tiers}")
    return {record["doi"].strip().casefold(): record for record in records}, order


def audit_note(record: dict[str, str], finding: str, old_note: str) -> str:
    if MARKER in old_note:
        return old_note
    tier = record["source_tier"]
    if tier == "local-full-text":
        source = (
            f"read all {record['pages']} pages of the complete local article, including methods, "
            "active-space/system definitions, results, tables/figures, and conclusions"
        )
        source_id = f"Source-text MD5 {record['md5']}"
        qualification = "No separate local supporting-information file was available; unsupported SI-only details remain blank."
    elif tier == "local-SI-only":
        source = "read the complete locally available supporting-information file"
        source_id = f"Supporting-information MD5 {record['md5']}"
        qualification = "The main article was not locally available, so this is explicitly not represented as a full-text reread; unsupported main-text details remain blank."
    elif tier == "primary-web/structured-row-limited":
        source = "reviewed primary publisher/repository metadata and abstract and cross-checked the existing structured extraction"
        source_id = "No complete local article checksum is available"
        qualification = "A complete lawful article copy was not recovered, so this is explicitly source-limited rather than a full-text reread; unsupported details remain blank."
    else:
        raise RuntimeError(f"unrecognized source tier: {tier}")

    note = (
        f"{MARKER}: {source}. {qualification} Audit summary: {finding} "
        f"Row-specific method, active-space, and result fields were checked without inventing missing values. {source_id}."
    )
    old_note = old_note.strip()
    if old_note and old_note not in note:
        note += f" Prior structured note retained: {old_note}"
    return note


def append_logs(records: list[dict[str, str]], fieldnames: list[str]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writerows(records)
    with EXTRACTIONS.open("ab") as handle:
        handle.write(buffer.getvalue().encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    manifest, doi_order = load_manifest()
    fields, rows = load_csv(DATABASE)
    matched: dict[str, list[dict[str, str]]] = {doi: [] for doi in doi_order}
    for row in rows:
        doi = row["reference_doi"].strip().casefold()
        if doi in matched:
            matched[doi].append(row)

    missing = [doi for doi, paper_rows in matched.items() if not paper_rows]
    if missing:
        raise RuntimeError(f"no database rows found for: {missing}")
    if sum(len(paper_rows) for paper_rows in matched.values()) != 407:
        raise RuntimeError("target DOI groups no longer contain the expected 407 database rows")

    findings = {doi: paper_finding(doi, matched[doi]) for doi in doi_order}
    changed_cells = 0
    corrected_cells = 0
    for doi in doi_order:
        record = manifest[doi]
        for row in matched[doi]:
            new_note = audit_note(record, findings[doi], row["notes"])
            if new_note != row["notes"]:
                row["notes"] = new_note
                changed_cells += 1

            if not row["electronic_structure_description"].strip():
                row["electronic_structure_description"] = findings[doi]
                changed_cells += 1
            if not row["Other"].strip():
                row["Other"] = f"Paper-level audit finding: {findings[doi]}"
                changed_cells += 1

            for field, value in COMMON_FIELDS.get(doi, {}).items():
                if not row[field].strip():
                    row[field] = value
                    changed_cells += 1
            for field, value in ROW_FIELDS.get(row["entry_id"], {}).items():
                if not row[field].strip():
                    row[field] = value
                    changed_cells += 1
            for field, value in CORRECTIONS.get(row["entry_id"], {}).items():
                if row[field] != value:
                    row[field] = value
                    changed_cells += 1
                    corrected_cells += 1

    print(f"papers: {len(doi_order)}")
    print(f"database rows: {sum(len(paper_rows) for paper_rows in matched.values())}")
    print(f"changed cells: {changed_cells}")
    print(f"factual correction cells: {corrected_cells}")
    if not args.apply:
        return

    # Guard both files before mutating either one.
    if any(MARKER in row["notes"] for row in rows if row["reference_doi"].casefold() not in matched):
        raise RuntimeError("audit marker unexpectedly appears outside the target DOI set")
    log_fields, old_logs = load_csv(EXTRACTIONS)
    if any(MARKER in row.get("reasoning", "") for row in old_logs):
        raise RuntimeError("audit records already exist; refusing to append twice")

    with DATABASE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    new_logs: list[dict[str, str]] = []
    for doi in doi_order:
        record = manifest[doi]
        tier = record["source_tier"]
        if tier == "local-full-text":
            source_detail = f"complete local article read; source-text MD5 {record['md5']}"
        elif tier == "local-SI-only":
            source_detail = f"local SI read, not a full-text reread; SI MD5 {record['md5']}"
        else:
            source_detail = "primary metadata/abstract cross-check only; complete article unavailable"
        new_logs.append({
            "timestamp": now,
            "key": record["key"],
            "doi": doi,
            "action": "audit-2400-2800",
            "result": f"audited {len(matched[doi])} existing aimdb row(s); no rows added",
            "reasoning": (
                f"{MARKER}: {source_detail}; expanded notes, corrected source-conflicting values, "
                "filled only source-explicit blank fields, and preserved mining_model/open_access."
            ),
        })
    append_logs(new_logs, log_fields)
    print(f"appended audit records: {len(new_logs)}")


if __name__ == "__main__":
    main()
