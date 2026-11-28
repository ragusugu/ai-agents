"""Challenge 4 first procedure: local policy ingestion only."""

import hashlib
import time
from pathlib import Path

from .local_embeddings import DEFAULT_RAG_DB_DIR, LocalEmbeddings, project_path, validate_vectors
from model import DeskError
from .rag_chunker import chunk_policy, load_policies, validate_chunk_options
from .vector_store import PolicyStore, fingerprint_id, ingest_lock


def _intact(source, previous, records, config_id):
    if not isinstance(previous, dict) or previous.get("sha256") != source.sha256:
        return False
    ids = previous.get("chunk_ids")
    if not isinstance(ids, list) or ids != [f"{source.name}#{index + 1}" for index in range(len(ids))]:
        return False
    if source.text.strip() and not ids:
        return False
    for index, chunk_id in enumerate(ids, 1):
        doc, meta = records.get(chunk_id, (None, None))
        if (not isinstance(doc, str) or not isinstance(meta, dict) or
                meta.get("source_file") != source.name or meta.get("chunk_index") != index or
                meta.get("file_sha256") != source.sha256 or meta.get("fingerprint") != config_id or
                meta.get("document_sha256") != hashlib.sha256(doc.encode()).hexdigest()):
            return False
    return True


def ingest_policies(source, *, db_dir=DEFAULT_RAG_DB_DIR, chunk_size=500,
                    overlap=50, reset=False, embedder=None, progress=None):
    started = time.perf_counter()
    def notify(kind, message, **extra):
        if progress is not None:
            progress(dict(kind=kind, message=message, **extra))
    source_dir, db_dir = project_path(source), project_path(db_dir)
    # Read and decode all sources before creating/opening the database.
    notify("loading_sources", f"Reading policies from {source_dir}")
    sources = load_policies(source_dir, progress=progress)
    embedder = embedder if embedder is not None else LocalEmbeddings()
    notify("loading_model", "Preparing the local CPU embedding model/cache…")
    embedder.prepare()
    validate_chunk_options(embedder.tokenizer, chunk_size, overlap, embedder.max_tokens)
    config = dict(schema_version=1, embedding=embedder.fingerprint,
                  chunk_tokens=chunk_size, overlap_tokens=overlap)
    config_id = fingerprint_id(config)
    try:
        with ingest_lock(db_dir):
            notify("checking_index", "Checking index/configuration and source hashes…")
            store = PolicyStore(db_dir)
            previous, records = store.inspect(config, reset=reset)
            # A file request updates that file only. Folder pruning is confined
            # to previously indexed files whose parent is exactly this folder.
            selected = {policy.name for policy in sources}
            scoped_removed = {name for name, entry in previous.items()
                if source_dir.is_dir() and Path(entry["source_path"]).parent == source_dir and name not in selected}
            files = {name: entry for name, entry in previous.items() if name not in scoped_removed}
            changed = []
            updated = unchanged = embedded = 0
            for policy in sources:
                policy_path = str(source_dir / policy.name if source_dir.is_dir() else source_dir)
                if policy.name in previous and previous[policy.name].get("source_path") != policy_path:
                    raise DeskError(f"Filename collision: {policy.name} is already indexed from another path. "
                                    "Rename the source file or use a separate --db-dir.")
                if _intact(policy, previous.get(policy.name), records, config_id):
                    files[policy.name] = previous[policy.name]
                    unchanged += 1
                    notify("file_unchanged", f"{policy.name}: unchanged; embeddings reused", source=policy.name)
                    continue
                notify("chunking", f"Chunking {policy.name}", source=policy.name)
                chunks = chunk_policy(policy, embedder.tokenizer, chunk_size, overlap, embedder.max_tokens)
                vectors = []
                batch_size = getattr(embedder, "batch_size", 8)
                for offset in range(0, len(chunks), batch_size):
                    part = chunks[offset:offset + batch_size]
                    notify("embedding", f"Embedding {policy.name}: chunks {offset + 1}–{offset + len(part)} of {len(chunks)}",
                           source=policy.name, completed=offset, total=len(chunks))
                    vectors.extend(validate_vectors(embedder.embed_documents([chunk.text for chunk in part]),
                                                     len(part), embedder.dimension))
                    notify("embedded_batch", f"Embedded {policy.name}: {len(vectors)}/{len(chunks)} chunks",
                           source=policy.name, completed=len(vectors), total=len(chunks))
                changed.append((chunks, vectors))
                files[policy.name] = dict(sha256=policy.sha256, source_path=policy_path,
                                         chunk_ids=[chunk.chunk_id for chunk in chunks])
                updated += 1
                embedded += len(chunks)
            expected = {item for entry in files.values() for item in entry["chunk_ids"]}
            stale = sorted(set(records) - expected)
            removed = len(scoped_removed)
            # Do not rewrite an intact unchanged manifest/index.
            if updated or removed or stale or reset or not store.manifest_path.exists():
                notify("storing", "Writing changed chunks and finalizing the persistent index…")
                store.publish(config, files, changed, stale, reset=reset, progress=progress)
            notify("ingest_complete", f"Index synchronized: {len(expected)} chunks; {embedded} embedded")
            return dict(files_total=len(sources), indexed_files_total=len(files), files_updated=updated, files_unchanged=unchanged,
                        files_removed=removed, chunks_total=len(expected), embedded_chunks=embedded,
                        chunks_removed=len(stale), latency_s=round(time.perf_counter() - started, 3),
                        source=str(source_dir), source_kind="folder" if source_dir.is_dir() else "file",
                        db_dir=str(db_dir), embed_model=embedder.model_name,
                        fingerprint=config_id, local_only=True)
    except DeskError:
        raise
    except Exception as exc:
        raise DeskError(f"Local policy ingest failed: {type(exc).__name__}: {exc}") from exc
