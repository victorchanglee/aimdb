# Claim review: rules for every benchmark and fix agent

Paths are relative to the aimdb root, `/media/victor/disk1/claude/aimdb/`.

## Ground truth

**The paper is the only ground truth.** That means its main text plus its
supplementary information (SI). A value stated only in the SI counts as stated
by the paper.

- Read text files with `grep -a` (some files read as binary to plain `grep`).
- Use the Read tool's `pages` option on the PDF for tables, signs, symmetry
  labels, and anything the text layer garbles.

## Policy

Field definitions and policy are in `CLAUDE.md`. Read it in full, especially:
- "The loop", steps 4 and 5;
- "A row must name a compound";
- "The active space must be an integer".

The rule is **copy, never infer**.

Allowed arithmetic (flag every use in `notes`):
- a d/f count from a stated oxidation state;
- nel from an explicitly listed orbital occupation;
- norb from a stated orbital list;
- a full-valence count from the paper's explicit "full valence" statement for
  the row's own species;
- unit conversions.

Never assume anything the paper does not state. That includes:
- a spin multiplicity ("singlet" for a closed-shell organic molecule included);
- a point group;
- a formula built from a compound name;
- the basis, software or geometry source;
- the ground state.

## What you may read

You may read only:
- your batch file;
- the paper files it names (`text/<key>.txt`, the PDF, the SI files);
- `CLAUDE.md`;
- the briefs in `benchmark/claim_review/`;
- for a fix agent, the benchmark file named in its brief.

Never open or search the database, `papers_index.csv`, `logs/`, `docs/`, git
history, or other papers' files. The rows under review are in your batch
file.

## Scratch and output

- Put scratch files only in a private directory with a unique name.
- Never read or run another agent's files.
- Write only the output file your brief names.

## Row schema

Allowed columns:

| group | columns |
|---|---|
| identity | entry_id, compound_name, system_class, formula, metal_center, metal_ox_state, d_electron_count, ligand_set, point_group |
| method | geometry_source, method, software, basis_set, relativistic_treatment, soc_included, ss_included |
| active space and states | active_space_nel, active_space_norb, active_space_orbital_description, active_space_protocol, multiplicities_studied, nroots_per_mult, ground_state_mult |
| text | electronic_structure_description, Other |
| reference | reference_short, reference_doi, year |
| caveats | notes |

The derived and bookkeeping columns (structure_file, element, properties,
open_access, date_added and the rest) are kept by the apply tool. Never
output them.

### Field rules

- **entry_id** is `<key>-a`, `<key>-b`, and so on. Keep an existing row's
  entry_id when the row still describes the same species.
- **reference_doi** is the DOI given in the batch file.
- **active_space_nel** and **active_space_norb** are bare integers, or empty.
  - Copy the counts the paper prints. Never convert a stated count into a
    different one. (A table labelled "4 electrons" is not a (2,2).)
  - If the paper's own statements conflict, for example a printed count
    against its listed orbitals, leave the integer empty and quote both in
    `notes`.
- **active_space_protocol** holds only a build-up sequence the paper
  describes, in the paper's order. Write it as
  `(nel,norb) step; (nel,norb) step; ...`.
  - Separate calculations that the paper does not present as an enlargement
    sequence do not belong here. Put them in Other or notes.
- **Other** holds what the active space or correlation treatment did to the
  answer, as CLAUDE.md defines it.
  - State only what the paper shows, for this row's species.
  - Do not generalise a "within X eV" statement beyond the cases the paper
    gives.
- **electronic_structure_description** holds every value the paper reports
  for the row's species. Give each value with its method and state labels.
- **notes** holds only caveats a chemist needs. Never write extraction
  narration, file or SI availability, checksums, or history.
- **system_class** is one of `atom`, `molecule`, `cluster-model` or
  `solid-state`.

### Rows

Make one row per species, or one per species and active space where the
paper reports results at several spaces.
- A model complex and its parent are different species.
- So are two metal sites.

A statement that holds for the whole paper goes only on the rows it is true
for. Do not copy it onto every row.
