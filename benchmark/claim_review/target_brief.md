# Targeted fix: clear the errors the recheck found

Read `benchmark/claim_review/common_rules.md` first, then follow it.

## Inputs

For the same batch of papers you have:
- the batch file: the paper's files;
- `fix_NN.json`: the current rows;
- `recheck_NN.json`: an independent benchmark of those rows.

This pass is **narrow**. Act only on what the recheck flags. Make no other
change to any row.

## What to do, per paper

1. **Unsupported claims and contradictions.** Return to the paper for every
   claim labelled `unsupported`.
   - If the paper settles it, correct the claim to what the paper states.
   - If the paper does not state the value at all, remove it.
   - Cite the passage that settles it.
   - If the paper shows the recheck is wrong, keep the claim and log
     `kept_benchmark_wrong` with the quote.
2. **Omissions.** Add an omission only when you find the fact in the paper or
   SI as printed. Add nothing by inference, arithmetic beyond the allowed
   kinds, or generalisation.
3. **Everything else stays as it is,** including entry_ids and `continues`.
   Do not rephrase, reorder or tidy.

## Output

Write the **complete row set**, not a diff, as one JSON file at the path your
brief names. Use the same format as `fix_brief.md`:

```
{"papers": {"<key>": {"decision": "usable|not_usable", "reason": "..."}},
 "rows": [ {...} ],
 "fix_log": [{"key": "...", "row": "...", "field": "...", "action": "fixed|added|removed|kept_benchmark_wrong", "evidence": "quote (location)"}]}
```

## Final message

Per paper, give:
- the number of unsupported claims cleared;
- the number of omissions added;
- the recheck items rejected, and why.
