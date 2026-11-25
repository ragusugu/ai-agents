---
name: structured-output
description: Process every customer email from a file or folder into validated OrderRequest JSONL using Desk, show a limited sample of outputs, and report available field-level evaluation. Use for /structured-output requests in this project.
---

# Structured output

Use this project's existing Python workflow to process the user's email path.
The project root is two directories above this skill folder. Run commands from
that root using `.venv/Scripts/python.exe` or `desk.cmd`.

## Stored template

Read [order_schema.py](order_schema.py): it is the authoritative Pydantic schema
template. [order_request.example.json](order_request.example.json) illustrates
the output shape; its values are examples, not expected answers. Native Bedrock
JSON Schema is derived by `bedrock_schema()` in that same Python file.

Keep this schema in the skill folder. `src/schemas.py` imports it for extraction
and scoring. Do not duplicate the schema, hand-generate predictions in this chat,
or replace native structured output with a prompt-only JSON request.

## Run

For an extraction request containing a path, execute the workflow on that path.
It sends selected email text to the configured Amazon Bedrock model. Preserve
the configured model; do not silently switch providers or models. A request to
edit the skill alone does not request live extraction.

```powershell
.\desk.cmd structured-output "data\emails"
```

Replace the example path with the user's actual file or directory. Quote paths
with spaces. Folders are flat: all `.txt` and `.eml` files are emails, sorted by
filename, with unique filename stems. Detect and process every email dynamically:
30, 40, or any other count. Do not add `--expected-count` unless the user explicitly
asks to assert a particular input count. Keep labels and notes out of the email folder.

The workflow reads one email per request with a fresh context, uses the stored
schema, validates with Pydantic, and sends validation errors back for at most two
repairs. Valid outputs append to `output/results.jsonl`; unsuccessful outcomes
go to `output/needs_review.jsonl`. Every email has a tracked outcome. Existing
compatible successes and reviews are reused; retry reviews only when requested
with `--retry-review`. Storage failures stop processing for local recovery.

Use `--plan-only` when the user asks to preview inputs/reuse without model calls.
The same `/structured-output` command accepts a single email file or a folder.
Do not delete existing results or tracking as part of a normal run.

`output/source-map.jsonl` stores only the email-to-result association needed for
evaluation and reuse. Extracted payloads are stored once in the result/review
files. No SQLite database or separate tracking command is required.

## Output sample and evaluation

For the project's email set, the workflow automatically selects the matching
15-label file in `evaluation/challenge3_labels.draft.json`. A different dataset
can supply `--labels "path\to\labels.json"`. Explicit labels must refer only to
selected source emails and match their checksums before any model call.

Process and save ALL selected emails, then display at most 15 outputs in chat by
default: the first 15 in filename order, including review outcomes. This sample
works even without labels. State the total processed count and displayed sample
count, and link the complete results/review files. For 40 inputs, process 40 and
show 15; for 8 inputs, process 8 and show 8. `--sample-size 5` changes only the
display limit. Never slice input files or model calls to enforce a display limit.
`--summary-only` omits sample JSON when the user asks for a shorter report.

Show aggregate coverage and field scores for ALL supplied matching labels. The
15-output display sample and the hand-labelled evaluation set are independent;
the displayed sample is not necessarily the labelled subset. Report the actual
labelled count. Never invent missing predictions or scores, or limit evaluation
to the output sample. `accuracy --show-results` also caps displayed email details
at 15 by default while scoring every label; its complete report stays on disk.

Human labels must come from reading the original emails. Existing annotations
are assistant drafts awaiting human review. The workflow writes a source-linked
review checklist; show its path. Do not mark labels approved on the user's behalf.
Until actual human review, call the scores **assistant draft agreement**, not
human-labelled accuracy. Explain that pending review is the remaining manual step.

After the user checks/corrects the labels and records their reviewer/date and
approved status, the accuracy report runs locally with one command:

```powershell
.\desk.cmd accuracy --require-reviewed --show-results
```

This report makes no model calls. Confidence is never scored as accuracy;
missing/review predictions stay in the score denominators. Line items are matched
one-to-one, independent of list order. Multi-intent uses primary and secondary
requests with the priority defined in `order_schema.py`.

Desk's interactive chat accepts `/structured-output <path> [options]` as a local
command and records its summary/results into the active chat session memory
(while keeping each email extraction request isolated on Bedrock). Type `/` for the compact
dark suggestions menu; arrows/Tab select a command. `/structured-output ... --`
suggests its flags; `/structured-output --help` lists every option. The only
chat commands are `/ask`, `/chat`, `/reset`, `/exit`, `/load`, `/save` and
`/structured-output`. Run the standalone accuracy command from PowerShell.

The chat command runs `src/structured_output.py`, which reads the schema from
this skill folder. Other repo skills and maintenance CLI commands do not appear
in chat suggestions.
