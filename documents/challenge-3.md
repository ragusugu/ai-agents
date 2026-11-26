# Challenge 3 — structured output skill

The reusable skill and its schema template are stored separately from the app:

```text
skills/structured-output/
  SKILL.md                     Workflow instructions
  order_schema.py              Pydantic schema; authoritative template
  order_request.example.json   Illustrative output shape
src/
  schemas.py                   Import bridge; no duplicate schema
  structured_output.py         Extraction + evaluation orchestration
  extraction.py                Native structured output, validation and repair
  batch.py                     Sequential processing and resume
  accuracy.py                  Local field comparison
  source_map.py                Small JSONL email-to-result mapping
```

The root `AGENTS.md` routes `/structured-output <path>` requests to the skill
instructions. The same slash command works inside `desk chat` as a local command.

Desk also understands requests such as:

> Use the structured-output skill on all emails in data/emails, save the results
> in output, and show accuracy at the end.

You can also select the skill and describe the arguments naturally:

```text
/structured-output data/emails source and store in the output folder
```

A bare `/structured-output` starts that conversation when a source is still
needed. Valid path/flag shortcuts continue to execute locally without an extra
routing request.

The configured LLM chooses the `structured_output` tool using native Bedrock tool
calling. Python validates its typed arguments and runs the existing workflow.
This is model-selected routing, not keyword matching or generated shell commands.
If the source folder is missing, Desk asks for it. If the path does not exist,
Desk reports the problem and may suggest the plural folder name; it does not
silently substitute another folder. Paths are relative to the project root.
Ask for a preview to plan without sending email text for extraction. A normal
execution request can incur extraction usage for inputs without reusable results.
Questions and requests to edit the skill do not request extraction.

