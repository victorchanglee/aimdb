#!/usr/bin/env python3
"""Apply the GPT-5.6 comprehensive reread for database records 2000-2400."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "aimdb.csv"
EXTRACTIONS = ROOT / "logs" / "extractions.csv"
MANIFEST = Path("/tmp/aimdb_reread2000_2400_manifest.csv")
MARKER = "GPT-5.6 comprehensive reread (2026-08-19; records 2000-2400 audit)"


# Each statement below comes from a full-article/dataset reread, not a keyword hit.
FINDINGS: dict[str, str] = {
    "10.1016/j.cplett.2017.03.074": (
        "PBE-D3/ZORA geometries were followed by DKH/ANO-RCC SA-CASSCF/CASPT2; the analysis assigns substantial covalent Au-Ln bonding involving Au 6s and lanthanide 5d orbitals."
    ),
    "10.1063/1.5115819": (
        "The paper derives and implements analytic PC-NEVPT2 gradients and dipoles, validates them against numerical derivatives, and benchmarks optimized structures and 0-0 energies from small molecules through polyacetylenes."
    ),
    "10.1063/1.3636084": (
        "Four-component MRCI/FSCC and two-step SO-CASPT2/SO-DDCI comparisons show that the two-step treatment recovers roughly 80% of the chalcogen-diatomic zero-field splittings and exposes state-dependent limitations."
    ),
    "10.1063/1.2187974": (
        "For oxo-Mn(salen), Hartree-Fock is qualitatively inadequate and common DFT functionals give inconsistent spin ordering; the large and reduced CASSCF spaces clarify the competing singlet, triplet, and quintet configurations."
    ),
    "10.1063/1.3651536": (
        "A five-state SA-CASSCF/MRCI wave-packet model follows pyrrole excitation into coupled valence/Rydberg states and the subsequent nonadiabatic N-H photodissociation pathways."
    ),
    "10.1063/1.5025942": (
        "CAS+DDCI, CC2, and MS-CASPT2 comparisons on model-protein local and charge-transfer states find CC2 accurate to about 0.1 eV for the first excitation but progressively less reliable for higher states."
    ),
    "10.1063/5.0087743": (
        "Two-color resonant four-wave-mixing spectra and state-averaged MCSCF-RAS/MRCI+Q calculations jointly assign a previously uncharacterized high-lying 0u+ rovibronic state of Cu2."
    ),
    "10.1063/1.4948956": (
        "The dynamics use semiempirical OM2/MRCISD rather than an AO-basis CASSCF calculation; adaptive time steps reduce wasted electronic-structure calls while retaining the successful-trajectory statistics for both chromophores."
    ),
    "10.1063/5.0010019": (
        "ORCA CASPT2-K changes the zeroth-order Hamiltonian to reduce empirical IPEA dependence; Cr2 curves and molecular benchmarks compare it directly with standard CASPT2, IPEA-CASPT2, and NEVPT2."
    ),
    "10.1063/5.0051211": (
        "The first approximate-RDM NEVPT2 study evaluates EPS, PS, and CU reconstructions across conjugated molecules and transition-metal systems, quantifying where lower-rank density information reproduces fully internally contracted results."
    ),
    "10.1063/1.4833563": (
        "Gas-phase stationary points and aqueous QM/MM trajectories show how explicit water modifies thymine's ultrafast internal-conversion routes among pi-pi*, n-pi*, and ground states."
    ),
    "10.1063/1.2202738": (
        "The decontraction algorithm converts internally contracted state-specific multireference functions into finite-difference references and is tested for SC/PC-NEVPT2 and NEVPT3 on several chemically distinct benchmarks."
    ),
    "10.1063/1.4989465": (
        "MS-CASPT2 structures, vibrations, and decay paths show that trimethylenecytosine planarization reshapes the S1 surface and the access to competing conical-intersection channels."
    ),
    "10.1063/1.5064716": (
        "Seven-state SA-CASSCF/CASPT2 calculations assign the low-energy electronic spectrum of methyl vinyl ketone oxide and characterize the six lowest singlet excitations."
    ),
    "10.1063/1.4972812": (
        "DKH/ANO-RCC CASSCF, CASPT2, and CASSI spin-orbit calculations determine ground terms and dense low-lying manifolds for ThC, UC, PuC, and AmC through about 17000 cm-1."
    ),
    "10.1063/1.468587": (
        "Planar and twisted bithiophene spectra require a ten-pi-orbital reference, with targeted orbital additions for the 2^1Ag and Rydberg states; CASPT2 corrects the CASSCF state ordering."
    ),
    "10.1002/jcc.24260": (
        "MP2 structures feed a 25-root SA-CASSCF/MS-CASPT2 description and nonadiabatic dynamics of HCFC-132b, resolving the valence/Rydberg excitation manifold and ultrafast C-Cl dissociation."
    ),
    "10.1002/poc.972": (
        "SA-CASSCF/CASPT2 calculations compare the electronic spectra and solvent response of hydroxy- and methoxybenzoylpyrrole, including the role of intramolecular proton transfer in the hydroxy compound."
    ),
    "10.1021/acs.jctc.6b00915": (
        "Five singlets and five triplets from SA-CASSCF/MS-CASPT2/RASSI-SO provide the correlated reference used to assess linear-response TDDFT spin-orbit couplings for 2-thiothymine."
    ),
    "10.1021/ct900282m": (
        "Systematic CAS/RAS expansions on Cu-O2 models show that small frontier spaces can give qualitatively misleading singlet-triplet gaps and that balanced metal, oxygen, and correlating orbitals are essential."
    ),
    "10.1021/acs.jctc.9b00396": (
        "Three-state XMS-CASPT2 surface hopping over 136 trajectories gives a 47+/-8% ring-opening yield, an 89+/-9 fs excited-state lifetime, and an extended S1/S0 intersection seam for cyclohexadiene."
    ),
    "10.1021/ja077322o": (
        "CASPT2 supports the D2d WH4(H2)4 assignment of the matrix-isolation IR spectrum and predicts an average H2 binding energy of about 15 kcal mol-1."
    ),
    "10.1021/jo062420y": (
        "MS-CASPT2 places calicene's principal gas-phase transition near 4.93 eV and finds that access to the rotational surface does not make cis-trans photoisomerization efficient."
    ),
    "10.1021/jp056791e": (
        "Active-space sensitivity along the Cu2O2 bis-mu-oxo/side-on-peroxo track shows that CASPT2 over-stabilizes the bis-mu-oxo form relative to the best coupled-cluster benchmarks."
    ),
    "10.1021/acs.jpca.4c04148": (
        "A delta-delta-E strategy compares CASPT2, MC-PDFT, and DFT for low-spin/high-spin gaps of Fe tris-diimine complexes and separates geometry, ligand, and dynamic-correlation errors."
    ),
    "10.1021/acs.jpca.6b05110": (
        "MS-CASPT2/RASSI-SO shows that replacing different thymine oxygens by sulfur changes the ordering and character of the lowest singlets/triplets and therefore the preferred intersystem-crossing routes."
    ),
    "10.1021/acs.jpca.6b05180": (
        "The multistate CASPT2 benchmark attributes the guanidinium auxochromic effect to state-specific mixing of aryl pi and guanidinium/lone-pair orbitals rather than a uniform spectral shift."
    ),
    "10.1021/acs.jpca.9b04372": (
        "The reported trajectories use semiempirical OM2/MRCISD and therefore no AO basis set; the simulations connect ring constraint to stereoselective azobenzene isomerization and decay."
    ),
    "10.1021/om701153t": (
        "CASSCF/CASPT2 supports a delicate spin equilibrium in the dichromium pentalene double-sandwich complex and ties it to the Cr-Cr and metal-ligand multiconfigurational bonding pattern."
    ),
    "10.1021/om900750t": (
        "CASPT2 geometries and vibrational frequencies assign the matrix IR bands of small Pd insertion and methylidene products and distinguish competing structures formed from methane precursors."
    ),
    "10.1007/s002140050246": (
        "CASSCF/CASPT2 mapping of the N8 cubane-to-pentalene rearrangement identifies the transition structure and demonstrates how enlargement of the rearrangement active space changes the barrier description."
    ),
    "10.1007/s00894-011-1283-1": (
        "SA-CASSCF/MS-CASPT2 energetics and minimum-energy crossing calculations distinguish spin-allowed and spin-forbidden oxygenation channels for the phenylhalocarbenes."
    ),
    "10.1063/1.5129029": (
        "Core-valence CASCI/NEVPT2 with QDPT spin-orbit coupling reproduces V L2,3-edge absorption/XMCD band positions and signs and explains the intensity through coupled core and valence multiplets."
    ),
    "10.1063/5.0038047": (
        "CASSCF/SS-CASPT2 scans show that Mg4 binding to NH3, H2O, and HF can trigger pronounced cluster and substrate bonding rearrangements, with active-space expansions used as explicit stability checks."
    ),
    "10.1063/5.0011948": (
        "Multistate CASPT2 potential surfaces and wave-packet calculations resolve the coupled channels and product branching in ultraviolet methanol photodissociation."
    ),
    "10.1016/j.cplett.2006.04.073": (
        "Full-valence CASSCF(12,10) and MRCI+Q/aug-cc-pVQZ surfaces provide the recommended balanced description of ground and low-lying excited N2H2 isomers and dissociation pathways."
    ),
    "10.1016/j.cplett.2017.03.007": (
        "MOLPRO SA3-CASSCF(2,2)/cc-pVDZ Ehrenfest dynamics for 1000 ethylene trajectories show that ultrafast electron diffraction is substantially more sensitive to hydrogen motion than the X-ray signal."
    ),
    "10.1016/j.cplett.2025.142096": (
        "A 21-molecule benchmark tests MS-NEVPT2 and SDSPT2 for high-lying valence excitations, documents root and intruder sensitivity, and evaluates real level shifts."
    ),
    "10.1016/j.combustflame.2025.114232": (
        "CASPT2-F12(2,2)/cc-pVTZ-F12 energies coupled to RRKM/master-equation kinetics establish the competing channels and pressure/temperature dependence of CH3 + NH2 combustion chemistry."
    ),
    "10.1016/j.combustflame.2026.115037": (
        "DLPNO-NEVPT2(11,11)/cc-pVTZ calculations and kinetic modeling revise the elementary pathways governing pyrrole pyrolysis and their contribution to product formation."
    ),
    "10.1016/j.jlumin.2018.02.066": (
        "The article combines a critical nucleobase photophysics review with its own CASPT2 examples, emphasizing why similar vertical spectra can lead to emissive or rapidly nonradiative behavior."
    ),
    "10.1016/j.jms.2024.111902": (
        "A CAS(9,8) spin-orbit treatment computes N2+ rovibronic transition strengths and identifies the intensity-borrowing mechanisms needed to reproduce weak observed bands."
    ),
    "10.1063/5.0165769": (
        "CASPT2 and coupled-cluster potential surfaces predict NO(A 2Sigma+)--CO2 van der Waals wells as deep as about 830 cm-1 and characterize their anisotropy and bound states."
    ),
    "10.1063/5.0262473": (
        "ICE-SCF references combined with full-rank NEVPT2 extend the method to active spaces as large as CAS(34,34) while controlling approximate-RDM errors."
    ),
    "10.1063/5.0320535": (
        "MS-CASPT2 nonadiabatic dynamics reproduce the femtosecond and picosecond stages of pyrazine relaxation and predict intersystem crossing on an approximately 10 ps scale, where TDDFT becomes unreliable."
    ),
    "10.1063/5.0051218": (
        "The second full-rank NEVPT2 paper demonstrates that the formulation avoids false intruder states generated by approximate reference density matrices and analyzes the remaining reconstruction error."
    ),
    "10.1063/5.0072129": (
        "An efficient internally contracted NEVPT2/CASPT2 implementation avoids explicit high-order RDM storage and benchmarks the resulting scaling and accuracy."
    ),
    "10.1063/5.0327441": (
        "Multireference calculations reinterpret the Fe(IV)-superoxide/perferrate electronic structures and show how metal-oxygen covalency and spin coupling alter their conventional oxidation-state labels."
    ),
    "10.1063/1.1385151": (
        "CASSCF/MRCI potential surfaces and scattering analysis identify the coupled pathways and product channels for the N(2D) + O2 reaction."
    ),
    "10.1088/1402-4896/ad2145": (
        "Relativistic multireference potential curves and transition properties assign the low-lying electronic states and spectroscopic constants of BaLi+."
    ),
    "10.1002/anie.202513772": (
        "SS-CASSCF(2,2) gives natural occupations 1.915/0.085 and a 9% beta diradical index for the bicyclo[1.1.0]tetragermane diradicaloid; the main article does not state the CASSCF software or basis, so those cells remain blank."
    ),
    "10.1002/cptc.201900072": (
        "Multistate calculations connect the contrasting emissive behavior of thionated cytosine/uracil analogues to their low-lying singlet/triplet state ordering and intersection accessibility."
    ),
    "10.1002/cptc.202200010": (
        "RASSCF and TDDFT analyses track photoinduced charge separation in a push-pull ruthenium complex and identify the ligand/metal orbital rearrangements behind the long-range state."
    ),
    "10.1088/1674-1056/ae12df": (
        "Spin-orbit multireference curves yield ground-state assignments, term energies, and spectroscopic constants for RhC and IrC, with relativistic effects central to the state ordering."
    ),
    "10.1002/vjch.70062": (
        "DMRG-CASPT2 calculations across CrBn clusters assign size-dependent ground states and expose changes in metal-boron bonding that are not captured by a single-reference picture."
    ),
    "10.1039/c7cp01331k": (
        "DMRG-CASPT2 and coupled-cluster calculations on a QM/MM NiFe-hydrogenase model find singlet H2 binding at Ni at least 47 kJ mol-1 more favorable than the competing descriptions."
    ),
    "10.1021/ct5010388": (
        "A state-specific polarizable QM/MM correction to MS-CASPT2(14,10)/cc-pVTZ shows that aqueous cytosine's n-pi* excitation lies above 6 eV and quantifies solvent polarization effects."
    ),
    "10.1021/acs.jpca.9b01397": (
        "CASPT2 calculations with a primary CAS(16,12) and targeted smaller spaces map 7-azaguanine's bright, dark, and intersection states that govern its nonradiative decay."
    ),
    "10.1139/cjc-2022-0267": (
        "Wave-packet tests starting from localized and delocalized vibrational functions for 1,1-difluoroethylene show no significant difference in the predicted dynamics or spectrum."
    ),
    "10.3390/ijms27156627": (
        "MNDO99 OM2/MRCI dynamics with a 16-electron/16-orbital pi space show competing E/Z photoisomerization and excited-state proton-transfer channels in the molecular motor."
    ),
    "10.1021/acs.jctc.7b00735": (
        "DMRG-cu(4)-XMS-CASPT2 with CAS(26,24) provides a balanced description of diarylethene open/closed forms and their low-lying photochemical states."
    ),
    "10.1039/d4cp04873c": (
        "CASPT2-F12 calculations with spaces through 13 electrons in 15 orbitals underpin a pressure- and temperature-dependent kinetic mechanism for methanethiol pyrolysis."
    ),
    "10.1039/d6cp01598k": (
        "ORCA 6.1 SA-CASSCF(12,12) surfaces quantify exchange-vibronic coupling and the characteristic pancake bonding of stacked pi diradicals."
    ),
    "10.1039/d6qi00728g": (
        "A 13-electron/17-orbital RASSCF partition resolves the dense spin-state and ligand-field manifold of Cr(phen)3 and its spectroscopic assignments."
    ),
    "10.1021/acs.inorgchem.7b00701": (
        "MOLCAS CASSCF(7,9)/RASSI/SINGLE_ANISO calculations on X-ray-derived Dy models quantify how solid-state ligand substitution changes crystal-field states and magnetic anisotropy."
    ),
    "10.1021/acs.inorgchem.7b00877": (
        "CASSCF(4,5) per Mn center with RASSI/SINGLE_ANISO on experimental structures analyzes local anisotropy in the Mn dimers; the main article does not state the multireference basis set."
    ),
    "10.1021/acs.inorgchem.8b00427": (
        "Ab initio crystal-field and exchange calculations explain the slow magnetic relaxation and coupled anisotropy of the dinuclear Dy single-molecule magnet."
    ),
    "10.1021/acs.inorgchem.8b01688": (
        "CASSCF/SINGLE_ANISO comparisons across lanthanide 18-crown-6 complexes connect the experimental relaxation trends to ion-specific crystal-field state compositions."
    ),
    "10.1021/jacs.5c11362": (
        "X-ray-geometry CASSCF/RASSI calculations use CAS(8,7) for the neutral and CAS(9,8) for the radical triple deckers and support antiferromagnetic Ln-radical coupling near -0.45 cm-1; software and basis are SI-only and remain blank."
    ),
    "10.1021/ja106329t": (
        "Multireference calculations show how through-bond communication tunes singlet-triplet gaps and diradical character across the bicycloalkatetraene series."
    ),
    "10.3390/chemistry6060095": (
        "Embedded 2M/MgO and 2M/BaO cluster calculations compare surface-supported metal-pair diradicals and identify support-dependent changes in coupling and frontier occupations."
    ),
    "10.1021/jp306218z": (
        "Multireference reaction surfaces locate the entrance complexes, crossings, and product channels controlling O + CS reactivity."
    ),
    "10.1088/1361-6455/ad9a2f": (
        "State-resolved multireference calculations assign the dissociative electron-ionization channels of OCS and relate the measured fragments to the accessible ionic surfaces."
    ),
    "10.1021/jp905462b": (
        "MOLCAS CASPT2/6-311+G(2df) calculations compare the radical-ion states of cyclobutanetetraone and provide an indirect experimental test of the predicted neutral 3B2u ground state."
    ),
    "10.17632/yr9trm7ysx.1": (
        "The archive contains 144 ORCA outputs for complete SA-CASSCF/MRACPF2a ArC+ potential curves, spanning the lowest 21 states over 70 geometries with aug-cc-pwCVTZ and aug-cc-pwCVQZ basis sets."
    ),
    "10.2139/ssrn.5234300": (
        "OpenMolcas 24.02 XMS-CASPT2(14,10)/ANO-RCC-VDZP maps the thio-caged switch from the bright S3 through dark S2 to S1; early intersystem crossing is a minor channel."
    ),
    "10.2139/ssrn.5279277": (
        "CASPT2(12,9) comparison values support the model-exact PPP/DVB analysis of thermally activated delayed fluorescence in star-fused benzotrithiophene isomers; the preprint does not explicitly tie a basis or program to CASPT2."
    ),
    "10.2139/ssrn.5289323": (
        "MOLPRO 2010.1 SS-CASPT2(6,5)/cc-pVTZ and NOPT CDAS-PT2 surfaces reveal strong torsion-inversion coupling in both cyclopropanecarboxylic acid halides."
    ),
    "10.2139/ssrn.5655502": (
        "OpenMolcas 24.10/Block2 calculations compare CASPT2(18,15) with DMRG-CASPT2(38,28), bond dimension 2000, to simulate vibrationally resolved oxyluciferin absorption and fluorescence spectra."
    ),
    "10.2139/ssrn.6297255": (
        "MOLPRO 2024 full-valence SA-CASSCF/icMRCI+Q/aug-cc-pVTZ curves characterize cis/trans HNNO spectroscopy and photochemistry; excited-state optimizations use a reduced CAS(11,10)."
    ),
    "10.2139/ssrn.6814820": (
        "MOLPRO 2012.1 CASSCF/cc-pVTZ treats all 18 valence electrons in 18 orbitals with symmetry/equivalence restrictions, reducing the ground-state benzene expansion to about 281000 CSFs."
    ),
    "10.2139/ssrn.6919244": (
        "MNDO99 OM2/MRCI nonadiabatic dynamics identify the competing decay channels of the PBQ ratiometric probe; because OM2 is semiempirical, no AO basis set applies."
    ),
    "10.2139/ssrn.7094198": (
        "OpenMolcas/GROMACS MS-CASPT2/MM with a five-state CAS(16,12)/cc-pVDZ reference compares triplet formation in thio- and seleno-psoralens in explicit aqueous environments."
    ),
    "10.2139/ssrn.5396947": (
        "MOLPRO multireference curves with a La segmented basis and H aug-cc-pVQZ, followed by MOLCAS VIBROT analysis, determine LaH term energies and spectroscopic constants."
    ),
    "10.26434/chemrxiv-2021-3p2sx": (
        "Periodic DMET/PySCF embeddings with progressively enlarged local active spaces recover multireference excited states of crystalline point defects; basis details are confined to unavailable SI and remain blank."
    ),
    "10.26434/chemrxiv-2021-6csxm": (
        "Machine-learned XMS-CASPT2(6,7)/aug-cc-pVDZ dynamics give substituent-dependent fluorobenzene lifetimes of roughly 64, 40, 18, and 8 ps and connect regioselectivity to pseudo-Jahn-Teller distortion."
    ),
    "10.26434/chemrxiv-2021-9ww0c-v2": (
        "Separately optimized RASSCF/MS-RASPT2 neutral and double-core-hole references reproduce double-core-hole spectral shifts and intensities without forcing a common orbital set."
    ),
    "10.26434/chemrxiv-2021-dnhxj": (
        "SC-NEVPT2 with CAS(4,4) reactants and CAS(8,8) transition structures on DFT geometries shows how XP-PCM pressure changes concerted versus stepwise cyclohexadiene dimerization barriers."
    ),
    "10.1021/acs.inorgchem.1c03005": (
        "BAGEL CASSCF/NEVPT2/cc-pVTZ calculations reproduce distinct Cr-Cr stretching modes near 196/266, 282, and 353 cm-1 and relate those frequencies to weak multiconfigurational metal-metal bonding."
    ),
    "10.1021/acs.jctc.1c01048": (
        "The first MC-PDFT nonadiabatic dynamics study uses SHARC thioformaldehyde trajectories and shows that the larger CAS(12,10) changes S1-to-T2 transfer by about a factor of 7.5 relative to CAS(10,6)."
    ),
    "10.26434/chemrxiv-2021-xr3x5": (
        "Analytic MC-PDFT dipoles reduce mean errors from about 0.77 D at CASSCF to roughly 0.24-0.29 D, with tPBE/tPBE0 and correlated-participating-orbital spaces giving the most consistent curves."
    ),
    "10.26434/chemrxiv-2022-14tkm": (
        "XMS-CASPT2-corrected dynamics predict gas-phase decarbonylation yields of 53% and 28% for two cyclopropenones, rising to about 58% in water, with 72/89 fs lifetimes."
    ),
    "10.1039/d2sc05839a": (
        "Complete local PMC full text shows that optimally tuned range-separated TDDFT misroutes the Fe photosensitizer dynamics, whereas CASPT2 deactivates into the metal-centered manifold in better agreement with experiment."
    ),
    "10.1021/acs.jctc.2c00368": (
        "Sigma-p regularization removes CASPT2 intruder singularities along Cr2 dissociation; sigma2 is smooth and slightly less parameter-sensitive, while sigma1 can be discontinuous at denominator sign changes."
    ),
    "10.26434/chemrxiv-2022-5v0tt": (
        "ORCA SC-NEVPT2 reaction paths with CAS(19,14) and CAS(17,13) show rapid Hg-radical oxidation by ozone and reduction channels that are roughly three to six orders of magnitude slower."
    ),
    "10.26434/chemrxiv-2022-b6078": (
        "XMS-CASPT2 minima, intersections, LIICs, and scans show how steric pretwisting and a nearby carbonyl n-pi* state select one-bond-flip photoisomerization routes in phytochrome models."
    ),
    "10.26434/chemrxiv-2022-cz4fr": (
        "OpenMolcas RASSCF/MS-RASPT2 with a one-center Auger approximation reproduces normal and resonant spectra for HNCO, NO2, and pyrimidine, including the high-binding-energy intensity gained with the expanded RAS."
    ),
    "10.26434/chemrxiv-2022-ls796": (
        "OpenMolcas CASSCF/CASPT2/MC-PDFT comparisons across Cr(IV) complexes connect active-space size and metal-ligand covalency to zero-field splitting trends relevant to molecular qubits."
    ),
    "10.26434/chemrxiv-2022-w1t0g-v2": (
        "Analytic gradients and couplings for MS/XMS/XDW/RMS CASPT2/RASPT2 show that RMS is least sensitive to the number of averaged states and that dioxetanone structures remain strongly partition-dependent."
    ),
}


# Only source-explicit, paper-wide values are applied to blank cells. Row-specific
# values already present in aimdb.csv are left untouched.
COMMON_FIELDS: dict[str, dict[str, str]] = {
    "10.1016/j.cplett.2017.03.074": {
        "geometry_source": "PBE-D3/ZORA optimized geometries; CASSCF/CASPT2 single-point bonding analysis.",
        "active_space_protocol": "Four electrons distributed over three Au 6s-derived and five lanthanide 5d-derived orbitals; ten singlet roots state averaged.",
    },
    "10.1063/1.3651536": {
        "geometry_source": "Five-state diabatic potential surfaces constructed for quantum wave-packet propagation from the pyrrole ground-state structure.",
        "active_space_protocol": "SA5-CASSCF(6,5) orbital reference; MRCI uses a CAS(4,4) reference augmented by the 3s Rydberg orbital.",
    },
    "10.1063/5.0087743": {
        "geometry_source": "Cu-Cu potential-energy curves and rovibrational levels compared directly with the new two-color spectroscopic progression.",
        "active_space_protocol": "State-averaged RAS with Cu 3d/4s/4p orbitals, at most one 3d hole and one 4p electron, followed by internally contracted MRCI+Q.",
    },
    "10.1063/1.4948956": {
        "geometry_source": "OM2/MRCISD nonadiabatic trajectories initialized from the paper's chromophore sampling protocol.",
        "active_space_protocol": "OHBI uses 12 electrons in 12 conjugated pi orbitals; F-NAIBP uses 8 electrons in 9 pi orbitals before MRCISD and surface hopping.",
    },
    "10.1063/5.0010019": {
        "software": "ORCA",
        "geometry_source": "Fixed molecular benchmark structures and a Cr-Cr dissociation grid used to compare zeroth-order Hamiltonians.",
        "active_space_protocol": "Common CASSCF references were reused for CASPT2, CASPT2-K, IPEA-CASPT2, and NEVPT2 comparisons; Cr2 uses CAS(12,12).",
    },
    "10.1002/jcc.24260": {
        "geometry_source": "MP2/aug-cc-pVTZ ground-state geometry from Gaussian 09; excited-state sampling and dynamics at SA-CASSCF/MS-CASPT2.",
        "active_space_protocol": "CAS(12,12) state averaged over 25 singlet roots spanning sigma/sigma-star, valence, and Rydberg orbitals.",
    },
    "10.1021/acs.jctc.6b00915": {
        "active_space_protocol": "CAS(14,10) with separate equal-weight state averages over five singlets and five triplets before MS-CASPT2/RASSI-SO.",
    },
    "10.1021/acs.jctc.9b00396": {
        "geometry_source": "PBE0 ground-state/Wigner initial sampling followed by on-the-fly three-state XMS-CASPT2 surface-hopping trajectories.",
        "active_space_protocol": "Three-state SA-CASSCF(6,6) pi reference followed by XMS-CASPT2 with a 0.5 a.u. level shift.",
    },
    "10.1021/jo062420y": {
        "geometry_source": "CASSCF/MS-CASPT2 stationary structures and scans along the inter-ring rotational coordinate, with PCM comparisons where reported.",
        "active_space_protocol": "Full CAS(8,8) pi space retained across the low-energy singlet/triplet and rotation calculations.",
    },
    "10.1021/acs.jpca.9b04372": {
        "geometry_source": "OM2/MRCISD nonadiabatic trajectories initiated from the cis-cyclobiazobenzene excited-state ensemble.",
    },
    "10.1021/om701153t": {
        "geometry_source": "Experimental molecular structure and computed structures used to analyze the observed spin equilibrium.",
        "active_space_protocol": "CAS(10,12) spans Cr-Cr and metal-pentalene bonding/antibonding orbitals for singlet, triplet, and quintet states.",
    },
    "10.1016/j.cplett.2017.03.007": {
        "geometry_source": "SA3-CASSCF(2,2)/cc-pVDZ on-the-fly Ehrenfest trajectories; 1000 initial conditions sampled for ethylene.",
        "active_space_protocol": "Three equally treated singlet states in a two-electron/two-orbital ethylene pi/pi-star space.",
    },
    "10.1021/jp905462b": {
        "software": "MOLCAS; Gaussian 03 for B3LYP geometries and CCSD(T)",
        "basis_set": "6-311+G(2df)",
    },
    "10.17632/yr9trm7ysx.1": {
        "software": "ORCA",
        "basis_set": "aug-cc-pwCVTZ; aug-cc-pwCVQZ",
        "geometry_source": "Seventy-point Ar-C distance scans; each point uses preceding-point orbitals as the next SA-CASSCF guess.",
        "active_space_protocol": "SA-CASSCF followed by MRACPF2a; ORCA nroots sequence 2,3,2,2,3,3,3,3 spans the lowest 21 states.",
    },
    "10.2139/ssrn.5234300": {
        "software": "OpenMolcas 24.02; Gaussian 09 D.01 for ancillary DFT",
        "basis_set": "ANO-RCC-VDZP",
        "geometry_source": "Ground/excited stationary structures, interpolation paths, and state energies evaluated for the thio-caged SDMAP switch.",
        "active_space_protocol": "XMS-CASPT2(14,10) state manifold used consistently to follow S3 to S2 to S1 relaxation and crossing regions.",
    },
    "10.2139/ssrn.5289323": {
        "software": "MOLPRO 2010.1; NOPT for CDAS-PT2",
        "basis_set": "cc-pVTZ",
        "geometry_source": "SS-CASPT2 optimized minima and coupled torsion-inversion potential surfaces for each acid halide.",
        "active_space_protocol": "SS-CASPT2(6,5), independently checked with CDAS-PT2 along the coupled torsion and inversion coordinates.",
    },
    "10.2139/ssrn.5655502": {
        "software": "OpenMolcas 24.10; Block2-OpenMolcas interface",
        "basis_set": "ANO-RCC-VDZP",
        "geometry_source": "State-specific optimized structures and normal modes used for vibrationally resolved absorption/fluorescence simulations.",
        "active_space_protocol": "CASPT2(18,15) compared with DMRG-CASPT2(38,28), Block2 bond dimension 2000, for all four oxyluciferin chromophores.",
    },
    "10.2139/ssrn.6297255": {
        "software": "MOLPRO 2024",
        "basis_set": "aug-cc-pVTZ",
        "geometry_source": "Ground/excited cis/trans minima, potential curves, and dissociation coordinates optimized or scanned at SA-CASSCF/icMRCI+Q.",
        "active_space_protocol": "Full-valence SA-CASSCF with 3 doublet roots per A-prime/A-double-prime and 2 quartet roots per symmetry; excited optimizations use CAS(11,10).",
    },
    "10.2139/ssrn.6814820": {
        "software": "MOLPRO 2012.1",
        "basis_set": "cc-pVTZ",
        "geometry_source": "D2h ground-state benzene geometry used for the constrained all-valence CASSCF bonding analysis.",
        "active_space_protocol": "All 18 valence electrons in 18 orbitals with D2h symmetry and equivalency restrictions, reducing the expansion to about 281000 CSFs.",
    },
    "10.2139/ssrn.6919244": {
        "software": "MNDO99",
        "geometry_source": "OM2/MRCI on-the-fly nonadiabatic trajectories initialized from the PBQ excited-state sampling ensemble.",
        "active_space_protocol": "OM2/MRCI CAS-like reference with 14 electrons in 12 orbitals; no Gaussian AO basis applies to the semiempirical Hamiltonian.",
    },
    "10.2139/ssrn.7094198": {
        "software": "OpenMolcas py2.03; GROMACS",
        "basis_set": "cc-pVDZ",
        "geometry_source": "MS-CASPT2/MM stationary points and aqueous trajectories in explicit GROMACS environments for each psoralen.",
        "active_space_protocol": "Five-state SA-CASSCF/MS-CASPT2(16,12) reference used for the coupled singlet/triplet manifolds.",
    },
    "10.2139/ssrn.5396947": {
        "software": "MOLPRO; MOLCAS VIBROT",
        "basis_set": "SEG basis on La; aug-cc-pVQZ on H",
        "geometry_source": "La-H potential-energy curves followed by VIBROT rovibrational analysis.",
        "active_space_protocol": "CASSCF(4,10) orbital reference followed by internally contracted MRCI for the low-lying states.",
    },
    "10.26434/chemrxiv-2021-6csxm": {
        "geometry_source": "XMS-CASPT2(6,7)/aug-cc-pVDZ training geometries and machine-learned nonadiabatic trajectories.",
        "active_space_protocol": "Common CAS(6,7) reference along each fluorobenzene photochemical trajectory.",
    },
    "10.1021/acs.inorgchem.1c03005": {
        "geometry_source": "Optimized coordination-complex structures followed by Cr-Cr normal-mode scans and CASSCF/NEVPT2 harmonic analysis.",
        "active_space_protocol": "CAS(8,8) Cr-Cr bonding/antibonding reference followed by NEVPT2 for each complex.",
    },
    "10.1039/d2sc05839a": {
        "geometry_source": "Optimally tuned range-separated DFT structures/dynamics compared against the article's CASSCF/CASPT2 reference pathways.",
        "active_space_protocol": "CAS(10,12) reference used to establish the correlated state ordering and metal-centered deactivation route.",
    },
}


ROW_FIELDS: dict[str, dict[str, str]] = {
    "W2009567571-a": {
        "basis_set": "Li (9s5p)/[4s2p]; F (9s6p1d)/[4s3p1d]",
        "geometry_source": "Li-F bond-distance grid through the neutral/ionic avoided-crossing region.",
        "active_space_protocol": "Two-state-averaged CASSCF(2,2) over the Li 2s and F 2p_z orbitals; SC/PC-NEVPT2 and finite-difference decontraction compared with FCI.",
    },
    "W2009567571-b": {
        "basis_set": "Li (9s5p)/[4s2p]; F (9s6p1d)/[4s3p1d]",
        "geometry_source": "Li-F bond-distance grid through the neutral/ionic avoided-crossing region.",
        "active_space_protocol": "Two-state-averaged CASSCF(6,6) enlarged LiF valence space; SC/PC-NEVPT2 finite-difference decontraction compared with FCI.",
    },
    "W2009567571-c": {
        "basis_set": "cc-pVQZ, spherical (12s6p3d2f1g)/[5s4p3d2f1g]",
        "geometry_source": "F-F bond-distance grid in D2h symmetry.",
        "active_space_protocol": "CASSCF(2,2) F-F sigma/sigma-star reference followed by SC/PC-NEVPT2, SC-NEVPT3, and finite-difference decontraction.",
    },
    "W2009567571-d": {
        "basis_set": "cc-pVQZ, spherical (12s6p3d2f1g)/[5s4p3d2f1g]",
        "geometry_source": "F-F bond-distance grid in D2h symmetry.",
        "active_space_protocol": "Full-valence CASSCF(10,6) reference followed by SC/PC-NEVPT2, SC-NEVPT3, and finite-difference decontraction.",
    },
    "W2009567571-e": {
        "basis_set": "cc-pVQZ, spherical (12s6p3d2f1g)/[5s4p3d2f1g]",
        "geometry_source": "F-F bond-distance grid in D2h symmetry.",
        "active_space_protocol": "CASSCF(10,10) enlarges the full-valence space by two correlating 2p_x-prime and two 2p_y-prime orbitals before the NEVPT/decontraction comparisons.",
    },
}


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_manifest() -> dict[str, dict[str, str]]:
    if not MANIFEST.exists():
        raise RuntimeError(f"audit manifest is missing: {MANIFEST}")
    _, records = load_csv(MANIFEST)
    manifest = {record["doi"].casefold(): record for record in records}
    if set(manifest) != set(FINDINGS):
        missing = sorted(set(FINDINGS) - set(manifest))
        extra = sorted(set(manifest) - set(FINDINGS))
        raise RuntimeError(f"manifest/finding mismatch; missing={missing}, extra={extra}")
    return manifest


def audit_note(record: dict[str, str], old_note: str) -> str:
    if MARKER in old_note:
        return old_note
    doi = record["doi"].casefold()
    if doi == "10.17632/yr9trm7ysx.1":
        source = "inspected the README and all 144 calculation outputs in the local data archive"
        source_id = f"Archive MD5 {record['md5']}"
    elif doi == "10.1039/d2sc05839a":
        source = "read the complete locally extracted PMC article text"
        source_id = f"Full-text extraction MD5 {record['md5']}"
    else:
        source = (
            f"read all {record['pages']} local article pages, including methods, "
            "active-space/system definitions, results, tables/figures, conclusions, and references"
        )
        source_id = f"Source PDF MD5 {record['md5']}"
    note = (
        f"{MARKER}: {source}. No separate local supporting-information file was available; "
        f"unsupported SI-only details were left blank. {FINDINGS[doi]} {source_id}."
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
    parser.add_argument("--database-only", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest()
    fields, rows = load_csv(DATABASE)
    matched: dict[str, list[dict[str, str]]] = {doi: [] for doi in FINDINGS}
    changed_cells = 0

    for row in rows:
        doi = row["reference_doi"].strip().casefold()
        if doi not in FINDINGS:
            continue
        matched[doi].append(row)
        new_note = audit_note(manifest[doi], row["notes"])
        if row["notes"] != new_note:
            row["notes"] = new_note
            changed_cells += 1

        # A source-level finding is useful in these fields only when the prior
        # extraction left them empty; it is explicitly labelled paper-level.
        if not row["electronic_structure_description"].strip():
            row["electronic_structure_description"] = FINDINGS[doi]
            changed_cells += 1
        if not row["Other"].strip():
            row["Other"] = f"Paper-level comprehensive-reread finding: {FINDINGS[doi]}"
            changed_cells += 1

        for field, value in COMMON_FIELDS.get(doi, {}).items():
            if not row[field].strip():
                row[field] = value
                changed_cells += 1
        for field, value in ROW_FIELDS.get(row["entry_id"], {}).items():
            if not row[field].strip():
                row[field] = value
                changed_cells += 1

    missing = [doi for doi, paper_rows in matched.items() if not paper_rows]
    if missing:
        raise RuntimeError(f"no database rows found for: {missing}")
    target_rows = sum(len(paper_rows) for paper_rows in matched.values())
    print(f"papers: {len(matched)}")
    print(f"database rows: {target_rows}")
    print(f"changed cells: {changed_cells}")
    if not args.apply and not args.database_only:
        return

    # Guard both files before mutating either one.
    if any(MARKER in row["notes"] for row in rows if row["reference_doi"].casefold() not in FINDINGS):
        raise RuntimeError("audit marker unexpectedly appears outside the target DOI set")
    log_fields: list[str] = []
    if not args.database_only:
        log_fields, old_logs = load_csv(EXTRACTIONS)
        if any(MARKER in row.get("reasoning", "") for row in old_logs):
            raise RuntimeError("audit records already exist; refusing to append twice")

    with DATABASE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    if args.database_only:
        print("applied source-explicit database fields only")
        return

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    new_logs: list[dict[str, str]] = []
    for doi, paper_rows in matched.items():
        record = manifest[doi]
        new_logs.append({
            "timestamp": now,
            "key": record["key"],
            "doi": doi,
            "action": "comprehensive-reread-2000-2400",
            "result": f"audited {len(paper_rows)} existing aimdb row(s); no rows added",
            "reasoning": (
                f"{MARKER}: source read comprehensively; expanded notes, filled only "
                f"source-explicit blank fields, and preserved mining_model/open_access. "
                f"Local source MD5 {record['md5']}."
            ),
        })
    append_logs(new_logs, log_fields)
    print(f"appended audit records: {len(new_logs)}")


if __name__ == "__main__":
    main()
