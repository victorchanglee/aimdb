# CASSCF Literature Mining Agent — Policy

You are running a loop that finds published papers containing CASSCF-family
calculations on transition-metal complexes, downloads the PDFs,
and transforms them into rows of `database/aimdb.csv`, so mined rows could be
merged into the decision agent's reference database. Follow this policy exactly.

## Second-read queue

`logs/second_read_queue.csv` lists every paper with at least one row missing a
core field — `active_space_nel`, `active_space_norb`,
`active_space_orbital_description`, `basis_set` or `software` — sorted so the
most rewarding re-reads come first. Regenerate it any time from `aimdb.csv`
plus `papers_index.csv`; it is a derived worklist, not a source of truth.

Tiers, in the order they appear in the file:

- **A-active-space** — the active space itself is missing on some row. Highest
  value: a row without (nel,norb) cannot answer the question the database
  exists for.
- **B-basis-orbitals** — space is present, `basis_set` or the orbital
  description is not.
- **D-software-only** — only `software` is missing. Cheapest to close, often a
  single grep of the methods section.
- **C-refetch** — no local text; needs `refetch` or `si` before anything can be
  read. Do these last.

A gap is only worth filling if the paper states the value. Many are genuinely
absent from the source — that is a finding, not a defect, and the row should
say so in `notes` rather than be filled by inference. Measured on 2026-10-11
with `code/tools/tools_find_active_spaces.py`: of the 491 papers with an
active-space gap and local text, **436 print no active space anywhere**, so
650 of the ~835 gap rows cannot be closed by reading what is on disk.

**Some empty cells are the paper's own answer, and should say so.** Three were
found in one pass, and in every case a *sibling row carrying a number* is what
made the blank look like an oversight:

- `W4415130779-a` — a nuclear-electronic study where the proton carries the
  active space: "No electronic active space was used for HeHHe+". Three
  sibling rows carry (2e,2o).
- `W2317548820-b` — the table settles it by what it omits, its rows reading
  `3CH3N3 CASSCF` and `3DMAZ B1K`. CASSCF was run on the smaller analogue to
  validate the DFT model used on the title compound.
- `W4367834028-a` — "CASSCF ... was used to perform magnetic analyses **on
  5**", complex 5 being the dysprosium analogue; this row's yttrium is
  diamagnetic, so there was no magnetic analysis to perform.

Annotating these is worth as much as filling one: it stops the row being
re-examined every time the queue is regenerated.

**A bare `(n,m)` in a text is weak evidence.** Two thirds of the papers whose
text states exactly one space still could not be filled from it. The recurring
false positives: a **literature-comparison table** of other groups' methods,
each with its own reference marker (`W2318674172`); an explicit citation
(`W2162377719`, "Johnson and Irikura [8] studied ... using the CASSCF (3,8)");
a general remark rather than a calculation (`W3088435364`, on where "the
classical quantum chemical limit" lies); a **range** with per-member values in
supplementary material (`W4324049352`); and a **class-named row**, where the
paper may state several spaces and none of them is the row's — `W2022699704`
gives (8,8), (12,12) and (10,10) by dimer class for one row covering all of
them. In that last case the empty cell is not the defect; the row is.

**THE READABLE QUEUE IS DRAINED (2026-10-11).** Every one of the **77 gap rows
whose paper states at least one active space** has been read and carries a
recorded verdict in `notes` — a filled value with its evidence, or the reason it
cannot be filled. Do not re-read them; `tools_find_active_spaces.py` will still
list them, because annotating a row does not fill its cell, so check `notes` for
a dated verdict before spending time on a paper. What remains is the 650 gap
rows in the 436 papers that print no active space at all, which need
supplementary information rather than re-reading.

How the 77 came out, and what each outcome means for a future pass:

| | rows | what to do next |
| --- | --- | --- |
| filled from stated evidence or a checkable rule | 88* | nothing |
| not stated, or genuinely ambiguous | 37 | fetch the SI, or leave |
| class-named row | 20 | **split the row**, then the spaces follow |
| reduced to a single binary | 17 | decide one structural fact per complex |
| the empty cell was correct | 3 | nothing |

\* 88 counts every active-space fill or correction this session, including rows
outside the 77 (the packed-convention and no-digit buckets).

**The 17 reduced to a binary are the best remaining value.** All are
`W3189614860`, whose rule is five 3d + five 3d′ + one σ (planar quadrilateral)
or two σ (nonplanar). Each row already carries both candidates and its
`d_electron_count`; one planarity decision per complex closes all seventeen.

**Prefer a derivation the paper lets you check.** The safe fills all had an
independent test: a stated rule plus the row's own identity (`CAS(N,N)` with N
the multimer size; the lanthanide f-shell recipe where the electron count *is*
the 4f count); an orbital composition that sums to the `norb` already stored
(`W2463145035`'s "3s, 4s, and 3d orbitals and t2g 4d orbitals" = 1+1+5+3);
a spin label that pins the d count (quartet, quartet, sextet for 3d³, 3d³,
3d⁵); or best of all, **the paper's own CSF count** — `W2098766693` states "the
linear combinations of 50 and 175 configurations", and the Weyl–Paldus singlet
dimension of CAS(6,5) is exactly 50 and of CAS(6,6) exactly 175.

## QUEST-sourced rows: keep here, filter on export

QUEST-series papers are **in scope for aimdb** — this is a general database and
their active spaces are legitimate data (user ruling 2026-08-04). The
contamination risk lives entirely at the **export boundary**: `claude-casscf`
holds QUEST as a held-out benchmark in `test/questdb/`, and its decision agent
may read `database/literature.csv`. So **any bulk refresh of
claude-casscf/literature.csv from aimdb.csv must drop rows whose
`reference_doi` is a QUEST-series paper** — check provenance before writing,
not after. This was learned the hard way: a 2026-08-03 wholesale refresh
carried 14 QUEST rows into literature.csv and had to be reverted.

The machine-readable copy of the list is `config.QUEST_DOIS`, and both
`code/tools/tools_export.py` and `mining_agent.query` import it from there —
`query.find()` withholds these rows unless a caller passes
`include_quest=True`. **Extend both this list and `config.QUEST_DOIS`** when
another QUEST paper is mined; the annotated version below is the one a reader
checks.

QUEST-sourced DOIs currently in `aimdb.csv` (extend this list when more are
mined):

- `10.1021/acs.jctc.8b01205` — Loos et al., *Reference Energies for Double
  Excitations* (rows `W2903558328-a` … `-n`, 14 rows)
- `10.48550/arxiv.2409.00302` — Song et al., *QUEST#4X* (rows
  `W4402953348-a` … `-q`, 17 rows)
