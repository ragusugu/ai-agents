# Project skills

Reusable skills live in `skills/`, separate from the application in `src/`.
Desk chat exposes `/ask`, `/chat`, `/reset`, `/exit`, `/load`, `/save`,
`/structured-output` and the user-requested `/ingest` (eight commands).
Keep menu descriptions short and the terminal palette dark.
The `/structured-output` command runs the Python workflow with the schema in
the skill folder. New skill folders must not expand the eight-command chat menu
without an explicit user request.

- For `/ingest <path>`, read `skills/ingest/SKILL.md` and run the shared local
  policy-ingest workflow. Ask for a source when missing. Single-file updates
  preserve all other indexed files; folder pruning is confined to that folder.
  Only UTF-8 `.md` files are supported. Keep retrieval/answer RAG separate.

- For `/structured-output <path>`, read
  `skills/structured-output/SKILL.md` and use its stored schema and Python workflow.
  A request to implement or edit the skill is not a request to run a live batch.
  Process every email in the selected folder, regardless of count; show at most
  15 sample outputs by default. The display limit must never limit processing.
- For `/graphify`, use the graphify skill at `~/.Codex/skills/graphify/SKILL.md`
  (or the installed `graphify-windows` skill when that is its available location).

The structured-output schema belongs in the skill folder. `src/schemas.py` is
only an import bridge; do not introduce a second schema definition there.

Shared provider/configuration, CLI/chat/session, presentation and telemetry modules
stay at `src/` root. Challenge 3's existing extraction/batch/scoring/tracking/verifier
modules live in `src/challenge3_structured_output/`; the verifier remains paused.
Challenge 4 modules live in `src/naive_rag/`, with generated vector data in its
gitignored `rag_db/`. Model cache stays in `.desk/models/`.

For each challenge, keep Build/Done When/Stretch checklists, stage status,
actual CLI/chat demos and test evidence in its main challenge document (preserve
an existing filename; Challenge 4 uses `challenges/challenge4/challenge4.md`).
Keep Break It experiments, failures, learning notes and retrieval assessments in
the existing canonical notebook; Challenge 4 uses repository-root `notes.md`.
Do not recreate a competing per-challenge notebook after the user moves it.
Build/Done When/Stretch typed inputs and actual responses belong in the challenge
document. Distinguish mocked/local/provider runs and observed
pass/fail/pending checks. The implementation plan links these canonical records
instead of duplicating transcripts. This convention does not authorize new work.

All Desk slash outputs arrive as produced: provider deltas for ask/chat, real
progress and persisted validated results for workflows, and immediate local
results for save/load/reset/exit. Do not simulate streaming or call a model to
animate local operations. RAG deltas are drafts until final citation-format checks;
rejected/interrupted drafts must be visibly marked and not saved as successful turns.
