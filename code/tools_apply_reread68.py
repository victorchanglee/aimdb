#!/usr/bin/env python3
"""Apply the 2026-08-19 comprehensive reread of under-documented rows."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "aimdb.csv"
EXTRACTIONS = ROOT / "logs" / "extractions.csv"
MARKER = "GPT-5.6 comprehensive reread (2026-08-19)"


PAPER_UPDATES: dict[str, dict[str, object]] = {
    "10.1016/s0301-0104(02)00966-7": {
        "pages": 10,
        "md5": "ea2e01c380cd9d75748e686e7a4b6f73",
        "notes": (
            f"{MARKER}: read all 10 article pages, including the computational and "
            "experimental methods, four tables, five figures, conclusions, and references. "
            "No supporting information is identified. The neutral calculation uses the full "
            "N(2s,2p)/S(3s,3p)/Cl(3s,3p) valence CAS(18,12); NSCl+ instead has 17 active "
            "electrons in the same 12 orbitals. The paper's MRCI(D) label denotes a restricted "
            "generator selection introduced to make the otherwise multi-billion-CSF cation "
            "calculations feasible, not a Davidson correction. Source PDF MD5 "
            "ea2e01c380cd9d75748e686e7a4b6f73."
        ),
        "fields": {
            "active_space_protocol": (
                "Neutral CAS(18,12); cation CAS(17,12) in the same full-valence orbital set. "
                "Cation calculations compare neutral orbitals, four-state-averaged orbitals "
                "within each Cs irrep, and individually optimized state orbitals; MRCI(D) uses "
                "only the lowest-excitation CAS CSFs as generators."
            ),
            "geometry_source": (
                "Neutral equilibrium geometry from a 35-point RHF/CASSCF/MRCI energy grid "
                "fitted to a fourth-degree surface; lowest cation-state geometries optimized "
                "at CASSCF/cc-pVQZ."
            ),
            "Other": (
                "cc-pVQZ/CASSCF-MRCI(D) vertical ionization energies with optimized cation "
                "orbitals (eV): (1)2A'=10.362, (2)2A'=11.153, (1)2A''=11.227, "
                "(3)2A'=13.394, (2)2A''=13.958, (4)2A'=14.202, (3)2A''=14.404, "
                "(4)2A''=15.042. The (3)2A' adiabatic ionization energy is "
                "13.798 +/- 0.002 eV."
            ),
        },
    },
    "10.1002/chem.200600228": {
        "pages": 12,
        "md5": "5ea3a0bb0e15b038127f01b13b02b3c1",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including every reported closed- "
            "and open-shell pathway, eight figures, computational methods, conclusions, "
            "and references. The article identifies online Supporting Information with "
            "coordinates, configurations, and pathway energetics, but that file is not in "
            "the local source set and was not used. CAS(8,11) describes the two 1,2-DPCB "
            "bond-stretch isomers and was checked against spaces through CAS(8,21); other "
            "structures/pathways use CAS(8,8), CAS(10,10), or the economical CAS(2,2) "
            "reference explicitly identified in Figure 1 and the text. Source PDF MD5 "
            "5ea3a0bb0e15b038127f01b13b02b3c1."
        ),
        "fields": {
            "method": "CASSCF/CASPT2; MR-ACPF; MR-ACPF-2",
            "software": "MOLCAS 6.0; ACES II; Gaussian 03; AMICA",
            "active_space_protocol": (
                "1,2-DPCB bond-stretch isomers: CAS(8,11), checked through CAS(8,21). "
                "Other minima use CAS(8,8), CAS(10,10), or CAS(2,2) as identified in "
                "Figure 1. Open-shell pathways use CASSCF(2,2)/ANO-S geometries, "
                "frequencies and IRCs followed by MR-ACPF/MR-ACPF-2 or occasional "
                "CASPT2 single points."
            ),
            "geometry_source": (
                "CASSCF/ANO optimized open-shell structures and pathway stationary points; "
                "the broader closed-shell PES was optimized primarily at B3LYP/cc-pVTZ "
                "with frequency and IRC verification."
            ),
        },
    },
    "10.1002/jcc.24897": {
        "pages": 8,
        "md5": "af757e87c388f26a0999fa0ef6c5e22d",
        "notes": (
            f"{MARKER}: read all 8 main-article pages, including the methods, all ten "
            "figures/energy profiles, mechanistic discussion, conclusions, and references. "
            "The online Supporting Information containing coordinates and optimized paths "
            "is identified by the article but is not in the local source set. The same "
            "CAS(10,8) is used throughout CASSCF and CASPT2; CASPT2 uses zero IPEA shift, "
            "a 0.2 Eh imaginary shift, Cholesky integrals, and PCM acetonitrile. Source PDF "
            "MD5 af757e87c388f26a0999fa0ef6c5e22d."
        ),
        "fields": {
            "software": "Gaussian 09; MOLCAS 8.0; ChemShell 3.5/DL-FIND",
            "basis_set": "6-31G*",
            "active_space_protocol": (
                "The same CAS(10,8) is used for SA-CASSCF geometries/paths and CASPT2 "
                "single points and vertical excitations. CASPT2 uses zero IPEA shift, a "
                "0.2 Eh imaginary shift, Cholesky-decomposed integrals, and PCM acetonitrile."
            ),
            "geometry_source": (
                "S0 and T1 minima/transition structures optimized with UB3LYP-D3/6-31G*; "
                "S0/S1 minima and minimum-energy paths with SA-CASSCF(10,8)/6-31G*; T1/S0 "
                "crossings with a penalty-function optimization in ChemShell/DL-FIND."
            ),
            "soc_included": "yes",
            "electronic_structure_description": (
                "CASPT2/PCM vertical energies at the Franck-Condon point: the two lowest "
                "1(npi*) states are 3.53 and 3.68 eV; bright 1(pipi*) lies 0.28 and 0.13 eV "
                "above them. The lowest 3(pipi*) state is 3.54 eV and the next 3(npi*) state "
                "is 0.17 eV higher. S1 favors barrierless [5+2], whereas T1 favors [2+2]."
            ),
            "Other": (
                "Preferred S1 [5+2] route is barrierless and exothermic by 27.4 kcal mol-1. "
                "The favored T1 [2+2] route forms the first bond over a 20.2 kcal mol-1 "
                "barrier, then crosses T1/S0 and closes on S0 over about 2.6 kcal mol-1. "
                "Competing T1 [5+2] can begin over a 2.2 kcal mol-1 barrier."
            ),
        },
    },
    "10.1021/acs.joc.6c01030": {
        "pages": 10,
        "md5": "cb00b7b847b7ecf4f5fa5664862fc99c",
        "notes": (
            f"{MARKER}: read all 10 main-article pages, including the complete results, "
            "five tables of state/kinetic data, reaction profiles, conclusions, and references. "
            "The article identifies Supporting Information, but it is not in the local source "
            "set and was not used. CASSCF(2,2) natural occupations on M06-2X geometries give "
            "diradical indices y0=0.60-0.72, and every functional tested favors the open-shell "
            "singlet over the closed-shell singlet and triplet. SP1 provides the largest sigma-"
            "closure barrier and longest predicted persistence; SP0 has no stable sigma product "
            "but instead undergoes rapid C-O cleavage. Source PDF MD5 "
            "cb00b7b847b7ecf4f5fa5664862fc99c."
        ),
        "fields": {
            "active_space_protocol": (
                "CASSCF(2,2) uses the pi-bonding HOMO and pi-antibonding LUMO of the "
                "1,3-diradical; natural occupations are evaluated on M06-2X/def2-TZVP "
                "geometries and compared with six broken-symmetry DFT functionals."
            ),
            "geometry_source": (
                "Diradicals, sigma products, transition states, and migration pathways "
                "optimized with M06-2X/def2-TZVP; CASSCF(2,2) electronic structures were "
                "evaluated on the M06-2X geometries."
            ),
        },
    },
    "10.1021/acs.cgd.5c00236": {
        "pages": 11,
        "md5": "5f0c8dbcaf488570a2588937e5d79716",
        "notes": (
            f"{MARKER}: read all 11 main-article pages, covering synthesis/structure, "
            "magnetometry, high-field EPR, DFT exchange calculations, the complete CASSCF/"
            "NEVPT2 analysis, conclusions, and references. The cited SI is not local. The "
            "multireference calculations deliberately magnetically dilute the Ni3Cr cluster "
            "as NiZn2Sc and Zn3Cr models and retain experimental X-ray coordinates. They "
            "support isotropic ferromagnetic Ni-Cr coupling and an S=9/2 cluster ground state; "
            "the weak cluster anisotropy is attributed to trigonal cancellation of the three "
            "Ni single-ion anisotropies. Source PDF MD5 5f0c8dbcaf488570a2588937e5d79716."
        ),
        "fields": {
            "software": "ORCA 5.0.4",
            "relativistic_treatment": "SOMF spin-orbit mean field",
            "soc_included": "yes",
            "active_space_protocol": (
                "State-averaged CASSCF on magnetic-dilution models: CAS(8,10) for NiZn2Sc "
                "and CAS(3,10) for Zn3Cr; SC-NEVPT2 dynamic correlation followed by "
                "SOMF/QDPT spin-orbit treatment and SINGLE_ANISO pseudospin analysis."
            ),
            "geometry_source": "Experimental X-ray coordinates; no geometry optimization for the CASSCF models.",
        },
    },
    "10.1021/acs.cgd.5c00337": {
        "pages": 13,
        "md5": "972f70b2d7a1f678f2271edd0590b59e",
        "notes": (
            f"{MARKER}: read all 13 main-article pages, including synthesis/crystallography, "
            "DC/AC magnetic measurements, relaxation fits, all Co-site ab initio results, "
            "conclusions, and references. The article's SI is not in the local set. Complex 1 "
            "contains two pseudo-octahedral and one pseudotetrahedral Co(II) sites and shows "
            "field-induced slow relaxation; all four Co(II) sites in complex 2 are pseudo-"
            "octahedral and show no slow relaxation. Calculated octahedral sites have large "
            "positive D and appreciable rhombicity, with substantial quantum-tunneling paths. "
            "Source PDF MD5 972f70b2d7a1f678f2271edd0590b59e."
        ),
        "fields": {
            "basis_set": "ZORA-def2-TZVPP(Co); ZORA-def2-TZVP(non-H); ZORA-def2-SVP(C,H)",
            "relativistic_treatment": "ZORA; RI-SOMF(1X) spin-orbit coupling",
            "soc_included": "yes",
            "active_space_protocol": (
                "CAS(7,5) spans the five Co 3d orbitals. All 10 quartet and 40 doublet "
                "roots were computed; RI-NEVPT2 and RI-SOMF(1X) precede SINGLE_ANISO "
                "analysis of two Kramers doublets per Co site."
            ),
            "nroots_per_mult": "10 quartets; 40 doublets",
            "geometry_source": (
                "Heavy-atom coordinates from X-ray structures; hydrogen positions optimized "
                "with BP86-D4 using the same ZORA-contracted basis hierarchy."
            ),
        },
    },
    "10.1021/acs.jctc.5c00190": {
        "pages": 12,
        "md5": "2507b46efb4ca344d2e8f3bf166eed6e",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including the ASCI algorithm, direct "
            "4-RDM-intermediate formulation, convergence tests, polyacene singlet-triplet "
            "benchmarks, Cr2 potential curves, summary, and references. The cited SI is not "
            "local. The implementation combines ASCI-SCF references with CASPT2-D and "
            "strongly contracted NEVPT2 while avoiding storage of the full four-particle RDM. "
            "Anthracene is an exact-CASSCF/ASCI reference check; Cr2 spaces extend through "
            "CAS(12,28), while the paper's largest demonstration is CAS(34,34). Source PDF "
            "MD5 2507b46efb4ca344d2e8f3bf166eed6e."
        ),
        "fields": {
            "active_space_protocol": (
                "ASCI determinant spaces and orbital optimization were converged before "
                "CASPT2-D or SC-NEVPT2; spin-adapted and non-spin-adapted variants and "
                "extrapolation against Epstein-Nesbet PT2 were compared."
            ),
            "geometry_source": (
                "Polyacene adiabatic singlet-triplet geometries and fixed-grid Cr2 bond "
                "distances used for method benchmarking as specified in the article."
            ),
        },
    },
    "10.1021/acs.jctc.5c01336": {
        "pages": 10,
        "md5": "0b19699b13866ac86c91381d7387adb3",
        "notes": (
            f"{MARKER}: read all 10 main-article pages, including the DMET+CASSI-SO "
            "formulation, R-DIIS/sR-DIIS algorithms, all three lanthanide benchmarks, error "
            "analysis, limitations, conclusions, and references. The cited SI is not local. "
            "DMET reproduces all-electron crystal-field splittings at much lower orbital cost, "
            "but the authors explicitly caution that a ground-state ROHF bath and localized "
            "embedded correlation can become insufficient for higher, delocalized excitations. "
            "Source PDF MD5 0b19699b13866ac86c91381d7387adb3."
        ),
        "fields": {
            "relativistic_treatment": "SFX2C-1e scalar relativity; SOMF Breit-Pauli spin-orbit coupling",
            "soc_included": "yes",
            "active_space_protocol": (
                "DMET cluster centered on lanthanide-localized orbitals with a ROHF bath; "
                "CAS(9,7) averages all 21 Dy sextets and CAS(11,7) all 35 Er quartets. "
                "CASSI-SO is tested with and without embedded-cluster NEVPT2."
            ),
            "geometry_source": "Molecular structures extracted from the cited experimental crystal structures.",
        },
    },
    "10.1021/acs.inorgchem.5c01823": {
        "pages": 12,
        "md5": "28e023c605fef8bdb5a15d315813d290",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including spin-state benchmarks, "
            "Fe-O scans, state-specific natural-orbital analyses, HAA reaction profiles, IBO "
            "electron/proton tracking, conclusions, and references. The cited SI is not local. "
            "The triplet Fe(IV)-oxo develops oxyl character and reacts by HAT (16.3 kcal/mol "
            "lowest barrier), whereas sextet Fe(III)-oxo lacks oxyl character and follows a "
            "higher-barrier PCET path (21.4 kcal/mol); quartet Fe(III) is an explicitly analyzed "
            "counterexample that can develop oxyl character. Source PDF MD5 "
            "28e023c605fef8bdb5a15d315813d290."
        ),
        "fields": {
            "active_space_protocol": (
                "Main spin-state spaces are CAS(12,14) for Fe(IV)-oxo and CAS(13,14) for "
                "Fe(III)-oxo; reduced CAS(10,13)/CAS(11,13) spaces follow Fe-O scans and "
                "CAS(12,15)/CAS(13,15) describe HAA transition states. NEVPT2 adds dynamic correlation."
            ),
            "geometry_source": (
                "PBE0-D3BJ/def2-TZVP(Fe, first sphere)/def2-SVP(rest), CPCM MeCN "
                "optimizations and IRCs; CASSCF/NEVPT2 single points use def2-TZVPP."
            ),
        },
    },
    "10.1021/acs.inorgchem.5c02059": {
        "pages": 19,
        "md5": "5bb91503578df9eead1360e579fa36fc",
        "notes": (
            f"{MARKER}: read all 19 main-article pages, covering synthesis, electrochemistry/"
            "spectroelectrochemistry, EPR, magnetism, P/S K-edge and Ru L3-edge XAS, DFT/TDDFT, "
            "CASSCF/CASPT2 details, conclusions, and references. The cited SI is not local. "
            "The first two oxidations of the redox-noninnocent complex are predominantly ligand "
            "centered. For doubly oxidized 3, CASPT2 confirms a singlet 8.9 kcal/mol below the "
            "triplet and a multiconfigurational singlet with 21% open-shell radical character; "
            "temperature-independent paramagnetism is assigned to SOC mixing rather than a "
            "thermally populated triplet. Source PDF MD5 5bb91503578df9eead1360e579fa36fc."
        ),
        "fields": {
            "soc_included": "no",
            "active_space_protocol": (
                "Initial CAS(2,2) ligand frontier space was enlarged to CAS(6,6), adding two "
                "Ru-ligand bonding/antibonding pairs; CASPT2 compared DFT-optimized singlet "
                "and triplet geometries of the doubly oxidized complex."
            ),
            "geometry_source": "DFT-optimized singlet and triplet structures used for CASSCF/CASPT2 single points.",
        },
    },
    "10.1021/acs.inorgchem.5c02481": {
        "pages": 11,
        "md5": "db9c1b2623b8697009c22603c505af78",
        "notes": (
            f"{MARKER}: read all 11 main-article pages, including MOF cluster construction, "
            "DFT/AIMD host-guest analysis, CASSCF-SO blockade barriers, trajectory sampling, "
            "spin-vibronic analysis, conclusions, and references. The cited SI is not local. "
            "Encapsulation in NU-1000, PCN-222-Zn, and MOF-177 preserves the dysprosocenium "
            "geometry and computed >1200 cm-1 barrier; dispersion dominates stabilization. "
            "NU-1000 attenuates the strongest spin-vibronic mode by about 30%, although the "
            "finite-cluster/AIMD sampling scope remains a model limitation. Source PDF MD5 "
            "db9c1b2623b8697009c22603c505af78."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": (
                "CAS(9,7) spans Dy 4f and includes all 21 sextets from the 6H, 6F, and 6P "
                "terms before RASSI-SO/SINGLE_ANISO; the same protocol is applied to the "
                "free ion, three full cluster models, and selected AIMD snapshots."
            ),
            "geometry_source": (
                "DFT-optimized finite MOF pore-cluster models; selected structures from "
                "AIMD trajectories (reported 1-16 ps sampling) for the NU-1000 guest."
            ),
        },
    },
    "10.1021/acs.inorgchem.5c02893": {
        "pages": 12,
        "md5": "903d29044d0b380a3e03da08c436d59e",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including synthesis/structures, "
            "spectroscopy, redox/deprotonation experiments, every active-space comparison, "
            "simulated spectra, conclusions, and references. The cited SI is not local. Neutral "
            "Cu corroles are predominantly open-shell singlets. The intense red/NIR Q bands of "
            "nitrophenyl anions require extended spaces containing meso-aryl acceptor orbitals "
            "and are assigned as corrole-to-aryl charge transfer; CAS(13,9) alone does not "
            "reproduce the hypercorrole band. Source PDF MD5 903d29044d0b380a3e03da08c436d59e."
        ),
        "fields": {
            "active_space_protocol": (
                "Cu-corrole spaces contain all five Cu 3d plus four Gouterman orbitals; "
                "reduced species expand CAS(13,9) to CAS(13,11) by adding two meso-aryl "
                "acceptors, with CAS(15,12) also tested. NEVPT2 energies/oscillator strengths "
                "were used for simulated spectra."
            ),
            "geometry_source": "PBE0/def2-SVP with def2-TZVP on Cu optimized geometries used for CASSCF/NEVPT2.",
        },
    },
    "10.1021/acs.inorgchem.5c03327": {
        "pages": 12,
        "md5": "6df4f64e71cdbc4f012a8070899f3501",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including the full DFT mechanism, "
            "nitrene-formation transition-state orbital analysis, both CASSCF imido wave "
            "functions, conclusions, and references. The cited SI is not local. Fe(III) has a "
            "35.9 kcal/mol nitrene-formation barrier, 14.5 kcal/mol above Fe(II), because its "
            "metal is displaced out of the porphyrin plane. The Fe(III)-imido doublet is strongly "
            "multiconfigurational; the Fe(II)-imido triplet is dominated (82%) by one configuration. "
            "Source PDF MD5 6df4f64e71cdbc4f012a8070899f3501."
        ),
        "fields": {
            "active_space_protocol": (
                "Balanced 13-orbital space includes Fe nonbonding 3d, Fe-N pi/sigma bonding "
                "and antibonding, equatorial bonding/antibonding, and five correlating Fe 4d "
                "orbitals; 9 electrons for Fe(III)-imido and 10 for Fe(II)-imido."
            ),
            "geometry_source": "State-specific CASSCF/def2-TZVPP analyses on DFT-B3LYP optimized imido geometries.",
        },
    },
    "10.1021/acs.inorgchem.5c03532": {
        "pages": 18,
        "md5": "86737f1b95cecb18b5bedba02ed9b1e9",
        "notes": (
            f"{MARKER}: read all 18 main-article pages, including the eight experimental "
            "di-mu-halide Dy2 complexes, 12 controlled models, single-ion anisotropy, exchange "
            "coupling, relaxation pathways, effective-barrier formulas, conclusions, and "
            "references. The cited SI is not local. The paper concludes that a simple F/Cl/Br/I "
            "ranking is not meaningful across structurally different complexes; controlled "
            "models instead identify fluoride as the strongest axial-field bridge and chloride "
            "as favorable among heavier halides. Source PDF MD5 86737f1b95cecb18b5bedba02ed9b1e9."
        ),
        "fields": {
            "relativistic_treatment": "DKH scalar relativity with RASSI spin-orbit coupling",
            "active_space_protocol": (
                "CAS(9,7) on each Dy(III), averaging 21 sextets before RASSI-SO and "
                "SINGLE_ANISO; POLY_ANISO combines local anisotropy with Dy-Dy exchange "
                "for eight crystallographic and 12 modeled dimers."
            ),
            "geometry_source": "Experimental crystal structures plus explicitly constructed ligand/halide substitution models.",
        },
    },
    "10.1021/acs.inorgchem.5c03903": {
        "pages": 11,
        "md5": "0387c935c808754f7a05ecc480f7d4f3",
        "notes": (
            f"{MARKER}: read all 11 main-article pages, covering all 20 pseudo-D5h/D6h Dy "
            "designs, DFT structures, CASSCF/RASSI-SO anisotropy, descriptor correlations, "
            "design criteria, conclusions, and references. The cited SI is not local. Barriers "
            "above 1200 cm-1 correlate most strongly with Dy displacement below 0.1 A from the "
            "equatorial plane, angular distortion below 2 degrees, and high axial/equatorial "
            "bond-length ratio; the analysis is a small, chemically diverse computed set rather "
            "than a trained predictive model. Source PDF MD5 0387c935c808754f7a05ecc480f7d4f3."
        ),
        "fields": {
            "active_space_protocol": (
                "CAS(9,7) spans Dy 4f and averages all 21 sextets before RASSI-SO/"
                "SINGLE_ANISO; a uniform protocol is used for correlation against geometric descriptors."
            ),
            "geometry_source": "DFT-optimized proposed pseudo-D5h and D6h Dy complexes.",
        },
    },
    "10.1021/acs.inorgchem.5c03929": {
        "pages": 5,
        "md5": "ae7531e63df6acd6d20a8d4645f102b6",
        "notes": (
            f"{MARKER}: read all 5 communication pages, including synthesis/structure, "
            "magnetometry, variable-temperature EPR, both active-space calculations, comparison "
            "with the phosphine analogue, conclusions, and references. The cited SI is not local. "
            "The AO basis is not stated in the main text and therefore remains unrecorded. "
            "CAS(13,8)/NEVPT2 gives D=-27 cm-1 and E/D=0.12 for quartet [(XantSb2)CoI2]; the "
            "larger |D| than the P analogue is assigned to both a genuine Sb heavy-atom effect "
            "and a smaller geometry contribution, while the sign/magnitude still require HFEPR/"
            "FIRMS confirmation. Source PDF MD5 ae7531e63df6acd6d20a8d4645f102b6."
        ),
        "fields": {
            "software": "ORCA",
            "soc_included": "yes",
            "active_space_protocol": (
                "Co-centered CAS(7,5) was expanded to CAS(13,8) by adding three Sb-donor/"
                "Co bonding combinations; NEVPT2 and spin-orbit ZFS calculations were "
                "compared with an isostructural P-donor model."
            ),
            "geometry_source": "Experimental X-ray geometry and a geometry-matched phosphorus analogue model.",
        },
    },
    "10.1021/acs.inorgchem.5c03943": {
        "pages": 17,
        "md5": "6a69e1ca9e3fb053a15726a90fda510f",
        "notes": (
            f"{MARKER}: read all 17 main-article pages, including peroxide-assisted assembly, "
            "crystallography/spectroscopy, DC/AC magnetism, relaxation models, Gd magnetocaloric "
            "data, DFT exchange, all CASSCF anisotropy calculations, summary, and references. "
            "The cited SI is not local. Dy4 and Er4 show field-induced SMM behavior; the Gd4 "
            "analogue is weakly antiferromagnetic with maximum -DeltaS=27.93 J K-1 kg-1 at 4 K, "
            "0-13 T. The calculations find weak antiferromagnetic exchange plus additional "
            "ferromagnetic dipolar contributions for Dy4. Source PDF MD5 "
            "6a69e1ca9e3fb053a15726a90fda510f."
        ),
        "fields": {
            "active_space_protocol": (
                "Dy CAS(9,7) includes 21 sextets, 224 quartets, and 490 doublets; Er "
                "CAS(11,7) includes 35 quartets and 112 doublets. RASSI-SO/SINGLE_ANISO "
                "provides local tensors and POLY_ANISO treats the tetranuclear coupling."
            ),
            "geometry_source": "Experimental X-ray structures used for the ab initio single-ion fragments.",
        },
    },
    "10.1021/acs.inorgchem.6c01030": {
        "pages": 16,
        "md5": "05954baf4b3166ca43b0705129567ed1",
        "notes": (
            f"{MARKER}: read all 16 main-article pages, including spin-state calibration, "
            "active-space expansions, full Co/Fe HAA surfaces, natural orbitals/spin densities, "
            "IBO electron tracking, conclusions, and references. The cited SI is not local. The "
            "mixed-valent Co diamond core has a valence-delocalized doublet with bridging-oxygen "
            "radical character and the lowest HAA barrier (11.7 kcal/mol); the Fe analogue has a "
            "quartet ground state and more metal-involved, charge-separated HAT-like motion. "
            "Source PDF MD5 05954baf4b3166ca43b0705129567ed1."
        ),
        "fields": {
            "active_space_protocol": (
                "Production spaces contain all five 3d orbitals on each metal: CAS(11,10) "
                "for Co2(III,IV) and CAS(9,10) for Fe2(III,IV). Co expansions CAS(15,12) "
                "and CAS(19,14) test added bridging-O character; SC-NEVPT2 refines energies."
            ),
            "geometry_source": "UB3LYP-D3 optimized reactants, transition structures, and reaction paths; CASSCF/NEVPT2 single points.",
        },
    },
    "10.1021/acs.joc.9b01197": {
        "pages": 8,
        "md5": "126f90e1dd79f5db12689fed06f168cd",
        "notes": (
            f"{MARKER}: read all 8 main-article pages, including ultrafast/long-time "
            "spectroscopy, product assignments, computed excited-state pathways, method "
            "comparison, conclusions, and references. The cited SI is not local. Photolysis "
            "forms a short-lived bicyclic oxaziridine, then a ring-open diazo species, while a "
            "separate conical-intersection route yields long-lived 1-oxa-3,4-diazepine. The "
            "measured oxaziridine decay barrier is 7.1+/-0.5 kcal/mol: close to RHF/CASSCF but "
            "not to methods adding dynamic correlation, several of which lose the minimum. "
            "Source PDF MD5 126f90e1dd79f5db12689fed06f168cd."
        ),
        "fields": {
            "software": "Gaussian 09",
            "active_space_protocol": "SA-CASSCF(8,8) includes the relevant pi/pi*, N/O lone-pair manifold for singlet/triplet photorearrangement surfaces.",
            "geometry_source": "CASSCF/RHF and correlated-method stationary points compared with time-resolved spectroscopic assignments.",
        },
    },
    "10.1021/acs.jpca.1c07108": {
        "pages": 13,
        "md5": "fd7514831bcec24f8a5b66672461b4ea",
        "notes": (
            f"{MARKER}: read all 13 main-article pages, including QM/MM preparation, every "
            "minimum/crossing and path in gas and acetonitrile, SOC analysis, conclusions, and "
            "references. The cited SI is not local. Bright S1(pi-pi*) relaxes by excited-state "
            "intramolecular proton transfer and can fluoresce, internally convert, or access "
            "triplets; the principal cycle proceeds through T1 ESIPT, a T1/S0 crossing in the "
            "enol region, and ground-state return to the keto form. Gas and solvent preserve the "
            "state ordering and qualitative paths. Source PDF MD5 fd7514831bcec24f8a5b66672461b4ea."
        ),
        "fields": {
            "software": "OpenMolcas; TINKER",
            "soc_included": "yes",
            "basis_set": "ANO-RCC-VDZP",
            "active_space_protocol": "CAS(14,10): nine pi/pi* orbitals plus one heteroatom lone-pair orbital; five equally weighted singlet/triplet roots for QM(CASSCF)/MM and CASPT2.",
            "geometry_source": "SA-CASSCF and QM(SA-CASSCF)/MM minima, conical intersections, and singlet-triplet crossings in gas phase and explicit acetonitrile MM environment.",
        },
    },
    "10.1021/acs.jpca.1c09150": {
        "pages": 8,
        "md5": "7413895926c308ea2ff33cd72ea294cb",
        "notes": (
            f"{MARKER}: read all 8 main-article pages, including electronic/vibronic "
            "methodology, finite-difference nonadiabatic/SOC/dipole derivatives, spectra, full "
            "kinetics, conclusions, and references. The cited SI is not local. DFT/MRCI finds "
            "inverted or near-degenerate S1/T1 states, but first-order fluorescence and ISC are "
            "symmetry forbidden; Herzberg-Teller and spin-vibronic coupling are therefore "
            "essential. Explicit rate calculations—not the gap sign alone—show efficient ISC/"
            "RISC cycling and delayed fluorescence. Source PDF MD5 7413895926c308ea2ff33cd72ea294cb."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": (
                "DFT/MRCI excitation selection used a 12e/10o pi space for heptazine and "
                "20e/20o for HAP-3MF; wavefunctions feed finite-difference nonadiabatic, "
                "spin-orbit, and transition-dipole derivative calculations."
            ),
            "geometry_source": "DFT optimized ground/excited-state structures and normal modes used in the vibronic kinetic model.",
        },
    },
    "10.1021/acs.jpca.4c08520": {
        "pages": 12,
        "md5": "824240340da09712524aa8f10ec4f46f",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including solvated-system setup, all "
            "minima/conical intersections/crossings, IC and ISC paths, SOC data, conclusions, "
            "and references. The cited SI is not local. In water both nucleosides populate bright "
            "S1(pi-pi*) and mainly return through S1/S0 intersections; computed barriers are "
            "9.5 kcal/mol for 5mdCyd and 1.6 for 5hmdCyd, consistent with their different 6.8/2.6 ps "
            "decays. Triplet routes exist but are secondary. Source PDF MD5 824240340da09712524aa8f10ec4f46f."
        ),
        "fields": {
            "soc_included": "yes",
            "basis_set": "ANO-RCC-VDZP",
            "active_space_protocol": "CAS(14,10) nucleobase lone-pair/pi manifold; three-root SA-CASSCF geometry optimizations and five-root CASPT2 energies in QM/MM water.",
            "geometry_source": "QM(SA-CASSCF)/MM optimized minima, conical intersections, and singlet-triplet crossings in an explicit spherical water environment.",
        },
    },
    "10.1021/acs.jpca.5c01912": {
        "pages": 11,
        "md5": "05ffa8701e639028e3d2fbe03691321d",
        "notes": (
            f"{MARKER}: read all 11 main-article pages, including two-dimensional surfaces, "
            "minimum-energy paths, orbital analysis, surface-hopping dynamics, conclusions, and "
            "references. The cited SI is not local. The NO+O air-afterglow reaction reaches a "
            "ground-surface ridge that bifurcates without a barrier toward NO2(2A1) and NO2(2B2); "
            "a thermally accessible excited-surface channel also materially populates emissive "
            "2B2 according to dynamics. Source PDF MD5 05ffa8701e639028e3d2fbe03691321d."
        ),
        "fields": {
            "active_space_protocol": "Four-state-average CAS(17,12), followed by four-state XMS-CASPT2 with an imaginary shift and no IPEA shift.",
            "geometry_source": "Unconstrained 4SA-CASSCF/def2-TZVP optimizations, 2D PES grids, and minimum-energy paths; XMS-CASPT2 corrected energies.",
        },
    },
    "10.1021/acs.jpca.5c02571": {
        "pages": 10,
        "md5": "b1877cd9c3409168c99bf5bd02cc48ac",
        "notes": (
            f"{MARKER}: read all 10 main-article pages, including five homologous cage models, "
            "seven comparison EMFs, DFT structure/EDA/NPA analyses, all CASSCF magnetic data, "
            "relaxation modeling, conclusions, and references. The cited SI is not local. All "
            "five principal DySc2N@C80-C120 cages have |mJ|=15/2 ground doublets and calculated "
            "barriers 999.3-1209.0 cm-1; cluster-cage electrostatics and predicted blocking "
            "temperature/relaxation generally weaken as cage size grows. Source PDF MD5 "
            "b1877cd9c3409168c99bf5bd02cc48ac."
        ),
        "fields": {
            "software": "ORCA 5.0.3",
            "basis_set": "SARC2-DKH-QZVP (Dy); DKH-def2-TZVP (Sc,N); DKH-def2-SVP (C)",
            "soc_included": "yes",
            "active_space_protocol": "CAS(9,7) for Dy(III) 4f followed by spin-orbit/SINGLE_ANISO analysis of the eight Kramers doublets across all modeled EMFs.",
            "geometry_source": "PBE0-D3 optimized endohedral-fullerene structures used for single-point CASSCF magnetic calculations.",
        },
    },
    "10.1021/acs.jpca.5c04929": {
        "pages": 10,
        "md5": "6b29daeab9d6c15e80f819cefe6f7682",
        "notes": (
            f"{MARKER}: read all 10 main-article pages, including aqueous QM/MM setup, all "
            "minima/intersections/crossings, IC/ISC paths, SOC values, conclusions, and references. "
            "The cited SI is not local. Bright S1(pi-pi*) is 4.29 eV and bifurcates between direct "
            "return and transfer to 1n-pi*; the respective ground-state IC barriers are 5.9 and "
            "1.5 kcal/mol. Triplet routes are feasible but minor, explaining how C5 fluorination "
            "changes cytidine photodynamics. Source PDF MD5 6b29daeab9d6c15e80f819cefe6f7682."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Five-root equal-weight CAS(16,11) spans N/O lone pairs, amino and C5-F pi, C5-F sigma/sigma*, and cytosine pi/pi* orbitals; CASPT2 corrects QM/MM energies.",
            "geometry_source": "QM(SA-CASSCF)/MM minima, conical intersections, and singlet-triplet crossings in explicit aqueous MM environment.",
        },
    },
    "10.1021/acs.jpca.5c05370": {
        "pages": 11,
        "md5": "e3c3b9fdf24de6774622dfdc9c848f09",
        "notes": (
            f"{MARKER}: read all 11 main-article pages, including both proton-transfer paths, "
            "stationary points/conical intersections, method comparisons, surface-hopping "
            "trajectories, conclusions, and references. The cited SI is not local. AHMD has a "
            "7.26 kcal/mol N-H to O ESIPT-1 path and a lower 4.25 kcal/mol O-H to O ESIPT-2 "
            "path; dynamics predominantly follows ESIPT-2 to its S1/S0 intersection. The OM2/"
            "MRCI dynamics level and MS-CASPT2 stationary-point level are distinct database "
            "entries, not separate compounds. Source PDF MD5 e3c3b9fdf24de6774622dfdc9c848f09."
        ),
        "fields": {
            "active_space_protocol": (
                "SA-CASSCF(10,8)/MS-CASPT2 stationary points and energies; OM2/MRCI "
                "CAS(14,12) surface-hopping trajectories test the dynamically competing channels."
            ),
            "geometry_source": "SA-CASSCF optimized minima, transition structures, and conical intersections; OM2/MRCI dynamics geometries.",
        },
    },
    "10.1021/acs.jpca.5c05510": {
        "pages": 13,
        "md5": "67099d1a60c43cf8bbd2a0419edb2d3d",
        "notes": (
            f"{MARKER}: read all 13 main-article pages, including the 16-molecule benchmark "
            "design, Franck-Condon and displaced geometries, all method/error analyses, nuclear-"
            "ensemble spectra, summary, and references. The cited SI is not local. CC3/aug-cc-"
            "pVTZ is the theoretical best estimate for dark carbonyl n-pi* transitions. XMS-"
            "CASPT2 uses molecule-specific full pi/pi* plus n spaces; performance beyond the "
            "Franck-Condon point is central because tiny distortions strongly alter oscillator "
            "strengths. The 12 AIMDb rows are the paper's multireference subset, not all 16 VOCs. "
            "Source PDF MD5 67099d1a60c43cf8bbd2a0419edb2d3d."
        ),
        "fields": {
            "active_space_protocol": (
                "Molecule-specific SA-CASSCF spaces include all relevant carbonyl/conjugated "
                "pi and pi* orbitals plus n lone pairs; XMS-CASPT2 applies a 0.1 au imaginary shift."
            ),
            "geometry_source": "Ground-state equilibrium and normal-mode-displaced geometries sampled for Franck-Condon/non-Condon benchmarking and nuclear-ensemble spectra.",
        },
    },
    "10.1021/acs.jpca.5c05513": {
        "pages": 19,
        "md5": "44f8ecc316a286c6387ee988835c11c7",
        "notes": (
            f"{MARKER}: read all 19 main-article pages, including full spin-free and spin-orbit "
            "potential curves, avoided crossings, spectroscopic constants, FPD thermochemistry, "
            "bonding/NBO analysis, conclusions, and references. The cited SI is not local. "
            "SA-CASSCF/SO-icMRCI+Q with core-valence correlation reproduces available spectra "
            "and predicts new Omega-state data. FPD D0 values are 192.4, 120.2, and 158.2 "
            "kcal/mol for BO, AlO, and ScO; AlO shows especially pronounced multireference "
            "character and perturbed/avoided-crossing structure. Source PDF MD5 "
            "44f8ecc316a286c6387ee988835c11c7."
        ),
        "fields": {
            "relativistic_treatment": "Douglas-Kroll scalar relativity plus explicit spin-orbit icMRCI",
            "soc_included": "yes",
            "active_space_protocol": (
                "State-averaged full-valence spaces: CAS(9,8) for BO/AlO and CAS(7,12) "
                "for ScO; internally contracted MRCI+Q adds core-valence correlation and "
                "spin-orbit coupling along complete potential curves."
            ),
            "geometry_source": "Dense gas-phase diatomic bond-length grids defining spin-free and spin-orbit potential energy curves.",
        },
    },
    "10.1021/acs.jpca.5c06689": {
        "pages": 12,
        "md5": "29f98f548a61f036315e03486440bc72",
        "notes": (
            f"{MARKER}: read all 12 main-article pages, including MOF fragment construction, "
            "TDDFT antenna states, Eu/Tb and linker CASSCF/NEVPT2 calculations, transfer-rate "
            "modeling, conclusions, and references. The cited SI is not local. Cd and Ag lower "
            "the linker T1 and improve transfer toward Eu(III), but vibrational relaxation still "
            "competes with emission; Tb rates were not quantitatively modeled because supporting "
            "experimental inputs were unavailable. Source PDF MD5 29f98f548a61f036315e03486440bc72."
        ),
        "fields": {
            "relativistic_treatment": "DKH with SARC-DKH-TZVP on lanthanides",
            "active_space_protocol": (
                "Eu CAS(6,7) and Tb CAS(8,7) use the seven 4f orbitals with 80 averaged "
                "roots; Cd/Ag-linker fragments use CAS(10,11) with 20 singlets and 20 triplets."
            ),
            "geometry_source": "Finite lanthanide/linker and metal-linker molecular models derived from the MOF and optimized as described in the paper.",
        },
    },
    "10.1021/acs.cgd.5c01058": {
        "pages": 8,
        "md5": "78d89116475ec82c4222c01e3f623472",
        "notes": (
            f"{MARKER}: read all 8 article pages and all 18 SI pages, including crystallographic "
            "tables, SHAPE metrics, AC/DC fits, calculated Kramers doublets, g tensors, transition "
            "moments, and crystal-field parameters. Ligand substitution changes the nonaxial "
            "field: 2-Dy is a zero-field SMM and has B(2,0) weight 14.43%, while 1-Dy requires a "
            "field and lacks a dominant axial term. Both Dy ground doublets are mainly |mJ|=15/2; "
            "the Gd analogues have similar magnetocaloric response. Main PDF MD5 "
            "78d89116475ec82c4222c01e3f623472."
        ),
        "fields": {
            "relativistic_treatment": "DKH scalar relativity with RASSI spin-orbit coupling",
            "active_space_protocol": (
                "CAS(9,7), averaging 21 sextets, 128/224 quartets, and 130/490 doublets, "
                "followed by RASSI-SO/SINGLE_ANISO; the local SI tables verify CF parameters "
                "and wavefunction compositions."
            ),
            "geometry_source": "Experimental X-ray structures used for CASSCF/RASSI-SO calculations.",
        },
    },
    "10.1021/acs.jctc.5c01321": {
        "pages": 16,
        "md5": "5d8fec28fc59d57af3e0a9e4bc41ce5b",
        "notes": (
            f"{MARKER}: read all 16 article pages and all 66 SI pages, including functional "
            "parameters, every database membership/active-space table, per-datum errors, and "
            "sample OpenMolcas/PySCF inputs. MC25 is trained on a more excitation-diverse set "
            "than MC23 and gives 0.14 eV mean unsigned excitation error while retaining strong "
            "ground-state performance; MC25L is the linearized form for multistate references. "
            "The 10 AIMDb rows are the SI-tabulated TM-SpinSplitting10 multireference cases. "
            "Main PDF MD5 5d8fec28fc59d57af3e0a9e4bc41ce5b."
        ),
        "fields": {
            "active_space_protocol": (
                "Compound-specific SA-CASSCF spaces and root counts are reproduced from SI "
                "Tables S2-S4; the same density matrices feed CASPT2, MC25 MC-PDFT, and "
                "linearized MC25 comparisons."
            ),
            "geometry_source": "Fixed benchmark geometries and reference definitions documented in the main text and local SI database tables.",
        },
    },
    "10.1021/acs.jctc.5c01411": {
        "pages": 17,
        "md5": "d4b9cde20c440805277f76d74e4fc40f",
        "notes": (
            f"{MARKER}: read all 17 article pages, all 21 SI pages, and inspected the local SI "
            "archive containing benchmark data. The database has 419 vertical spin-flip gaps: "
            "379 single-reference CCSD(T) values and 40 multireference MS-CASPT2/experimental "
            "values. The SI explicitly tests small-to-full-valence active-space convergence and "
            "validates full-valence MS-CASPT2 against 13 experimental gaps. The seven AIMDb rows "
            "are source-explicit members of the multireference subset, not the full dataset. Main "
            "PDF MD5 d4b9cde20c440805277f76d74e4fc40f."
        ),
        "fields": {
            "active_space_protocol": (
                "Two-root equal-weight full-valence SA-CASSCF with MS-CASPT2, IPEA shift "
                "0.25 au; SI compares CAS(2,2), CAS(4,4), CAS(6,6), and production full-valence spaces."
            ),
            "geometry_source": "Fixed vertical-gap benchmark geometries supplied/documented with the local benchmark SI.",
        },
    },
    "10.1021/acs.jpca.5c04699": {
        "pages": 13,
        "md5": "bca1ee47b9243fddafb389bbf1943dda",
        "notes": (
            f"{MARKER}: read all 13 article pages, all 24 SI pages, and inspected all six sheets "
            "of the local XLSX benchmark workbook (singlet/triplet excitations and spin-spin "
            "couplings). TD-GVB-srDFT adds short-range dynamic correlation to long-range GVB-PP, "
            "reducing excitation errors to about 0.2 eV, comparable to CAS-srDFT; generalized TDA "
            "is necessary for reliable triplets. For metal fluorides, range-separated response "
            "greatly improves CASSCF/GVB coupling constants. Main PDF MD5 "
            "bca1ee47b9243fddafb389bbf1943dda."
        ),
        "fields": {
            "active_space_protocol": "Full metal-ligand CAS(10,10) reference compared with GVB perfect-pairing and their srLDA/srPBE response variants; gTDA variants are separately assessed.",
            "geometry_source": "Fixed benchmark geometries documented with the local SI and XLSX results workbook.",
        },
    },
    "10.48550/arxiv.2601.19699": {
        "pages": 7,
        "md5": "ae9d164d57399778ecfb0d8636ce7750",
        "notes": (
            f"{MARKER}: read all 7 arXiv pages, including the constrained Newton-Raphson "
            "derivation, analytical-gradient equations, LiH/H2O validation, geometry optimizations, "
            "limitations, conclusion, and references. OC-CASSCF optimizes mutually orthogonal "
            "state-specific orbitals and avoids variational collapse; analytical gradients agree "
            "with finite differences within 1e-4 Eh/A and improve excited-state geometries over "
            "ordinary SA-CASSCF even with small spaces. Source PDF MD5 "
            "ae9d164d57399778ecfb0d8636ce7750."
        ),
        "fields": {
            "active_space_protocol": "Three mutually orthogonal singlet states optimized with state-specific OC-CASSCF(2,2), compared directly with three-root SA-CASSCF.",
            "geometry_source": "Analytical OC-CASSCF gradients used in LiH bond scans and excited-state geometry optimizations; numerical gradients provide validation.",
        },
    },
    "10.48550/arxiv.2602.04420": {
        "pages": 59,
        "md5": "1b13a13c6f65ee8ff1528d71840b01ba",
        "notes": (
            f"{MARKER}: read all 59 arXiv pages, including UGA-SSMRPT2 theory, implementation, "
            "all benchmark categories/tables, per-state error analyses, comparisons, limitations, "
            "conclusion, and references. The state-specific, spin-free method is size extensive "
            "and intruder resistant without an IPEA shift, and usually lies within 0.20 eV of "
            "EOM-CCSD/theoretical best estimates using relatively small spaces. The 60 AIMDb rows "
            "represent distinct source-tabulated molecule/category/active-space cases; shared "
            "protocols must not be mistaken for 60 newly synthesized compounds. Source PDF MD5 "
            "1b13a13c6f65ee8ff1528d71840b01ba."
        ),
        "fields": {
            "active_space_protocol": (
                "Molecule- and state-category-specific SA-CASSCF spaces from the benchmark "
                "tables feed UGA-SSMRPT2 and comparisons with averaged UGA-SSMRPT2, MCQDPT2, "
                "SC-NEVPT2, and FIC-CASPT2."
            ),
            "geometry_source": "Published vertical-excitation benchmark geometries used without reoptimization, as documented by benchmark category.",
        },
    },
    "10.48550/arxiv.2602.07746": {
        "pages": 34,
        "md5": "ac38cc29f797e450389f30d1fc7d9e34",
        "notes": (
            f"{MARKER}: read all 34 arXiv pages, including complex-spinor eDSC/hDSC theory, "
            "four-configuration construction, SOC-strength tests, phenoxyl-phenol application, "
            "limitations/future work, conclusion, and references. The generalized constrained "
            "CAS(3,2) treatment yields smooth Kramers-doublet charge-transfer crossings and rapid "
            "SCF convergence; the test finds a quadratic gap dependence on SOC. Diabatization "
            "and nonadiabatic dynamics are identified as future work, not performed here. No AO "
            "basis set is stated in the article, so that field remains blank. Source "
            "PDF MD5 ac38cc29f797e450389f30d1fc7d9e34."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Odd-electron hDSC CAS(3,2) with four complex-valued spinor configurations and dynamically weighted constrained state averaging across Kramers-restricted crossings.",
            "geometry_source": "Phenoxyl-phenol proton-coupled charge-transfer coordinate and model geometries used to scan crossings over varied SOC strengths.",
        },
    },
    "10.48550/arxiv.2602.24236": {
        "pages": 45,
        "md5": "4650ccfe1c692f7f4771a4cfd33b765d",
        "notes": (
            f"{MARKER}: read all 45 arXiv pages, including derivation/implementation of X2Ccorr, "
            "all chalcogen ZFS benchmarks, two-electron SOC/spin-spin/QED decompositions, Nd "
            "aquo-cluster calculations through second shells, conclusions, and references. "
            "X2Ccorr picture-change-corrects the fluctuation potential; with a Dirac-Coulomb-Gaunt "
            "Hamiltonian it captures electron spin-spin effects important for heavier chalcogens. "
            "The Cholesky/super-CI implementation enables large Nd clusters and shows explicit "
            "second-shell effects on ligand-field splittings. Source PDF MD5 "
            "4650ccfe1c692f7f4771a4cfd33b765d."
        ),
        "fields": {
            "relativistic_treatment": "Hierarchy of X2C/X2CAMF/X2Ccorr Hamiltonians including two-electron SOC, Gaunt spin-spin, and assessed QED terms",
            "soc_included": "yes",
            "active_space_protocol": (
                "Chalcogens: three-state X2C-CASSCF(8e,12 spinors) in valence np spinors. "
                "Nd aquo ions: X2C-CASSCF(3e,14 4f spinors), averaging the stated low-lying manifolds."
            ),
            "geometry_source": "Diatomic equilibrium/ZFS benchmark geometries and experimental/optimized first- and second-shell Nd aquo-cluster models.",
        },
    },
    "10.48550/arxiv.2603.07089": {
        "pages": 65,
        "md5": "05ad3ce93ef583810f9557c646c8501c",
        "notes": (
            f"{MARKER}: read all 65 arXiv pages, including four-state ozone surfaces, active-"
            "space/basis convergence, conical intersections, nonadiabatic couplings and topology, "
            "ADT/curl-condition tests, the diabatic Hamiltonian construction, conclusion, and "
            "references. The production SA-MCSCF(18,12)/ic-MRCI(Q)/aug-cc-pVQZ description "
            "covers four low singlets; CAS(12,9), CAS(24,15), larger basis sets, additional spin "
            "manifolds, and asymptotes are used as sensitivity checks. The result is a four-state "
            "diabatic model, not a dynamics/lifetime calculation. Source PDF MD5 "
            "05ad3ce93ef583810f9557c646c8501c."
        ),
        "fields": {
            "active_space_protocol": (
                "Production full-valence four-state SA-CASSCF(18,12), followed by ic-MRCI(Q); "
                "CAS(12,9) and CAS(24,15), basis AVDZ-AV6Z/CBS, and extra singlet/triplet/"
                "quintet state averages test surface, coupling, and asymptotic convergence."
            ),
            "geometry_source": "Dense O3 internal-coordinate grids, optimized conical intersections, and asymptotic cuts used to fit four adiabatic surfaces and their diabatic transformation.",
        },
    },
    "10.1063/1.1355986": {
        "pages": 7,
        "md5": "1aacd396fdc614e51d3c049eb2fc3ad0",
        "notes": (
            f"{MARKER}: read all 7 article pages, including silica cluster models, ground-state "
            "geometry tests, active-space/correlation/basis sensitivity, excited-state assignments, "
            "conclusions, and references. CASPT2 assigns the weak approximately 0.7 eV band to a "
            "terminal-O internal excitation and the intense 5.5 eV band to O1-to-terminal-O2 "
            "charge transfer; it finds no other low-energy absorption. The multiple AIMDb rows "
            "are systematically enlarged embedded cluster models of the same peroxy defect. "
            "Source PDF MD5 1aacd396fdc614e51d3c049eb2fc3ad0."
        ),
        "fields": {
            "active_space_protocol": "CASSCF spaces and silica cluster size/correlation shells were enlarged systematically before CASPT2; basis and UMP2-versus-DFT ground-geometry sensitivity was checked.",
            "geometry_source": "Embedded silica peroxy-radical cluster geometries optimized with UMP2 and DFT variants and compared for spectral robustness.",
        },
    },
    "10.1080/00268976.2016.1164348": {
        "pages": 9,
        "md5": "ea61ade68605aaadbee136585b77e0b6",
        "notes": (
            f"{MARKER}: read all 9 article pages, including vertical spectra, four S1/S0 "
            "intersection classes, surface-hopping dynamics, timescale comparison, conclusions, "
            "and references. The cited supplemental material is not local. CASPT2 places four "
            "bright pi-pi* transitions at 4.47, 5.35, 5.97, and 6.30 eV. Four geometrically "
            "distinct internal-conversion funnels have comparable simulated timescales, so the "
            "paper does not single out one exclusive photophysical route. Source PDF MD5 "
            "ea61ade68605aaadbee136585b77e0b6."
        ),
        "fields": {
            "active_space_protocol": "Two-root state-averaged CASSCF for S0/S1 conical intersections; CASPT2/cc-pVTZ corrects vertical excitation energies at the MP2 equilibrium geometry.",
            "geometry_source": "MP2 and CASSCF gas-phase minima plus four SA2-CASSCF optimized S1/S0 conical-intersection families and surface-hopping geometries.",
        },
    },
    "10.1080/00268976.2016.1201600": {
        "pages": 30,
        "md5": "ce1e1eb3245152a47972a62ca76d3009",
        "notes": (
            f"{MARKER}: read all 30 article pages, including formal theory, the eight-diatomic/"
            "15-polyatomic benchmark, every excitation/SOC table, orbital-dependence analysis, "
            "conclusions, and references. DFT/MRCI, revised DFT/MRCI-R, and two MR-MP2 variants "
            "are tested against experiment and CASSCF/CASPT2 references. SOC matrix elements are "
            "not automatically more robust than excitation energies: n-to-pi* cases are especially "
            "sensitive to compact HF versus KS orbitals and differential correlation. The six "
            "AIMDb rows are the explicit CASSCF/CASPT2 benchmark subset. Source PDF MD5 "
            "ce1e1eb3245152a47972a62ca76d3009."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Molecule-specific SA-CASSCF/CASPT2 reference spaces benchmark DFT/MRCI(-R) and MR-MP2 variants built from either MRHF or BH-LYP Kohn-Sham orbitals.",
            "geometry_source": "Fixed experimental or established benchmark geometries specified for each diatomic/polyatomic test case.",
        },
    },
    "10.1080/00268976.2016.1213436": {
        "pages": 11,
        "md5": "2490ec0cd13ffe7fae1006198c825fde",
        "notes": (
            f"{MARKER}: read all 11 article pages, including three tautomer structures, spectra, "
            "S0/S1 proton-transfer profiles, method comparison, conclusions, and references. The "
            "cited supplemental material is not local. The untransferred E tautomer is the S0 "
            "global minimum and accounts for 2.54 eV absorption; single-transfer SK is the S1 "
            "minimum and accounts for 1.64 eV emission. The double-transfer DK route has too high "
            "a barrier to contribute materially, explaining observed single rather than double "
            "ESIPT. Source PDF MD5 2490ec0cd13ffe7fae1006198c825fde."
        ),
        "fields": {
            "active_space_protocol": "Two-state SA-CASSCF with molecule-centered pi/lone-pair active orbitals, followed by CASPT2 single points; B3LYP/TD-B3LYP provides an independent comparison.",
            "geometry_source": "CASSCF/6-31G* optimized E, SK, and DK minima and constrained proton-transfer profiles on S0 and S1.",
        },
    },
    "10.1080/00268976.2025.2563030": {
        "pages": 14,
        "md5": "4fffd374ef2a451fd5ef7c13739430a6",
        "notes": (
            f"{MARKER}: read all 14 article pages, including state characterization, both "
            "trajectory ensembles, hopping geometries, vibrational-mode analysis, mechanistic "
            "classification, conclusions, and references. The cited supplement is not local. No "
            "S1-initiated trajectory decays within 100 fs, consistent with slow tunneling; 44% of "
            "S2-initiated trajectories internally convert to S1. Ring butterfly/out-of-plane "
            "motion controls ultrafast S2 decay without breaking the intramolecular H bond, while "
            "100 fs sampling cannot address the nanosecond S1 process. Source PDF MD5 "
            "4fffd374ef2a451fd5ef7c13739430a6."
        ),
        "fields": {
            "active_space_protocol": "Three-state SA-CASSCF(12,9) for S0/S1(pi-pi*)/S2(pi-sigma*) with Zhu-Nakamura surface-hopping probabilities.",
            "geometry_source": "SA3-CASSCF/6-311++G** minima and on-the-fly 100 fs nonadiabatic trajectory geometries initiated separately in S1 and S2.",
        },
    },
    "10.1021/acs.jpca.6c01999": {
        "pages": 12,
        "md5": "ece6b586e386dbdf7e69945409c87821",
        "notes": (
            f"{MARKER}: read all 12 article pages, including 21 spin-free curves, spin-orbit "
            "states, dipole/transition moments, spectroscopic constants, bonding, photoionization "
            "simulation, conclusions, and references. The cited SI is not local. State-specific "
            "CASSCF/MRCI and coupled-cluster methods put 1Sigma+ slightly below 3Pi before SOC; "
            "the Omega=0+ ground state is strongly mixed (52% 3Pi, 41% 1Sigma+). The bonding has "
            "about Hf+0.50/Si-0.50 charge separation. Source PDF MD5 "
            "ece6b586e386dbdf7e69945409c87821."
        ),
        "fields": {
            "relativistic_treatment": "Hf relativistic pseudopotential plus explicit spin-orbit state interaction",
            "soc_included": "yes",
            "active_space_protocol": "CASSCF(8,13) surveys HfSi states; selected states receive state-specific CASSCF-reference MRCI and spin-orbit coupling, with CCSD(T)/CCSDT(Q) checks.",
            "geometry_source": "Gas-phase Hf-Si bond-length grids for PEC/PDM/TDM curves; fitted minima provide spectroscopic constants.",
        },
    },
    "10.1021/acs.jpca.6c02386": {
        "pages": 13,
        "md5": "52e09c739eeef3fb918a857b56945962",
        "notes": (
            f"{MARKER}: read all 13 article pages and all 11 SI pages, including coordinates, "
            "ORCA inputs, charge-specific active spaces/root counts, and magnetomechanical scan "
            "script. Across -2 to +2 redox states, dual-bridge paracyclophane suppresses slippage "
            "and preserves pancake covalency; peri-naphthalene expands/slips and loses up to 68% "
            "bond order on reduction. SA-CASSCF/NEVPT2 describes exchange and multistate NEVPT2 "
            "spectra; charge-specific rows are genuine redox states, not protocol intermediates. "
            "Main PDF MD5 52e09c739eeef3fb918a857b56945962."
        ),
        "fields": {
            "active_space_protocol": "Charge-specific CASSCF spaces/root counts selected from frontier pancake-bond orbitals; SC/QD-NEVPT2 supplies exchange and absorption energies, with constrained interdeck scans.",
            "geometry_source": "DFT-optimized structures for both scaffolds at charges -2 through +2 plus constrained 2.8-4.1 A interdeck magnetomechanical scans documented in local SI.",
        },
    },
    "10.1039/c8cp00602d": {
        "pages": 11,
        "md5": "75629d3ef20b875b93bbfd96556c5ba2",
        "notes": (
            f"{MARKER}: read all 11 article pages, including absorption experiments, trans/cis "
            "structures, active-space checks, solvent spectra, isomerization paths, conclusions, "
            "and references. The cited ESI is not local. Multiconfigurational calculations "
            "rationalize different spectra and the approximately tenfold lower trans-to-cis yield "
            "of 2,4'-dihydroxy versus 2,4,4'-trihydroxychalcone through hydroxylation-dependent "
            "state ordering and decay access. The four AIMDb rows distinguish compound/isomer "
            "cases used on the photochemical surfaces. Source PDF MD5 "
            "75629d3ef20b875b93bbfd96556c5ba2."
        ),
        "fields": {
            "active_space_protocol": "Full pi-valence screening was reduced to the reported production CASSCF/RASSCF space and CASPT2 energies; gas-phase and PCM-water calculations were compared.",
            "geometry_source": "CASSCF optimized trans/cis minima and isomerization-path stationary points in vacuum and implicit water.",
        },
    },
    "10.1039/d1dt02038b": {
        "pages": 17,
        "md5": "0f6710b136cd1d5d8155ba6cfa85c6c7",
        "notes": (
            f"{MARKER}: read all 17 article pages, including synthesis/order-of-addition effects, "
            "five crystal structures, DC/AC magnetism, DFT exchange, all Co/Ln CASSCF fragments, "
            "conclusions, and references. The cited ESI is not local. Lanthanide contraction and "
            "reagent sequence switch tetranuclear versus pentanuclear products; Dy permits both. "
            "Single-ion calculations explain anisotropy/relaxation but use magnetically diluted "
            "fragments, so the AIMDb rows are distinct metal sites/models rather than six isolated "
            "bulk compounds. Source PDF MD5 0f6710b136cd1d5d8155ba6cfa85c6c7."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Site-specific CAS uses five Co 3d or seven Ln 4f orbitals with the corresponding ion electron count; RASSI-SO/SINGLE_ANISO treats Ln sites and DFT supplies exchange parameters.",
            "geometry_source": "Experimental X-ray geometries partitioned into magnetically diluted single-ion fragments for ab initio anisotropy calculations.",
        },
    },
    "10.1039/d3cp01243c": {
        "pages": 14,
        "md5": "0cef8339d025088b6dc478277311ad00",
        "notes": (
            f"{MARKER}: read all 14 article pages, including geometry/ZFS validation, d-shell "
            "expansions, AILFT, relaxation paths, mode-resolved spin-vibrational coupling, "
            "conclusions, and references. The cited ESI is not local. Complexes 1/3 reproduce "
            "experimental anisotropy; 2 is easy-plane and 4 triaxial with positive D. Complex 4 "
            "shows that dynamic correlation and an extended d space can change the sign of D; "
            "slow relaxation depends on both the electronic barrier and which vibrations couple "
            "to it. Source PDF MD5 0cef8339d025088b6dc478277311ad00."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Co-centered CASSCF spaces include five 3d orbitals and reported correlating-shell expansions; NEVPT2 and SOC provide ZFS, while mode displacements give spin-phonon derivatives.",
            "geometry_source": "DFT-D3BJ optimized structures and numerical normal-mode displacements used for CASSCF/NEVPT2/SOC anisotropy and spin-vibration coupling.",
        },
    },
    "10.1021/jacs.5c03770": {
        "pages": 15,
        "md5": "b264f434942f622d1c99a8826f053266",
        "notes": (
            f"{MARKER}: read all 15 article pages and all 127 SI pages, including synthesis, "
            "kinetics/quantum yields, EPR/UV-vis product assignments, atmosphere/solvent tests, "
            "TDDFT, CASSCF/QD-NEVPT2 spectra/spin surfaces, coordinates, and crystallography. All "
            "four Ni(II) tolyl chlorides have analogous Ni-aryl bonding-to-antibonding MLCT access "
            "and comparable photodegradation quantum yields. HN2 suppresses radical side reactions "
            "and stabilizes Ni(I); ortho/para substitution changes geometry and susceptibility to "
            "side chemistry. Main PDF MD5 b264f434942f622d1c99a8826f053266."
        ),
        "fields": {
            "active_space_protocol": "Compound-specific CASSCF spaces selected from Ni-aryl bonding/antibonding and Ni d orbitals; QD-NEVPT2 compares singlet, square-planar triplet, tetrahedral triplet, and MLCT states.",
            "geometry_source": "Experimental crystal structures and DFT-optimized ground/square-planar/tetrahedral structures; full coordinates and CASSCF inputs verified in local SI.",
        },
    },
    "10.1021/jacs.5c15650": {
        "pages": 12,
        "md5": "e97966e9f410c61d20c79e1a671a7778",
        "notes": (
            f"{MARKER}: read all 12 article pages and all 30 SI pages, including synthesis, "
            "quick-XAS/chemometrics, diffraction/spectroscopy/electrochemistry, protonation and "
            "spin-state models, CASSCF wavefunctions, and references. [P2W15Mo3O62] can accept "
            "12 electrons in acid; after six electrons it reorganizes to form Mo-Mo bonds. The "
            "most stable 12-electron model is triplet with three Mo-O-Mo protons and nine electrons "
            "on {Mo3O13}, but coexisting proton/spin forms cannot be excluded. Main PDF MD5 "
            "e97966e9f410c61d20c79e1a671a7778."
        ),
        "fields": {
            "active_space_protocol": "CASSCF(12,12) distributes the 12 metal electrons among 12 Mo/W d-type orbitals; triplet/quintet and protonation isomers are compared with DFT high-spin analyses.",
            "geometry_source": "DFT-optimized protonation/reduction isomers constrained by in situ XANES/EXAFS and crystallographic structural changes; local SI documents alternatives.",
        },
    },
    "10.1021/ja809624w": {
        "pages": 12,
        "md5": "367bb7a7c0a7c4987dc61c7ebc90ae11",
        "notes": (
            f"{MARKER}: read all 12 article pages, including synthesis/structures, XANES "
            "valence measurements, magnetism, DFT geometries, CASSCF configuration mixing, "
            "alternative-model exclusions, conclusion, and references. Cp*2Yb bipyridine/"
            "diazabutadiene adducts are intermediate-valent multiconfigurational singlets mixing "
            "closed-shell f14 and antiferromagnetically coupled f13(ligand pi*)1 configurations. "
            "The mixing fraction tracks metal-ligand antiferromagnetic coupling and is not a "
            "thermally varying valence equilibrium. Source PDF MD5 367bb7a7c0a7c4987dc61c7ebc90ae11."
        ),
        "fields": {
            "active_space_protocol": "CASSCF includes the Yb f orbital of ligand-pi* symmetry and the ligand pi* acceptor, with remaining f occupancy represented in the multiconfigurational singlet model.",
            "geometry_source": "Unconstrained CASSCF and B3PW91 optimized Cp2 model geometries compared with Cp*2 experimental structures.",
        },
    },
    "10.1021/jp509561v": {
        "pages": 6,
        "md5": "9c329c8edea67afa4e216b6e3a1bc714",
        "notes": (
            f"{MARKER}: read all 6 article pages and all 4 SI pages, including spectra, ion-source "
            "chemistry, all candidate-isomer energies/transitions, oscillator strengths, charge/"
            "spin tables, conclusions, and references. Matrix bands at 497/354 nm are assigned to "
            "the first/second excited doublets of cyclic B+, while 528 nm belongs to chain ylide F+. "
            "The 14 AIMDb rows are candidate H2C6O+ isomers explicitly screened by MS-CASPT2; "
            "only B+ and F+ are observed carriers. Main PDF MD5 "
            "9c329c8edea67afa4e216b6e3a1bc714."
        ),
        "fields": {
            "active_space_protocol": "CAS(9,9) ground-state geometry calculations; larger MS-CASPT2(11,11) excitation calculations with state averages documented per isomer in main text/SI.",
            "geometry_source": "CASPT2/CASSCF optimized candidate-isomer geometries compared to 6 K neon-matrix vibronic spectra.",
        },
    },
    "10.1021/acs.jpca.5c07496": {
        "pages": 8,
        "md5": "2fb9eedc4534425dfca6207d67be2ff3",
        "notes": (
            f"{MARKER}: read all 8 article pages, including stationary points, electronic-state "
            "assignments, on-the-fly trajectories, decay-coordinate statistics, conclusions, and "
            "references. The cited SI is not local. Nitrile substitution suppresses conventional "
            "ESIPT in HMAN and redirects S1 relaxation mainly to approximately 90-degree C=N "
            "torsion and an S1/S0 intersection, with a secondary pathway involving the adjacent "
            "torsion; the conclusion is based on finite trajectory sampling. Source PDF MD5 "
            "2fb9eedc4534425dfca6207d67be2ff3."
        ),
        "fields": {
            "active_space_protocol": "Four-state-average CASSCF(12,10)/6-31G** supplies surfaces/dynamics; CASPT2/6-311G** corrects vertical energies.",
            "geometry_source": "SA4-CASSCF optimized minima/intersections and on-the-fly surface-hopping trajectory geometries.",
        },
    },
    "10.1021/acs.jpca.5c08237": {
        "pages": 11,
        "md5": "edb6cd56f132e157f2cc679c915ad5e7",
        "notes": (
            f"{MARKER}: read all 11 article pages, including the microsolvated structures, four "
            "competitive paths, intersections/crossings, proton-transfer profiles, SOC values, "
            "conclusions, and references. The cited SI is not local. For 5HF-2H2O, barrierless "
            "S2(pi-pi*) ESIPT followed by conical-intersection return and reverse ground-state "
            "proton transfer dominates. Three secondary ISC/internal-conversion paths exist; a "
            "30.4 cm-1 n-pi*/triplet SOC facilitates one of them. Source PDF MD5 "
            "edb6cd56f132e157f2cc679c915ad5e7."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": "Three equal-weight roots in state-averaged CASSCF for the relevant singlet and triplet manifolds; CASPT2 corrects energies and supplies SOC at crossings.",
            "geometry_source": "CASSCF minima, conical intersections, singlet-triplet crossings, and constrained proton-transfer paths for the two-water cluster.",
        },
    },
    "10.1021/acs.jpcc.6b10391": {
        "pages": 4,
        "md5": "4a503a0e658b8d9f0970bea9b026fba9",
        "notes": (
            f"{MARKER}: read all 4 article pages, including the 6 K matrix spectrum, vibrational "
            "assignments, active-space calculation, conclusion, and references. The absorption "
            "origin at 632.5 nm (1.96 eV) is assigned to ferrocenium 1 2E1' <- X 2E2' in D5h; "
            "CASPT2 vertical energies/oscillator strengths establish the state assignment and DFT "
            "frequencies assign the progression. Source PDF MD5 "
            "4a503a0e658b8d9f0970bea9b026fba9."
        ),
        "fields": {
            "active_space_protocol": "MS-CASPT2 production space distributes 11 electrons in 12 Fe/cyclopentadienyl valence orbitals; CAS(11,11) is a reported sensitivity check.",
            "geometry_source": "DFT optimized D5h ferrocenium structure and frequencies used with vertical MS-CASPT2 spectrum for 6 K neon-matrix assignment.",
        },
    },
    "10.1021/acs.jpca.6b10687": {
        "pages": 7,
        "md5": "1fe44f69c9ab04071c6629d1f06924a8",
        "notes": (
            f"{MARKER}: read all 7 article pages and all 12 SI pages, including candidate structures, "
            "active orbitals/configurations, CASPT2 energies, Franck-Condon simulations, frequencies, "
            "conclusions, and references. C7H4O2+ bands at 649.6/431.0/372.0 nm are assigned to A+; "
            "C7H5O2+ 366.4 nm belongs to J+, and neutralized J gives four systems at 291.3-461.2 nm. "
            "The 10 AIMDb rows are explicitly calculated cation/neutral candidate isomers; only "
            "specific carriers receive experimental assignments. Main PDF MD5 "
            "1fe44f69c9ab04071c6629d1f06924a8."
        ),
        "fields": {
            "active_space_protocol": "MS-CASPT2 uses CAS(11,12) for C7H4O2+ and CAS(12,12) for C7H5O2+; reduced CAS/TDDFT frequencies supply Franck-Condon simulations, with orbital/configuration tables verified in SI.",
            "geometry_source": "MP2/CASSCF optimized candidate isomers and excited-state/DFT frequency geometries used in 6 K neon-matrix Franck-Condon assignment.",
        },
    },
    "10.1021/jp803213j": {
        "pages": 5,
        "md5": "0681ff90730c238dd7d49604c868a6b4",
        "notes": (
            f"{MARKER}: read all 5 article pages, including ANO construction/contracted sets, "
            "atomic tests, Ce2/LuF3 applications, basis convergence, conclusion, and references. "
            "ANO-RCC sets for La-Lu are built from averaged atomic/ionic/field-perturbed density "
            "matrices with DKH scalar relativity and CASSCF/CASPT2 correlation. The Ce diatom "
            "and LuF3 rows are validation applications, not two versions of one protocol. Source "
            "PDF MD5 0681ff90730c238dd7d49604c868a6b4."
        ),
        "fields": {
            "relativistic_treatment": "Douglas-Kroll-Hess scalar relativity",
            "active_space_protocol": "System-specific CASSCF references for Ce2 and LuF3 followed by CASPT2, used to validate contraction and convergence of newly generated lanthanide ANO-RCC sets.",
            "geometry_source": "Diatomic/pyramidal bond-distance and structure tests used for spectroscopic/thermochemical basis-set validation.",
        },
    },
    "10.1021/jp8037335": {
        "pages": 7,
        "md5": "a7c8f7153eed833620755566ea59f73c",
        "notes": (
            f"{MARKER}: read all 7 article pages, including GIAO-CASSCF methodology, all NICS/"
            "shielding/susceptibility tables, correlation checks, conclusions, and references. "
            "Magnetic criteria classify benzene S0 aromatic but its T1/S1 antiaromatic; square "
            "cyclobutadiene T1/S1 aromatic and S2 antiaromatic; rectangular cyclobutadiene T1 "
            "aromatic and S1 antiaromatic. The three AIMDb rows group species/geometry cases; the "
            "paper cautions that generalized excited-state nuclear deshielding can mimic an "
            "antiaromatic signature. Source PDF MD5 a7c8f7153eed833620755566ea59f73c."
        ),
        "fields": {
            "active_space_protocol": "Full pi spaces: CASSCF(6,6) for benzene and CASSCF(4,4) for square/rectangular cyclobutadiene, evaluated with GIAO magnetic response.",
            "geometry_source": "Symmetry-constrained D6h benzene and D4h/D2h cyclobutadiene ground/excited-state geometries specified in the article.",
        },
    },
    "10.1021/jp807172h": {
        "pages": 8,
        "md5": "fd9e2d539460e1ed37fae66f4d7818ba",
        "notes": (
            f"{MARKER}: read all 8 article pages and all 5 SI pages, including retinal/rhodopsin "
            "QM regions, geometry dependence, basis/root/space tests, every excitation/oscillator "
            "table, mutant electrostatics, summary, and references. B3LYP retinal geometries avoid "
            "the approximately 100 nm blue-shift error of CASSCF geometries; DDCI2+Q reliably "
            "models relative spectral shifts. Protein electrostatics largely cancel except for "
            "Glu113, and E122Q/E113Q changes are separated into chromophore and environment effects. "
            "Main PDF MD5 fd9e2d539460e1ed37fae66f4d7818ba."
        ),
        "fields": {
            "active_space_protocol": "Production six-root CAS(12,12) retinal pi space with DDCI2+Q; CAS(6,6), root count, selection threshold, basis, and QM-region variants are tabulated in local SI.",
            "geometry_source": "B3LYP retinal and B3LYP/AMBER rhodopsin/mutant QM/MM geometries; CASSCF geometries retained only as an explicit comparison.",
        },
    },
    "10.1021/acs.jpclett.5c01270": {
        "pages": 7,
        "md5": "5f0310c47fb7c624056bad58310ef0a5",
        "notes": (
            f"{MARKER}: read all 7 article pages and all 30 SI pages, including matrix generation/"
            "isotope labeling, spectra, competing pathways, SOC calculations, energy profiles, "
            "tables, and all coordinates. Triplet CH3N acts as a hydrogen-bond acceptor toward "
            "H2O/HCl at 6 K. UV excitation gives competing 1,2-H migration and H-X insertion; "
            "water mediates crossing before migration, whereas HCl changes the insertion landscape. "
            "Main PDF MD5 5f0310c47fb7c624056bad58310ef0a5."
        ),
        "fields": {
            "soc_included": "yes",
            "active_space_protocol": (
                "CASSCF/CASPT2(10,10) reaction profiles with larger geometry-specific spaces "
                "reported in SI (including 12,11 for H2O and 14,12 for HCl); MRCI(10,11) supplies SOC."
            ),
            "geometry_source": "CASSCF/aug-cc-pVTZ minima, transition structures, and crossing geometries; all coordinates verified in local SI.",
        },
    },
    "10.1021/acs.jpclett.5c02294": {
        "pages": 9,
        "md5": "534daf5d554da0af770ae0cf0ce1b115",
        "notes": (
            f"{MARKER}: read all 9 article pages and the full 10-page SI (also present with source "
            "and figures in the local ZIP), including coincidence maps, roaming reconstruction, "
            "fit/error analysis, DFT AIMD, CASSCF NAMD, populations, and methods. Pump-probe "
            "imaging identifies neutral D2 roaming en route to D3+ in CD3OD dication; simulations "
            "separate direct dissociation, single/double H migration, and roaming/migration. "
            "Neutral and dication rows are different charge-state dynamics models, not duplicate "
            "protocol steps. Main PDF MD5 534daf5d554da0af770ae0cf0ce1b115."
        ),
        "fields": {
            "active_space_protocol": "SA-CASSCF(12,12) neutral-state characterization and SA-CASSCF(8,8) dication surface-hopping dynamics, complemented by ground-state DFT AIMD.",
            "geometry_source": "On-the-fly DFT and SA-CASSCF trajectories initialized from sampled CD3OD geometries; SI documents coordinates, velocities, populations, and fragmentation criteria.",
        },
    },
    "10.1021/acs.jpclett.5c03195": {
        "pages": 8,
        "md5": "4923de84507a071deee79b39c33fc3d3",
        "notes": (
            f"{MARKER}: read all 8 article pages, all 29 technical-SI pages, and all 14 pages of "
            "the local peer-review file, including active spaces, trajectory counts/convergence, "
            "hopping distributions, reviewer-raised limitations, and author responses. MRSF-TDDFT "
            "tracks MS-CASPT2 dynamics well for ethylene; functional dependence is larger for "
            "DMABN/fulvene, with DTCAM-VAEE best. Each method starts from 300 Wigner samples, and "
            "the SI reports collapsed/effective trajectories; transfer to larger/SOC-dominated "
            "systems remains unproven. Main PDF MD5 4923de84507a071deee79b39c33fc3d3."
        ),
        "fields": {
            "active_space_protocol": "SA/MS-CAS references: ethylene CAS(2,2), DMABN CAS(10,10), fulvene CAS(6,6); global-flux surface hopping uses 300 initial samples with convergence/effective counts in local SI.",
            "geometry_source": "BH&HLYP ground-state minima/frequencies and Wigner sampling; on-the-fly 200/100/50 fs trajectories for ethylene/DMABN/fulvene, respectively.",
        },
    },
    "10.1063/1.4983704": {
        "pages": 12,
        "md5": "1634db907f3ad325d4ffce9e89b56181",
        "notes": (
            f"{MARKER}: read all 12 article pages, including 193 nm velocity-map imaging, H-atom "
            "detection, product translational distributions, all dissociation curves/state "
            "assignments, comparison with earlier work, conclusions, and references. The dominant "
            "N,N-dimethylformamide channels are N-CO cleavage to HCO+N(CH3)2 and CH3 loss; slow/"
            "fast H signals include secondary HCO photolysis. CASPT2 curves rationalize access "
            "along N-CO, N-CH3, and aldehydic C-H coordinates rather than claiming a single path. "
            "Source PDF MD5 1634db907f3ad325d4ffce9e89b56181."
        ),
        "fields": {
            "active_space_protocol": "SA-CASSCF(12,9) spans three sigma, two sigma*, O lone-pair, C=O pi/pi*, and N p orbitals; CASPT2 follows the relevant ground/excited dissociation cuts.",
            "geometry_source": "Ground-state equilibrium geometry and relaxed/rigid dissociation-coordinate cuts along N-CO, N-CH3, and C-H compared with 193 nm fragment imaging.",
        },
    },
    "10.1063/1.2943147": {
        "pages": 8,
        "md5": "aa787aaa549b67455982b9eb132bbd4d",
        "notes": (
            f"{MARKER}: read all 8 article pages, including global cluster selection, all six "
            "defect structures, RASSCF active-space selection, CASPT2 versus hybrid-TDDFT spectra, "
            "charge-transfer/local classifications, conclusions, and references. CASPT2 is the "
            "benchmark: B3LYP underestimates charge-transfer excitation energies because of its "
            "lower exact exchange, while BB1K is generally closer but neither hybrid is uniformly "
            "reliable. The six AIMDb rows are distinct Si4O8 low-energy defect isomers. Source "
            "PDF MD5 aa787aaa549b67455982b9eb132bbd4d."
        ),
        "fields": {
            "active_space_protocol": "RASSCF prescreening selects defect-centered occupied/virtual orbitals for isomer-specific CAS(12,12), CAS(14,14), or CAS(16,16); CASPT2 correlates all Si 3s/3p and O 2s/2p valence electrons outside the active space.",
            "geometry_source": "Low-energy Si4O8 cluster isomers from global optimization, reoptimized for the compared ground-state methods before vertical excitations.",
        },
    },
    "10.1063/5.0030944": {
        "pages": 10,
        "md5": "f432a91a7215c2128e861c10b4971d18",
        "notes": (
            f"{MARKER}: read all 10 article pages, including derivation of two symmetry-aware "
            "XDW exponents, all five photochemical tests, parameter limits, discontinuity/state-"
            "mixing analysis, conclusions, and references. The new exponents prevent mixing of "
            "different irreducible representations and recover the accuracy of multistate CASPT2; "
            "one becomes parameter-free in the fully state-specific limit. Pyridine, ethene, "
            "thymine, Mo2+, and PSB3 are distinct stress tests with source-tabulated spaces. "
            "Source PDF MD5 f432a91a7215c2128e861c10b4971d18."
        ),
        "fields": {
            "active_space_protocol": "System-specific SA-CASSCF spaces feed MS-, XMS-, XDW-, and RMS-CASPT2; symmetry-aware dynamic weights are varied through state-averaged to state-specific limits.",
            "geometry_source": "Established benchmark geometries/coordinates and reaction cuts for pyridine, ethene, thymine, Mo2+, and PSB3 as specified in each test.",
        },
    },
    "10.1063/1.3474571": {
        "pages": 13,
        "md5": "bec0252b9923d37c9d716d469fbf14e5",
        "notes": (
            f"{MARKER}: read all 13 article pages, including relativistic Hamiltonians, symmetric "
            "dissociation curves for I3-/I3, method-by-method state comparisons, intruder/symmetry "
            "analysis, conclusions, and references. Four-component MRCI and Fock-space coupled "
            "cluster provide benchmarks. SO-CASPT2 is economical and reasonable near equilibrium "
            "but is strongly symmetry-sensitive and develops intruder-state spikes away from "
            "equilibrium that level shifts did not cure; this limitation is retained explicitly. "
            "Source PDF MD5 bec0252b9923d37c9d716d469fbf14e5."
        ),
        "fields": {
            "relativistic_treatment": "DKH/SO-RASSI for CASPT2 comparison; four-component Dirac-Coulomb(-Gaunt) treatments in relativistic MRCI/FSCC benchmarks",
            "soc_included": "yes",
            "active_space_protocol": "CAS(16,9) for I3- and (15,9) for I3 in iodine sigma/pi valence orbitals, with RASSI SOC; matched Kramers-pair relativistic MRCI spaces benchmark the two-step treatment.",
            "geometry_source": "Linear symmetric I-I dissociation coordinate and near-equilibrium geometries; no asymmetric CASPT2 scan is treated as reliable because of symmetry breaking.",
        },
    },
    "10.1063/1.4818727": {
        "pages": 5,
        "md5": "3f0d0b7b432aaafd8b8f6bf01ab55eef",
        "notes": (
            f"{MARKER}: read all 5 communication pages, including every radical structure, "
            "ten-root excitation table/spectrum, experimental reassignment, summary, and references. "
            "CASPT2//CASSCF treats C5/C6 OH-addition radicals of uracil/thymine/cytosine and four "
            "H-abstraction radicals of 5,6-dihydrouracil. It excludes C5OH as the main uracil "
            "transient contributor and provides a unified assignment based on band positions/"
            "intensities; the 10 rows are chemically distinct radicals, not calculation steps. "
            "Source PDF MD5 3f0d0b7b432aaafd8b8f6bf01ab55eef."
        ),
        "fields": {
            "active_space_protocol": "Ten-root SA-CASSCF/CASPT2 with CAS(15,10) for unsaturated OH-addition radicals and CAS(11,8) for dihydrouracil abstraction radicals.",
            "geometry_source": "CASSCF optimized radical minima; vertical CASPT2/ANO-L spectra convoluted for comparison with transient UV-vis experiments.",
        },
    },
    "10.1063/1.4928588": {
        "pages": 13,
        "md5": "8c85448e364577f420ebd0215b37f88c",
        "notes": (
            f"{MARKER}: read all 13 article pages, including neutral/mono-/dication structures, "
            "scalar-relativistic CASSCF/CASPT2, CASSI spin-orbit states, transition moments/Einstein "
            "coefficients at 298/3000 K, thermodynamic implications, conclusions, and references. "
            "The six species are the three charge states of both NpO and NpO2. SO-CASPT2 assigns "
            "their dense low-lying spectra and temperature-dependent intensities; different active "
            "electron counts reflect ionization, not duplicated protocols. Source PDF MD5 "
            "8c85448e364577f420ebd0215b37f88c."
        ),
        "fields": {
            "relativistic_treatment": "Douglas-Kroll-Hess scalar relativity followed by CASSI spin-orbit coupling",
            "soc_included": "yes",
            "active_space_protocol": "NpO uses 16 active orbitals with 11/10/9 electrons for neutral/+1/+2; NpO2 uses 14 orbitals with 11/10/9 electrons, spanning Np 7s/6d/5f and selected O bonding/antibonding orbitals.",
            "geometry_source": "Scalar-relativistic CASSCF/CASPT2 optimized gas-phase NpO/NpO2 charge-state geometries used for SO-CASSI spectra.",
        },
    },
}


ROW_UPDATES: dict[str, dict[str, str]] = {
    "W7165173266-a": {
        "electronic_structure_description": (
            "CASSCF(2,2)//M06-2X diradical index y0=0.60. The open-shell singlet is "
            "the ground state; wB97X-D gives an open-singlet/triplet gap of -9.80 kJ mol-1."
        ),
        "Other": (
            "M06-2X sigma closure: DeltaG‡=43.16 and DeltaG=-54.67 kJ mol-1 "
            "(k=1.2e5 s-1, tau=1.2e-6 s at 293 K). C1 alkoxy migration barrier "
            "107.34 kJ mol-1 (tau=2.2e6 s)."
        ),
    },
    "W7165173266-b": {
        "electronic_structure_description": (
            "CASSCF(2,2)//M06-2X diradical index y0=0.72. The open-shell singlet is "
            "the ground state; wB97X-D gives an open-singlet/triplet gap of -2.88 kJ mol-1."
        ),
        "Other": (
            "No stable sigma-bonded minimum or C1-migration saddle point was located; "
            "the calculations instead predict rapid C-O bond cleavage."
        ),
    },
    "W7165173266-c": {
        "electronic_structure_description": (
            "The open-shell singlet is the ground state; wB97X-D gives an open-singlet/"
            "triplet gap of -3.31 kJ mol-1. SP1 is the paper's optimum strain/flexibility case."
        ),
        "Other": (
            "M06-2X sigma closure: DeltaG‡=72.52 and DeltaG=+50.72 kJ mol-1 "
            "(k=0.72 s-1, tau=1.3 s); strain energy 134.68 kJ mol-1. C1 and C3 "
            "migration barriers are 140.68 and 86.21 kJ mol-1, respectively."
        ),
    },
    "W7165173266-d": {
        "electronic_structure_description": (
            "The open-shell singlet is the ground state; wB97X-D gives an open-singlet/"
            "triplet gap of -5.70 kJ mol-1."
        ),
        "Other": (
            "M06-2X sigma closure: DeltaG‡=18.09 and DeltaG=-37.25 kJ mol-1 "
            "(k=3.6e9 s-1, tau=2.7e-10 s); strain energy 75.13 kJ mol-1. C1 and C3 "
            "migration barriers are 122.94 and 105.95 kJ mol-1, respectively."
        ),
    },
    "W7165173266-e": {
        "electronic_structure_description": (
            "The open-shell singlet is the ground state; wB97X-D gives an open-singlet/"
            "triplet gap of -8.70 kJ mol-1."
        ),
        "Other": (
            "M06-2X sigma closure: DeltaG‡=26.94 and DeltaG=-28.76 kJ mol-1 "
            "(k=4.0e7 s-1, tau=2.5e-8 s); strain energy 58.31 kJ mol-1. C1 and C3 "
            "migration barriers are 80.59 and 78.84 kJ mol-1, respectively."
        ),
    },
    "W1971437397-a": {
        "electronic_structure_description": (
            "The two 1,2-diphosphacyclobutadiene bond-stretch isomers 6 and 7 remain "
            "distinct CASSCF minima. Closed-shell 6 is 13.1 kJ mol-1 below 7 at CBS-QB3; "
            "CASPT2 places open-shell 6' 19.2 kJ mol-1 below 7', while MR-ACPF-2 makes "
            "the open-shell structures more stable than their closed-shell analogues."
        ),
        "Other": (
            "Closed-shell head-to-head formation of 1,2-DPCB 6 has an approximately "
            "260 kJ mol-1 Gibbs barrier. The open-shell route begins with a 98.9 kJ mol-1 "
            "barrier to 16' and reaches 7' over a further 31.3 kJ mol-1 barrier."
        ),
    },
    "W1971437397-b": {
        "electronic_structure_description": (
            "1,3-Diphosphacyclobutadiene 13 has localized single/double C-P bonds and is "
            "strongly antiaromatic (reported NICS = +36.2); its CASSCF open-shell analogue "
            "has more balanced bonds and is thermodynamically preferred."
        ),
        "Other": (
            "Closed-shell head-to-head formation of 13 has a 159.6 kJ mol-1 Gibbs barrier "
            "and product Gibbs energy 0.3 kJ mol-1 below two HCP molecules; the head-to-tail "
            "route has a 207.3 kJ mol-1 barrier. The open-shell branch through 15' reaches "
            "13' over a 141.1 kJ mol-1 barrier."
        ),
    },
}


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-only", action="store_true")
    parser.add_argument("--repair-format", action="store_true")
    args = parser.parse_args()

    if args.repair_format:
        fields, rows = load(DATABASE)
        with DATABASE.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)

        log_fields, logs = load(EXTRACTIONS)
        new_logs = [row for row in logs if MARKER in row.get("reasoning", "")]
        if len(new_logs) != len(PAPER_UPDATES):
            raise RuntimeError(
                f"expected {len(PAPER_UPDATES)} reread logs, found {len(new_logs)}"
            )
        base = subprocess.check_output(
            ["git", "show", f"HEAD:{EXTRACTIONS.relative_to(ROOT)}"], cwd=ROOT
        )
        if MARKER.encode() in base:
            raise RuntimeError("HEAD unexpectedly already contains reread audit records")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=log_fields, lineterminator="\r\n")
        writer.writerows(new_logs)
        EXTRACTIONS.write_bytes(base + buffer.getvalue().encode("utf-8"))
        print("restored historical CSV formatting and retained reread records")
        return

    fields, rows = load(DATABASE)
    matched: dict[str, list[dict[str, str]]] = {doi: [] for doi in PAPER_UPDATES}
    changed: list[dict[str, str]] = []
    for row in rows:
        doi = row["reference_doi"].strip().casefold()
        update = PAPER_UPDATES.get(doi)
        if update is None:
            continue
        matched[doi].append(row)
        row["notes"] = str(update["notes"])
        for field, value in dict(update.get("fields", {})).items():
            row[field] = str(value)
        for field, value in ROW_UPDATES.get(row["entry_id"], {}).items():
            row[field] = value
        changed.append(row)

    missing = [doi for doi, paper_rows in matched.items() if not paper_rows]
    if missing:
        raise RuntimeError(f"no database rows found for: {missing}")

    print(f"paper updates: {len(PAPER_UPDATES)}")
    print(f"row updates: {len(changed)}")
    if not args.apply and not args.database_only:
        return

    with DATABASE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    if args.database_only:
        print("applied database updates only")
        return

    log_fields, logs = load(EXTRACTIONS)
    if any(MARKER in row.get("reasoning", "") for row in logs):
        raise RuntimeError("reread audit records already exist; refusing to append twice")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    for doi, update in PAPER_UPDATES.items():
        paper_rows = matched[doi]
        logs.append({
            "timestamp": now,
            "key": paper_rows[0]["entry_id"].rsplit("-", 1)[0],
            "doi": doi,
            "action": "comprehensive-reread",
            "result": f"updated {len(paper_rows)} aimdb row(s)",
            "reasoning": (
                f"{MARKER}: read all {update['pages']} main-article pages and available "
                f"supporting files; replaced boilerplate notes and corrected only "
                f"source-explicit fields. Main PDF MD5 {update['md5']}."
            ),
        })
    with EXTRACTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=log_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(logs)

    print("applied database updates and appended reread audit records")


if __name__ == "__main__":
    main()