- `10.1021/acs.jctc.9b01216` — Loos, Scemama, Jacquemin et al., *A
  Mountaineering Strategy to Excited States* (QUEST#3, row `W3003925803-a`).
- `10.1021/acs.jctc.3c01080` — Jacquemin, Boggio-Pasqua & Loos, *Reference
  Vertical Excitation Energies for Transition Metal Compounds* (row
  `W4387325820-a`). **QUEST-series**: an explicit extension of the QUEST
  database to eleven fourth-row transition metal diatomics (CuCl, CuF, CuH,
  ScF, ScH, ScO, ScS, TiN, ZnH, ZnO, ZnS).
- `10.1021/acs.jctc.1c01197` — Sarkar, Loos, Boggio-Pasqua & Jacquemin,
  *Assessing the Performances of CASPT2 and NEVPT2 for Vertical Excitation
  Energies* (row `W3215360477-a`). **QUEST-adjacent** in the same sense: the
  CASPT2/NEVPT2 numbers are its own, but all 265 theoretical best estimates and
  the single-reference comparison statistics are pulled from the QUEST
  database. Drop on export.

Related, and already `not_usable` so it produces no row: `10.1021/acs.jpclett.0c00014`
(Loos, Scemama & Jacquemin, *The Quest for Highly Accurate Excitation Energies:
A Computational Perspective*, key `W3009380936`) is the QUEST review itself. If
a future pass ever finds a way to mine it, it belongs on this list.

**QUEST-sourced DOIs that no longer have rows** (2026-08-17). Their single row
named a dataset rather than a compound and was stripped under the rule below;
the rows are preserved in `logs/removed_rows.csv`. They are listed here
because the contamination risk returns the moment anyone re-mines them:

- `10.1002/wcms.1517` — Véril, Scemama, Caffarel, Loos, Jacquemin et al.,
  *QUESTDB: a database of highly accurate excitation energies*. The QUEST
  database paper itself (was row `W3110161356-a`).
- `10.1021/acs.jctc.4c00410` — Loos, Boggio-Pasqua, Jacquemin et al.,
  *Reference Energies for Double Excitations: Improvement and Extension*,
  QUEST-series successor to `10.1021/acs.jctc.8b01205` (was `W4399729459-a`).
- `10.1063/5.0095887` — Boggio-Pasqua, Jacquemin & Loos, *Benchmarking CASPT3
  Vertical Excitation Energies*. QUEST-adjacent: its own CASPT2/CASPT3 study,
  but geometries and reference values taken wholesale from QUEST (was
  `W4223990773-a`).

## The active space must be an integer

`active_space_nel` and `active_space_norb` are the two fields the database
exists to answer on, and a consumer filters and sorts on them. **511 cells
across 308 rows hold something that is not an integer** (measured 2026-10-11),
so no filter sees those rows at all. Run
`code/tools/tools_classify_active_spaces.py` for the current breakdown.

**Half of it is one convention, not 300 mistakes.** 256 cells in 143 rows pack
two or three whole spaces into one cell, positionally paired across the two
fields: nel `14; 8` beside norb `10; 7` means CAS(14,10) and CAS(8,7). One such
row says so outright — "both active-space variants are consolidated". The
schema has one slot per row and the paper ran two calculations, so packing was
the only way to keep both. Fixing it means either reading the paper for the
production space or giving each calculation level its own row; it is not a
formatting cleanup.

**Do not sweep by taking the leading number.** It is the obvious fix and it
would reintroduce the error this project keeps finding — recording a space the
paper reports but does not compute with. Counter-examples sit in the first
thirty samples: `8 in the minimal space, 12 in the extended one` (which is
production?), `12 for geometry optimization; 8 for Hessian` (two different
jobs), `10, 12, 14, and 18` (a convergence series, so the leading value is the
smallest). One is not a formatting problem at all: `9 for F2+, 7 for O2+, 4 for
Be2 and 14 for NiC` is a single row standing for four molecules, which is the
class-named-row defect wearing a formatting problem's clothes.

**The test of whether the leading number is right also failed, instructively.**
Looking for an `(n,m)` in the prose fields next to a production marker and
comparing it with the leading pair returned 10 disagreements against 6
agreements, which read as a refutation. Every disagreement was the regex: the
prose says "used for the variational calculations **and** (6,7) for [something
else]", and a window after the marker word reaches past the space the marker
describes to the next one. So the hypothesis is **untested, not refuted** — and
unsettleable this way regardless, because 118 of the 143 packed rows carry no
production marker in their prose at all.

**Only one bucket is safe to convert mechanically**: a cell whose own wording
marks the leading number as the one used and the rest as a test, check,
validation, probe or variant — `8; 13 in vertical-excitation test`, `11, with a
15-electron variant for the configuration-interaction check`. Convert only when
**both** fields of the row qualify, because a row with a structured `nel` and a
prose `norb` is more misleading than one where both are prose: it looks
answerable and is not. That was 23 cells in 14 rows, which is the size of the
mechanical corner.

**A cell that merely asserts absence is empty, not prose.** Nine cells across
seven rows held sentences like "NEVER STATED" or "not stated for the
isolated-species calculation" inside the integer field. An empty cell says the
same and stays sortable; the sentence belongs in `notes`. Eight further cells
assert an absence *and* carry real numbers — "2 for diradical diagnostic; 12 in
initial spectral screening; final occupation-selected spectral electron count
not reported" — and emptying those would discard stated values.

## A row must name a compound

`compound_name` is what makes a row answerable — a consumer asks *what active
space does this molecule need*. A row whose `compound_name` names no chemical
species answers that for nothing, and cannot be checked against the paper
either. Three shapes fail the test and must not be added:

- a dataset or benchmark label — "Thiel benchmark set of organic molecules",
  "STGABS27 TADF emitter benchmark set", "HAB79 dataset";
