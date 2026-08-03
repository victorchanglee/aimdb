# AIMdb: Artificial Intelligence multiconfigurational database

A curated, machine-readable database of **multiconfigurational quantum
chemistry calculations** extracted from the published literature: which active
space was used, how it was built, on what compound, with what method and basis,
and what came out.

Multiconfigurational methods (CASSCF, RASSCF, CASPT2, NEVPT2, MRCI, DMRG,
MC-PDFT) live or die by the choice of active space, and that choice is craft
knowledge — scattered across methods sections and supporting information,
described in a dozen different phrasings, and almost never tabulated. AIMdb
turns that scattered prose into rows you can query, so that the question *"what
active space have people actually used for a d⁶ iron complex, and why?"* has an
answer you can look up instead of guess.

**[database/aimdb.csv](database/aimdb.csv)** is the database. Everything else
in this repository exists to produce it, check it, or publish it.

---

## The database at a glance

| | |
|---|---|
| Rows (compound × method results) | **1,441** |
| Distinct source papers | **834** |
| Papers screened to get there | 3,274 |
| Distinct metal centres | 74 (plus 740 metal-free organic rows) |
| Licence | CC BY 4.0 |

Field coverage — useful for knowing what the database can actually answer:

| Column | Filled |
|---|---|
| `method`, `reference_doi` | 100% |
| `active_space_orbital_description` | 93.3% |
| `active_space_norb` | 92.7% |
| `active_space_nel` | 91.1% |
| `active_space_protocol` | 88.8% |
| `multiplicities_studied` | 88.0% |
| `software` | 66.3% |
| `nroots_per_mult` | 38.1% |

