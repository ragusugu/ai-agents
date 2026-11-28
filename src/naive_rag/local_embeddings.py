"""In-process BGE document embeddings; no answer-provider or service calls."""

import hashlib
import importlib.metadata
import math
import os
from functools import lru_cache
from pathlib import Path

from model import DeskError
from constants import RAG_QUERY_INSTRUCTION

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_RAG_DB_DIR = "src/naive_rag/rag_db"
EXPORT_REPO = "Qdrant/bge-small-en-v1.5-onnx-Q"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def sha256_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_vectors(vectors, expected_count, dimension):
    """Reject malformed output before the first persistent write."""
    try:
        result = [[float(value) for value in vector] for vector in vectors]
        if len(result) != expected_count:
            raise ValueError("incorrect vector count")
        for vector in result:
            if len(vector) != dimension:
                raise ValueError(f"expected {dimension} dimensions")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("non-finite vector values")
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isfinite(norm) or norm <= 0:
                raise ValueError("invalid vector norm")
            # Persist normalized vectors even if a runtime returns slight drift.
            vector[:] = [value / norm for value in vector]
        return result
    except (TypeError, ValueError, OverflowError) as exc:
        raise DeskError(f"Invalid local embedding output: {exc}") from exc


class LocalEmbeddings:
    dimension = 384
    max_tokens = 512

    def __init__(self, *, model=DEFAULT_EMBED_MODEL, cache_dir=".desk/models",
                 threads=2, batch_size=8, offline=False):
        if model != DEFAULT_EMBED_MODEL:
            raise DeskError(f"Unsupported local embedding model: {model}. Use {DEFAULT_EMBED_MODEL}.")
        if threads <= 0 or batch_size <= 0:
            raise DeskError("Embedding threads and batch size must be positive integers.")
        self.model_name = model
        self.cache_dir = project_path(cache_dir)
        self.threads, self.batch_size, self.offline = threads, batch_size, offline
        self._runtime = None
        self._fingerprint = None
        self.tokenizer = None

    def prepare(self):
        if self._runtime is not None:
            return
        try:
            from fastembed import TextEmbedding
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise DeskError("Local embedding dependencies are missing; install requirements.txt in .venv.") from exc
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached = any(self.cache_dir.rglob("model_optimized.onnx"))
            runtime = TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir),
                                    threads=self.threads, providers=["CPUExecutionProvider"],
                                    local_files_only=self.offline or cached)
            # FastEmbed 0.9.1 exposes its ONNX adapter here. Keep access in this
            # boundary and fail clearly if a dependency upgrade changes it.
            native = runtime.model
            model_dir = Path(native._model_dir)
            if native.model.get_providers() != ["CPUExecutionProvider"]:
                raise ValueError("embedding execution is not CPU-only")
            tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
            tokenizer.no_truncation()
            tokenizer.no_padding()
            files = sorted(path for path in model_dir.rglob("*")
                           if path.is_file() and path.suffix in {".onnx", ".json", ".txt"})
            hashes = {path.relative_to(model_dir).as_posix(): sha256_file(path) for path in files}
            if "model_optimized.onnx" not in hashes or "tokenizer.json" not in hashes:
                raise ValueError("missing selected ONNX/tokenizer artifact")
            versions = {name: importlib.metadata.version(name) for name in
                        ("fastembed", "onnxruntime", "tokenizers", "numpy")}
            self._fingerprint = dict(provider="local-fastembed", model=self.model_name,
                export_repo=EXPORT_REPO, artifact_sha256=hashes, versions=versions,
                revision=(model_dir.name if model_dir.parent.name == "snapshots" else "artifact-sha256"),
                dimension=self.dimension, normalized=True, metric="cosine",
                tokenizer="bundled-wordpiece-offsets-v1", special_tokens=tokenizer.num_special_tokens_to_add(False),
                document_prefix="", query_instruction=RAG_QUERY_INSTRUCTION, max_tokens=self.max_tokens)
            self.tokenizer, self._runtime = tokenizer, runtime
        except Exception as exc:
            mode = "offline cache" if self.offline else "model cache/download or Windows runtime"
            raise DeskError(f"Cannot initialize local embeddings ({mode}); check {self.cache_dir} "
                            f"and requirements.txt. {type(exc).__name__}: {exc}") from exc

    @property
    def fingerprint(self):
        self.prepare()
        return self._fingerprint.copy()

    def embed_documents(self, texts):
        self.prepare()
        for text in texts:
            if not text.strip() or len(self.tokenizer.encode(text).ids) > self.max_tokens:
                raise DeskError("A document chunk is empty or exceeds the 512-token embedding budget.")
        try:
            vectors = self._runtime.embed(texts, batch_size=self.batch_size, parallel=None)
            return validate_vectors(vectors, len(texts), self.dimension)
        except DeskError:
            raise
        except Exception as exc:
            raise DeskError(f"Local embedding inference failed: {type(exc).__name__}: {exc}") from exc

    def embed_query(self, question):
        if not question.strip():
            raise DeskError("The policy question must not be empty.")
        # The document method validates the entire prefixed input, without truncation.
        return self.embed_documents([RAG_QUERY_INSTRUCTION + question.strip()])[0]


def configured_embeddings(*, model=None, cache_dir=None, threads=None, batch_size=None, offline=False):
    try:
        return _cached_embeddings(model or os.environ.get("DESK_EMBED_MODEL", DEFAULT_EMBED_MODEL),
            str(project_path(cache_dir or os.environ.get("DESK_EMBED_CACHE_DIR", ".desk/models"))),
            threads or int(os.environ.get("DESK_EMBED_THREADS", "2")),
            batch_size or int(os.environ.get("DESK_EMBED_BATCH_SIZE", "8")),
            offline or os.environ.get("DESK_EMBED_OFFLINE", "0") == "1")
    except ValueError as exc:
        raise DeskError("DESK_EMBED_THREADS and DESK_EMBED_BATCH_SIZE must be positive integers.") from exc


@lru_cache(maxsize=2)
def _cached_embeddings(model, cache_dir, threads, batch_size, offline):
    return LocalEmbeddings(model=model, cache_dir=cache_dir, threads=threads,
                           batch_size=batch_size, offline=offline)
