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

Only these ten touch `database/aimdb.csv`, and each refuses to act without
evidence or without preserving what it replaces. The last two delete text, so
they are held to a stricter rule: they only ever remove a second copy of
something the row still says elsewhere, they reword nothing, and both run
`--dry-run` before `--apply`.

| tool | what it does |
| --- | --- |
| `tools/tools_fill_gaps.py` | applies reviewed gap-fills. Refuses to overwrite a non-empty cell (unless `--allow-replace`) and refuses any fill without a quoted sentence. Logs every edit. |
| `tools/tools_repoint_duplicate_text.py` | after a duplicate is resolved, gives the surviving key the local text sitting under the discarded one. Prefixes the copy with a banner naming the key and DOI it came from, because preprint and published text are not the same document. Touches no row. |
| `tools/tools_resolve_duplicate_papers.py` | resolves a paper mined twice, once from its preprint and once from the journal. The peer-reviewed version survives (user ruling 2026-10-11), its loser's rows are quarantined, its index record is marked `not_usable`, and the survivor's `notes` gains the alternate DOI. Acts only when the survivor already covers every `(nel,norb)` the loser holds, which is what stops the ruling from destroying data. |
| `tools/tools_find_published_version.py` | the case that tool cannot see: a row citing a preprint whose published version is **not in the index at all**, so no title match inside the index can find it (353 rows in 136 groups on 2026-10-11). Asks OpenAlex twice per group -- the preprint record's own `locations` for a journal it links to, then a title search confirmed by whole-title equality. Reports only; a title match is a candidate, not a decision, since a published version retitled in review is invisible to both routes and two papers can share a title. |
| `tools/tools_strip_rows.py` | removes rows whose `compound_name` names no compound, quarantining each removed row verbatim to `logs/removed_rows.csv` first. |
| `tools/tools_stampdoi.py` | stamps `reference_doi` into row JSONs from the index, so a DOI is never typed from memory. |
| `tools/tools_trim_restated_name.py` | removes the row's own `compound_name` where it opens a prose segment. Keeps any qualifier after the name, and never touches a segment naming a different species. |
| `tools/tools_strip_llm_narration.py` | removes the mining model's account of its own reading, and records of past bulk edits, from `notes`. Re-appends any MD5 or DOI found inside a deleted sentence, and keeps contribution provenance and the QUEST export rule. |
| `tools/tools_fill_element.py` | fills the derived `element` column from `metal_center` and `formula`. Empty cells only by default; `--regenerate` recomputes every row but **keeps any value it would shrink** and reports it, because an abbreviated formula (`Co(PPh3)2I`, `[Fe(TPP)Cl]`) hides the carbon and hydrogen a symbol scan needs — measured 2026-10-11, a blind regenerate would have dropped hydrogen from 303 rows and carbon from 293. `--allow-shrink` overrides. |
| `tools/tools_fix_shout_caps.py` | lower-cases ordinary English words written mid-sentence in capitals. Matches whole tokens only, so `HS-IS` (intermediate spin) and `TWO-STATE` survive, and the greppable CLAUDE.md markers are masked out. |
| `tools/tools_dedupe_within_head.py` | where several segments open with the same head, says a clause common to all of them once. Requires the clause in every segment of the group, so a clause telling those segments apart is never collapsed. |
| `tools/tools_hoist_repeated_sentence.py` | moves a sentence repeated in every segment of a field to a single copy at the end. Requires three recurrences; splits on periods only, so a semicolon-joined clause is never orphaned. |
| `tools/tools_save_coordinate_block.py` | copies a coordinate block from `text/<file>` into `database/structures/<entry_id>.xyz` VERBATIM and sets `structure_file`/`structure_provenance` on the row (`computational` or `experimental`, the reader's statement of how the paper got the geometry). Refuses a composition that disagrees with the row's `formula`, refuses to overwrite without `--replace`, and takes `--range A B` for a block that page breaks split. `--batch decisions.json` applies a reviewed list in order. Line numbers are `grep -n` numbering. |
| `tools/tools_pubchem_identifiers.py` | resolves each molecule row's `compound_name` in PubChem and writes `database/identifiers.csv` (CID, InChIKey, InChI, SMILES, PubChem formula, and a `status` saying whether that formula matches the row's). With `--apply`, stamps the queued PubChem 3D conformers as `structure_provenance=ai_generated` on rows that have no structure, and only where the formula matched. A name fragment never counts without a formula to check it against. One request per second: PubChem blocks a client for many minutes at rates its documentation allows, because a failed name lookup costs it seconds of server time. |

## Querying the database (for other code and agents)

`mining_agent/query.py` is the read-only way in, for `claude-casscf` and for
anything else that wants rows without loading and grepping the whole 11 MB
CSV. It is a library first and a CLI second:

```python
from mining_agent import query

query.get("W2971968767-e")                      # one row, or None
query.find(metal="Dy", has_space=True, limit=5) # filtered, with an envelope
query.spaces_for(element="Fe")                  # histogram the spaces used
```

```
.venv/bin/python -m mining_agent query --element Fe --spaces --format tsv
.venv/bin/python -m mining_agent query --doi 10.1063/5.0269968 --format json
.venv/bin/python -m mining_agent query --schema
```

Three things about it are deliberate.

**QUEST rows are included** (user ruling 2026-10-15; `config.QUEST_EXCLUDE = False`). While the exclusion applied, they were withheld by default: The export boundary in CLAUDE.md is
enforced in code here, not left to whoever remembers to run
`tools_export.py`; `include_quest=True` (`--include-quest`) is the only way
past it, and the envelope always says how many rows were withheld. The DOI
list now lives in `mining_agent/config.py` so this module and
`tools_export.py` cannot drift apart.

