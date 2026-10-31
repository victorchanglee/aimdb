# Recheck: benchmark the fixed rows

Read `benchmark/claim_review/common_rules.md` first, then follow it.

This is the second benchmark. Do it exactly as `bench_brief.md` describes,
with one change: the rows under review are the **fixed rows** in
`fix_NN.json` (its `rows` list), not the `rows` in the batch file. Use the
batch file only for each paper's files, DOI, `instructions` and
`previous_rows`.

You did not write these rows and did not judge the earlier version. Judge
them only against the paper and its SI.

Be strict about two kinds of claim:
- a claim the paper does not state, including anything assumed or inferred;
- a claim that **contradicts** what the paper states. Mark these
  `unsupported`, and say in `evidence` that the claim contradicts the paper,
  quoting the passage it contradicts.

## Output

Write the same JSON format as `bench_brief.md` to the path your brief names.
