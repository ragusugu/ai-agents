# Project skills

Reusable skills live in `skills/`, separate from the application in `src/`.
Desk chat exposes only `/ask`, `/chat`, `/reset`, `/exit`, `/load`, `/save` and
`/structured-output`. Keep menu descriptions short and the terminal palette dark.
The `/structured-output` command runs the Python workflow with the schema in
the skill folder. New skill folders must not expand the seven-command chat menu.

- For `/structured-output <path>`, read
  `skills/structured-output/SKILL.md` and use its stored schema and Python workflow.
  A request to implement or edit the skill is not a request to run a live batch.
  Process every email in the selected folder, regardless of count; show at most
  15 sample outputs by default. The display limit must never limit processing.
- For `/graphify`, use the graphify skill at `~/.Codex/skills/graphify/SKILL.md`
  (or the installed `graphify-windows` skill when that is its available location).

The structured-output schema belongs in the skill folder. `src/schemas.py` is
only an import bridge; do not introduce a second schema definition there.
