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

Extract only these six top-level fields: `customer`, `intent`, `line_items`,
`requested_date`, `urgency`, `confidence`. Each item has only `sku`, `description`,
`quantity`, `unit`. Do not add contact, request objects, authorization fields or
unrelated commentary. Missing facts remain null. The verifier checks only facts
applicable to this field set, rather than demanding extra request narratives.

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

The workflow does not automatically select or check the project's draft labels.
Run label evaluation only when the user explicitly supplies a label-file path
with `--labels "path\to\labels.json"`. Explicit labels must refer only to
selected source emails and match their checksums before any model call.

Process and save ALL selected emails, then display at most 15 outputs in chat by
default: the first 15 in filename order, including review outcomes. This sample
works even without labels. State the total processed count and displayed sample
count, and link the complete results/review files. For 40 inputs, process 40 and
show 15; for 8 inputs, process 8 and show 8. `--sample-size 5` changes only the
display limit. Never slice input files or model calls to enforce a display limit.
`--summary-only` omits sample JSON when the user asks for a shorter report.

Show aggregate coverage and field scores for ALL supplied matching labels. The
validation response must end with the overall field score and labelled-email
coverage, including with `--summary-only`; do not require a separate accuracy
command. Show total validation/review counts separately from accuracy. With no
explicitly supplied labels, end with accuracy unmeasured rather than inventing a percentage.
The same final summary belongs in the saved chat session after the sample data.
Pending annotations must still be named assistant draft agreement.
The chat response highlights one overall score. Keep the detailed per-field
table in the report file rather than filling chat with repeated 15/15 rows.
The labelled count is disclosed as the measurement coverage, not the input count.
Interactive results use the shared assistant presentation and conversation
details. Preserve latency, first-token timing when available, input/output and
session token totals, context usage and any configured cost estimate. The shared
dispatcher collects these for all current and future commands; do not add a
separate metrics switch or duplicate the usage inside a new challenge.

The 15-output display sample and any explicitly supplied evaluation set are independent;
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

Add `--field-level` to the standalone accuracy command to print the detailed
per-field table in an interactive terminal. Plain redirected output already
contains that table. The chat workflow keeps its compact overall-score summary.

This report makes no model calls. Confidence is never scored as accuracy;
missing/review predictions stay in the score denominators. Line items are matched
one-to-one, independent of list order. Multi-intent returns just one primary
`intent` by the schema's priority: return, complaint, order, status, other.
Quote and stock/price enquiries map to other. No secondary-request fields are
extracted. Older label metadata outside the requested fields is not scored.
Earlier richer results remain preserved under their old fingerprint; they are
not reused as current six-field outputs. Explicit historical scoring compares
only the requested subset and cannot establish current-provider behavior.

Desk's interactive chat also accepts natural-language execution requests, such as
"Use the structured-output skill on data/emails and save the results in output."
The configured LLM selects the `structured_output` tool through native Bedrock
tool calling and supplies typed paths/options. Python validates those arguments
and executes this same workflow; it never runs shell text generated by the model.
Missing source paths prompt a clarifying question. Invalid paths get an error
and, when applicable, a plural-folder suggestion without silently changing the
input. Questions, quoted examples and code-edit requests do not request a batch.
Relative natural-language paths resolve from the project root. The model's tool
selection is a chat request; per-email extraction and verification remain isolated.
The real results and final accuracy summary are retained in conversation history
for follow-up questions and `/save`/`/load`.
Type `/` or a prefix such as `/s` at any word position in the message to open
and filter the same eight-command menu. Selecting a skill replaces only the
slash token at the cursor, preserving the surrounding sentence. For example:
"I need to structure my email by using /structured-output on data/emails and
save the results in output." Path/URL separator slashes are not menu triggers.
Users may also select the skill and describe its arguments conversationally:
`/structured-output data/emails source and store in the output folder`.
A bare `/structured-output` uses a clear source from conversation or asks for it.
Valid path/flag shortcuts still run locally without a routing model call.

Desk's interactive chat accepts `/structured-output <path> [options]` as a local
command and records its summary/results into the active chat session memory
(while keeping each email extraction request isolated on Bedrock). Type `/` for the compact
dark suggestions menu; arrows/Tab select a command. `/structured-output ... --`
suggests its flags; `/structured-output --help` lists every option. The only
chat commands are `/ask`, `/chat`, `/reset`, `/exit`, `/load`, `/save`,
`/structured-output` and `/ingest`. Run the standalone accuracy command from PowerShell.

The chat command runs `src/challenge3_structured_output/structured_output.py`, which reads the schema from
this skill folder. Natural-language routing exposes this workflow as a tool;
the eight slash shortcuts include the user-requested policy `/ingest` skill. Other repo skills and maintenance CLI commands do not appear
in chat suggestions.
