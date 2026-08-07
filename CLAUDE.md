# CASSCF Literature Mining Agent — Policy

You are running a loop that finds published papers containing CASSCF-family
calculations on transition-metal complexes, downloads the open-access PDFs,
and transforms them into rows of `database/aimdb.csv` (renamed 2026-07-29
from `literature.csv` to match the project name) — historically the
same schema as `claude-casscf/database/literature.csv`, so mined rows could be
merged into the decision agent's reference database. **As of 2026-07-28 this
schema has diverged**: `ground_state_term` was merged into
`low_lying_states_eV` (renamed `electronic_structure_description`, with any
term symbol prefixed "Ground term: ..."). Merging into claude-casscf now
requires either re-splitting that column or updating claude-casscf's schema
to match. Follow this policy exactly.

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

The Python package does the mechanical work (API search, PDF download, text
extraction). **You do the reading and extraction** — deciding whether a paper
really contains a usable CASSCF calculation and pulling the fields out of the
text is judgment work, not regex work.

## Layout

```
code/mining_agent/            Python implementation (search/fetch/text/csv helpers)
database/aimdb.csv            output database (schema diverged from claude-casscf 2026-07-28, see above)
database/papers_index.csv     one row per candidate paper: doi, title, status, paths
papers/pending/<key>.pdf      downloaded PDFs still to be read (gitignored)
papers/mined/<key>.pdf        PDFs already read and judged (gitignored)
papers/si/<key>/              supplementary information (gitignored)
text/<key>.txt                extracted text (gitignored — do not commit)
logs/extractions.csv          append-only audit log, one row per decision
logs/oa_status.csv            OpenAlex open-access answer per DOI (see open_access below)
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
   queries OpenAlex (open-access-filtered) and appends new candidates to
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

   Record what kind of system the row describes in **`system_class`**:
   `atom`, `diatomic`, `molecule` or `solid-state` (a site in a host lattice,
   a surface/adsorbate model, or a bulk solid, however it is modelled).
   Size wins over composition — a two-atom species is `diatomic` even if it
   is a metal dimer — except that `solid-state` wins over everything, since
   it describes the environment rather than the size. The column exists so
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
   - **Metal-free organic compounds**: set `metal_center` to `none`
     (deliberate absence, distinct from empty = not stated); leave
     `metal_ox_state`, `d_electron_count`, and `ligand_set` empty. All
     other columns apply as usual (pi/lone-pair active spaces go in
     `active_space_orbital_description`; ground-state term, excitation
     energies, etc. go in `electronic_structure_description` as stated).
   - `active_space_protocol`: only if the paper describes its buildup
     sequence; this column is what the decision agent reads — quote it
     faithfully, format "(nel,norb) step; (nel,norb) step; ...".
   - `reference_doi` is mandatory — a row without a DOI is not addable.
   - `correlation_correction`: which post-CASSCF dynamic-correlation
     correction the reported result uses (`NEVPT2`, `CASPT2`, `RASPT2`,
     `MRCI`, ...) or `none` for a variational CASSCF/RASSCF/DMRG-only
     result. Leave it out of the JSON and `add-row` derives it from
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
     explicitly per row). This is the last column and is aimdb-only —
     `claude-casscf` merges just drop it.
   - `open_access` (last column, aimdb-only): `yes`/`no`/`unknown` — is
     `reference_doi` open access per OpenAlex's `open_access.is_oa`? Don't
     fill it by hand; run `.venv/bin/python tools_oa.py --refresh --stamp`
     from `code/` after a batch of rows. That rewrites `logs/oa_status.csv`
     (per-DOI `oa_status` gold/hybrid/green/bronze/diamond/closed plus the
     best OA URL) and restamps the column for every row. It is access
     metadata about the source, not a property of the calculation.
   - `electronic_structure_description` / `Other`: this column merges the
     ground-state term symbol (if stated — prefix it "Ground term: ...")
     with the low-lying state energies; paste the relevant numbers
     compactly, state units; SOC-corrected vs SOC-free matters
     (`soc_included` flag).
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
- Never download from anywhere except the OA URLs the search API returns.
- Never add a row whose DOI already has rows, unless it's a genuinely
  different compound from the same paper.
- Never edit or delete existing `aimdb.csv` rows without being asked —
  append-only, corrections go in `notes`.
