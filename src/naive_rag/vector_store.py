"""Desk-owned Chroma collection and an explicit interrupted-sync guard."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from model import DeskError

COLLECTION = "desk_policies"
SCHEMA_VERSION = 1


def fingerprint_id(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def ingest_lock(directory):
    """OS-released lock: a crash cannot leave a stale exclusive lock."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".desk-ingest.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise DeskError("Another desk ingest is using this index; wait for it to finish.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class PolicyStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest_path = self.directory / "desk-policies.json"
        self.pending_path = self.directory / "desk-policies.pending"
        try:
            import chromadb
            from chromadb.config import Settings
            self.client = chromadb.PersistentClient(path=str(self.directory),
                settings=Settings(anonymized_telemetry=False))
        except ImportError as exc:
            raise DeskError("Chroma dependencies are missing; install requirements.txt in .venv.") from exc
        except Exception as exc:
            raise DeskError(f"Cannot open local Chroma index {self.directory}: {exc}") from exc

    def inspect(self, config, *, reset=False):
        """Read/validate before embedding or changing the policy collection."""
        if self.pending_path.exists() and not reset:
            raise DeskError("Policy sync was interrupted. Run desk ingest --reset with the same --db-dir.")
        names = {getattr(item, "name", item) for item in self.client.list_collections()}
        self.collection = (self.client.get_collection(COLLECTION, embedding_function=None)
                           if COLLECTION in names else None)
        manifest = None
        if self.manifest_path.exists() and not reset:
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if (manifest["schema_version"] != SCHEMA_VERSION or not isinstance(manifest["files"], dict)
                        or manifest["fingerprint"] != fingerprint_id(manifest["config"])):
                    raise ValueError("invalid manifest contract")
                for name, entry in manifest["files"].items():
                    if (not isinstance(entry, dict) or not isinstance(entry.get("source_path"), str)
                            or not Path(entry["source_path"]).is_absolute()
                            or Path(entry["source_path"]).name != name
                            or not isinstance(entry.get("sha256"), str)
                            or not isinstance(entry.get("chunk_ids"), list)
                            or any(not isinstance(item, str) for item in entry["chunk_ids"])):
                        raise ValueError("invalid manifest source entry")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise DeskError("Policy manifest is invalid; rebuild with desk ingest --reset.") from exc
        if reset:
            return {}, {}
        if manifest is not None:
            if manifest["config"] != config:
                raise DeskError("Policy index configuration/model/artifacts changed; run desk ingest --reset.")
            if (self.collection is None or
                    (self.collection.metadata or {}).get("fingerprint") != manifest["fingerprint"]):
                raise DeskError("Policy collection/manifest is inconsistent; run desk ingest --reset.")
        elif self.collection is not None:
            raise DeskError("Policy collection has no compatible manifest; run desk ingest --reset.")
        rows = self.collection.get(include=["documents", "metadatas"]) if self.collection else {}
        records = {item: (doc, meta) for item, doc, meta in
                   zip(rows.get("ids", []), rows.get("documents", []), rows.get("metadatas", []))}
        return (manifest or {}).get("files", {}), records

    def publish(self, config, files, changed, stale_ids, *, reset=False, progress=None):
        """Embeddings are staged/validated first. Any partial write requires reset.

        Chroma writes and JSON replacement are not one transaction. The durable
        pending marker prevents a subsequent ingest trusting partial state.
        """
        config_id = fingerprint_id(config)
        with self.pending_path.open("w", encoding="utf-8") as stream:
            stream.write(config_id)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if reset and self.collection is not None:
                self.client.delete_collection(COLLECTION)
                self.collection = None
            if self.collection is None:
                self.collection = self.client.create_collection(COLLECTION, embedding_function=None,
                    metadata={"hnsw:space": "cosine", "fingerprint": config_id})
            for chunks, vectors in changed:
                # Keep DB batches bounded independently of inference batches.
                for start in range(0, len(chunks), 128):
                    part = chunks[start:start + 128]
                    self.collection.upsert(ids=[chunk.chunk_id for chunk in part],
                        documents=[chunk.text for chunk in part], embeddings=vectors[start:start + 128],
                        metadatas=[dict(source_file=chunk.source_file, chunk_index=chunk.chunk_index,
                            source_path=files[chunk.source_file]["source_path"],
                            file_sha256=chunk.file_sha256, token_count=chunk.token_count,
                            document_sha256=hashlib.sha256(chunk.text.encode()).hexdigest(),
                            fingerprint=config_id) for chunk in part])
                    if progress is not None:
                        progress(dict(kind="stored_batch", message=f"Stored {len(part)} chunk records; index finalization pending"))
            if not reset:
                for start in range(0, len(stale_ids), 128):
                    self.collection.delete(ids=stale_ids[start:start + 128])
                    if progress is not None:
                        progress(dict(kind="pruned_batch", message=f"Removed {len(stale_ids[start:start + 128])} stale chunk records"))
            expected = {item for entry in files.values() for item in entry["chunk_ids"]}
            actual = set(self.collection.get(include=[])["ids"])
            if actual != expected:
                raise ValueError("stored chunk IDs do not match the synchronized sources")
            manifest = dict(schema_version=SCHEMA_VERSION, config=config, fingerprint=config_id, files=files)
            temp = self.manifest_path.with_suffix(".json.tmp")
            with temp.open("w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(self.manifest_path)
            self.pending_path.unlink()
        except Exception as exc:
            raise DeskError("Policy sync did not finish; partial index writes may exist. "
                            f"Run desk ingest --reset. {type(exc).__name__}: {exc}") from exc