- a class with no species — "iron(II) complexes - spin-state energetics
  benchmark set", "free d- and f-block metal ions", "planar cis-[MA2B2]
  transition-metal complexes" (`MA2B2` is a placeholder, not a formula);
- the paper's internal numbering — "compound 6", "complex 4, Dy(II) site",
  "benchmark molecule 3" — unless a sibling row resolves it.

Naming *several* compounds is fine: "test set: acrolein, benzene, benzyne,
PSB3" names four, and is an over-merged row rather than a nameless one. Split
it if you have the per-compound data; do not strip it.

**A class-named row is usually a SPLIT, not a removal.** Nine were resolved on
2026-10-11 without losing anything: eight became per-compound rows (8 rows
became 23) and one was simply narrowed. Splitting is worth the trouble because
it corrects fields, not just adds them — a merged row carries one active space
and the paper rarely uses one. W2606848775 recorded (5,9)/15 states for seven
U(V) complexes when the paper uses (1,7)/7 states for two of them;
W4200089368 recorded CAS(1,7) and 4f1 for an isostructural Ce/Bk pair when the
paper states "CAS(1,7) and CAS(8,7) for Ce1 and Bk1"; W2175930880 recorded the
Dy (9,7) space for its Ni(II) centres, which the paper computes at (8,5). The
space follows the shell and the compound, so one row cannot hold it for several.

Splitting also *checks* the row, which removal does not. W7155069273 was named
"dinuclear rare-earth (Eu/Dy) ... complexes" and carried europium in `element`;
the paper studies no europium at all, and every "Eu" in its text is the
corresponding author's first name, a cited complex from earlier work, or a
reference title. That had been making the site's periodic-table filter return
the paper for europium.

**Two kinds of row look class-named and should be left alone.** Both were
examined on 2026-10-11 and deliberately not split:

- `W2172599360` — "pseudotetrahedral cobalt(II) complexes with halide
  ligands". Its tables are crystallographic, and its subject is **two
  polymorphs (3A, 3B) of one complex**, with the other three halides as
  literature context. Four compound rows would misrepresent what was computed.
- `W7150817998` — "idealised YbF_x / ErF_x model series". A **geometry scan**,
  not a set of compounds: there is nothing to name per row, and the 8.0 and
  18.0 its text quotes are the 2*g_J*m_J ceilings rather than results.

A row describing a polymorph pair or a geometry scan names what was actually
computed, which is the test. What fails the test is a row standing for N
distinct compounds.

**Not every split is a split, either.** Check which compounds the paper
actually treats before creating rows. `W2467810201` named "the cobalt(II) and
copper(II) complexes" but its CAS(7,5) is a d7 space used on the cobalt alone,
so the copper compound earns no row and the fix was a narrowing.
`W2769765377` named six complexes but the paper structurally characterises
five; `W4403467707` named a family of five but its table covers three, two of
its four columns being a truncated model and the full molecule of the same
compound.

39 rows failing the test were removed on 2026-08-19 with
`code/tools/tools_strip_rows.py`, which quarantines every removed row to
`logs/removed_rows.csv` first. Decide this by reading, never by pattern:
an early attempt matched `n ?= ?` and flagged every formula containing `N=O`.

The quarantine file is a log, not a data source — do not load it alongside
`aimdb.csv`. It lived at `database/removed_rows.csv` until 2026-08-19, so the
54 `strip_row` entries already in `logs/extractions.csv` name that old path;
they were accurate when written and are left alone, because the log is
append-only. It is also not the same content as the row's last version in git:
four of the 39 rows had `software` or `basis_set` filled in the same commit
that removed them, so the quarantine holds the row as it actually was at
removal and the git parent holds an emptier one.

The Python package does the mechanical work (API search, PDF download, text
extraction). **You do the reading and extraction** — deciding whether a paper
really contains a usable CASSCF calculation and pulling the fields out of the
text is judgment work, not regex work.

## Layout

```
code/mining_agent/            Python implementation (search/fetch/text/csv helpers)
code/tools/                   standalone re-runnable tools (see code/README.md)
database/aimdb.csv            output database (schema diverged from claude-casscf 2026-07-28, see above)
database/papers_index.csv     one row per candidate paper: doi, title, status, paths
papers/pending/<key>.pdf      downloaded PDFs still to be read (gitignored)
papers/mined/<key>.pdf        PDFs already read and judged (gitignored)
papers/si/<key>/              supplementary information (gitignored)
text/<key>.txt                extracted text (gitignored — do not commit)
logs/extractions.csv          append-only audit log, one row per decision
logs/oa_status.csv            OpenAlex open-access answer per DOI (see open_access below)
logs/second_read_queue.csv    papers whose rows have gaps worth a second read (see below)
```

Run all `python -m mining_agent ...` commands from `code/` with
`code/.venv/bin/python`.

