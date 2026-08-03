# AIMdb: Artificial Intelligence multiconfigurational database

A database of **multiconfigurational quantum
chemistry calculations** extracted from the published literature.

Multiconfigurational methods (CASSCF, RASSCF, CASPT2, NEVPT2, MRCI, DMRG,
MC-PDFT) rely on the choice of active space, and that choice is scattered across methods sections and supporting information,
described in a dozen different phrasings, and almost never tabulated. AIMdb
turns that scattered prose into rows you can query, so that the question *"what
active space have people actually used for a d⁶ iron complex, and why?"* has an
answer you can look up instead of guess.

**[database/aimdb.csv](database/aimdb.csv)** is the database. Everything else
in this repository exists to produce it, check it, or publish it.

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

Every status change appends to `logs/extractions.csv` with a timestamp, DOI,
action, result and free-text reasoning. **The audit log is the review
mechanism** — reasoning is written so a chemist can check it, including for
papers that were rejected.

### Rules the extraction follows

- **Copy, never infer.** Every value must be stated in the paper, or be an
  arithmetic restatement of something stated (eV from cm⁻¹, d-count from a
  stated oxidation state) with the conversion noted in `notes`.
- **Append-only.** Existing rows are not edited or deleted; corrections go in
  `notes`.
- **`reference_doi` is mandatory.** A row without provenance is not addable.


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

## Licence and citation

Released under [CC BY 4.0](LICENSE) — share and adapt freely, including
commercially, with attribution.

```
AIMdb: Artificial Intelligence multiconfigurational database.
Victor Chang Lee, 2026. https://github.com/victorchanglee/aimdb
```

Every row carries a `reference_doi`. **Please cite the original paper** for any
value you take from the database.
