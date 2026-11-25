"""Sequential email extraction with resumable outcomes and optional offline plans."""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from extraction import (OUTPUT_DIR, _read_email, read_run_history, _reserve_output,
                        _write_record, append_result, extract_email, extraction_fingerprint, rebuild_outputs)
from model import DeskError
from schemas import OrderRequest


def provider_target(model):
    if not model:
        raise DeskError("Set DESK_MODEL or pass --model before planning a batch.")
    if os.environ.get("AWS_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL_BEDROCK_RUNTIME"):
        raise DeskError("An AWS endpoint override is set; review the actual destination before batch planning.")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    if not re.fullmatch(r"[a-z0-9-]+", region):
        raise DeskError("Invalid AWS region for batch destination.")
    domain = "amazonaws.com.cn" if region.startswith("cn-") else "amazonaws.com"
    return {"provider": "Amazon Bedrock", "model": model, "region": region,
            "endpoint": f"https://bedrock-runtime.{region}.{domain}"}


def _snapshot(path):
    result = {"path": str(path.resolve()), "id": path.stem, "sha256": None,
              "bytes": None, "input_error": None}
    try:
        result["bytes"] = path.stat().st_size
        with path.open("rb") as handle:
            result["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        _read_email(path)
    except (DeskError, OSError) as exc:
        result["input_error"] = type(exc).__name__ + ": invalid or unreadable email"
    return result


def reusable_record(rows, source, model, fingerprint):
    """Latest outcome with the complete current extraction/verifier contract."""
    for row in reversed(rows):
        saved = row.get("source", {})
        if (os.path.normcase(saved.get("path", "")) != os.path.normcase(source["path"]) or not source["sha256"] or
                saved.get("sha256") != source["sha256"] or row.get("model") != model or
                any(row.get(key) != value for key, value in fingerprint.items()) or
                row.get("status") not in {"validated", "needs_review"}):
            continue
        result = dict(row)
        if result["status"] == "validated":
            try:
                OrderRequest.model_validate_json(json.dumps(result.get("data")))
            except ValidationError:
                # Local constraints can tighten without changing the provider
                # schema. A fresh run must produce a persisted current outcome.
                return None
        return result
    return None


def _email_files(source_path):
    """An explicit file or a flat folder containing only the selected emails."""
    source_path = Path(source_path).expanduser().resolve()
    if source_path.is_file() and source_path.suffix.lower() in {".txt", ".eml"}:
        return [source_path]
    if not source_path.is_dir():
        raise DeskError("Input must be an existing .txt/.eml email or an email folder.")
    files = sorted((p for p in source_path.iterdir() if p.is_file() and p.suffix.lower() in {".txt", ".eml"}),
                   key=lambda p: (p.name.casefold(), p.name))
    if any(not p.resolve().is_relative_to(source_path) for p in files):
        raise DeskError("Batch inputs must stay inside the selected directory (no external symlinks).")
    if len({p.stem.casefold() for p in files}) != len(files):
        raise DeskError("Email filenames must have unique IDs (stems), including across .txt and .eml files.")
    return files


def create_plan(directory, model, *, output_dir=None, expected_count=None, retry_review=False, max_tokens=4000):
    """Read local files/results only. Never creates a provider client."""
    selected = Path(directory).expanduser().resolve()
    files = _email_files(selected)
    directory = selected.parent if selected.is_file() else selected
    output = Path(OUTPUT_DIR if output_dir is None else output_dir).resolve()
    if type(max_tokens) is not int or max_tokens <= 0:
        raise DeskError("Batch max_tokens must be a positive integer.")
    if expected_count is not None and (type(expected_count) is not int or expected_count <= 0):
        raise DeskError("Expected email count must be a positive integer.")
    if not files or (expected_count is not None and len(files) != expected_count):
        raise DeskError(f"Expected {expected_count or 'at least one'} email files; found {len(files)}.")
    target = provider_target(model)
    fingerprint = extraction_fingerprint()
    _, rows = read_run_history(output)
    entries = []
    for path in files:
        source = _snapshot(path)
        previous = reusable_record(rows, source, model, fingerprint)
        action = "review_input" if source["input_error"] else "run"
        if previous is not None and not (retry_review and previous["status"] == "needs_review"):
            action = "reuse"
        entries.append({"source": source, "action": action,
                        "reuse_run_id": previous.get("run_id") if previous else None,
                        "reuse_status": previous.get("status") if previous else None,
                        "legacy_prompt_unknown": bool(previous and not previous.get("prompt_sha256"))})
    sends = [entry for entry in entries if entry["action"] == "run"]
    plan = {"version": 1, "batch_id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "plan_only", "input_dir": str(directory), "output_dir": str(output),
            "input_file": str(selected) if selected.is_file() else None,
            "max_tokens": max_tokens, "expected_count": expected_count,
            "target": target, "fingerprint": fingerprint, "retry_review": retry_review,
            "source_count": len(entries), "new_email_payloads": len(sends),
            "reused_count": sum(e["action"] == "reuse" for e in entries),
            "input_review_count": sum(e["action"] == "review_input" for e in entries),
            "new_payload_bytes": sum(entry["source"]["bytes"] for entry in sends),
            "max_response_requests": len(sends) * 6, "max_transport_attempts": len(sends) * 18,
            "sources": entries}
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"batch-plan-{plan['batch_id']}.json"
    _write_record(path, plan)
    return path, plan


def _review(source, model, fingerprint, reason, *, code, output, uncertain=False):
    record = {"record_version": 1, "schema_version": 1, "run_id": uuid4().hex,
              **fingerprint, "source": {"path": source["path"], "sha256": source["sha256"]},
              "model": model, "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "needs_review", "reason": reason, "data": None, "attempts": [],
              "responses_received": None if uncertain else 0, "repair_requests": 0,
              "transport_attempts": None if uncertain else 0,
              "provider_error": {"code": code, "message": reason}, "execution_uncertain": uncertain}
    _reserve_output(Path(source["path"]), output, record)
    append_result(record, output_dir=output)
    return record


def _validated_plan(plan_path, model, output, max_tokens):
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        entries = plan["sources"]
        directory = Path(plan["input_dir"]).resolve()
        if (plan["version"] != 1 or plan["mode"] != "plan_only" or
                plan["target"] != provider_target(model) or plan["fingerprint"] != extraction_fingerprint() or
                Path(plan["output_dir"]).resolve() != output or type(plan["retry_review"]) is not bool or
                type(plan["max_tokens"]) is not int or plan["max_tokens"] <= 0 or
                (max_tokens is not None and plan["max_tokens"] != max_tokens) or
                len(entries) != plan["source_count"] or not entries):
            raise ValueError("Plan configuration differs.")
        paths = [entry["source"]["path"] for entry in entries]
        if len(set(paths)) != len(paths) or len({entry["source"]["id"] for entry in entries}) != len(entries):
            raise ValueError("Duplicate source in plan.")
        selected = Path(plan.get("input_file") or directory).resolve()
        if plan.get("input_file") and selected.parent != directory:
            raise ValueError("Selected email differs from its directory.")
        current_files = sorted(str(p.resolve()) for p in _email_files(selected))
        if sorted(paths) != current_files:
            raise ValueError("Source set changed.")
        if plan["expected_count"] is not None:
            if type(plan["expected_count"]) is not int or len(paths) != plan["expected_count"]:
                raise ValueError("Incomplete expected email set.")
        for entry in entries:
            source = Path(entry["source"]["path"])
            if (source.resolve().parent != directory or source.suffix.lower() not in {".txt", ".eml"} or
                    source.stem != entry["source"]["id"] or _snapshot(source) != entry["source"] or
                    entry["action"] not in {"run", "reuse", "review_input"}):
                raise ValueError("Source changed.")
        sends = [e for e in entries if e["action"] == "run"]
        if (plan["new_email_payloads"] != len(sends) or
                plan["new_payload_bytes"] != sum(e["source"]["bytes"] for e in sends) or
                plan["max_response_requests"] != len(sends) * 6 or plan["max_transport_attempts"] != len(sends) * 18):
            raise ValueError("Planned bounds differ.")
        return plan
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DeskError("Plan, source set, destination or configuration changed; regenerate/review before any send.") from exc


def _recover_failed_email(output, source, model, fingerprint, before_ids):
    pending = list((output / "pending").glob("*.json"))
    for path in pending:
        value = json.loads(path.read_text(encoding="utf-8"))
        saved = value["source"]
        source_path = (Path(__file__).resolve().parents[1] / saved["path"]).resolve()
        if str(source_path) != source["path"] or saved["sha256"] != source["sha256"]:
            raise DeskError("Another pending run exists; automatic batch recovery stopped.")
    if pending:
        rebuild_outputs(output_dir=output)
    _, rows = read_run_history(output)
    current = reusable_record(rows, source, model, fingerprint)
    return current if current and current["run_id"] not in before_ids else None


def execute_plan(plan_path, model, *, output_dir=None, extractor=None, allow_provider_calls=False, max_tokens=None, progress=None):
    """Execute an explicitly requested workflow. Tests inject fake provider I/O."""
    if extractor is None and not allow_provider_calls:
        raise DeskError("Provider calls are disabled; review/approve the concrete plan before execution.")
    output = Path(OUTPUT_DIR if output_dir is None else output_dir).resolve()
    plan = _validated_plan(plan_path, model, output, max_tokens)
    extractor = extract_email if extractor is None else extractor
    manifest = {"batch_id": plan["batch_id"], "plan_sha256": hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
                "target": plan["target"], "sources": [], "status": "running"}
    manifest_path = output / f"batch-run-{plan['batch_id']}-{uuid4().hex}.json"
    lock = output / ".batch.lock"
    locked = False
    blocked = None
    counts = {"reused": 0, "newly_validated": 0, "needs_review": 0}
    def notify(kind, **extra):
        if progress is not None:
            progress({"kind": kind, "completed": sum(counts.values()), "total": plan["source_count"],
                      "counts": dict(counts), **extra})
    try:
        with lock.open("x", encoding="utf-8"):
            locked = True
        _write_record(manifest_path, manifest)
        for entry in plan["sources"]:
            source = entry["source"]
            _, rows = read_run_history(output)
            existing = reusable_record(rows, source, model, plan["fingerprint"])
            retry_selected_review = (existing and plan["retry_review"] and existing["status"] == "needs_review"
                                     and existing["run_id"] == entry["reuse_run_id"])
            action = entry["action"]
            if existing and not retry_selected_review:
                record, action = existing, "reused"
            elif entry["action"] == "reuse" and existing is None:
                action = "reviewed_without_send"
                record = _review(source, model, plan["fingerprint"], "planned_resume_record_missing", code="ResumeMissing", output=output)
            elif blocked or source["input_error"] or _snapshot(Path(source["path"])) != source:
                reason = "batch_provider_blocked" if blocked else "input_error" if source["input_error"] else "source_changed_after_plan"
                action = "reviewed_without_send"
                record = _review(source, model, plan["fingerprint"], reason, code=blocked or "InvalidInput", output=output)
            else:
                before_ids = {row["run_id"] for row in rows}
                try:
                    _, record = extractor(source["path"], model, output_dir=output, max_tokens=plan["max_tokens"],
                                          expected_source_sha256=source["sha256"], expected_endpoint=plan["target"]["endpoint"])
                except Exception as exc:
                    record = _recover_failed_email(output, source, model, plan["fingerprint"], before_ids)
                    if record is None:
                        record = _review(source, model, plan["fingerprint"], "batch_execution_error",
                                         code=type(exc).__name__, output=output, uncertain=True)
                    action = "recovered_or_reviewed"
                # An extractor cannot claim success without a persisted source-associated outcome.
                _, persisted = read_run_history(output)
                saved = next((r for r in persisted if r["run_id"] == record["run_id"]), None)
                if (saved is None or os.path.normcase(saved["source"]["path"]) != os.path.normcase(source["path"]) or
                        saved["source"]["sha256"] != source["sha256"] or saved["model"] != model or
                        saved["status"] != record["status"] or any(saved.get(key) != value for key, value in plan["fingerprint"].items())):
                    raise DeskError("Extractor did not persist a matching outcome; batch stopped before further sends.")
                error_code = (record.get("provider_error") or {}).get("code")
                if record.get("reason") == "capability_error" or error_code in {
                    "AccessDeniedException", "UnrecognizedClientException", "NoCredentialsError",
                    "InvalidSignatureException", "DestinationMismatch",
                }:
                    blocked = error_code or "CapabilityError"
            # Completion is emitted only AFTER both persisted outcome and manifest are verified.
            _, outcomes = read_run_history(output)
            if not any(row["run_id"] == record["run_id"] and row["status"] == record["status"] for row in outcomes):
                raise DeskError("Outcome was not persisted; refusing to publish completion.")
            manifest["sources"].append({"id": source["id"], "action": action,
                                        "status": record["status"], "run_id": record.get("run_id"),
                                        "reason": record.get("reason")})
            _write_record(manifest_path, manifest)
            bucket = "needs_review" if record["status"] == "needs_review" else "reused" if action == "reused" else "newly_validated"
            counts[bucket] += 1
            notify("email_complete", source_id=source["id"], action=action, status=record["status"])
        manifest["status"] = "complete" if all(e["status"] == "validated" for e in manifest["sources"]) else "complete_with_review"
        _write_record(manifest_path, manifest)
        notify("batch_complete", status=manifest["status"])
        return manifest_path, manifest
    except (DeskError, OSError) as exc:
        if locked:
            done = len(manifest["sources"])
            manifest.update(status="storage_or_execution_blocked", unprocessed=[e["source"]["id"] for e in plan["sources"][done:]])
            _write_record(manifest_path, manifest)
            notify("batch_blocked", status=manifest["status"], unprocessed=len(manifest["unprocessed"]))
        raise DeskError(f"Batch stopped; inspect {manifest_path}. No further sends attempted.") from exc
    finally:
        if locked:
            lock.unlink(missing_ok=True)
