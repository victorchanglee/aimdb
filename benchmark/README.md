# benchmark/

Re-runnable checks on the *accuracy* of `database/aimdb.csv`, as opposed to its
schema. `code/tools/tools_audit_database.py` asks whether a row is
well-formed; these ask whether it is true.

## check_grounding.py — does the number exist in the paper?

```
code/.venv/bin/python benchmark/check_grounding.py              # full report
code/.venv/bin/python benchmark/check_grounding.py --calibrate  # vs cases.csv
code/.venv/bin/python benchmark/check_grounding.py --selftest   # sensitivity
code/.venv/bin/python benchmark/check_grounding.py --entry W2055916038-a
```

Every decimal in a row's prose columns (`electronic_structure_description`,
`Other`, `active_space_protocol`, `method`, `notes`) is looked up in
`text/<key>.txt`. A value that is nowhere in the source is either a
transcription slip or an invention. The full report goes to
`logs/grounding_report.csv`, one line per checked row.

Only decimals count. Integers in prose ("the 3 lowest states", "a (12,11)
space") are too common to carry evidence, and matching them inflates the hit
rate — the first hand run did match them, and two of its five alarms turned out
to be rows containing no decimal at all.

**Reading the output.** The headline located fraction is a health indicator,
not an error rate; what matters is the triage of the flagged rows:

| bucket | meaning |
| --- | --- |
| `review` | healthy source text, and this row fails while its siblings pass. The row is the suspect — re-read it. |
| `review-weak-text` | same, but the source's decimal density sits in the bottom tenth of the corpus. Read the paper before trusting the alarm. |
| `unverifiable-source-wide` | most of the paper's rows fail together, so the text is missing the tables the rows were read from. Not a row defect. |
| `unverifiable-text-damaged` | the text layer lost its decimal points outright (`W931703638`: 2,888 digits, zero decimals). Unanswerable here by construction. |

As of 2026-10-09: 4,877 rows checkable, 67,159 claims, 94.9% located, 60 rows
flagged — 13 to review, 47 unverifiable from the source.

**Limits worth knowing before acting on a flag.**

- A **one-row paper** cannot be told apart from a source problem by sibling
  agreement, so a single-row flag needs a human to open the PDF. Several of
  the current `review` rows quote total energies to eight decimals, which
  normally live in tables; that is a likely source loss, not a likely slip.
- **Derived values** — a difference or a unit conversion the extractor worked
  out from the paper's own statements — are correct and absent from the text by
  definition. Such rows usually say so in `notes`.
- **SI text** (`text/<key>_si_*.txt`) is not searched; a value the paper states
  only in its supplementary information reads as missing.
- Rows whose paper has no local text are not checked at all. About half the
  database is in that position, and restoring it is not cheap: of 2,429 rowed
  papers lacking text on 2026-10-09, only 12 still had a PDF on disk.

## cases.csv — the calibration set

Ten rows hand-adjudicated against their sources on 2026-10-09, each with the
verdict a human reached (`label`) and what the detector is expected to do with
the row *today* (`expect`). These are not the same thing: `W1996550977-a` was a
real transcription error, found and corrected, so it is expected to pass now —
a mismatch there would mean the correction had been lost.

`--calibrate` prints one line per case and a count of agreements. **A mismatch
is not automatically a bug in the detector**: the row may have changed, or the
source text may have been re-extracted. Read the case note first.

The set deliberately holds two rows from `W2397900523`, because one row failing
is a row problem and most of a paper failing is a source problem, and the rule
that separates them cannot be tested on a single example.

Extend it whenever a flag is adjudicated by hand — that is the only way the
screen's precision stays a measured quantity. Keep the note specific enough
that a later reader can tell why the verdict was reached without redoing the
reading.

## --selftest — sensitivity

`cases.csv` contains no row that is both wrong and still in the database, so it
can only measure false alarms. `--selftest` supplies the other half: it takes
fully grounded rows, bumps one digit of one value to something the paper does
not contain, and checks the alteration is reported. 276/276 detected at
`--n 300 --seed 7` (24 rows skipped where every neighbouring value also appears
in the paper).

That is sensitivity to a single altered digit at the *value* level. A row is
only flagged when it locates under 40% of at least 4 claims, so one bad number
in a long prose field will show in `logs/grounding_report.csv` without flagging
the row — by design, since one miss is far more often a rounding or layout
artefact than an error.

## Thresholds

`--min-values` (4) and `--threshold` (0.4) set when a row is flagged. The
decimal-density cuts for `text_health` are constants in the script, drawn from
the measured distribution over the 2,665 local texts with at least 500 digits:
median 0.067 decimals per digit, p10 0.024, p2 0.009. `decimal-stripped` is
drawn at 0.010 and `decimal-poor` at 0.025. Re-derive them if the corpus
changes substantially, and re-run `--calibrate` and `--selftest` afterwards.

## extraction_rubric.py — the Shi/Rampal (Yaghi group) Y/N/\ rubric

```
code/.venv/bin/python benchmark/extraction_rubric.py
code/.venv/bin/python benchmark/extraction_rubric.py --by-model
code/.venv/bin/python benchmark/extraction_rubric.py --explain obedience
code/.venv/bin/python benchmark/extraction_rubric.py --validate software
```

Implements the evaluation framework of Shi, Rampal, Zhao, Fu, Borgs, Chayes &
Yaghi, *Comparison of LLMs in extracting synthesis conditions and generating
Q&A datasets for metal–organic frameworks*, **Digital Discovery 2025, 4,
2676** (DOI `10.1039/d5dd00081e`). Each extracted item is marked `Y` (criterion
met), `N` (extracted but not met) or `\` (never extracted), and the summary
reports those proportions plus a **net-Y-ratio** of Y/(Y+N) — quality among
what was actually extracted, independent of coverage.

Their three criteria transplant onto aimdb as:

| theirs | here |
| --- | --- |
| completeness — are temperature, concentration, reagent amounts all present? | are the core five (`active_space_nel`, `active_space_norb`, `active_space_orbital_description`, `basis_set`, `software`) filled **where the paper states them**? |
| correctness — is the extracted value factually right? | invariants (capacity, parity) plus numeral grounding from `check_grounding.py` |
| characterization-free compliance — did the model obey an explicit prompt instruction? | does the row obey CLAUDE.md's written extraction rules? |

The obedience mapping is the one that needed interpretation. Theirs tested a
single instruction ("exclude characterization data"); aimdb's prompt is
CLAUDE.md, so the analogue is adherence to the rules it states in those terms —
no extraction narration in `notes`, no structured column restated in prose,
`d_electron_count` written with its shell, no prose in the numeric columns, no
retired marker values.

**Completeness is the only check in this folder that measures recall.**
Everything else asks whether what is written is true; this asks what was
missed. A row is marked `N` only when a core field is empty *and* the source
text demonstrably states it, because CLAUDE.md is explicit that "a gap is only
worth filling if the paper states the value" — an empty cell is frequently the
correct answer, and scoring it as a miss would invert the policy.

### Results, 2026-10-09 (12,541 rows)

| criterion | Y | N | \ | scored | net-Y-ratio |
| --- | --- | --- | --- | --- | --- |
| completeness | 40.3% | 7.6% | 52.0% | 6,019 | **84.1%** |
| correctness | 47.1% | 0.8% | 52.1% | 6,001 | **98.4%** |
| obedience | 82.4% | 17.6% | 0% | 12,541 | **82.4%** |

For context, their human-scored figures on 115 MOF products: completeness
67.8% / 83.5% / 72.2% and correctness 83.5% / 86.1% / 95.7% for GPT-4 Turbo,
Claude 3 Opus and Gemini 1.5 Pro, with net-Y-ratios above 95%.

The `\` rate of ~52% is not a refusal to extract, as it is in their setting —
it is the half of the database whose source text no longer exists on disk, so
neither completeness nor correctness can be judged there at all.

### Why --by-model is not a model comparison

aimdb stamps `mining_model`, which looks like a free replication of their
LLM-versus-LLM design. It is not, for completeness and correctness: local text
survives for 85% of `claude-opus-5` rows but **1%** of `gpt-5.6`, 0% of
`claude-opus-4-8` and 0% of `gpt-5-codex`. Cutting those two criteria by model
compares which papers still have a text file. The script prints the `scored`
denominator and flags any cut judging under a fifth of its rows.

**Obedience is comparable** — it needs no source text. By model: `gpt-5-codex`
95.9% (n=73), `claude-opus-4-8` 94.1% (n=681), `claude-opus-5` 82.4%
(n=7,016), `gpt-5.6` 80.6% (n=4,763). Read that as a statement about the two
high-volume mining models, not a general model ranking: the cohorts differ in
era and in which papers they were given.

### Limits

- The completeness detector cannot tell **which method** a name belongs to. A
  paper naming `6-311G(d)` for its DFT/NICS step and nothing for its CASSCF
  will flag an empty `basis_set` that was correctly empty. Treat
  completeness-`N` as a worklist, not a verdict.
- Detector precision is measured, not assumed — `--validate` prints flagged
  rows with the matching sentence for hand scoring. On 2026-10-09: `basis_set`
  6/6 correct; `software` 7/8 before the name lists were tightened (`dirac`
  matched "Dirac-Fock", `ams` matched "Ames Cray Y-MP"), 12/12 after, with one
  of the twelve resting on a reference-list citation rather than a methods
  sentence.
- Two cheaper designs for that detector were tried and rejected: harvesting the
  corpus's own `software` column yields 587 "names" including `active`,
  `analysis` and `based`; weighting each token by how concentrated it is in
  `software` versus the chemistry prose columns still keeps `visualization`,
  `programs` and `python`. Both reference corpora were wrong, so the lists are
  curated and their precision is measured instead.
- `correctness` here is an automated proxy over a narrower error class than a
  human read. The hand-scored sample of 25 rows is still the only human
  measurement of aimdb's accuracy.
- Obedience counts a violation of today's rules against a row written before
  some of them existed. The retired `no` marker is **not** such a case, though:
  293 of those rows were added in September and 145 in October 2026, after the
  rule changed, so they are live violations rather than legacy.

## find_missed_zfs.py — papers whose text states a ZFS the rows don't

```
code/.venv/bin/python benchmark/find_missed_zfs.py
code/.venv/bin/python benchmark/find_missed_zfs.py --calibrate
code/.venv/bin/python benchmark/find_missed_zfs.py --tier D-value --show 40
code/.venv/bin/python benchmark/find_missed_zfs.py --evidence W3177508800
```

Searches every paper that has rows and local text for evidence of a
zero-field splitting its rows fail to record, and separates two states that
need different work:

| state | meaning |
| --- | --- |
| `unparsed` | the row's prose discusses ZFS but never states D, so `tools_zfs_columns.py` had nothing to lift. The number may be a few lines away in a text already on disk. |
| `unmined` | the prose doesn't mention ZFS at all, yet the paper computes it. Missed at first reading; needs a genuine second read. |

**Read `--calibrate` before the results.** The tier that sounds strongest — a
parseable `D = x cm⁻¹` near a computational marker — fires on only **6%** of
the papers that demonstrably carry a ZFS value. D lives in tables, and tables
are what a PDF text layer loses, so an absence there means almost nothing. The
weaker `ZFS-phrase` tier reaches **88%** and is the screen to use. Taking the
`D-value` count as the answer would understate the gap by more than tenfold.

As of 2026-10-10: **169 candidate papers / 478 rows** — 74 `unparsed` and 91
`unmined` at `ZFS-phrase`, 4 at `D-value`. Hand-scoring ten gave roughly six
probable true positives, two clear false positives and two borderline, so this
is a worklist and never a count.

### Exclusions, each from a false positive it produced first

- **A singlet ground state has no ZFS**, however much its paper discusses
  magnetic anisotropy. 15 papers dropped on this.
- **A match in the reference list is not a result** — the bibliography is cut
  before searching.
- Lowercase `d` is a shell label and `De` is a dissociation energy; an `re.I`
  pattern over `[DE]\s*=\s*\d+` once inflated a ZFS count from 210 to 252.
- `D` is also the DMRG bond dimension, the Debye, and a pseudo-Jahn–Teller gap
  in eV. All three have appeared as spurious ZFS values.
- An uncertainty can hide the unit: `D = -178(1) MHz` read as unitless, and the
  cm⁻¹ default made one stored value wrong by a factor of 30,000.
- Gauss cannot be converted without *g*, so a field-unit value is not evidence
  of a ZFS in cm⁻¹.

### The judgment it deliberately leaves to you

**86 of the 169 are flagged `kramers`** — Dy(III) and other Kramers
lanthanides, where the splitting is reported as crystal-field Kramers-doublet
gaps rather than a spin-Hamiltonian D and E. They are flagged rather than
dropped because whether those belong in the D/E columns is a chemist's call,
and that single decision is the largest factor in how big the real gap is.

### Limit

**1,108 papers with rows have no local text at all** and cannot be checked by
this or any other script here. That is the ceiling on the audit, not a
property of the data.
