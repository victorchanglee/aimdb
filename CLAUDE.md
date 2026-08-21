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
say so in `notes` rather than be filled by inference.

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
     `none`) and those in `formula`, so it is only as good as those two and
     is regenerated whenever either changes. Empty is correct and common
     (1522 rows) when neither a metal centre nor a formula is stated.
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

## Things to never do

- Never fabricate or infer a value the paper doesn't state — empty cell wins.
- Never commit `papers/` or `text/` (copyrighted content; they're gitignored).
- Never add a row whose DOI already has rows, unless it's a genuinely
  different compound from the same paper.
- Never edit or delete existing `aimdb.csv` rows without being asked —
  append-only, corrections go in `notes`.
