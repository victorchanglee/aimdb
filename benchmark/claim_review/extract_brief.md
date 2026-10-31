# Extraction: first pass on newly mined papers

Read `benchmark/claim_review/common_rules.md` first, then follow it.

## Input

Your batch file lists papers. For each, it gives the key, DOI, title, `text`,
`pdf` and `si` (SI files, possibly none). Ignore any `rows` it carries.

## What to do

For each paper, decide:
- **usable:** the paper reports its own multireference calculation (CASSCF,
  RASSCF, CASPT2, NEVPT2, MRCI, DMRG and so on) on a named species, with
  (nel,norb) stated, or derivable by the allowed arithmetic;
- **not_usable:** otherwise. Give the reason. Values cited from other work
  do not count.

For a usable paper, write one row per species, or per species and active
space, following the schema in `common_rules.md`. Record every value the
paper reports for each row (energies, D, E/D, g values, barriers, and so on)
and the active-space findings, each with its method.

## Output

Write one JSON file at the path your brief names:

```
{"papers": {"<key>": {"decision": "usable|not_usable", "reason": "..."}}, "rows": [ {...} ]}
```

## Final message

Per paper, give the decision and each row's compound and (nel,norb).

## Next steps

Your rows then go through the four review passes in CLAUDE.md step 5b.
