"""Small JSONL email-to-result map; extracted payloads stay in results.jsonl."""

import json
import os
import re
import tempfile
from pathlib import Path

from model import DeskError

MAP_NAME = "source-map.jsonl"
FIELDS = {"run_id", "source", "config", "status", "line", "sha256"}


def validate_entries(entries):
    ids, lines = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise DeskError("Source map contains unknown or missing fields.")
        identifier = entry["run_id"]
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise DeskError("Source map contains duplicate/invalid run IDs.")
        ids.add(identifier)
        source = entry["source"]
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str):
            raise DeskError("Invalid email source association.")
        if source["sha256"] is not None and (not isinstance(source["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
            raise DeskError("Invalid source checksum in source map.")
        if (not isinstance(entry["status"], str) or entry["status"] not in {"validated", "needs_review"} or type(entry["line"]) is not int or entry["line"] < 1 or
                any(not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key]) for key in ("config", "sha256"))):
            raise DeskError("Invalid source-map outcome/configuration/checksum.")
        position = (entry["status"], entry["line"])
        if position in lines:
            raise DeskError("Two source-map entries reference the same output line.")
        lines.add(position)
    return entries


def read_entries(directory):
    path = Path(directory) / MAP_NAME
    if not path.exists():
        return []
    try:
        return validate_entries([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()])
    except (OSError, ValueError) as exc:
        raise DeskError("Source map is corrupt/unreadable; no data was replaced.") from exc


def _write_entries(path, entries):
    """Caller holds the output writer lock; replace the complete map atomically."""
    validate_entries(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def insert_entry(directory, entry):
    validate_entries([entry])
    directory = Path(directory)
    current = read_entries(directory)
    match = next((value for value in current if value["run_id"] == entry["run_id"]), None)
    if match is not None:
        if match != entry:
            raise DeskError("This run ID already has a different email-to-result mapping.")
        return
    try:
        _write_entries(directory / MAP_NAME, [*current, entry])
        if read_entries(directory) != [*current, entry]:
            raise DeskError("Source-map write verification failed; inspect the pending commit.")
    except (OSError, ValueError) as exc:
        raise DeskError("Source-map write failed; previous mapping and pending recovery were preserved.") from exc
