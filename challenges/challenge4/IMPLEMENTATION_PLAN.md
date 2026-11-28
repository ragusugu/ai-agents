# Challenge 4: Naive RAG — Implementation Plan

**Branch:** `ch04`  
**Reference:** [agentic-ai-15-challenges.pdf](../../documents/references/agentic-ai-15-challenges.pdf) (Stage 2, Page 7)  
**Updated:** 2026-11-28 (Asia/Calcutta). **Current scope: Challenge 4 Naive RAG, implemented and tested stage by stage.** Shared `desk ingest` and `/ingest`, local top-four retrieval, `desk ask` and `/ask`, cited/refusal answer prompting, `--debug` and `--no-rag` are implemented. Controlled existing-provider tests were explicitly authorized and completed. Challenge 5 rewriting/hybrid search/reranking and other future challenges are outside scope.

Canonical progress, Build/Done When/Stretch checks, actual demos and test evidence: [challenge4.md](challenge4.md). Break It experiments, numeric retrieval assessment and learning observations: [notes.md](../../notes.md). This plan owns design/status, not duplicate transcripts.

**Constraint:** Local embedding-library calls plus the existing raw answer-provider SDK (`boto3` `bedrock-runtime`); **no agent frameworks** (Ground Rule #1 for Challenges 1–7). The user's explicit `/ingest` request extends the original seven-command menu to eight, preserving all existing commands, dark styling, usage/telemetry and Challenge 1–3 behavior. Leave the paused Challenge 3 semantic-verifier work and unrelated dirty files untouched; do not run an email batch or redefine its schema. All new RAG implementation modules belong together in `src/naive_rag/`; the default vector DB is `src/naive_rag/rag_db/` (gitignored), and the model cache remains `.desk/models/`.

---

## 1. Objective & Gap Addressed

In Challenge 3, Desk had no access to Meridian Supply Co.'s internal `data/policies/` documents (10 Markdown files, ~336–406 words each), so policy questions either failed to cite sources or risked fabrication. Challenge 4 introduces **Naive RAG**:

1. **Implemented procedure:** `desk ingest <path>` / `/ingest <path>` loads the user's selected UTF-8 `.md` file or every top-level `.md` in their selected folder. It splits new/changed files into 500 content-token chunks with 50 overlap, embeds locally and updates persistent Chroma. No source is assumed; bare `/ingest` asks for one. A file update preserves all other indexed files; folder pruning is confined to that exact source folder.
2. **Implemented:** `desk ask` and `/ask` embed the latest question, retrieve top-four local chunks and call the existing answer API with only that reference context.
3. **Implemented prompt/format contract:** require citations such as `[returns-2025-10.md#1]` and exact `not in the documents` fallback. Live examples passed; per-claim semantic faithfulness is not guaranteed by a formatting check.
4. **Implemented stretch (`--debug`):** print retrieved IDs, cosine similarities and full source chunks in dark/plain modes, matching original PDF page 7.

---

## 2. Architecture & Design Decisions

### 2.0 Hardware inspection and selected local model

Read-only inspection on 2026-11-28 found:

| Item | Observed configuration | Design consequence |
| --- | --- | --- |
| OS / CPU | Windows 11 Pro x64; Intel Core i5-8250U @ 1.60 GHz, 4 cores / 8 logical processors | Use a small quantized CPU embedding model |
| RAM | 17,022,496,768 bytes total (~15.85 GiB, 16 GB class); 2,729,956 KiB free (~2.60 GiB) at inspection | Free RAM varies; start with small batches and no worker processes |
| GPU | Intel UHD Graphics 620; AdapterRAM reports 1 GiB | Integrated/shared graphics report is not dedicated VRAM evidence; select CPU explicitly. No NVIDIA adapter appeared in the inventory |
| Project interpreter | `.venv/Scripts/python.exe`: CPython 3.13.15, Windows AMD64 | Use this interpreter, not the unrelated Python 3.9 on PATH |
| Project packages | `boto3==1.44.7`, `pip==26.3`; no FastEmbed, ONNX Runtime, Chroma, tokenizers, tiktoken, NumPy, Torch or sentence-transformers distribution found in `.venv` | Installation/import/inference compatibility is still untested |
| Other runtimes | `uv` and an Ollama executable are present | Ollama is unnecessary; no model service was started or queried |
| Answer configuration | `.env`: `DESK_MODEL=global.anthropic.claude-sonnet-5-5`, `AWS_REGION=us-east-1`; AWS credential entries are present | Preserve existing runtime resolution and credentials; presence does not prove authentication/model access |

Evidence: Windows CIM processor/OS/video/computer-system queries, project interpreter version, `.venv/pyvenv.cfg` and installed distribution directories, `desk.cmd`, existing provider source and a configuration-presence check. Credential values were not displayed. CIM required a read-only sandbox escalation.

**Selected model: `BAAI/bge-small-en-v1.5`, quantized ONNX, using FastEmbed and ONNX Runtime `CPUExecutionProvider`.** The supported-model definition resolves to `Qdrant/bge-small-en-v1.5-onnx-Q` / `model_optimized.onnx`. The export repository is approximately 67.4 MB, including a 66.5 MB ONNX file; download size is not peak RAM. It produces normalized 384-dimensional vectors and accepts up to 512 model tokens. It is an English model suitable for the current English policies; reliable Tamil query retrieval is not established. A multilingual replacement would need evaluation and an index rebuild. See the [upstream model card](https://huggingface.co/BAAI/bge-small-en-v1.5), [FastEmbed supported-model source](https://github.com/qdrant/fastembed/blob/main/fastembed/text/onnx_embedding.py) and [export files](https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/tree/main).

This compact model is a reasonable fit for the older mobile CPU and currently limited free RAM. Start with `threads=2`, `batch_size=8`, one lazily initialized model per process and no multiprocessing. Actual latency and peak memory must be measured later; this is a hardware-based selection, not a benchmark. Use in-process CPU inference; no Ollama/Qdrant server, CUDA, PyTorch or embedding API key is needed. Do not enable GPU autodetection or install `fastembed-gpu` for the UHD 620. [FastEmbed CPU documentation](https://qdrant.tech/documentation/tutorials-basics/generate-embeddings-fastembed/) supports this runtime choice.

**Only embeddings and vector storage are local.** Answer generation continues through the existing `DESK_MODEL`, `make_client()` and `call_model()`/`stream_model()` API configuration and credential chain. Retrieved policy text is sent to that existing answer API. Do not request or replace credentials, introduce another answer provider, or change the configured answer model.

### 2.0.1 Compatibility and cache plan

Published metadata lists FastEmbed 0.9.1 (Python >=3.10, Python 3.13 listed), ONNX Runtime 1.32.0 (`cp313-cp313-win_amd64` wheel), and Chroma 1.5.9 (`cp39-abi3-win_amd64` wheel). This combination subsequently installed and passed imports/inference/isolated DB checks on the project interpreter. Existing provider/Pydantic pins were preserved. Windows ONNX Runtime documents the Visual C++ runtime prerequisite; actual successful ONNX execution establishes runtime availability for this checkout. Sources: [FastEmbed metadata](https://pypi.org/project/fastembed/), [ONNX Runtime wheels](https://pypi.org/project/onnxruntime/#files), [Chroma wheels](https://pypi.org/project/chromadb/#files), [ONNX Runtime prerequisites](https://onnxruntime.ai/docs/install/).

First initialization downloads only the selected export/tokenizer into gitignored `.desk/models/`; subsequent runs reuse cached artifacts. `--offline` / `DESK_EMBED_OFFLINE=1` requires cached artifacts and reports missing-cache errors. No silent model substitution or remote embedding fallback. Initialization is lazy so help and unrelated Challenge 1–3 flows do not load embeddings. Shell PyPI DNS failed during the earlier plan-only inspection; the subsequent authorized installation/download succeeded with sandbox escalation. FastEmbed 0.9.1, ONNX Runtime 1.32.0, Chroma 1.5.9, tokenizers 0.23.3 and NumPy 2.5.5 are installed/pinned; `pip check` passed and genuine CPU inference produced 384-dimensional vectors. Existing provider/Pydantic pins were retained.

### 2.1 Vector Database & Tokenization
- **Vector store:** Chroma's embedded persistent client under `src/naive_rag/rag_db/`, gitignored. Installation and actual DB writes succeeded; no FAISS fallback is needed. `--db-dir` / `DESK_RAG_DB_DIR` overrides are preserved. The old default `.desk/rag_db/` did not exist and no database migration was needed.
  - Why persistent Chroma: built-in metadata storage, cosine similarity (`hnsw:space = cosine`), upsert by deterministic ID, and deletion of stale chunks without maintaining a separate sidecar metadata index.
- **Embeddings:** Local FastEmbed adapter in `src/naive_rag/local_embeddings.py`, default `DESK_EMBED_MODEL=BAAI/bge-small-en-v1.5`, explicitly using `CPUExecutionProvider`. No Bedrock embedding calls. Chroma receives explicit embeddings with its default embedding function disabled, preventing a second model or unexpected download.
- **Chunking:** Fixed windows of 500 content tokens with 50 overlap using the exact bundled BGE WordPiece tokenizer, replacing the original `tiktoken/cl100k_base` proposal. Different tokenizers can turn a 500-token chunk into more than BGE's 512 tokens and silently truncate it.
  - Disable truncation while counting/splitting; reserve special-token overhead (normally two). Check the complete embedding input stays within 512 tokens and reject oversized chunk sizes.
  - Preserve original Markdown/SKU/table text through tokenizer character offsets. Re-tokenize extracted substrings and adjust boundaries if needed; do not reconstruct policy prose from decoded WordPiece tokens.
  - Embed passages unchanged. Prefix each query exactly once with the upstream instruction `Represent this sentence for searching relevant passages: `; do not also add generic `query:`/`passage:` prefixes. Reject queries exceeding the total input budget rather than silently truncating them.
  - Keep 500/50 configurable within the model's budget; actual chunk counts depend on the selected tokenizer and must be measured.

### 2.2 Idempotency & Citation Contract
- **Deterministic chunk IDs:** `<filename>#<1-based-chunk-index>` (e.g., `returns-2025-10.md#1`).
- **Source tracking:** Chunk metadata stores `source_file`, absolute `source_path`, `chunk_index`, `file_sha256`, original-text checksum, token count and embedding fingerprint. The collection/manifest fingerprint includes provider, model/export/revision, ONNX/tokenizer/config SHA-256 hashes, relevant runtime/tokenizer versions, dimension (384), normalization, cosine metric, document preprocessing and chunk/overlap parameters. Per-file source paths live in manifest entries so additional user-selected sources can share a compatible index; filename collisions from different paths fail clearly. Future query preprocessing belongs to the retrieval contract when implemented.
- **Idempotent re-ingest:**
  - If a file's SHA-256 and chunk/embedding config are unchanged, skip re-embedding and leave existing records intact (zero duplicates).
  - If a file changed, upsert its new chunks and delete any leftover chunk indices beyond the new chunk count.
  - A file request never prunes other files. A folder request prunes only removed files whose tracked parent is exactly that selected folder. Missing paths fail before index mutation; existing empty folders clear only their scoped records. Source files remain unchanged.
  - Ingest and retrieval validate the fingerprint. Incompatible model/artifact/dimension/tokenizer/chunk configuration fails with `DeskError` and reset guidance. Explicit `--reset` rebuilds the entire `desk_policies` collection from the selected source, preserving other collections/cache; it is not an implicit single-file update.
  - Validate vector count, finite numeric values, expected dimension and nonzero norm before any write/search. Detect missing records rather than trusting the manifest alone. Publish the manifest after successful sync; define recovery/rejection for interrupted partial Chroma writes without claiming multi-file atomicity.

### 2.3 CLI & Chat Menu Compatibility
- Per the explicit user override in [AGENTS.md](../../AGENTS.md), chat exposes exactly eight commands: `/ask`, `/chat`, `/reset`, `/exit`, `/load`, `/save`, `/structured-output`, `/ingest`.
- `desk ingest` and `/ingest` call the same `src/naive_rag/ingest.py` workflow; reusable guidance is `skills/ingest/SKILL.md`. Quoted Windows paths/spaces work, and bare `/ingest` prompts for a source. Typed native tool routing exposes `ingest_policies`; an actual natural-language chat demo selected it and reused all ten unchanged policies. Direct CLI/slash execution needs no answer-provider call; the natural-language route uses the existing API to select the tool, then runs the same local workflow.
- **Implemented:** `desk ask` and `/ask` are the RAG query entry points:
  - When the RAG index exists, `desk ask` runs Naive RAG retrieval (top 4 chunks) unless `--no-rag` is passed.
  - If the RAG index has not been built yet, raise a clear `DeskError` directing the user to run `desk ingest` (unless `--no-rag` is passed).
  - Add `--debug` to `desk ask` to print retrieved chunks, citations, and similarity scores before the answer.
  - Use `/ask` for policy RAG inside chat; preserve ordinary conversational and skill turns. Consecutive `/ask` queries use only the raw latest question, without rewriting/history enrichment, for the vague-follow-up experiment (`"what about for bulk?"`). Do not route natural-language skill execution through policy retrieval.

---

## 3. Planned File Changes

| File | Action | Responsibility |
| --- | --- | --- |
| `requirements.txt` | Update | Pin verified FastEmbed, CPU ONNX Runtime, bundled-tokenizer dependencies and Chroma; FAISS only if an actual Chroma incompatibility requires it |
| `.env.example` | Update | Document local embedding/cache/offline/thread/batch settings, `DESK_RAG_DB_DIR` and `DESK_RAG_TOP_K`; preserve answer configuration |
| `.gitignore` | Updated | Ignore `.desk/` model cache/test evidence and `/src/naive_rag/rag_db/` generated DB contents |
| `src/constants.py` | Updated | Shared RAG system prompt, exact refusal and query instruction; challenge-specific adapter defaults stay in the Naive RAG package |
| `src/naive_rag/local_embeddings.py` | Implemented | Cached lazy CPU document/query embeddings, bundled tokenizer, input/vector validation, offline behavior and artifact fingerprint |
| `src/model.py` | Updated | Optional `system_prompt=SYSTEM_PROMPT` on `call_model`; unchanged default provider behavior, stream interface, client, retries and telemetry |
| `src/naive_rag/rag_chunker.py` | Implemented | Selected file/folder loader, SHA-256 and fixed native-tokenizer original-text windows with deterministic IDs |
| `src/naive_rag/vector_store.py` | Implemented | Persistent Chroma, compatibility guards, scoped upsert/pruning, lock and interrupted-sync marker |
| `src/naive_rag/ingest.py` | Implemented | Canonical shared ingestion and selected-source scope |
| `src/naive_rag/retrieval.py` | Implemented | Guarded explicit-vector top-k search, source metadata integrity, delimited context and citation-format validation |
| `src/desk.py`, `src/chat_commands.py`, `src/skill_tools.py` | Updated | Shared ingest CLI/slash/guided/typed-tool execution, RAG ask and bypass/debug flags, eight-command menu |
| `src/presentation.py` | Updated | Genuine incremental answers, noninteractive fallback, workflow progress/results, and full-chunk debug output |
| `skills/ingest/SKILL.md` | Created | Reusable guidance for actual file types, user-selected scope, paths and shared execution |
| `challenges/challenge4/test_ingest.py`, `test_retrieval.py`, `smoke_ingest.py`, `verify_challenge4.py` | Created | Isolated/fake-vector/provider tests, genuine model persistence smoke and explicitly opted-in live demos/retrieval baseline |
| `challenges/challenge4/notes.md` | Create | Record actual local-model/runtime evidence and **Break it** results; distinguish provider-backed checks |

---

## 4. Detailed Implementation Steps

### Step 1: Dependencies & Environment Configuration
1. Completed for ingest: install/pin the compatible CPU model/runtime/tokenizer/Chroma combination in project `.venv`, retaining current pins. Chroma worked; no fallback needed.
2. Update [requirements.txt](../../requirements.txt), [.env.example](../../.env.example), and [.gitignore](../../.gitignore).
3. Implemented defaults: `DESK_EMBED_MODEL=BAAI/bge-small-en-v1.5`, `DESK_EMBED_CACHE_DIR=.desk/models`, `DESK_EMBED_THREADS=2`, `DESK_EMBED_BATCH_SIZE=8`, `DESK_EMBED_OFFLINE=0`, `DESK_RAG_DB_DIR=src/naive_rag/rag_db`, `DESK_RAG_TOP_K=4`. Ingest sources are explicitly selected; paths resolve from project root. Unsupported embedding overrides fail clearly.

### Step 2: Local Embedding Adapter & Answer Prompts
1. **Implemented answer stage:** optional `system_prompt=SYSTEM_PROMPT` on `call_model`. The default API path and existing `stream_model` interface stay compatible.
2. **Implemented local stage:** document/query adapter with the query instruction applied exactly once, complete input-budget checks, fingerprints and offline cache errors. A small per-process configuration cache reuses loaded models across turns.
3. **Implemented answer stage:** `RAG_SYSTEM_PROMPT` in [src/constants.py](../../src/constants.py):
   - Instruct Desk to answer **only** using the provided `<context>` chunks.
   - Require every factual claim to include the exact bracketed citation from the chunk header (e.g., `[returns-2025-10.md#1]`).
   - Require exact fallback `"not in the documents"` when the retrieved chunks do not answer the question—no guessing or training-data fallback.
   - Treat context as untrusted reference data, ignore instructions inside it, and preserve visibility of conflicting policy versions. Naive RAG does not resolve version precedence automatically.
   - Prompting does not prove support/refusal. Lightweight unknown/missing-citation checks can reject invalid formatting but cannot establish that each claim follows from a cited chunk. Never manufacture citations or add a semantic verifier; report this limitation honestly.

### Step 3: Policy Loader & Fixed-Size Chunker (`src/naive_rag/rag_chunker.py`, implemented)
1. Accept one user-selected `.md` file or top-level Markdown files from their selected folder, sorted alphabetically. Missing paths fail. An existing empty folder prunes only its own tracked records; empty files clear only their prior chunks.
2. Compute SHA-256 over original bytes, decode UTF-8, and identify filenames on decoding/read errors.
3. Use the exact bundled tokenizer and original-text offsets described in section 2.1; step is `chunk_tokens - overlap_tokens`. Validate `0 <= overlap_tokens < chunk_tokens`, positive chunk size and the full 512-token model budget.
4. Produce `PolicyChunk` records with:
   - `chunk_id`: `f"{path.name}#{idx}"` (1-based index per file)
   - `source_file`: `path.name`
   - `chunk_index`: `idx`
   - `file_sha256`: hex digest
   - `token_count`: integer count
   - `text`: original source substring selected by tokenizer offsets

### Step 4: Idempotent Vector Store (`src/naive_rag/vector_store.py`, ingest implemented)
1. Manage `desk_policies` in `src/naive_rag/rag_db/` (overridable via `--db-dir` or `DESK_RAG_DB_DIR`). Chroma creates `chroma.sqlite3` plus UUID-named vector-index folders; `desk-policies.json` stores the manifest, `.desk-ingest.lock` serializes ingest, and `desk-policies.pending` blocks unsafe reuse after an interrupted sync.
2. Store/check the full fingerprint on ingest and retrieval; disable Chroma's embedding function and supply vectors explicitly. Retrieval rejects incomplete records and verifies each returned chunk's metadata/text checksum.
3. On `sync_documents(chunks_by_file, embed_fn)`:
   - Compare stored `file_sha256` per `source_file` against current files.
   - Skip embedding calls for unchanged files.
   - Embed and validate chunks only for new/modified or damaged/missing records before replacing them; commit the manifest after successful sync and handle partial-write recovery.
   - Delete stale chunk IDs (shrunk or deleted files).
4. **Implemented retrieval module:** query `min(top_k, collection_count)`, return ranked source/text/score records and convert cosine distance to `1 - distance`. Scores are not calibrated confidence. Empty indexes yield the exact fallback without an answer API call.

### Step 5: Shared ingestion and retrieval/answer integration (implemented)
1. `ingest_policies(...)`: Orchestrates chunking -> incremental sync -> returns summary counts (`files_total`, `files_updated`, `files_unchanged`, `files_removed`, `chunks_total`, `embedded_chunks`, `latency_s`).
2. `retrieve_chunks` in `src/naive_rag/retrieval.py` validates the index/query and retrieves top-four chunks with original text and scores.
3. `cmd_ask` calls shared retrieval, formats `<context>` as JSON reference records with citation IDs, and calls the existing `stream_model(..., RAG_SYSTEM_PROMPT, on_text=...)`. Deltas are displayed as produced, marked as drafts until the complete response passes citation-format checks. Unknown/missing citations or incomplete streams produce a visible rejection/interruption and no successful saved turn; already displayed text cannot be retracted. The empty-index path makes no provider call. Actual provider usage, first-token timing and local preparation latency are preserved without fabricated API tokens.

### Step 6: CLI & Presentation Integration (`src/desk.py`, `src/presentation.py`)
1. Add `ingest` subparser in `build_parser()`:
   - Required user choice via positional path or `--source`; no implicit default corpus. DB defaults to `src/naive_rag/rag_db`; chunk size/overlap 500/50; selected model plus `--cache-dir`, `--threads`, `--batch-size`, `--offline`, `--reset`. `/ingest` uses this parser/workflow and a guided source prompt.
2. **Implemented:** update `ask` subparser and `cmd_ask`:
   - Add `--debug` (`action="store_true"`) to print retrieved chunks and similarity scores.
   - Add `--no-rag` (`action="store_true"`) to bypass retrieval if explicitly needed.
   - Preserve usage footer, telemetry turn accounting and Rich rendering. Local embedding timing is separate, with no fabricated API token usage/cost. `--no-rag` must not initialize local models or require an index.
3. Implemented `/ingest` completion/typed dispatch and `/ask --debug`, preserving all seven previous commands. Ordinary chat and existing skills retain their behavior; consecutive `/ask` turns retrieve the raw latest question without rewriting/history enrichment.

---

## 5. Verification & Testing Plan

### 5.1 Automated Tests (`challenges/challenge4/test_ingest.py`)
Ingest/retrieval tests use real temporary Chroma/tokenizer instances and injected embedding/provider fakes. They cover chunking, idempotence, scoped updates/deletion, config/reset, interrupted writes, input budgets, top-four search, prompt/citation/refusal wiring and CLI/slash/tool/guided-source interfaces. Genuine model and live provider evidence is recorded separately in the canonical challenge document.
- **Chunking:** ~500-token chunks with 50-token overlap; deterministic `[file.md#1]` IDs; validation errors on invalid overlap/missing folder.
- **Idempotency:** Running `ingest` twice produces the exact same chunk count and makes zero embedding calls on the second run; modifying a file updates its chunks and deletes excess tail chunks; deleting a file removes its chunks.
- **Config/input guards:** Ingest and query reject model/artifact/tokenizer/dimension/chunk/source mismatch; test invalid vector counts/dimensions/NaN/zero norm, missing packages/cache, offline errors, Unicode/table/SKU preservation and overflow without truncation. Verify scoped reset, restart persistence, final-file deletion and interrupted-sync handling.
- **Retrieval & Grounding wiring:** Verify top-four context, system prompt, citation IDs, injected fallback responses, empty-index refusal and `--no-rag`. Mocked answers establish wiring and output handling, not semantic retrieval accuracy, faithful citations or guaranteed refusal.
- **Stretch (`--debug`):** Verifies chunk IDs and similarity scores are printed in both plain and Rich terminal modes.
- **Regression:** Root discovery now works with `python -m unittest discover -s challenges -v`; helper imports were package-qualified during reorganization. Native Windows tests need temporary-file/pipe access; sandbox restrictions were observed and the successful suite ran with escalation. Existing direct-API tests select `--no-rag`, and two menu assertions reflect the requested eighth command. No verifier behavior was changed.

### 5.2 Live Terminal Verification & "Break It" Experiments
Completed genuine local BGE/persistent-Chroma fixture checks, source-policy ingestion/re-ingestion and a small labeled retrieval baseline. Actual timings, vector readback/recomputation/search, restart evidence and limitations live in the canonical challenge/notes documents; injected-vector tests are not presented as genuine inference.

Provider checks were explicitly authorized and completed through the existing configured API. The following coverage is split between Build/Done/Stretch demos in `challenge4.md` and Break It observations in `notes.md`:
1. `.\desk.cmd ingest` -> confirm 10 policy files ingested; re-run `.\desk.cmd ingest` -> confirm 0 duplicates / 0 re-embedded chunks.
2. `.\desk.cmd ask "What is the return window for unopened stock products?" --debug` -> confirm `[returns-2025-10.md#...]` citation and chunk scores printed.
3. `.\desk.cmd ask "What is Meridian's CEO's favorite color?"` -> confirm `"not in the documents"`.
4. **Break it experiments** (from PDF Page 7):
   - Search for exact SKU `MS-VLV-0200`.
   - Ask a question whose answer lives inside a Markdown table (e.g., bulk pricing tiers or shipping rates).
   - Ask about the topic where `returns-2025-01.md` and `returns-2025-10.md` contradict each other.
   - In `desk chat`, use consecutive `/ask` turns, ending with `"what about for bulk?"`, without query rewriting.
   - Record a labeled small-fixture retrieval assessment and observed citations/refusals/errors to set up Challenge 5; do not claim guaranteed refusal or universal accuracy.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| Future Chroma wheel/dependency conflict | Current Windows/Python combination passed; keep `src/naive_rag/vector_store.py` as the storage boundary |
| Local model/package download or Windows runtime incompatibility | Verify dependency resolution/imports and Visual C++ runtime; cache only the selected model, support offline errors, and never switch silently to remote embeddings |
| Breaking prior behavior | Answer-provider behavior remains unchanged; preserve all seven previous commands plus requested `/ingest`; run scoped/combined regression checks |
| Policy docs (~350–406 words) fitting in 1 chunk at 500 tokens | Default to PDF's 500/50 spec while supporting `--chunk-size` / `--overlap` CLI flags for testing chunk-boundary effects |
| Native 512-token input limit, English-only retrieval and currently limited free RAM | Use bundled-tokenizer budgets, explicit CPU execution, small batches, and measured later smoke checks; multilingual quality remains unverified |
| Prompted answers may omit citations, misread conflicting policies or invent support | Separate format checks from semantic evaluation; record actual provider-backed outcomes without adding a semantic verifier |

## 7. Status of This Update

Challenge 4 implementation and controlled validation are complete for the tested original PDF requirements/examples. The latest streaming regression suite passed 115 tests. Default policy ingestion retained 10 files / 15 chunks on repeat with zero re-embedding; a genuine 13-vector multi-batch fixture passed restart/readback/search/scoped-update checks. Six current streaming answer calls used the existing configured API, with callback flush measurements before provider completion. Earlier natural-language ingest routing was also verified. Known naive-retrieval limitations remain documented rather than solved with Challenge 5 features. Current typed-input/actual-response demos are in `challenge4.md`; only original Break It observations belong in root `notes.md`.

The user's later authorization permitted read-only use of the actual policy corpus; it is now indexed at `src/naive_rag/rag_db/`. Old/interim defaults had no data, so no migration/deletion was necessary. Fixture evidence stays under `.desk/ingest-smoke/`. No email batch or future challenge was run. Pre-existing dirty files and legacy outputs remain preserved.

## 8. Source organization

Shared provider/configuration, CLI/chat/session, presentation, tool dispatch, telemetry and the schema import bridge remain directly under `src/`. Six existing Challenge 3 modules moved to `src/challenge3_structured_output/`; package imports and project-root paths were adjusted. Function/class ASTs matched before/after after normalizing the necessary parent-depth path adjustment; paused `grounding.py` and `source_map.py` were byte-identical across the move. No Challenge 1/2 folders were invented for shared files. All new RAG code is in `src/naive_rag/`.

Reordering is separate from the new Challenge 4 behavior. Existing source-code provenance hashes can change when import/path text changes; legacy serialized outputs were not rewritten or relabeled. The authoritative schema stays in `skills/structured-output/`, with `src/schemas.py` unchanged as its import bridge.

## 9. Incremental output contract

- CLI `ask` and `/ask` share genuine provider streaming for RAG and `--no-rag`. Ordinary chat retains real streaming. Interactive Rich consoles redraw arriving deltas immediately; noninteractive/dumb Rich surfaces emit incremental text rather than buffering in an invisible Live widget. No delayed typewriter is used.
- RAG text is a draft until a complete end-turn, reported usage and citation-format checks pass. Empty, truncated, interrupted, protocol-incomplete or citation-invalid drafts are visibly unaccepted and not saved as successful turns. Already visible text cannot be retracted; citation formatting cannot certify semantic support.
- Retry is allowed before answer text, never by replaying a partially displayed answer. Streams close on success/failure/interruption. Actual usage is counted once; unreported failed-request usage is labeled incomplete.
- Ingest emits actual source/model/config/chunk/batch/store phases and completion. Store events distinguish written records from final manifest completion. Local embeddings, model fingerprints and source scope remain unchanged.
- Structured-output emits planning/per-email progress and persisted validated results or review notices as each completes. Display limits never limit processing; final summaries do not repeat displayed results. Unvalidated candidate/repair fragments are not final results. Validation/repair/verifier logic was not redesigned; no live email batch was run.
- Save/load/reset/exit show immediate actual local results without model calls or simulated streaming.

Evidence: [PDF acceptance assertions](../../.desk/streaming-verification/20261128T140225Z/acceptance.json), [real delta timings/report](../../.desk/challenge4-verification/20261128T135740Z/report.json), [local arrival timing](../../.desk/streaming-verification/20261128T140225Z/local-chat.json), and [streaming tests](test_streaming.py). Prior captures remain in their original reports and an [archived earlier demo document](../../.desk/streaming-verification/20261128T140225Z/challenge4-before-streaming.md). The concise canonical demo is [challenge4.md](challenge4.md); Break It stays in [root notes.md](../../notes.md#streaming-recheck).
