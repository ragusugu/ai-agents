"""Deterministic policy loading and original-text tokenizer-offset windows."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

from model import DeskError


@dataclass(frozen=True)
class PolicySource:
    name: str
    sha256: str
    text: str


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    source_file: str
    chunk_index: int
    file_sha256: str
    token_count: int
    text: str


def load_policies(directory, *, progress=None):
    directory = Path(directory)
    if not directory.exists():
        raise DeskError(f"Policy source does not exist: {directory}")
    if directory.is_file() and directory.suffix.lower() != ".md":
        raise DeskError("Policy ingest supports UTF-8 .md files or a folder of top-level .md files.")
    if not (directory.is_file() or directory.is_dir()):
        raise DeskError(f"Policy source is not a file or folder: {directory}")
    sources = []
    try:
        paths = ([directory] if directory.is_file() else
                 sorted((p for p in directory.iterdir() if p.suffix.lower() == ".md"), key=lambda item: item.name))
        for path in paths:
            if not path.is_file():
                continue
            raw = path.read_bytes()
            sources.append(PolicySource(path.name, hashlib.sha256(raw).hexdigest(), raw.decode("utf-8")))
            if progress is not None:
                progress(dict(kind="source_loaded", message=f"Read policy {path.name}", source=path.name))
    except (OSError, UnicodeError) as exc:
        raise DeskError(f"Cannot read UTF-8 policy {path}: {exc}") from exc
    return sources


def validate_chunk_options(tokenizer, chunk_size, overlap, max_tokens=512):
    budget = max_tokens - tokenizer.num_special_tokens_to_add(False)
    if not 0 < chunk_size <= budget:
        raise DeskError(f"Chunk size must be between 1 and {budget} content tokens.")
    if not 0 <= overlap < chunk_size:
        raise DeskError("Overlap must be nonnegative and smaller than chunk size.")


def chunk_policy(source, tokenizer, chunk_size=500, overlap=50, max_tokens=512):
    validate_chunk_options(tokenizer, chunk_size, overlap, max_tokens)
    encoded = tokenizer.encode(source.text, add_special_tokens=False)
    offsets = encoded.offsets
    if not offsets:
        return []
    chunks, start = [], 0
    while start < len(offsets):
        end = min(start + chunk_size, len(offsets))
        # Include whitespace around windows verbatim; middle windows start at
        # a tokenizer offset. Never decode WordPiece IDs into source prose.
        left = 0 if start == 0 else offsets[start][0]
        while end > start:
            right = len(source.text) if end == len(offsets) else offsets[end][0]
            text = source.text[left:right]
            count = len(tokenizer.encode(text, add_special_tokens=False).ids)
            if count <= chunk_size and len(tokenizer.encode(text).ids) <= max_tokens:
                break
            end -= 1
        if end <= start or (end < len(offsets) and end - start <= overlap):
            raise DeskError(f"Cannot make a safe tokenizer window for {source.name}; reduce overlap.")
        index = len(chunks) + 1
        chunks.append(PolicyChunk(f"{source.name}#{index}", source.name, index, source.sha256, count, text))
        if end == len(offsets):
            break
        start = end - overlap
    return chunks
