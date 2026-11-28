"""Naive top-k policy retrieval and citation-format checks; no verifier/rewriter."""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import re

from constants import RAG_REFUSAL
from model import DeskError
from .local_embeddings import DEFAULT_RAG_DB_DIR, configured_embeddings, project_path, validate_vectors
from .vector_store import PolicyStore, fingerprint_id, ingest_lock


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_file: str
    chunk_index: int
    score: float
    text: str


def retrieve_chunks(question, *, db_dir=None, top_k=None, embedder=None):
    if not question.strip():
        raise DeskError("The policy question must not be empty.")
    directory = project_path(db_dir or os.environ.get("DESK_RAG_DB_DIR", DEFAULT_RAG_DB_DIR))
    if not (directory / "desk-policies.json").is_file():
        raise DeskError(f"Policy index has not been built at {directory}. Run desk ingest <policy-file-or-folder> first, "
                        "or use desk ask --no-rag for the direct API path.")
    try:
        count = int(top_k if top_k is not None else os.environ.get("DESK_RAG_TOP_K", "4"))
        if count <= 0:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise DeskError("RAG top-k must be a positive integer.") from exc
    embedder = embedder if embedder is not None else configured_embeddings()
    embedder.prepare()
    try:
        with ingest_lock(directory):
            store = PolicyStore(directory)
            try:
                saved = json.loads(store.manifest_path.read_text(encoding="utf-8"))
                config = dict(saved["config"], embedding=embedder.fingerprint)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise DeskError("Policy manifest is invalid; run desk ingest --reset.") from exc
            files, records = store.inspect(config)
            expected = {item for entry in files.values() for item in entry["chunk_ids"]}
            if expected != set(records):
                raise DeskError("Policy index has missing or stale chunks; run desk ingest on the source to repair it.")
            if not records:
                return []
            vector = validate_vectors([embedder.embed_query(question)], 1, embedder.dimension)[0]
            result = store.collection.query(query_embeddings=[vector], n_results=min(count, len(records)),
                                             include=["documents", "metadatas", "distances"])
            chunks = []
            for chunk_id, document, metadata, distance in zip(result["ids"][0], result["documents"][0],
                    result["metadatas"][0], result["distances"][0]):
                if (chunk_id not in expected or not isinstance(document, str) or not isinstance(metadata, dict)
                        or metadata.get("fingerprint") != fingerprint_id(config)
                        or metadata.get("document_sha256") != hashlib.sha256(document.encode()).hexdigest()
                        or chunk_id != f"{metadata.get('source_file')}#{metadata.get('chunk_index')}"):
                    raise DeskError("Retrieved policy data is inconsistent; run desk ingest to repair it.")
                chunks.append(RetrievedChunk(chunk_id, metadata["source_file"], metadata["chunk_index"],
                                             float(1 - distance), document))
            return chunks
    except DeskError:
        raise
    except Exception as exc:
        raise DeskError(f"Local policy retrieval failed: {type(exc).__name__}: {exc}") from exc


def build_rag_prompt(question, chunks):
    # Encode delimiters in reference data so a policy cannot close the context block.
    context = json.dumps([dict(citation=f"[{chunk.chunk_id}]", text=chunk.text) for chunk in chunks], ensure_ascii=False)
    context = context.replace("<", "\\u003c").replace(">", "\\u003e")
    return f"<context>\n{context}\n</context>\nQuestion: {json.dumps(question, ensure_ascii=False)}"


def validate_citations(answer, chunks):
    """Formatting guard only; it cannot prove entailment or per-claim support."""
    answer = answer.strip()
    if answer == RAG_REFUSAL:
        return answer
    cited = set(re.findall(r"\[([^\[\]\r\n]+#\d+)\]", answer))
    allowed = {chunk.chunk_id for chunk in chunks}
    if not cited or not cited <= allowed:
        raise DeskError("The answer omitted citations or cited chunks outside the retrieved context. "
                        "No grounded answer could be confirmed; please try again.")
    return answer


def chunk_records(chunks):
    return [asdict(chunk) for chunk in chunks]
