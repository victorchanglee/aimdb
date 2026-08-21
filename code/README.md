# code/

`mining_agent/` is the pipeline: search, fetch, text extraction, index and CSV
handling. Run it from this directory with `.venv/bin/python -m mining_agent
<command>` — see CLAUDE.md for the policy it implements.

`tools/` holds the standalone tools. They are all re-runnable: none holds a
hard-coded table of edits, and none is a record of a change that has already
been applied. One-off scripts of that kind are deliberately not kept — the
record of what they did lives in `logs/extractions.csv` and in git history.

Run them from this directory:

```
.venv/bin/python tools/tools_second_read_queue.py
```

They resolve the repository root from their own location, so they also work
from anywhere else. `tools/_bootstrap.py` is the one non-tool in there: it puts
`code/` on `sys.path` so a script one level down can still import
`mining_agent`.

## Reading and triage

| tool | what it does |
| --- | --- |
| `tools/tools_triage.py` | orders the reading queue by what each `text/<key>.txt` names. Never a substitute for reading: an empty hit count is not evidence of absence. |
| `tools/tools_heads.py` | prints the opening of many papers at once, so a long queue can be coarsely ordered in one pass. |
| `tools/tools_ctx.py` | pulls just the windows that decide the schema fields, so a paper can be judged from ~4-8k chars instead of 80k. |
| `tools/tools_despace.py` | repairs extracted text whose glyphs come out one character per token, which otherwise makes every regex silently miss. |

## Fetching

| tool | what it does |
| --- | --- |
| `tools/tools_parfetch.py` | parallel OA fetch for large candidate batches; same contract as `mining_agent fetch`. |
| `tools/tools_parrefetch.py` | parallel recovery pass over `fetch_failed`, trying every OA location and falling back to Europe PMC. Imports the host gate from `tools/tools_parfetch.py`. |

## Writing to the database

Only these nine touch `database/aimdb.csv`, and each refuses to act without
evidence or without preserving what it replaces. The last two delete text, so
they are held to a stricter rule: they only ever remove a second copy of
something the row still says elsewhere, they reword nothing, and both run
`--dry-run` before `--apply`.

| tool | what it does |
| --- | --- |
| `tools/tools_fill_gaps.py` | applies reviewed gap-fills. Refuses to overwrite a non-empty cell (unless `--allow-replace`) and refuses any fill without a quoted sentence. Logs every edit. |
| `tools/tools_resolve_duplicate_papers.py` | resolves a paper mined twice, once from its preprint and once from the journal. Keeps whichever key has more rows (journal wins a tie), quarantines the loser's, marks its index record `not_usable`, and puts the alternate DOI in the survivor's `notes`. Acts only when the survivor already covers every `(nel,norb)` the loser holds. |
| `tools/tools_strip_rows.py` | removes rows whose `compound_name` names no compound, quarantining each removed row verbatim to `logs/removed_rows.csv` first. |
| `tools/tools_stampdoi.py` | stamps `reference_doi` into row JSONs from the index, so a DOI is never typed from memory. |
| `tools/tools_trim_restated_name.py` | removes the row's own `compound_name` where it opens a prose segment. Keeps any qualifier after the name, and never touches a segment naming a different species. |
| `tools/tools_strip_llm_narration.py` | removes the mining model's account of its own reading, and records of past bulk edits, from `notes`. Re-appends any MD5 or DOI found inside a deleted sentence, and keeps contribution provenance and the QUEST export rule. |
| `tools/tools_fix_shout_caps.py` | lower-cases ordinary English words written mid-sentence in capitals. Matches whole tokens only, so `HS-IS` (intermediate spin) and `TWO-STATE` survive, and the greppable CLAUDE.md markers are masked out. |
| `tools/tools_dedupe_within_head.py` | where several segments open with the same head, says a clause common to all of them once. Requires the clause in every segment of the group, so a clause telling those segments apart is never collapsed. |
| `tools/tools_hoist_repeated_sentence.py` | moves a sentence repeated in every segment of a field to a single copy at the end. Requires three recurrences; splits on periods only, so a semicolon-joined clause is never orphaned. |

## Audit and derived files

| tool | what it does |
| --- | --- |
| `tools/tools_audit_database.py` | row-level completeness and source-evidence audit. Deliberately never fills a field. |
| `tools/tools_second_read_queue.py` | regenerates `logs/second_read_queue.csv`. A derived worklist — regenerate it whenever rows are added or text is fetched, because a stale queue hides work behind a wrong `text_available=no`. |
| `tools/tools_dupfp.py` | content-fingerprint duplicate scan; catches papers retitled between preprint and publication, which DOI dedup cannot. |
| `tools/tools_oa.py` | refreshes the `open_access` column from OpenAlex and keeps the full answer in `logs/oa_status.csv`. |
| `tools/tools_export.py` | exports `aimdb.csv` with QUEST-sourced rows dropped. This is the export boundary the contamination rule in CLAUDE.md depends on. |