The [Bedrock streaming tool protocol](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
supplies model-selected tool names and argument fragments. Desk waits for a complete,
valid tool request before executing. Truncated, malformed, unknown or multiple
skill calls do not execute a workflow. The actual workflow summary, source path,
outcomes and accuracy are saved as the assistant's reply for follow-up questions.
Tool execution does not add another slash command to the seven-command menu.

## Desk chat suggestions

In the active project `.venv` terminal, run `desk` to start chat directly. The
local `.venv/Scripts/desk.cmd` launcher takes precedence over Windows `desk.cpl`.
From the project folder, `.\desk` also starts chat. Explicit `desk chat` and
other subcommands continue to work; `desk --help` shows CLI help.

Type `/` anywhere at a word boundary in your message to open the compact dark menu. For example,
`I need to structure my email by using /s` offers `/save` and `/structured-output`.
Selecting the skill replaces only `/s`; text before and after the cursor is
preserved. Folder and URL separators such as `data/emails` do not trigger menus.
Keep typing
to filter; arrows and Tab select. Entering `/` prints the same list, including
when input is redirected. Only these seven slash commands are available:

- `/ask <question>`: ask a single question; multiword questions work without quotes.
- `/chat [message]`: continue the conversation.
- `/reset`: start a fresh conversation.
- `/exit`: leave Desk.
- `/load <name>`: open a saved session.
- `/save <name>`: save this session.
- `/structured-output <path> [options]`: extract emails into JSON.

`/structured-output --help` shows all workflow options. Typing `--` after a
workflow command suggests its flags. Local menus and session commands do not
initialize an AWS client or make model calls. Interactive completion uses the
pinned `prompt-toolkit` dependency, with cyan selection and short descriptions.

The menu uses a fixed set of seven commands and the existing CLI option parsers.
`/structured-output` directly runs the Python workflow with the Pydantic template
in the skill folder. Adding skill folders does not expand the chat menu.
Recovery and standalone accuracy commands remain available
in PowerShell. Inside `desk chat`, `/ask` and `/structured-output` record their
summaries and outcomes into conversation history (while each Bedrock email
extraction call itself still runs in a fresh isolated context); `/save` and
`/load` preserve conversation history and token totals.

## Run on a path

Python 3.11+ and the pinned packages in `requirements.txt` are required.
Configure the existing Bedrock credentials/region and `DESK_MODEL` in `.env`.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.\desk.cmd structured-output "data\emails"
```

This is an execution command: it sends each selected email to the configured
Bedrock model, one at a time. Each email gets a fresh context. It does not use
saved chat history, labels, instructor answers, product catalogs or an order DB
as model input. `--model` and `--max-tokens` are explicit overrides.

For an offline preview with no model calls:

```powershell
.\desk.cmd structured-output "data\emails" --plan-only
```

An explicit `.txt` or `.eml` file is also accepted. A folder is non-recursive;
all `.txt`/`.eml` files in it are treated as emails and sorted by filename.
Use a dedicated email folder. Filenames may be arbitrary, but stems must be
unique (for example, `mail.txt` and `mail.eml` cannot share an input folder).
Sources are UTF-8, nonempty and at most 100 KB each.

The count is dynamic: 30, 40 or any number of email files are all processed.
`--expected-count N` is only an optional explicit assertion, not the default.
The separate `--sample-size` controls display only (default 15). For 40 inputs,
all 40 have persisted outcomes and the first 15 outputs are printed as samples.
For fewer than 15, all available outputs are shown. Review outcomes stay visible
in the sample. `--sample-size 5` shows five without reducing processing or storage.

The native JSON Schema is derived from the skill's Pydantic models. Every
response is validated locally. Invalid JSON, types, bounds, cross-field rules,
truncation or unsupported SKU evidence allow at most two repair requests using
the original email, previous output and validation errors. There are at most
three extraction responses per email. Transport retries are separate and bounded.
Provider refusal/capability failures go to review; no prompt-only fallback is used.

Schema-valid candidates also receive a separate native-schema source-grounding
check against the same email. Its evidence ledger covers every factual output
field and every source segment. Unsupported or omitted facts share the same two
repair attempts; an unavailable, truncated or uncertain verifier cannot approve
a success. There are at most six response requests and eighteen transport attempts
per email, including verification. A passing check is model evidence, not a
replacement for independently reviewed accuracy labels.

## Results and resume

- `output/results.jsonl`: only validated OrderRequest objects, one per line.
- `output/needs_review.jsonl`: unsuccessful outcomes and useful validation details;
  created only when a review outcome occurs.
- `output/source-map.jsonl`: small email-to-result mapping (source path/checksum,
  run ID, success/review file line, payload checksum and config reference).
- `output/configs/`: shared model/schema/prompt fingerprints for evaluation/reuse.
  There is no tracking database.
- `output/verifications/`: passing evidence receipts tied to the payload, source
  checksum and verifier fingerprint, with request/token/repair counts.
- `output/batch-plan-*.json` and `output/batch-run-*.json`: selected inputs and
  per-email outcomes for the batch.
- `output/accuracy-report.json`: field scores, coverage and label provenance.

Running the same workflow again reuses compatible persisted outcomes, including
review outcomes; it does not silently recharge them. To explicitly retry existing
reviews once, use `--retry-review`. A changed source, model, schema or prompt can
require new extraction. Earlier incompatible outputs remain preserved.

Historical payloads are checked for file/config integrity under their saved
schema fingerprint. Batch reuse and accuracy apply the current schema only
after selecting compatible records, so a schema change does not block unrelated
history. Saved results that fail tightened local constraints are extracted again.

Batch completion may be `complete` or `complete_with_review`: each selected
email has a validated result or a review outcome. A storage failure stops the
batch before more sends. After an interruption, verify that no writer is active,
then recover locally before restarting:

```powershell
.\desk.cmd rebuild-output
```

The result and source-map JSONL files are separate atomic writes. A minimal
temporary pending journal handles that recovery boundary. Do not edit result
lines and their source associations independently. Generated output is git-ignored.

Use the same `structured-output` command for single-email and folder runs.
`--plan-only` provides the local preview. Separate `extract`, `batch` and old
tracking/migration CLI commands have been removed. The earlier SQLite database
was replaced by the small source-map file after verifying the exported association.
Existing source emails, extracted results and labels are preserved.

## Fifteen human labels and the chat report

For the project's complete source set, the workflow automatically uses
`evaluation/challenge3_labels.draft.json`. It contains 15 assistant-drafted
annotations and is **not yet human ground truth**. The source-linked
`evaluation/challenge3_labels_review.md` checklist is generated on evaluation.
Read each original email, correct expected values/concept terms, then record the
actual reviewer/date and approved status in the label JSON. The software never
approves labels automatically. Predictions must not be used to invent expected
answers. The existing draft excludes EM-001 because its prediction was seen earlier.

The workflow prints a sample of up to 15 processed emails' JSON and outcomes,
independently of whether they have labels. It then prints coverage and field-level
scores for every matching supplied label. The display sample and the human-labelled
evaluation set are independent: limiting output never limits evaluation.
Pending labels are reported as **assistant draft agreement**. Use `--summary-only`
to omit sample JSON. `accuracy --show-results` also displays at most 15 email
details by default; its JSON report retains every label's evaluation.
The validation command ends with the overall percentage, correct/total field
checks and labelled-email coverage, including in saved chat history and with
`--summary-only`. Validation/review counts are separate from accuracy. Without
matching labels the final line says accuracy is unmeasured. No second command or
extra model call is needed to calculate the summary.
In chat, the overall score is the main result; the per-field table remains in
the detailed report rather than being printed after every skill run. Accuracy
is measured on the available labels, which is distinct from validating every
email in the full batch.

Interactive Desk uses dark assistant message panels, streaming Markdown,
readable six-field email cards, review badges and a live progress indicator.
Narrow terminals switch product tables to wrapped item details. Redirected
output remains plain text; JSONL files retain their unchanged schema.

Every chat turn and command automatically ends with **Conversation details**:
whole-request latency, first-token time when available, reported input/output
tokens, session totals, context size, model, retries when relevant, and estimated
cost when pricing is configured. This is a shared default in the dispatcher and
chat loop, not a per-challenge option. Future command handlers use the same
default. Provider adapters should use `model.call_model`, `stream_model` or
`call_structured_model`; these automatically report usage to the current turn.
Custom adapters can report through `telemetry.note_response`.

Skill totals include extraction, repairs and verification responses. Reusing
saved outcomes adds no extraction tokens. Nested commands share one turn so
usage and session totals are not counted twice. Failed requests without usage
metadata are identified as incomplete rather than assigned an invented cost.
Once labels have actually been human reviewed, the report runs with one command:

```powershell
.\desk.cmd accuracy --require-reviewed --show-results
```

No model call is made by `accuracy`. Use `--labels path/to/labels.json` for another
label file. For an external dataset, `source.relative_path` can be an explicit
absolute path; otherwise it is relative to this project. Source IDs must equal
filename stems, and SHA-256 checksums must match. Human-authored labels may set
`provenance.kind` to `human`; reviewed assistant drafts retain their origin.
Explicit labels outside the selected extraction input are rejected before sends.
If no matching labels are available, extraction still works and no accuracy claim
is made. `--require-reviewed` on the workflow enforces actual review before calls.

Scoring compares only customer, intent, requested date, urgency and line items.
Quantities are compared numerically; units have limited documented normalization
in code. Products are matched one-to-one, independent of list order, with extra predictions
penalized. Description scoring uses explicit concept/synonym groups and is not a
general semantic judge. Missing/review outcomes remain in score denominators;
an entirely uncovered report is unmeasured. Confidence is never scored as accuracy.

## Schema policy

Unknown facts stay null. Do not invent SKUs, quantity, units, urgency or dates.
Products need a SKU or description. Quantities must be positive finite numbers,
excluding strings and booleans; confidence is finite in [0, 1]. An output may
validate and still be factually wrong: that is what the hand-label comparison measures.

The output has exactly six top-level fields: `customer`, `intent`, `line_items`,
`requested_date`, `urgency`, `confidence`. Line items contain only `sku`,
`description`, `quantity`, `unit`. Extra output fields fail validation.
No contact, primary/secondary request objects or purchase-authorization fields
are extracted. Descriptions stay about products and necessary product uncertainty.

Multi-intent resolves to one primary intent by priority:
return, complaint, order, status, other. Quote/availability/price enquiries map to other.
Status concerns an existing order, while availability concerns product stock.
Intent order requires an explicit purchase instruction; quote-only uses other.
The workflow never places a real purchase.

The six-field contract supersedes earlier richer outputs. Existing results and
labels are preserved. Old label metadata is ignored in current scoring; an
explicit historical report scores only the requested subset and is clearly
marked historical. Previous percentages do not establish accuracy for the new
schema, and a new live run is required to measure current provider behavior.

## Verification

```powershell
.\desk.cmd structured-output "data\emails" --plan-only
.venv\Scripts\python.exe -m unittest discover -s challenges/challenge3 -v
.venv\Scripts\python.exe -m pip --disable-pip-version-check check
git diff --check
```

The automated suite uses disposable synthetic sources and mocked provider I/O.
It covers schema constraints, native requests, bounded retries/repairs, grounding
failures, storage interruption/recovery, 30/40-email batches, resume, display
limits and one-command scoring of all 15 synthetic labels. Reordering repeated
SKU lines must preserve scores. Storage failures must stop before another send.
The suite does not require git-ignored historical outputs or call Bedrock.
Chat tests also exercise fragmented native tool requests, malformed/truncated
calls, typed paths, ordinary replies, skill selection, local shortcuts and real
workflow summaries retained for follow-up questions.

Live routing was checked on 26 November 2026 with the configured Bedrock model:
natural execution wording, a usage question, missing paths, preview, follow-up
paths, the skill-prefixed sentence, a bare skill selection and an unavailable
skill. Those eight checks tested tool selection without executing email extraction.
Local evidence is in `output/chat-routing-smoke-20261126.json` and
`output/chat-routing-smoke-selected-20261126.json`.

Use the offline preview to verify selected inputs and reuse before a live run.
Actual human review and a live email batch are needed to establish extraction
accuracy and provider behavior. The optional model cost/accuracy comparison
remains a stretch task.
