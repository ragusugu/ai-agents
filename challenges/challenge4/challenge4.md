# Challenge 4: Naive RAG — Build, Done When and Stretch

**Current check: 28 November 2026. Build / Done When / Stretch: PASS for the tested requirements and examples.** Current streaming API demos ran **19:27:40–19:28:58 IST**. The full suite passed **115 tests**; six bounded answer calls used the existing configured model. No live email batch was run.

Source of truth: original PDF page 7, [extracted Challenge 4 lines 179–207](../../documents/references/source-extracted.txt). Design/setup details stay in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Original Break It experiments and limitations stay only in the existing root [notes.md](../../notes.md#streaming-recheck). Copy/paste command reference: [comments.md](comments.md).

## BUILD — requirements checked

| Original requirement | Current evidence | Status |
| --- | --- | --- |
| Load policies, fixed chunks about 500 / overlap 50 | Bundled-tokenizer windows, original text and input-budget tests | PASS |
| Embed and persist in a vector DB | Genuine local BGE CPU model; persistent Chroma; 384-dimensional normalized vectors | PASS |
| Embed question and retrieve top 4 as answer context | Actual top-four source/text records and shared prompt wiring checked | PASS |
| Claims have chunk citations | Required policy examples cite their actual chunks; missing/unknown citation formats fail visibly | PASS for demonstrated examples |
| Missing information → exact refusal | Actual answer is exactly `not in the documents` | PASS |
| Re-ingest creates no duplicates | Default index stays 10 files / 15 chunks; unchanged embeddings 0 | PASS |

Citation formatting and example checks do not certify semantic faithfulness for every possible generated claim.

### 1. Ingest the policy folder

Input in Terminal (PowerShell, repository root):

```powershell
.\desk.cmd ingest "data\policies" --offline
```

Actual summary excerpt:

```text
Policy ingest complete: 10 selected files | updated 0 | unchanged 10 | removed 0
Index: 10 files | 15 chunks | embedded 0 | removed chunks 0
Local CPU model: BAAI/bge-small-en-v1.5 | elapsed 9.02s
Vector DB: C:\Users\suganeshwaran\Desktop\AI Agents\src\naive_rag\rag_db
```

The full actual phase output is in [ingest-folder.txt](../../.desk/challenge4-verification/20261128T135740Z/ingest-folder.txt). This is the default DB at `src/naive_rag/rag_db/`, collection `desk_policies`. The original first ingest embedded all 15 chunks; this unchanged repeat embedded zero.

### 2. Update a selected file without removing other policies

Input:

```powershell
.\desk.cmd ingest --source "data\policies\returns-2025-10.md" --offline
```

Actual summary excerpt:

```text
Policy ingest complete: 1 selected files | updated 0 | unchanged 1 | removed 0
Index: 10 files | 15 chunks | embedded 0 | removed chunks 0
Local CPU model: BAAI/bge-small-en-v1.5 | elapsed 8.71s
Vector DB: C:\Users\suganeshwaran\Desktop\AI Agents\src\naive_rag\rag_db
```

The selected file was reused and all ten indexed files remained. Full output: [ingest-file.txt](../../.desk/challenge4-verification/20261128T135740Z/ingest-file.txt).

### 3. Genuine embedding/persistence check

Input:

```powershell
.\.venv\Scripts\python.exe challenges\challenge4\smoke_ingest.py
```

Actual final status:

```text
Actual local embedding/Chroma smoke passed. Evidence: C:\Users\suganeshwaran\Desktop\AI Agents\.desk\ingest-smoke\fbb19e5e24d546b7b1420745e3dc8f68\report.json
```

Observed: two synthetic files produced **13 real vectors**, including two embedding batches for the long file; unchanged repeat embedded **0**. A fresh CLI reopened the same database. Stored vectors were finite, normalized and 384-dimensional; recomputation differed by at most `2.9043494331748576e-08`, and direct similarity search returned the relevant policy. File shrink/deletion/config-reset checks used only this isolated fixture. [Actual report](../../.desk/ingest-smoke/fbb19e5e24d546b7b1420745e3dc8f68/report.json). The actual user-policy index remains ten files / fifteen chunks.

## DONE WHEN — actual input/response pairs

### Policy answer with correct citations

Start Desk chat:

```powershell
.\.venv\Scripts\python.exe src\desk.py chat
```

Type this exact chat input:

```text
/ask For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee? --debug
```

Actual assistant answer:

```text
Under the Returns Policy Update (POL-011, Version 2.0, effective 2025-10-01), which applies to orders placed on or after October 1, 2025 [returns-2025-10.md#1]:

- **Return window:** Unopened, unused stock products may be requested for return within 45 calendar days after delivery. The day after delivery is day one, and a request on day 45 qualifies for review. A request on day 46 requires an exception decision [returns-2025-10.md#1].
- **Restocking fee:** 10% applies to a discretionary return of conforming goods. It is calculated on the net merchandise value paid for the returned quantity, after the original bulk discount [returns-2025-10.md#1].

Verified fulfillment errors, transit damage, and accepted warranty defects carry no restocking fee [returns-2025-10.md#1].
```

**PASS:** 45 calendar days / 10% for the October policy; the citation points to `returns-2025-10.md#1` in the actual retrieved context. Full streamed terminal capture: [chat.txt](../../.desk/challenge4-verification/20261128T135740Z/chat.txt).

### Out-of-scope refusal

Terminal input:

```powershell
.\desk.cmd ask "What is the favorite color of the CEO of Meridian Supply Co.?" --debug
```

Actual answer text:

```text
not in the documents
```

**PASS:** exact refusal, with no invented fact. Full capture: [out-of-scope.txt](../../.desk/challenge4-verification/20261128T135740Z/out-of-scope.txt). Single-question captures used the actual Desk CLI dispatcher with these exact arguments and genuine provider I/O; launcher commands above forward the same arguments.

### Idempotence

The repeated folder command in BUILD retained **15 → 15** chunks and embedded **0**. Selected-file ingestion also retained all **10** indexed files. **PASS.**

## STRETCH — full chunks and similarities

The `--debug` inputs above print **all retrieved chunk text**, IDs and cosine scores before the streamed answer. Source text is no longer truncated to a 240-character preview. Plain and Rich output are tested.

Actual ID/score lines from the return-policy chat turn (full text follows each header in the linked capture):

```text
[returns-2025-01.md#1] score=0.7496
[returns-2025-10.md#1] score=0.7335
[price-adjustments-and-refunds.md#1] score=0.6651
[order-cancellation.md#1] score=0.6531
```

**PASS:** top-four IDs/scores and complete source chunks are present in [chat.txt](../../.desk/challenge4-verification/20261128T135740Z/chat.txt). Scores are similarities, not confidence probabilities.

## Streaming and acceptance evidence

| Operation | What arrives as produced | Verification |
| --- | --- | --- |
| `/ask`, CLI `ask`, `/chat` | Actual provider text deltas; no buffered-response typewriter | Controlled generator/flush checks plus real API delta measurements |
| `/ingest` | Actual load/model/index/chunk/embed/store phases and batch completion | Genuine multi-batch fixture and timestamped local chat output |
| `/structured-output` | Planning/per-email progress; only persisted validated outcomes as they complete | Mocked extraction/repair regressions, before-next-email assertions, sample/summary checks; no live email batch |
| `/save`, `/load`, `/reset`, `/exit` | Immediate local completion result; no animation/model call | Actual local chat capture and flush/provider-forbidden tests |

Actual live streaming measurements (each delta was visible and flushed before provider-stream return):

| Query | Delta events | First visible delta (s) | Stream returned (s) | Result |
| --- | ---: | ---: | ---: | --- |
| out-of-scope | 1 | 1.936 | 1.938 | PASS |
| table | 21 | 1.523 | 2.214 | PASS |
| conflict | 68 | 1.712 | 3.955 | PASS |

The short refusal arrived as one provider chunk; no fake word-by-word animation was added. The longer answers arrived in many genuine deltas. Timing records: [report.json](../../.desk/challenge4-verification/20261128T135740Z/report.json).

**Draft limitation:** streamed RAG text is visible before citation-format validation finishes. A rejected, interrupted, empty, truncated or protocol-incomplete stream is not saved as a successful history turn. Visible text cannot be retracted; a clear rejection/interruption result follows it. Semantic correctness is not guaranteed by a citation-format check.

**Tests:** 115 passed in 69.905 seconds, covering prior challenge regressions and new plain/interactive-Rich/noninteractive streaming, retry/close, incomplete streams, citation rejection, single history/usage accounting, progressive ingest and validated per-email results. Stream tests assert visibility while the producer is still running, not just a streaming function name. [Tests](test_streaming.py).

**Actual local captures:** [guided/file ingest and immediate local commands](../../.desk/streaming-verification/20261128T140225Z/local-chat.txt), [timestamped local arrival events](../../.desk/streaming-verification/20261128T140225Z/local-chat.json), and [email plan-only preview](../../.desk/streaming-verification/20261128T140225Z/structured-preview.txt). The preview made zero model calls. Live email extraction was not tested. [Original-PDF acceptance checklist](../../.desk/streaming-verification/20261128T140225Z/acceptance.json).

Original Break It inputs, actual responses, the measured retrieval baseline and the deliberately exposed vague-follow-up failure are in [root notes.md](../../notes.md#streaming-recheck). No Challenge 5 techniques were added.
