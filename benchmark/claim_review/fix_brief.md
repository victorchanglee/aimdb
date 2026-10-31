# Fix: rewrite a paper's rows using its benchmark

Read `benchmark/claim_review/common_rules.md` first, then follow it.

## Inputs

For the same batch of papers you have:
- the batch file: the paper's files and its current rows;
- the benchmark file, which judged those rows against the paper. It labels
  every claim and lists every omission.

A paper entry may also carry:
- `instructions`: maintainer decisions for that paper. Follow them.
- `previous_rows`: an older version of the rows. Check it for any fact the
  paper states that your rows lack, and add each one you find, verified like
  an omission.

The benchmark is a lead, not ground truth. Verify each item in the paper and
SI before you act on it.

## What to do, per paper

1. **Fix unsupported claims.** Fix every `unsupported` claim the paper
   confirms is wrong, by correcting it or removing it.
2. **Add omissions.** Add every omission the paper confirms: new rows, field
   values, reported values, Other findings and build-up sequences.
   - Every value you add needs its own quote.
   - Copy it as the paper prints it. Do not convert or reinterpret.
   - This is where most new errors came from in the evaluation: a table label
     turned into a different (nel,norb), separate calculations turned into a
     build-up sequence, a series reversed, and a value attributed to the wrong
     calculation.
3. **Remove** bookkeeping and narration.
   - Never merge rows that are kept apart for distinct species, reactions or
     environments, such as gas phase versus solvent, when the paper reports
     separate results for each. Merging loses the per-row answer.
   - Splitting a merged row is the usual fix.
4. **Change the decision** if the benchmark says it is wrong and the paper
   agrees.
5. **Re-check the rest of each row** against the paper while you are there,
   and fix any further error, including ones the benchmark missed.

## Output

Write the **complete corrected row set** for every paper, not a diff, as one
JSON file at the path your brief names:

```
{"papers": {"<key>": {"decision": "usable|not_usable", "reason": "..."}},
 "rows": [ {...} ],
 "fix_log": [{"key": "...", "row": "...", "field": "...", "action": "fixed|added|removed|kept_benchmark_wrong", "evidence": "quote (location)"}]}
```

- Give every row a `continues` field: the entry_id of the database row that
  describes the same species, and the same active space where there are
  several. Database rows are the `previous_rows` when the batch has them,
  otherwise the `rows`. Leave `continues` empty for a species the database
  did not have. The apply tool uses it to carry structure files over, so
  never point two rows at one database row unless the old row merged them.
- Use `kept_benchmark_wrong` when the paper shows the benchmark was mistaken.
- Give a `not_usable` paper no rows.

## Final message

Per paper, give:
- the number of claims fixed;
- the number of omissions added;
- the benchmark items you rejected, and why.
