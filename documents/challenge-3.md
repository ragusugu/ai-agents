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

## Desk chat suggestions

In the active project `.venv` terminal, run `desk` to start chat directly. The
local `.venv/Scripts/desk.cmd` launcher takes precedence over Windows `desk.cpl`.
From the project folder, `.\desk` also starts chat. Explicit `desk chat` and
other subcommands continue to work; `desk --help` shows CLI help.

Type `/` to open the compact dark menu. Keep typing
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

## Results and resume

- `output/results.jsonl`: only validated OrderRequest objects, one per line.
- `output/needs_review.jsonl`: unsuccessful outcomes and useful validation details;
  created only when a review outcome occurs.
- `output/source-map.jsonl`: small email-to-result mapping (source path/checksum,
  run ID, success/review file line, payload checksum and config reference).
- `output/configs/`: shared model/schema/prompt fingerprints for evaluation/reuse.
  There is no tracking database.
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

Scoring compares customer/contact/intent/date/urgency/purchase authorization,
primary request kind, line items and request coverage. Quantities are compared
numerically; units have limited documented normalization in code. Products and
requests are matched one-to-one, independent of list order, with extra predictions
penalized. Description scoring uses explicit concept/synonym groups and is not a
general semantic judge. Missing/review outcomes remain in score denominators;
an entirely uncovered report is unmeasured. Confidence is never scored as accuracy.

## Schema policy

Unknown facts stay null. Do not invent SKUs, quantity, units, urgency or dates.
Products need a SKU or description. Quantities must be positive finite numbers,
excluding strings and booleans; confidence is finite in [0, 1]. An output may
validate and still be factually wrong: that is what the hand-label comparison measures.

Multi-intent uses `primary_request` and `secondary_requests`. Primary priority:
return, complaint, order, status, quote, availability, delivery_cost, other.
First mention breaks ties. Quote/availability/delivery_cost map to intent other.
Status concerns an existing order, while availability concerns product stock.
An order requires explicit purchase authorization; quote-only means authorization
is false. This extraction metadata never places a real purchase.

## Verification

```powershell
.\desk.cmd structured-output "data\emails" --plan-only
.venv\Scripts\python.exe -m pip --disable-pip-version-check check
git diff --check
```

No automated test suite is included in this checkout. Use the offline preview
to verify selected inputs and reuse before a live run. Actual human review and
a live email batch are needed to establish extraction accuracy and provider
behavior. The optional model cost/accuracy comparison remains a stretch task.
