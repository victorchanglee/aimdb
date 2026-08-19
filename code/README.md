# code/

`mining_agent/` is the pipeline: search, fetch, text extraction, index and CSV
handling. Run it from this directory with `.venv/bin/python -m mining_agent
<command>` — see CLAUDE.md for the policy it implements.

Everything else here is a standalone tool. They are all re-runnable: none holds
a hard-coded table of edits, and none is a record of a change that has already
been applied. One-off scripts of that kind are deliberately not kept — the
record of what they did lives in `logs/extractions.csv` and in git history.

## Reading and triage

| tool | what it does |
| --- | --- |
| `tools_triage.py` | orders the reading queue by what each `text/<key>.txt` names. Never a substitute for reading: an empty hit count is not evidence of absence. |
| `tools_heads.py` | prints the opening of many papers at once, so a long queue can be coarsely ordered in one pass. |
| `tools_ctx.py` | pulls just the windows that decide the schema fields, so a paper can be judged from ~4-8k chars instead of 80k. |
| `tools_despace.py` | repairs extracted text whose glyphs come out one character per token, which otherwise makes every regex silently miss. |

## Fetching

| tool | what it does |
| --- | --- |
| `tools_parfetch.py` | parallel OA fetch for large candidate batches; same contract as `mining_agent fetch`. |
| `tools_parrefetch.py` | parallel recovery pass over `fetch_failed`, trying every OA location and falling back to Europe PMC. Imports the host gate from `tools_parfetch.py`. |

## Writing to the database

Only these three touch `database/aimdb.csv`, and each refuses to act without
evidence or without preserving what it replaces.

| tool | what it does |
| --- | --- |
| `tools_fill_gaps.py` | applies reviewed gap-fills. Refuses to overwrite a non-empty cell (unless `--allow-replace`) and refuses any fill without a quoted sentence. Logs every edit. |
| `tools_strip_rows.py` | removes rows whose `compound_name` names no compound, quarantining each removed row verbatim to `database/removed_rows.csv` first. |
| `tools_stampdoi.py` | stamps `reference_doi` into row JSONs from the index, so a DOI is never typed from memory. |

## Audit and derived files

| tool | what it does |
| --- | --- |
| `tools_audit_database.py` | row-level completeness and source-evidence audit. Deliberately never fills a field. |
| `tools_second_read_queue.py` | regenerates `logs/second_read_queue.csv`. A derived worklist — regenerate it whenever rows are added or text is fetched, because a stale queue hides work behind a wrong `text_available=no`. |
| `tools_dupfp.py` | content-fingerprint duplicate scan; catches papers retitled between preprint and publication, which DOI dedup cannot. |
| `tools_oa.py` | refreshes the `open_access` column from OpenAlex and keeps the full answer in `logs/oa_status.csv`. |
| `tools_export.py` | exports `aimdb.csv` with QUEST-sourced rows dropped. This is the export boundary the contamination rule in CLAUDE.md depends on. |
