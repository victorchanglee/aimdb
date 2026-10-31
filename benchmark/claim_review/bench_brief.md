# Benchmark: judge a paper's rows against the paper

Read `benchmark/claim_review/common_rules.md` first, then follow it.

Your batch file holds, for each paper:
- the paper's files;
- the rows currently recorded for it.

Judge the rows only against the paper and its SI. You did not write them and
must not assume they are right.

A paper entry may also carry:
- `instructions`: maintainer decisions for that paper. Follow them.
- `previous_rows`: an older version of the rows. It is not ground truth.
  Treat any fact in it that the rows lack as a possible omission. List it only
  if the paper states it.

For each paper:

1. **Decision.** Is the paper usable? It must report a multireference
   calculation of its own on a named species, with an active space stated
   anywhere. If it is not usable, say why.
2. **Claims.** Split every field of every row into atomic claims. An atomic
   claim is one checkable fact with its species attached, for example:
   - "(nel,norb) = (8,7) for complex 2";
   - "NEVPT2 D = -45.8 cm-1 for [Co(tpy)Br2]";
   - "ground state is a triplet".

   Count claims per row. The same claim on three rows is three claims.

   Label each claim:
   - `supported`: the paper states it, or it is allowed arithmetic on stated
     values.
   - `unsupported`: the paper does not state it, or states something
     different. This covers:
     - a wrong value, sign, unit, method or species;
     - an assumed multiplicity, point group or formula;
     - an interpretation the paper does not make;
     - a protocol order the paper does not give;
     - a false "not stated".
   - `not_a_paper_claim`: bookkeeping that is not about the paper.

   Give evidence (a quote with its location) for every `unsupported` claim.
   Say what the paper does state.
3. **Omissions.** List everything the paper reports that belongs in the
   schema but the rows lack. Each omission is one atomic claim, with the
   species, the field it belongs in, and evidence. Include:
   - missing rows: a species, or species and active space, that the paper
     computes with a multireference method and reports results for;
   - empty or incomplete fields whose value the paper states;
   - reported values missing from electronic_structure_description;
   - active-space findings missing from Other;
   - build-up sequences missing from active_space_protocol.

   Do not list bookkeeping. Do not list facts outside the schema's purpose,
   such as synthesis details.

Be literal and exhaustive. A vaguer statement does not cover a specific one.

## Output

Write one JSON file at the path your brief names:

```
{"papers": {"<key>": {"decision": "usable|not_usable", "decision_note": "...",
   "claims": [{"row": "<entry_id>", "field": "...", "claim": "...", "label": "supported|unsupported|not_a_paper_claim", "evidence": "..."}],
   "omissions": [{"species": "...", "field": "...", "claim": "...", "evidence": "quote (location)"}]}}}
```

## Final message

Per paper, give:
- the number of claims supported, unsupported and bookkeeping;
- the number of omissions;
- the main errors.