**Every result reports its blind spots.** A filter can only match rows whose
field is filled, and coverage is uneven — `metal_center` is set on 38% of
rows, `formula` on 73%, `element` on 86%. So each result counts the rows an
active filter could never have matched, and names the column a caller would
have to go and fill. An empty result and an unextracted field are different
answers.

**The schema is a published contract.** `query.schema()` returns
`config.SCHEMA_VERSION` together with a fingerprint derived from the column
names, so a consumer can detect drift even if a schema change forgets to bump
the version. Bump it when `LITERATURE_COLUMNS` changes — the schema has
drifted once already (2026-07-28).

There is no write path here on purpose. Rows go in through
`csvio.append_row`, and CLAUDE.md is explicit that extraction is judgement
work, so nothing in this module lets an agent append a row it has not read a
paper for.

## Audit and derived files

| tool | what it does |
| --- | --- |
| `tools/tools_audit_database.py` | row-level completeness and source-evidence audit. Deliberately never fills a field. |
| `tools/tools_second_read_queue.py` | regenerates `logs/second_read_queue.csv`. A derived worklist — regenerate it whenever rows are added or text is fetched, because a stale queue hides work behind a wrong `text_available=no`. |
| `tools/tools_dupfp.py` | content-fingerprint duplicate scan; catches papers retitled between preprint and publication, which DOI dedup cannot. |
| `tools/tools_crossref_zfs_project.py` | cross-references an external ZFS extraction (`../zfs/zfs_database.csv`, 782 papers, one row per compound x determination) against aimdb per compound. Useful for the one thing aimdb cannot do for itself: naming the compounds a class-named row hides. 14 of its papers carry own-work multireference rows, 12 are shared with aimdb, and one is a genuine gap -- 10.1039/c5dt00600g, where zfs names eight Ni(II) Schiff-base complexes at CAS(8,5) and aimdb has a single class-named row. Reports LEADS: the pairing is token overlap and the two projects name compounds differently. |
| `tools/tools_find_class_named_rows.py` | the queue for splitting work: rows whose `compound_name` shows an enumeration signal, ranked by how many compounds appear compressed into them, with whether the source text is on disk. 536 candidates on 2026-10-11, 466 splittable now. A CANDIDATE list -- CLAUDE.md warns the `compound_name` proxy over-fires, so read the name before acting. Two kinds of range are excluded from the count rather than miscounted: an atom count ("13-61-atom models") and a solvent-shell count ("0-30 water molecules"), both of which an earlier version read as compound counts. |
| `tools/tools_find_active_spaces.py` | for rows with an EMPTY active space: scans each paper's text for every (n,m) it states, in the forms papers use (`CAS(n,m)`, `(10e,8o)`, "ten electrons in eight orbitals"), so a batch can be adjudicated at once. Reports only. Measured 2026-10-11: of 506 papers with a gap and local text, **436 state no space anywhere** — three quarters of the gap is absent from the source, not mistranscribed. A bare (n,m) is weak evidence: two thirds of the single-space papers were still not fillable, the number belonging to a literature-comparison table, another group's work, a general remark, or a class-named row. |
| `tools/tools_classify_active_spaces.py` | buckets the rows whose `active_space_nel`/`norb` is not an integer (511 cells / 308 rows on 2026-10-11) by whether the number is actually recoverable. Half are one mining-era convention -- two or three whole spaces packed into one cell, positionally paired across the two fields, so nel `14; 8` beside norb `10; 7` is CAS(14,10) and CAS(8,7). `--apply` converts only the bucket whose own wording marks the leading number as the production space and the rest as a test or variant, and only when BOTH fields of the row are recoverable. Everything else needs the paper. |
| `tools/tools_batch_si.py` | runs the `si` fetch (figshare component DOIs for ACS papers, PMC OA packages for anything with a PMC id, resolved 200 DOIs per request) over every paper with a structureless row, text-extracting each PDF to `text/<key>_si_<stem>.txt`. Resumable through `logs/si_batch.csv`. Fetched 150 papers' SI from the first 900 keys on 2026-10-11. |
| `tools/tools_find_coordinate_blocks.py` | finds every Cartesian coordinate block in the local text (article and SI), joins blocks across page-break noise, and reports per block the atom count, composition, nearest species label, and which of the paper's rows share that composition, to `logs/coordinate_blocks.csv`. A worklist for `tools_save_coordinate_block.py`, never a decision: an SI prints every stationary point and every DFT comparison geometry, and only one is the row's. |
| `tools/tools_check_property_leaks.py` | after any hand edit to `properties`, finds a row whose own note or `Other` quotes a value the same edit stored -- which makes the extractor re-derive hand-curated data from the annotation describing the curation. Reads notes and `Other` ALONE, because a row's mining-era prose legitimately carries values the extractor lifted and comparing against all of it buries the real thing. Baseline is seven pre-existing mining-era restatements; a higher count is new. |
| `tools/tools_properties.py` | fills the packed `properties` field (`D=-31.5 cm-1 calc; gz=19.86 calc; Ueff=877 cm-1 exp`) from the prose already in each row, so the values stay grounded in the source and `benchmark/check_grounding.py` still covers them. Keys are D, E/D, gz and Ueff; a new observable is a new key, not a new column. `--fill-only` merges per key and never overwrites, which is the safe mode after hand-mining; `--apply` rewrites the whole field and discards hand curation. `--migrate` is the one-off that folded the retired `zfs_*` columns in. |
| `tools/tools_oa.py` | refreshes the `open_access` column from OpenAlex and keeps the full answer in `logs/oa_status.csv`. |
| `tools/tools_export.py` | exports `aimdb.csv`. Drops QUEST-sourced rows only when `config.QUEST_EXCLUDE` is set, which it is not since 2026-10-15. |