The weak columns are weak because the *papers* are silent, not because the
extraction skipped them — see [Empty means empty](#empty-means-empty).

---

## Schema

One row per distinct compound × method result. 33 columns, grouped:

**Identity** — `entry_id`, `compound_name`, `formula`, `point_group`

**Metal centre** — `metal_center`, `metal_ox_state`, `d_electron_count`,
`ligand_set`. `metal_center` is `none` for metal-free organics (a deliberate
absence, distinct from empty = not stated); for f-elements the f-electron count
goes in `d_electron_count` (`4f9`).

**Level of theory** — `method`, `software`, `basis_set`,
`relativistic_treatment`, `soc_included`, `ss_included`,
`correlation_correction`

**Active space** — the heart of the database:
- `active_space_nel` / `active_space_norb` — the (n,m) of the production calculation
- `active_space_orbital_description` — *which* orbitals, in the paper's own words
- `active_space_protocol` — the buildup sequence, formatted
  `(nel,norb) step; (nel,norb) step; ...`. This column records how chemists
  actually arrive at an active space, and it is what makes the database more
  than a table of numbers.

**Results** — `multiplicities_studied` (numeric 2S+1), `nroots_per_mult`,
`ground_state_mult`, `electronic_structure_description` (ground term prefixed
`Ground term: ...`, plus low-lying state energies with units), `Other`

**Geometry** — `geometry_source`, `structure_file`, `structure_provenance`
(`computational` / `experimental` / `ai_generated`). Coordinates in
`database/structures/` are verbatim from the paper's SI where marked
`computational`/`experimental`; `ai_generated` means a PubChem conformer that
is *not* the paper's geometry.

**Provenance** — `reference_short`, `reference_doi` (mandatory), `year`,
`notes`, `entry_type` (`llm_mining` / `llm_reproduced` / `human`),
`mining_model`

---

## How the data is produced

The Python package does the mechanical work. **The reading and extraction
judgment is done by an LLM session** following the policy in
[`CLAUDE.md`](CLAUDE.md) — deciding whether a paper really contains a usable
multiconfigurational calculation, and pulling the fields out of prose, is judgment
work rather than regex work.

```
search / import  →  fetch  →  text  →  READ AND JUDGE  →  add-row
   OpenAlex        OA PDFs   extract     (the LLM)        aimdb.csv
```

Every status change appends to `logs/extractions.csv` with a timestamp, DOI,
action, result and free-text reasoning. **The audit log is the review
mechanism** — reasoning is written so a chemist can check it, including for
papers that were rejected.

### Rules the extraction follows

- **Copy, never infer.** Every value must be stated in the paper, or be an
  arithmetic restatement of something stated (eV from cm⁻¹, d-count from a
  stated oxidation state) with the conversion noted in `notes`.
- **Only open-access sources.** Nothing is ever downloaded except the OA
  locations the APIs report. Downloaded PDFs and extracted text are
  gitignored — they are copyrighted and are not redistributed here.
- **Append-only.** Existing rows are not edited or deleted; corrections go in
  `notes`.
- **`reference_doi` is mandatory.** A row without provenance is not addable.

### Empty means empty

A blank cell means *the paper did not state it*. It never means "we didn't
look", and never means a plausible default was withheld. This is the single
most important property of the database: if `active_space_nel` is empty on a
row whose paper says the space was "extended by a σ(M–C) orbital" without
giving a number, that emptiness is information. Filling it by counting
electrons yourself would look identical to a real value and be unverifiable.

### Quality controls

Duplicate detection runs in **four independent layers**, because each catches
what the previous cannot:

1. **md5** — byte-identical files under different DOIs
2. **DOI** — the index deduplicates on DOI at import
3. **Normalised title prefix** — catches preprint/published pairs, which have
   genuinely different DOIs
4. **Content fingerprint** (`code/tools_dupfp.py`) — catches papers *retitled*
   on publication, which defeat title matching entirely, by comparing the sets
   of distinctive decimal numbers in their texts

Also routine: title-vs-text overlap scanning (OA links do sometimes serve a
completely unrelated paper), and DOI stamping from the index
(`code/tools_stampdoi.py`) so a DOI is never typed by hand into a row.

---

## Repository layout

```
database/aimdb.csv            the database
database/papers_index.csv     one row per candidate paper: doi, title, status, paths
database/structures/          .xyz geometries, provenance-stamped
database/contributions.csv    community submissions awaiting review
database/blocked_papers.csv   papers whose OA link could not be fetched, with reasons
code/mining_agent/            search / fetch / text-extract / CSV helpers
code/tools_*.py               triage, dedup, repair and audit utilities
logs/extractions.csv          append-only audit log, one row per decision
site/                         static site generator for the public database browser
CLAUDE.md                     the extraction policy the LLM session follows
papers/, text/                downloaded PDFs and extracted text (gitignored)
```

---

## Getting started

Requires Python 3.10+.

```bash
git clone git@github.com:victorchanglee/aimdb.git
cd aimdb/code
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # requests, pypdf
```

Just using the data needs none of that — `database/aimdb.csv` is a plain CSV:

```python
import pandas as pd
df = pd.read_csv("database/aimdb.csv")

# active spaces used on iron complexes
fe = df[df.metal_center == "Fe"]
print(fe[["compound_name", "active_space_nel", "active_space_norb", "method"]])

# how do people build up an active space?
print(df[df.active_space_protocol.notna()].active_space_protocol.head())
```

### CLI

Run from `code/`:

```bash
.venv/bin/python -m mining_agent status                    # index + database summary
.venv/bin/python -m mining_agent search --query "NEVPT2 zero-field splitting" --max 25
.venv/bin/python -m mining_agent import --csv my_dois.csv  # any CSV with a doi column
.venv/bin/python -m mining_agent fetch --max 5
.venv/bin/python -m mining_agent refetch                   # retry repository mirrors + Europe PMC
.venv/bin/python -m mining_agent text
.venv/bin/python -m mining_agent si --key W1234567         # supporting information
.venv/bin/python -m mining_agent add-row --json row.json
.venv/bin/python -m mining_agent mark --key W1234567 --status extracted --reasoning "..."
.venv/bin/python -m mining_agent tidy                      # reconcile files with the index
```

---

## Contributing

**Data corrections and additions** are welcome. The site has a Contribute form
that emits a one-row CSV; submissions land in `database/contributions.csv` with
`review_status=pending` and are **never auto-merged**. Each is reviewed against
its DOI exactly like a mined paper — scope test plus copy-never-infer — before
being promoted into `aimdb.csv` with `entry_type=human`.

If you find a row that misstates what a paper says, please open an issue with
the `entry_id` and the DOI. Corrections are appended to `notes` rather than
overwriting the original value, so the record of what was extracted stays
intact.

---

## Scope and known limitations

- **What counts as usable:** a real multiconfigurational calculation
  (CASSCF/RASSCF/CASPT2/NEVPT2/MRCI/DMRG/MC-PDFT) on a *specific chemical
  compound*, with at least the active space size stated. Transition-metal
  complexes and metal-free organics both count. Reviews citing others' numbers,
  and algorithm papers that never specify an active space, do not.
- **Bare diatomics and free atoms are currently excluded**, triatomics and
  larger admitted. This line is arbitrary and the excluded set is substantial —
  those papers are marked `not_usable` with their full active spaces recorded
  in the audit log, so they convert to rows immediately if the rule is relaxed.
- **Coverage is open-access-limited.** Roughly 1,400 indexed papers could not
  be fetched: publisher sites that block scripted clients, dead OA links, and
  HTML-only landing pages. They are listed with reasons in
  `database/blocked_papers.csv`. Nothing behind a paywall is ever scraped.
- **`nroots_per_mult` is sparse (38%)** — mostly genuine absence, since many
  papers converge states individually rather than state-averaging over a stated
  number of roots.
- **Rows are LLM-extracted** (`entry_type=llm_mining`, with the model recorded
  per row in `mining_model`). They are reviewable rather than reviewed: the
  audit log gives the reasoning behind each one, but the database has not been
  independently verified against every source paper. Treat it as a
  well-documented starting point, and cite the primary paper — not this
  database — for any number you use in your own work.

---

## Licence and citation

Released under [CC BY 4.0](LICENSE) — share and adapt freely, including
commercially, with attribution.

```
AIMdb: Artificial Intelligence multiconfigurational database.
Victor Chang Lee, 2026. https://github.com/victorchanglee/aimdb
```

Every row carries a `reference_doi`. **Please cite the original paper** for any
value you take from the database.
