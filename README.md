# AIMdb: Artificial Intelligence Multiconfigurational database

A database of **multiconfigurational quantum
chemistry calculations** extracted from the published literature.

Multiconfigurational quantum chemistry methods (CASSCF, RASSCF, CASPT2, NEVPT2, MRCI, etc.) rely on the choice of active space, and that choice is scattered across methods sections and supporting information of thousands of scientific articles. 
Historically, these choices have been documented inconsistently—scattered across primary texts and supporting information in non-standardized formats. AIMdb
transforms this scattered prose into a queryable database. The database is built by an agentic literature-mining pipeline that exploits a large language model that performs the reading-comprehension step conventional and judges whether a paper reports a usable, compound-specific calculation, and extracting its reported fields under a strict copy-never-infer discipline, with every decision recorded in an append-only audit log.

**[database/aimdb.csv](database/aimdb.csv)** is the database.

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
docs/                         static site generator for the public database browser
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
AIMdb: Artificial Intelligence Multiconfigurational database.
Victor Chang Lee, 2026. https://github.com/victorchanglee/aimdb
```

Every row carries a `reference_doi`. **Please cite the original paper** for any
value you take from the database.
