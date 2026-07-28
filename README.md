# AIMdb: Artificial Intelligence multireference database

Finds open-access papers containing CASSCF/RASSCF/CASPT2/NEVPT2 calculations
on transition-metal complexes via the [OpenAlex](https://openalex.org) API,
downloads and text-extracts the PDFs, and transforms them into rows of
`database/literature.csv` — historically schema-identical to the decision
agent's reference database for direct merging, though as of 2026-07-28 that
schema has diverged (`ground_state_term` merged into
`electronic_structure_description`; see `CLAUDE.md`).

The Python package (`code/mining_agent/`) does the mechanical work; the
extraction judgment (is this a usable calculation? what does the paper
actually state?) is done by a Claude Code session following `CLAUDE.md`.

```
code/.venv/bin/python -m mining_agent search --query "CASSCF transition metal complex" --max 25
code/.venv/bin/python -m mining_agent fetch --max 5
code/.venv/bin/python -m mining_agent text
code/.venv/bin/python -m mining_agent status
```