**The pending/mined queues.** `fetch` downloads into `papers/pending/`.
The moment a paper reaches a status meaning it has been read and judged —
`extracted`, `extracted_partial`, `not_usable`, `text_unreadable`
(`config.MINED_STATUSES`) — `index.set_status()` moves its PDF to
`papers/mined/` and rewrites `pdf_path`. So **`papers/pending/` always shows
exactly the work still to do**; never move these files by hand. Index paths
are stored *relative to the project root* so renaming the project doesn't
break them. `python -m mining_agent tidy` reconciles the two directories
with the index (moves stragglers, repairs stale paths, and reports pending
PDFs that were added by hand and aren't in the index).

## The loop, one paper at a time

1. **Search.** `python -m mining_agent search --query "<terms>" --max N`
   queries OpenAlex and appends new candidates to
   `papers_index.csv` with `status=candidate`, deduplicated by DOI. Vary
   queries across cycles: "CASSCF transition metal complex",
   "NEVPT2 zero-field splitting", "CASPT2 spin states iron", metal-specific
   terms, etc. Papers already in the index (any status) are never re-added.

2. **Fetch.** `python -m mining_agent fetch --max N` downloads PDFs for
   candidates that have an open-access URL → `status=fetched`
   (or `fetch_failed` with the reason). Only OA locations reported by the
   API are ever downloaded — never scrape paywalled content or mirrors.

3. **Extract text.** `python -m mining_agent text --key <key>` (or
   `--all-fetched`) converts the PDF to `text/<key>.txt` → `status=text_ready`.

4. **Read and judge.** Read `text/<key>.txt` yourself. A paper is *usable* if
   it reports an actual multireference calculation (CASSCF / RASSCF / CASPT2 /
   NEVPT2 / MRCI) **on a specific chemical compound** — transition-metal
   complexes and metal-free organic molecules both count (user decision
   2026-07-14) — with at least the active space size (nel, norb) stated.
   **Solid-state systems are also in scope (user decision 2026-08-05):**
   colour centres and point defects (NV in diamond, F/F+ centres in oxides,
   defects in hBN or SiC), doped crystals and phosphors (Ce3+:YAG, Eu2+
   nitrides, Mn4+:K2SiF6), bulk solids and adsorbate/surface models — the
   usual case is an embedded- or bare-cluster model of a site in a host
   lattice. This reverses the 2026-07-24 practice of excluding them as "not a
   molecular TM complex nor organic molecule"; papers ruled out on that ground
   before 2026-08-05 are worth revisiting. **Say so in `notes`**: a
   solid-state row must state that the system is a site in a lattice or on a
   surface treated by a cluster model, not an isolated molecule, so the row is
   never mistaken for a gas-phase molecular result.
   **No exclusions by system size or class (user decision 2026-08-07):**
   single atoms, bare diatomics, molecules of any size, clusters and
   solid-state models are all in scope. This overturns the "bare-diatomic
   convention" that mining sessions invented between 2026-08-03 and
   2026-08-05 and used to reject ~167 papers — those are being re-read, and
   the rule must never be reintroduced. What still makes a paper unusable is
   only this: **it reports no multireference calculation of its own, or never
   states the active space.** Reviews that merely cite other people's numbers,
   and papers where the active space is never specified anywhere (main text or
   SI), are `status=not_usable` (log why).

   **Quantum-algorithm papers need a hardware caveat in `notes`.** When the
   active-space eigenvalue is obtained by VQE (or a simulator of it), the space
   size is set by the qubit budget — n active orbitals means 2n qubits — not by
   the chemistry. CAS(2,2) on ethylene or CAS(4,4) on water is a circuit-width
   decision, and a consumer asking "what space does this molecule need" would be
   misled by it. Start the caveat with the literal string
   `ACTIVE SPACE IS HARDWARE-LIMITED:` so the category stays greppable
   (13 rows carry it as of 2026-08-10). **Do not apply it to molecular
   spin-qubit chemistry** — VOTPP, vanadyl SMMs, Er(III) complexes, DTDA
   diradicals — where the molecule *is* the qubit but the active space is chosen
   on ordinary chemical grounds. The word "qubit" in a row is not the test; the
   test is whether a quantum processor computed the eigenvalue.

   Record what kind of system the row describes in **`system_class`**:
   `atom`, `molecule`, `cluster-model` or `solid-state`.
   **`cluster-model`** (added 2026-08-14, displayed "Cluster model") is a
   finite cluster standing in for something larger — an embedded or bare
   cluster cut from a solid, a surface/adsorbate cluster, an enzyme
   active-site model, a QM/MM QM region. **`solid-state`** is now reserved for
   a site in a host lattice or a bulk solid treated as *extended*
   (periodic/PBC); if the paper models it as a finite cluster, the row is
   `cluster-model`. 419 rows moved on the split, 403 of them out of
   `solid-state`.
   **`molecule` covers any bound species of two or more atoms, diatomics
   included** — there is no separate `diatomic` value (user decision
   2026-08-10: O2 and N2 are molecules; the old value was merged and its 221
   rows relabelled). `solid-state` wins over the size-based values, since it
   describes the environment rather than the size. The column exists so
   consumers can filter for themselves instead of the policy deciding for
   them; it is never a reason to reject a paper.

4b. **Fetch SI when it matters.** If the main text defers computational
   details ("see SI"), or key fields (active space composition, geometry,
   software, state energies) are missing, run
   `python -m mining_agent si --key <key>` (figshare SI DOIs first, then
   PMC OA packages; SI PDFs are auto-text-extracted to
   `text/<key>_si_*.txt`). Read those before declaring a field unstated.
   Coordinates found in SI are saved **verbatim** to
   `database/structures/<entry_id>.xyz` with a VERBATIM provenance line —
   these are the paper's real geometries and outrank generated ones. Set
   `structure_provenance` to `computational` or `experimental` depending on
   how the paper obtained that geometry (DFT/optimized vs.
   X-ray/neutron/measured). For compounds without SI coordinates,
   `structure --entry-id X --name Y` may save a PubChem conformer, always
   labeled GENERATED / not the paper's geometry and always stamped
   `structure_provenance=ai_generated` automatically; sanity-check the atom
   count against the compound before keeping it. SI files live in
   `papers/si/<key>/` (gitignored, copyrighted).

5. **Extract rows.** For each distinct compound+method result in a usable
   paper, build a JSON dict of the schema fields and append it with
   `python -m mining_agent add-row --json <file>.json`. Rules:
   - **Copy, never infer.** Every value must be stated in the paper (or be
     an arithmetic restatement, e.g. eV from cm⁻¹ — note the conversion in
     `notes`). A field the paper doesn't state stays **empty**. Never
     estimate, never fill from general chemistry knowledge. d_electron_count
     from the stated oxidation state is allowed (it's arithmetic), but flag
     it in `notes` if the paper doesn't state the ox state explicitly.
   - **`d_electron_count` covers d *and* f blocks**, and is always written
     **with its shell**: `3d7`, `4d9`, `5d6`, `4f9`, `5f2` — never bare `d7`,
     bare `f9`, or a bare integer `7`. The shell follows from `metal_center`
     (Sc–Zn 3d, Y–Cd 4d, Hf–Hg 5d, La–Lu 4f, Ac–Lr 5f), and the count is
     `group valence electrons − oxidation state`. Leave it empty for
     main-group centres, where neither shell applies. The column keeps its
     historical name for schema parity with `claude-casscf`; the site labels
     it "d/f electron count". Normalized and backfilled across the whole
     database on 2026-08-05.
   - `entry_id`: the papers_index `key`, plus `-a`, `-b`, ... for multiple
     compounds from one paper. `structure_file`: empty unless you actually
     save a geometry to `database/structures/`. `structure_provenance`:
     `computational` / `experimental` / `ai_generated` — mandatory whenever
     `structure_file` is set (see step 4b); empty otherwise.
   - `element` (added 2026-08-20, sits after `metal_center`): the element
     symbols the site's periodic-table filter matches on, space separated
     and alphabetical — `C Mg Ni O`. **Derived, not read from the paper**:
     it is the union of the symbols in `metal_center` (unless that is
     `none`) and those in `formula`, so it is only as good as those two.
     Empty is correct and common (1557 rows on 2026-10-11, across 627
     papers) when neither a metal centre nor a formula is stated.

     **`--regenerate` is not safe to run blind, and never was.** Measured on
     2026-10-11: it would have changed 246 rows and SHRUNK 387 others,
     dropping hydrogen from 303 rows, carbon from 293 and nitrogen from 238.
     The cause is that most real coordination-chemistry formulae are
     abbreviated — `Co(PPh3)2I`, `Dy(acac)3(H2O)2`, `[Fe(TPP)Cl]` — and a
     symbol scan cannot see the carbon and hydrogen inside `PPh3`, `acac` or
     `TPP`. 295 of the 387 have no `formula` at all, so the derivation
     returns the metal alone. `tools_fill_element.py` now KEEPS any value the
     derivation would shrink and reports it; `--allow-shrink` overrides, and
     is right only when the existing value is actually wrong.

     **So a metal-only `element` is usually faithful to the rule and wrong
     about the molecule**, and the gap is upstream in `formula`. 945 rows
     carry a single metal symbol while naming organic ligands. Fixing one
     means writing the `formula`, not editing `element` — a hand-written
     `element` with nothing behind it is unbacked, and `--regenerate` is
     exactly the command that discards it. When no honest formula can be
     written, because the paper names a compound without ever printing its
     atom counts, a hand-identified `element` is the right answer and the
     shrink guard is what protects it.
     `docs/build_site.py` reads this column directly; it falls back to
     deriving the set itself only if the column is absent. The derivation
     masks ligand abbreviations that a bare `[A-Z][a-z]?` scan misreads as
     symbols — `OAc`/`SAc`/`HOAc` as actinium, `Por` as polonium, `Nor` as
     nobelium, `BArF` as argon, `CmH2m` as curium, and the word `Table` as
     tantalum. Genuine entries are untouched: `PoCl6(2-)`, `XeH+`, `NoO`,
     `Ta2`, `AcCO` and `Co2O37W10^6-` all keep their tags.
   - **Metal-free organic compounds**: leave `metal_center` **empty**, and
     likewise `metal_ox_state`, `d_electron_count` and `ligand_set`. The
     `none` marker used until 2026-08-20 was emptied database-wide; the
     absence of a metal is evident from `formula` and `compound_name`. All
     other columns apply as usual (pi/lone-pair active spaces go in
     `active_space_orbital_description`; ground-state term, excitation
     energies, etc. go in `electronic_structure_description` as stated).
   - `active_space_protocol`: only if the paper describes its buildup
     sequence; this column is what the decision agent reads — quote it
     faithfully, format "(nel,norb) step; (nel,norb) step; ...".
   - `reference_doi` is mandatory — a row without a DOI is not addable.
   - `correlation_correction`: which post-CASSCF dynamic-correlation
     correction the reported result uses (`NEVPT2`, `CASPT2`, `RASPT2`,
     `MRCI`, ...), or **empty** when the reported result is variational
     CASSCF/RASSCF/DMRG only — that is evident from `method`, and since
     2026-08-20 only stated values are recorded. Leave it out of the JSON
     and `add-row` derives it from
     `method` via `csvio.classify_correction`; set it explicitly only when
     the paper's wording makes the derivation wrong.
   - `entry_type`: how the entry was produced — `llm_mining` (LLM-mined from
     the literature; the default when omitted), `llm_reproduced` (a
     calculation an LLM actually re-ran), or `human` (human-entered).
     `add-row` validates it against `config.ENTRY_TYPES` and defaults it to
     `config.DEFAULT_ENTRY_TYPE`.
   - `mining_model`: provenance of which LLM did the extraction. Leave it
     out of the JSON and `add-row` auto-stamps `config.CURRENT_MINING_MODEL`.
     When a new Claude model takes over the mining, bump
     `CURRENT_MINING_MODEL` in `code/mining_agent/config.py` so new rows
     record the model that actually extracted them (or pass `mining_model`
     explicitly per row). This is the second-to-last column and is
     aimdb-only — `claude-casscf` merges just drop it.
   - `open_access` (last column, aimdb-only): `yes`/`no`/`unknown` — is
     `reference_doi` open access per OpenAlex's `open_access.is_oa`? Don't
     fill it by hand; run `.venv/bin/python tools/tools_oa.py --refresh --stamp`
     from `code/` after a batch of rows. That rewrites `logs/oa_status.csv`
     (per-DOI `oa_status` gold/hybrid/green/bronze/diamond/closed plus the
     best OA URL) and restamps the column for every row. It is access
     metadata about the source, not a property of the calculation.
   - `electronic_structure_description`: **what the states are.** This
     column merges the ground-state term symbol (if stated — prefix it
     "Ground term: ...") with the low-lying state energies; paste the
     relevant numbers compactly, state units; SOC-corrected vs SOC-free
     matters (`soc_included` flag: `yes` when stated, otherwise empty —
     the bare `no` used until 2026-08-20 was emptied database-wide, as was
     `ss_included` `no`).
   - `Other`: **what the active space did to the answer.** A separate
     column from the one above — do not fold them together. This is where
     the *methodological* finding goes: how the choice of active space,
     or of the correlation treatment on top of it, changed the result.
     86% of rows carry one, and it is the column a consumer choosing a
     space actually reads. Good entries look like:
     - "Cu 3d double-shell effect shifts CASPT2 Delta_EST by >10 kcal/mol
       between (8in6) and (16in15) reference"
     - "PT2 correction critical for state ordering: at variational
       ASCI-SCF level 5A1g is lowest, triplet ground state only after +PT2"
     - "Stabilization increases monotonically with space size: -0.027 eV
       at (6e/5o), -0.031 at (10e/9o), -0.057 at (12e/11o)"

     Write it whenever the paper says or shows any of: a space was
     enlarged/reduced and the number moved; dynamic correlation (PT2/MRCI)
     changed a state ordering or an energy materially; orbitals were
     deliberately excluded and why; a space was chosen for surface
     continuity or dissociation balance rather than for best energies;
     state-averaging was forced by degeneracy; the authors caveat their
     own numbers; or the space size was set by hardware rather than
     chemistry. **Also use it to warn about traps in the source** — e.g. a
     paper whose "(5,5)" label counts orbitals per irreducible
     representation rather than (nel,norb). Leave it empty only when the
     paper genuinely offers no such finding.

     **What `Other` is not for.** Not a paper-level summary of what the
     study found — that is `electronic_structure_description`. Not a
     restatement of a value another column already holds: naming the row's
     own space is fine when the sentence needs it ("the (8,7) space alone
     places this diradical too high"), but a field that only repeats
     `basis_set`, `software` or `(nel,norb)` adds nothing. And never a
     copy of another field's text.

     **An empty `Other` is a better answer than a filled one that dodges
     the question.** A paper-level takeaway sitting in this column does not
     read as a gap, so nobody comes back to it, and the finding the column
     exists for is silently lost. Audit of 2026-08-21: 434 rows carried
     `Other` values of the form "Paper-level takeaway beyond the
     active-space specification: <verbatim copy of
     electronic_structure_description>". On 376 of them the field said
     nothing about the active space at all. If the paper offers no
     active-space finding, leave the cell empty and say why in `notes`.

     **One prose field, one job.** Do not open several fields with the same
     bracketed identifier tag. 83 rows begin `Other`, `notes`,
     `electronic_structure_description` and `active_space_protocol` with
     the same `[CAS(32,34); Fe(II) porphyrin - ...]` prefix, which restates
     `active_space_nel`/`norb` and `compound_name` four times over. The
     row is already identified by `entry_id`.

     **Length is not the defect; restatement is.** The 2026-08-21 audit of
     the 1,210 rows whose `Other` runs past 2,500 characters found 96% of
     them genuinely about the active space, with no repeated sentences and a
     *lower* numeric density than shorter rows — long because the finding
     was long, which is fine. Do not trim a row for its size alone. Two
     habits inside a long field are the real problem, and both are
     mechanical:

     - Opening every pipe-separated segment with the row's own
       `compound_name`. 309 rows did this across 2,702 segments — some
       65,000 characters restating a column the row already holds, one row
       naming its compound 112 times in a single cell. A segment naming a
       *different* species is data, not restatement: leave it.
     - Repeating a paper-level sentence inside every segment. 46 rows did;
       one restated its trajectory-ensemble setup 33 times, once per
       stationary point, so 8,820 characters said what 1,677 say now. Write
       such a statement once, as the field's last segment.

     `code/tools/tools_trim_restated_name.py` and
     `tools_hoist_repeated_sentence.py` fix these two and nothing else. They
     removed ~98,000 characters on 2026-08-21 without touching a non-prose
     column or emptying a field, because they only ever delete a second copy
     of text the row already contains — they reword nothing, and where the
     redundancy would be a judgment call they leave it alone.

     What they deliberately do not touch: 572 segments in these rows
     describe a related species that has no row of its own — reaction-path
     stationary points, other members of a benchmark set. That is extra
     data, not duplication. Splitting it into rows is the fix if you have
     the per-compound values; deleting it is not.
   - `notes`: **what a reader needs in order to trust the row** — a caveat
     the authors give, a value that is arithmetic rather than quoted, a field
     left empty because the paper never states it, a source checksum, a data
     DOI, or provenance that is not obvious from the other columns (a row
     contributed by an outside pull request, say).

     **Never narrate the extraction.** "GPT-5.6 comprehensively read all 17
     pages of the complete local article, including methods,
     active-space/system definitions, results, tables/figures, and
     conclusions" is not a fact about the chemistry, and neither is a record
     of a past bulk edit — `logs/extractions.csv` already holds those, with
     a timestamp. Which model did the extraction is `mining_model`; that the
     row came from mining at all is `entry_type`. The audit of 2026-08-21
     removed 1,024,000 characters of this from 3,377 rows, a fifth of the
     whole column, and left 96 rows with an empty `notes` because narration
     was all they had ever contained. An empty `notes` is the honest result.
     `code/tools/tools_strip_llm_narration.py` does this and is re-runnable.
   - One row per compound, not per table — condense.
   Then `status=extracted` (or `extracted_partial` if key fields were
   missing but the row is still useful).

6. **Log.** Every status change appends to `logs/extractions.csv`:
   `timestamp, key, doi, action, result, reasoning`. The audit trail is the
   review mechanism — write reasoning a chemist can check.

## Give up / escalate conditions

- PDF text extraction garbled (equations/tables shredded beyond reliable
  reading): `status=text_unreadable`, move on — never guess at garbled
  numbers.
- API errors or rate-limit responses: back off (the code already rate-limits;
  don't hammer), retry next cycle, and stop and report if a source stays
  down across a whole cycle.
- Anything that looks like a licensing/access problem beyond "not OA":
  stop and ask the user.

## Community contributions (website form)

The site has a **Contribute** section whose form emits a one-row CSV with the
`database/contributions.csv` schema (review metadata + the literature
columns) and emails it to the maintainer. These are **human submissions,
never trusted blindly**:

- Collect an emailed submission with
  `python -m mining_agent contributions --add <file>.csv` (appends to
  `database/contributions.csv` with `review_status=pending`);
  `--list` shows the pending queue.
- Review each pending row against its DOI exactly like a mined paper (scope
  test + copy-never-infer). If it holds up, promote it into `aimdb.csv`
  via the normal `add-row` path (assigning an `entry_id`; `entry_type`
  stays `human`, `mining_model` empty), then mark the contribution row
  reviewed. Contributions are **never auto-merged**.

## Preprint and journal versions are one paper

A paper mined from its preprint and again from the published version gets two
`entry_id` keys and two DOIs, so neither DOI dedup nor a hash catches it. Match
on the **whole** normalized title — a prefix pulls in series papers sharing a
long stem ("...NEVPT2 I / II / III") and every such false positive disappears
at full length. Then read the DOI: `10.26434` (chemRxiv), `10.48550` (arXiv)
and `10.21203` (Research Square) are preprints, anything else the journal.

**This recurs.** 14 pairs were resolved on 2026-07-30 and there were 29 by
2026-08-21, because each intake pass can reintroduce it. Run
`code/tools/tools_resolve_duplicate_papers.py` after every intake.

**Row count says nothing about which copy was fetched.** After the 2026-08-21
pass, 21 of the 49 removed rows had local text while their survivor had none —
the discarded key was the readable one. Nothing is deleted, since `not_usable`
is only an index status, but a later audit checking a surviving row finds no
source and no reason to look under the twin. Run
`code/tools/tools_repoint_duplicate_text.py` after resolving: it copies the
text across and banners it, since a preprint and a published article are not
the same document.

**The peer-reviewed version always survives** (user ruling 2026-10-11: "the
peer review article should be the authors results"). This replaces the earlier
rule, which kept whichever key carried more rows and gave the journal only the
tie — that let a preprint stand as the citation of record whenever it happened
to have been mined more thoroughly, which is the wrong provenance for a
published result even when it is the fuller reading.

**Only resolve a pair when the survivor already covers every `(nel,norb)` the
loser holds.** This guard is what keeps the ruling from destroying data, and it
is doing real work: measured over the whole index on 2026-10-11, removing every
duplicate preprint unconditionally would delete **247 rows of which only 35 are
genuinely redundant**. The other 212 break down as

| | groups | preprint rows | journal rows |
| --- | --- | --- | --- |
| journal copy indexed but never mined | 20 | 92 | 0 |
| journal copy misses a space the preprint holds | 11 | 51 | 40 |
| no journal copy in the index at all | 49 | 69 | 0 |

**That last line undercounts by a factor of three, and the reason is worth
knowing.** It was measured over the index's 205 preprint/journal *title
groups*, so it saw only preprints that have a same-title sibling indexed —
typically a v1 and a v2 of the same chemRxiv deposit. A preprint sitting alone
in the index never joins a title group and so was never counted. Counting the
rows instead of the groups, on 2026-10-11 after the resolutions below: **163
preprint index records carry 487 rows**, of which 134 have since been
re-attributed, leaving **353 rows in 136 groups still citing a preprint with no
journal version anywhere in the index** — 57 of those groups have an indexed
sibling, 106 are alone. Measure this from `aimdb.csv`'s `reference_doi`, which
is what a consumer actually reads, not from the shape of the index.

and all of those are **re-attribution work, not deletions** — the fix is to
point the rows' `reference_doi` at the published article where one exists (and
to search for one where it does not), not to drop the only reading the database
has. 35 rows across 9 pairs were removed on 2026-10-11 under the new rule.

**When the two copies disagree on `(nel,norb)`, suspect the row before the
paper.** The guard above treats a conflicting space as a reason not to resolve,
which is right as a reflex and wrong as a conclusion: read the source and the
conflict usually dissolves. Of the 11 pairs where both keys carried rows, **six
were one paper reporting several active spaces and the preprint row recording
the wrong one** — the geometry-optimisation space rather than the production
space (cyclobutanone, (8,8) against (6,6), where the paper says it "settles on"
the smaller for "all subsequent electronic structure calculations"); a rung on
a convergence ladder (pentacene, (16,16) against the full-π (22,22)); a
representative accuracy demonstration (salicylaldimine, (8,8) against the
(2,2) every dynamics figure uses). A paper with a methods section that tests
active spaces will state three or four of them, and only one is the answer to
"what did this calculation use". Two more pairs merely disagreed because the
preprint row was class-named, and one agreed on the numbers while the journal
row stated them in prose.

**The conflict can also be the survivor's fault.** Resolving these found
`W4385800761-a` (ferrioxalate) holding `nel=9 norb=13` with a protocol reading
"minimal (7,6); expanded production (9,13)". The paper says the reverse — it
opens "we start with a (7e,6o) active space", computes every optimisation and
both energy tables there, and introduces the larger space with "to check
whether our conclusions are biased by a too-small active space". Production and
check were transposed, and the *preprint* row carried the correct (7,6). So the
guard's premise — that the survivor is the better record — is not free either;
when the loser holds a space the survivor lacks, one of the two is wrong and
which one is an empirical question.

**Three of the 11 were real merges**, where the journal row lumped into a class
what the preprint had as compounds, so deleting the preprint would have
destroyed the better record. The tell is in the survivor's own fields: the
`[Co(III)(TAML)]⁻ redox series` row itemised **two different active spaces in
one `active_space_orbital_description`**, (14,13) for the anion and (13,12) for
the neutral, and the XS-CASSCF benchmark-set row listed eleven per-molecule
spaces in its `active_space_protocol`. A row carrying more than one
`(nel,norb)` in its prose is standing for more than one compound. One merge was
different again: the dipole-moment paper's two readings **did not overlap at
all** — 22 diatomics under the preprint key, 6 polyatomics under the journal's,
both molecule sets present in both texts — so the union is the record and
nothing was deleted.

After that pass, 14 more rows were quarantined and 35 re-attributed, leaving
one pair unresolved and raised with the user: the An(III) soft-donor study,
where the journal rows are themselves class-named *and* carry spaces the
preprint's natural-orbital analysis shows to be wrong.

Two blind spots in the title matching were fixed the same day, both found by
noticing identical values under two keys rather than by the tool:

- **HTML markup.** OpenAlex returns publisher titles with tags intact, so one
  paper arrived as `... Air-Stable <i>D</i> <sub>5h</sub> SIMs**` and its
  preprint as `... air-stable D5h SIMs`; stripping only non-alphanumerics left
  `idisub5hsubsims` against `d5hsims`.
- **Unicode typesetting.** A preprint writing an oxidation state in modifier
  letters normalised to `cotaml` while the journal's plain `III` gave
  `coiiitaml`. `_title()` now applies NFKC before stripping.

Between them these took detection from 11 pairs to 20 among rows-on-both-sides
cases, and the full index holds **205** preprint/journal groups.

A second mechanism produces the same damage invisibly: a paper that already has
rows being **re-mined from a hand-supplied PDF**. It writes under the same key
and DOI, so no title or DOI check can see it — look for `read-supplied-file`
after an `add-row` for the same key in `logs/extractions.csv`. Ten papers were
mined twice this way on 2026-08-06/07, and the second pass read a *different
document*: `W4253843485`'s rows claim (64,64) and (60,60), `W4205703165-d`
claims (54,36), and none of those appear in the stored `text/<key>.txt`.

## Structure files and molecule identifiers

A row's `structure_file` is what lets a consumer rerun the calculation. Three
sources exist, and `structure_provenance` says which one a file came from:

- **the paper's own coordinates** (`computational` or `experimental`), copied
  verbatim from a coordinate table in the article or its SI. This is the only
  kind that is the geometry the row's calculation used.
- **a PubChem conformer** (`ai_generated`): the compound's generic 3D
  structure, never the paper's geometry. Its file says `GENERATED` on the
  comment line and the row's `notes` say so too.

**The pipeline, in order** (all re-runnable, from `code/`):

1. `tools/tools_batch_si.py` fetches SI for every paper with a structureless
   row, over the two sanctioned routes only (figshare component DOIs for ACS,
   PMC OA packages), and text-extracts the PDFs to `text/<key>_si_*.txt`.
2. `tools/tools_find_coordinate_blocks.py` finds every coordinate block in
   the local text and writes `logs/coordinate_blocks.csv`: file, line, atom
   count, composition, the nearest species label, and which rows share the
   composition. **It is a worklist, not a decision.** An SI prints every
   stationary point, every conformer and every DFT comparison geometry; which
   block is the row's is read from the label and the methods section.
3. `tools/tools_save_coordinate_block.py` copies the chosen block verbatim,
   checks its composition against the row's `formula`, sets
   `structure_file`/`structure_provenance`, appends a note naming file and
   lines, and logs. `--range A B` joins a block that page breaks split;
   `--batch` applies a reviewed JSON list of decisions.
4. `tools/tools_pubchem_identifiers.py` resolves `compound_name` in PubChem
   for every molecule row and writes `database/identifiers.csv` (CID,
   InChIKey, InChI, SMILES, PubChem formula, `status`). `--apply` stamps the
   queued conformers onto rows that still have no structure, and only where
   `status=match`, i.e. PubChem's composition equals the row's `formula`.

**Line numbers are `grep -n` numbering.** 231 text files contain form feeds
or Unicode line separators that Python's `splitlines()` also breaks on, so a
line number from `splitlines()` can be off by dozens from what `sed -n`
shows. Both tools split on `\n` only; a note that says "lines 947-998" can be
checked with `sed -n '947,998p'`.

**What the composition check catches, and what it cannot.** When the row's
`formula` is plain (`C5H6N6`), the saver refuses a block of any other
composition, and that caught a transposed page range on the first pass. When
the formula is abbreviated or empty (`Mn(acac)3`, `[CuO2]+ with the
histidine-brace ligand set`), nothing is checked: count the atoms against the
compound yourself before saving. Three acac rows were first saved with
30 of 43 atoms because the range stopped at a page footer, and the counts
were what showed it.

**A PubChem hit is only as good as its formula check.** A name like
`1H-1,2,3-benzotriazole parent molecule` resolves correctly once the trailing
words are dropped, but a fragment cut from a prose name (`1H-1` from
`1H-1,2,3-benzotriazole`) resolves to an unrelated compound. So a fragment
counts only when the row has a formula to check it against, and a row with
no formula records a whole-name hit as `no_formula`, flagged unverified, with
no conformer. `identifiers.csv` is a sidecar keyed by `entry_id` rather than
new columns, so the schema and `claude-casscf` are untouched until the
columns are deliberately merged.

**PubChem blocks a client for many minutes at rates its documentation
allows.** Five requests per second is the stated limit, but a failed name
lookup costs the server seconds, and the 300 s-per-minute server-time cap
produced HTTP 429 for every request after a burst at four to eight requests
per second. The tool now runs one request per second, treats a 429 as a
five-minute cooldown, and records a lookup that got no answer as `deferred`
rather than `unresolved`, so a rerun asks again instead of believing the
throttle.

**Outcome of the first full pass (2026-10-11/12).** `structure_file` went
from 908 to 1,914 rows: 666 verbatim geometries read out of 413 papers'
coordinate blocks, plus 340 formula-checked PubChem conformers. About two
thirds of the rows in those papers were deliberately skipped, and the
reasons recur, so read for them first:

- **the row names no single structure**: a reaction path, a scan, a whole
  network, or a class ("complexes 1-5"). One file per species, never one
  file holding several molecules, and constitutional isomers count as
  different molecules.
- **the calculation ran on a geometry that is not printed**: a truncated
  model (tBu to Me or H, Ln to Y), an X-ray structure cited but not
  reproduced, or a CASSCF re-optimisation where the SI prints only DFT.
  A printed geometry of a *different* model is not the row's.
- **extraction damage**: digit runs split by a space, minus signs lost or
  turned into letters, two structures printed side by side, a block one
  atom short. The saver refuses the first three; the last is caught only by
  counting atoms against the compound, or by an odd electron count where
  the spin state needs an even one.

The parser handles Gaussian's `center / atomic-number / type` columns,
GAMESS's nuclear-charge column, atomic numbers in place of symbols, Unicode
hyphens as minus signs, and (in `--range`) a species label printed on the
first coordinate line. It does not handle element symbols in capitals
(`FE`, `CR`, `MG`), so such blocks still need skipping.

**Reading blocks turns up row errors.** Composition is the strongest check
the row's own fields ever get. This pass corrected 21 formulas or names and
the active space of 9 rows this way, each with the quote in `notes`, and left a further
list unfixed because it needs the paper read, not just a block counted.

## Things to never do

- Never fabricate or infer a value the paper doesn't state — empty cell wins.
- Never commit `papers/` or `text/` (copyrighted content; they're gitignored).
- Never add a row whose DOI already has rows, unless it's a genuinely
  different compound from the same paper.
- Never edit or delete existing `aimdb.csv` rows without being asked —
  append-only, corrections go in `notes`.
