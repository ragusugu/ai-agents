---
name: ingest
description: Load or update user-selected UTF-8 Markdown policies in Desk's local vector database using local embeddings. Use for /ingest or requests to update a policy file or folder in the vector DB.
---

# Ingest policies

Use the shared `src/naive_rag/ingest.py` workflow through Desk from the project root.
Local embedding, chunking and persistence modules live together in `src/naive_rag/`:

```powershell
.\desk.cmd ingest "path\to\policy.md"
.\desk.cmd ingest --source "path\to\policies"
```

Inside Desk chat use `/ingest "path\to\policy.md"` or `/ingest "path\to\policies"`.
A bare `/ingest` asks for the source; provide a path on the next turn. Paths with
spaces must be quoted when combined with flags. Preserve Windows backslashes.
Relative paths resolve from the Desk project, not the terminal's current folder.

Supported inputs are one UTF-8 `.md` file or every top-level `.md` file in a folder;
subfolders, PDFs, Word documents and email extraction are outside this workflow.
Keep original files unchanged. Do not invent a source or use an unrelated default.

File requests update only that file and retain other indexed policies. Folder
synchronization prunes deleted files only within that exact source folder. A missing
path fails without deleting records; an existing empty folder clears that folder's
indexed records. Identical filenames from different paths cannot share the same
`filename#index` IDs: report the collision and use distinct names or `--db-dir`.

The workflow uses SHA-256 to skip unchanged files, bundled-tokenizer 500/50 windows,
local quantized BGE small CPU embeddings and persistent Chroma with explicit vectors.
It updates/shrinks changed chunks and summarizes actual selected/updated/unchanged/
removed files, indexed chunks, embedded chunks and elapsed time. Repeating intact
unchanged inputs makes zero embedding calls and adds no duplicate IDs.

`--db-dir`, `--chunk-size`, `--overlap`, `--embed-model`, `--cache-dir`, `--threads`,
`--batch-size` and `--offline` configure the same workflow. `--help` lists options.
Incompatible config/artifacts or interrupted writes fail clearly. Use `--reset`
only when explicitly requested: it rebuilds the entire Desk policy collection from
the selected source, retaining other Chroma collections and the model cache.

The first run may download the selected compact ONNX model; inference is local.
The default database is `src/naive_rag/rag_db/` (gitignored); the Chroma collection
is `desk_policies`. Chroma persists `chroma.sqlite3` and local vector-index files.
`desk-policies.json` tracks source hashes/configuration; a pending marker detects
interrupted writes. Model artifacts are cached separately in `.desk/models/`.
Use `--db-dir` or `DESK_RAG_DB_DIR` to override database placement.
No answer-model/provider request is made by direct CLI or `/ingest` execution.
Natural-language chat requests use the existing Desk API only to select the typed
`ingest_policies` tool; the resulting ingestion is this same local workflow. Ask for
a missing source. Usage questions, examples and code-edit requests do not authorize
ingestion. Never claim success/counts before the Python workflow completes.

For policy questions after ingest, use `desk ask "question" --debug` or `/ask` in
chat. Those commands retrieve local vectors and send context to the existing Desk
answer API; `--no-rag` keeps the direct API path. Ingest itself stays local.
