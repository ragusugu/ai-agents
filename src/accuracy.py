"""Deterministic, local field scoring. Draft agreement is NOT human-labelled accuracy."""

import hashlib
import json
import os
import re
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from extraction import OUTPUT_DIR, read_run_history, _write_record, extraction_fingerprint
from model import DeskError
from schemas import EmailRequest, ExtractionModel, Intent, LineItem, OrderRequest, RequestKind

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = ROOT / "evaluation" / "challenge3_labels.draft.json"


class ExpectedItem(LineItem):
    description_terms: list[list[str]] = Field(default_factory=list)


class ExpectedRequest(EmailRequest):
    description_terms: list[list[str]] = Field(min_length=1)


class ExpectedFields(ExtractionModel):
    customer: str | None
    contact: str | None
    intent: Intent
    primary_request_kind: RequestKind
    requested_date: date | None
    urgency: Literal["low", "normal", "high", "urgent"] | None
    purchase_authorized: bool | None
    line_items: list[ExpectedItem]
    requests: list[ExpectedRequest] = Field(min_length=1)


class Source(ExtractionModel):
    id: str
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Label(ExtractionModel):
    source: Source
    expected: ExpectedFields
    notes: str


class HumanReview(ExtractionModel):
    status: Literal["pending", "approved"]
    reviewer: str | None
    reviewed_on: date | None

    @model_validator(mode="after")
    def require_attestation(self) -> Self:
        if self.status == "approved" and (self.reviewer is None or self.reviewed_on is None):
            raise ValueError("Approved labels need an actual human reviewer and review date.")
        return self


class Provenance(ExtractionModel):
    kind: Literal["assistant_source_draft", "human"]
    author: str
    created_on: date
    method: str
    human_review: HumanReview


class LabelSet(ExtractionModel):
    version: Literal[1]
    provenance: Provenance
    labels: list[Label] = Field(min_length=1)


def label_source(label, project_root=ROOT):
    """Resolve a declared source; relative paths are based on the project root."""
    declared = Path(label.source.relative_path).expanduser()
    if ".." in declared.parts or declared.suffix.lower() not in {".txt", ".eml"}:
        raise ValueError("Label sources must explicitly name .txt/.eml emails without parent traversal.")
    source = (Path(project_root) / declared).resolve()
    if not declared.is_absolute() and not source.is_relative_to(Path(project_root).resolve()):
        raise ValueError("Relative label source escapes the project.")
    return source


def load_labels(path=DEFAULT_LABELS, *, project_root=ROOT):
    try:
        label_set = LabelSet.model_validate_json(Path(path).read_text(encoding="utf-8"))
        ids = [label.source.id for label in label_set.labels]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate source IDs in labels.")
        for label in label_set.labels:
            source = label_source(label, project_root)
            if source.stem != label.source.id or hashlib.sha256(source.read_bytes()).hexdigest() != label.source.sha256:
                raise ValueError("Label source ID/hash differs from the current email.")
            expected = label.expected
            if expected.requests[0].kind != expected.primary_request_kind or expected.requests[0].intent != expected.intent:
                raise ValueError("Label primary intent/kind disagrees with its first request.")
            # Validate the same local extraction policy; confidence is a placeholder,
            # never a ground-truth target or scored field.
            OrderRequest.model_validate_json(json.dumps({
                **expected.model_dump(mode="json", exclude={"primary_request_kind", "requests", "line_items"}),
                "confidence": 1.0,
                "primary_request": expected.requests[0].model_dump(exclude={"description_terms"}),
                "secondary_requests": [r.model_dump(exclude={"description_terms"}) for r in expected.requests[1:]],
                "line_items": [item.model_dump(exclude={"description_terms"}) for item in expected.line_items],
            }))
            for value in [*expected.line_items, *expected.requests]:
                if any(not group for group in value.description_terms):
                    raise ValueError("Description synonym groups cannot be empty.")
                if isinstance(value, ExpectedItem) and value.sku is None and not value.description_terms:
                    raise ValueError("Description-only items need identity concept groups.")
        return label_set
    except (OSError, ValueError) as exc:
        raise DeskError(f"Cannot use labels: {exc}") from exc


def normalize(value):
    return " ".join(re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value).casefold()).split())


def concepts_match(text, groups):
    normalized = " " + normalize(text or "") + " "
    return bool(groups) and all(any(" " + normalize(term) + " " in normalized for term in group) for group in groups)


def _pairs(expected, predicted, identity_score):
    """One-to-one weighted assignment: cardinality first, then exact-SKU priority.

    Rectangular Hungarian assignment with dummy unmatched columns. Polynomial,
    deterministic tie-breaking; one prediction cannot satisfy two expectations.
    """
    n, predicted_count = len(expected), len(predicted)
    if not n or not predicted_count:
        return {}
    scores = [[identity_score(e, p) for p in predicted] for e in expected]
    cardinality_weight = (max(max(row) for row in scores) + 1) * (n + 1)
    costs = [[-(cardinality_weight + score) if score > 0 else 0 for score in row] + [0] * n for row in scores]
    m = predicted_count + n
    u, v, owner, previous = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        owner[0], column = i, 0
        distance, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[column] = True
            row, delta, next_column = owner[column], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    value = costs[row - 1][j - 1] - u[row] - v[j]
                    if value < distance[j]:
                        distance[j], previous[j] = value, column
                    if distance[j] < delta:
                        delta, next_column = distance[j], j
            for j in range(m + 1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    distance[j] -= delta
            column = next_column
            if owner[column] == 0:
                break
        while column:
            earlier = previous[column]
            owner[column] = owner[earlier]
            column = earlier
    return {owner[j] - 1: j - 1 for j in range(1, predicted_count + 1)
            if owner[j] and scores[owner[j] - 1][j - 1] > 0}


def _unit(value):
    if value is None:
        return None
    text = normalize(value)
    return {"units": "unit", "selling units": "selling unit", "ea": "each"}.get(text, text)


def _equal(expected, actual, field):
    if expected is None or actual is None:
        return expected is None and actual is None
    if field == "quantity":
        return Decimal(str(expected)) == Decimal(str(actual))
    if field == "unit":
        return _unit(expected) == _unit(actual)
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().casefold() == actual.strip().casefold() if field == "sku" else normalize(expected) == normalize(actual)
    return type(expected) is type(actual) and expected == actual


def score_fields(expected, prediction):
    """A check is one field slot. Missing/review predictions get NO null-value credit."""
    checks = []
    available = prediction is not None
    def add(field, correct):
        checks.append({"field": field, "correct": bool(available and correct), "covered": available})
    for field in ("customer", "contact", "intent", "requested_date", "urgency", "purchase_authorized"):
        add(field, available and _equal(getattr(expected, field), getattr(prediction, field), field))
    add("primary_request.kind", available and expected.primary_request_kind == prediction.primary_request.kind)
    actual_items = prediction.line_items if available else []
    add("line_items.count", available and len(expected.line_items) == len(actual_items))
    def identity(e, p):
        if e.sku is not None and p.sku is not None and _equal(e.sku, p.sku, "sku"):
            return 2
        return int(concepts_match(p.description, e.description_terms))
    items = _pairs(expected.line_items, actual_items, identity)
    for index, item in enumerate(expected.line_items):
        predicted = actual_items[items[index]] if index in items else None
        for field in ("sku", "quantity", "unit"):
            add("line_items." + field, predicted is not None and _equal(getattr(item, field), getattr(predicted, field), field))
        if item.description_terms:
            add("line_items.description", predicted is not None and concepts_match(predicted.description, item.description_terms))
    for _ in set(range(len(actual_items))) - set(items.values()):
        add("line_items.extra", False)
    actual_requests = [prediction.primary_request, *prediction.secondary_requests] if available else []
    matched = _pairs(expected.requests, actual_requests,
                     lambda e, p: int(e.kind == p.kind and concepts_match(p.description, e.description_terms)))
    for index in range(len(expected.requests)):
        add("requests.present", index in matched)
    for _ in set(range(len(actual_requests))) - set(matched.values()):
        add("requests.extra", False)
    return checks


def select_output(label_set, model, *, output_dir=None, project_root=ROOT,
                  allow_historical=False, config_id=None):
    """Select one coherent run/config, never silently mix old and current policy."""
    if allow_historical and output_dir is None:
        raise DeskError("Historical scoring requires an explicit --output-dir.")
    current = extraction_fingerprint()
    wanted = {(os.path.normcase(str(label_source(label, project_root))), label.source.sha256)
              for label in label_set.labels}
    root = Path(OUTPUT_DIR).resolve()
    directories = ([Path(output_dir).expanduser().resolve()] if output_dir is not None else
                   [root, *sorted(p for p in root.iterdir() if p.is_dir())] if root.exists() else [root])
    eligible = []
    for directory in directories:
        if not (directory / "source-map.jsonl").is_file():
            continue
        if (directory / ".batch.lock").exists() or (directory / ".results.jsonl.lock").exists():
            raise DeskError(f"Output is being written; wait before scoring: {directory}")
        _, rows = read_run_history(directory)
        groups = {}
        for row in rows:
            if row["model"] != model or (config_id is not None and row["config_id"] != config_id):
                continue
            compatible = all(row.get(key) == value for key, value in current.items())
            if not compatible and not allow_historical:
                continue
            groups.setdefault(row["config_id"], []).append(row)
        groups = {key: group for key, group in groups.items() if any(
            (os.path.normcase(row["source"]["path"]), row["source"]["sha256"]) in wanted for row in group)}
        if len(groups) > 1:
            raise DeskError(f"Multiple extraction configurations in {directory}; select --config explicitly.")
        if groups:
            selected, group = next(iter(groups.items()))
            eligible.append(((directory / "source-map.jsonl").stat().st_mtime_ns, directory, selected, group))
    if not eligible:
        raise DeskError("No matching current verified output for these labels/model. Select an output run with --output-dir; "
                        "old runs require explicit --allow-historical. No extraction was started.")
    eligible.sort(key=lambda value: value[0], reverse=True)
    if len(eligible) > 1 and eligible[0][0] == eligible[1][0]:
        raise DeskError("Latest output run is ambiguous; select --output-dir explicitly.")
    _, directory, selected, rows = eligible[0]
    saved = {key: rows[0].get(key) for key in current}
    return directory, selected, rows, saved


def accuracy_report(labels_path=DEFAULT_LABELS, *, results_path=None, model, project_root=ROOT,
                    output_dir=None, require_reviewed=False, allow_historical=False, config_id=None):
    label_set = load_labels(labels_path, project_root=project_root)
    reviewed = label_set.provenance.human_review.status == "approved"
    if require_reviewed and not reviewed:
        raise DeskError("Labels are assistant drafts; a human must review/approve them before an accuracy claim.")
    output, selected_config, rows, fingerprint = select_output(
        label_set, model, output_dir=output_dir, project_root=project_root,
        allow_historical=allow_historical, config_id=config_id)
    if results_path is not None and Path(results_path).resolve() != output / "results.jsonl":
        raise DeskError("Scoring requires the clean results file and its adjacent minimal tracking/config files.")
    coverage = {"labels": len(label_set.labels), "validated": 0, "needs_review": 0,
                "missing": 0, "invalid_output": 0, "legacy_prompt_unknown": 0}
    metrics, details = {}, []
    for label in label_set.labels:
        wanted = os.path.normcase(str(label_source(label, project_root)))
        matching = [row for row in rows if row.get("model") == model and
                    os.path.normcase(row.get("source", {}).get("path", "")) == wanted and
                    row.get("source", {}).get("sha256") == label.source.sha256 and
                    row.get("config_id") == selected_config]
        record = matching[-1] if matching else None  # Latest compatible run; never cherry-pick success.
        prediction, status = None, "missing"
        if record is not None:
            status = "needs_review" if record.get("status") == "needs_review" else "invalid_output"
            if record.get("status") == "validated":
                try:
                    prediction = OrderRequest.model_validate_json(json.dumps(record.get("data")))
                    status = "validated"
                except ValidationError:
                    pass
            if record.get("prompt_sha256") is None:
                coverage["legacy_prompt_unknown"] += 1
        coverage[status] += 1
        checks = score_fields(label.expected, prediction)
        for check in checks:
            metric = metrics.setdefault(check["field"], {"correct": 0, "total": 0, "covered_total": 0})
            metric["total"] += 1
            metric["correct"] += int(check["correct"])
            metric["covered_total"] += int(check["covered"])
        details.append({"source_id": label.source.id, "status": status,
                        "run_id": record.get("run_id") if record else None,
                        "output_line": record.get("result_line") if record else None,
                        "incorrect_fields": [c["field"] for c in checks if not c["correct"]]})
    correct = sum(m["correct"] for m in metrics.values())
    total = sum(m["total"] for m in metrics.values())
    for metric in metrics.values():
        metric["score"] = metric["correct"] / metric["total"] if coverage["validated"] else None
        metric["score_on_validated"] = metric["correct"] / metric["covered_total"] if metric["covered_total"] else None
    report = {"report_version": 1, "model": model, "fingerprint": fingerprint,
              "current_fingerprint": extraction_fingerprint(), "output_dir": str(output),
              "selected_config": selected_config, "historical": fingerprint != extraction_fingerprint(),
              "labels_path": str(Path(labels_path).resolve()),
              "labels_sha256": hashlib.sha256(Path(labels_path).read_bytes()).hexdigest(),
              "label_provenance": label_set.provenance.model_dump(mode="json"),
              "measurement_kind": "human_reviewed_field_accuracy" if reviewed else "assistant_draft_agreement",
              "coverage": coverage, "results_rows_read": len(rows), "fields": metrics,
              "overall": {"correct": correct, "total": total,
                          "score": correct / total if coverage["validated"] else None},
              "emails": details,
              "limitations": ["Confidence is not scored as accuracy.",
                              "Description checks use explicit concept/synonym groups, not full semantic equivalence.",
                              "Missing/review/invalid outputs remain in field denominators; no null-value credit.",
                              "One output directory and configuration are scored; historical selection is explicit.",
                              "Historical scores do not establish success under the current verifier/policy."]}
    output.mkdir(parents=True, exist_ok=True)
    path = output / "accuracy-report.json"
    _write_record(path, report)
    return path, report


def write_label_review(labels_path=DEFAULT_LABELS, *, project_root=ROOT, destination=None):
    """A source-linked human review checklist; never changes approval status."""
    labels = load_labels(labels_path, project_root=project_root)
    path = Path(destination) if destination else Path(labels_path).with_name("challenge3_labels_review.md")
    origin = "Assistant-drafted" if labels.provenance.kind == "assistant_source_draft" else "Human-authored"
    lines = [f"# Challenge 3 — review the {len(labels.labels)} labels", "",
             f"{origin} annotations. Recorded review status: {labels.provenance.human_review.status}.",
             "Check every label against its source email before approving ground truth.",
             "Read each source, correct the draft JSON and synonyms, then record an actual",
             "reviewer/date and approved status in provenance.human_review after all labels",
             "are checked. Checkboxes here do not automatically approve ground truth.", ""]
    for label in labels.labels:
        expected = label.expected
        source = label_source(label, project_root).as_posix()
        lines += [f"## {label.source.id}", "", f"[Open source email](<{source}>)", "",
                  f"Customer: {expected.customer}; contact: {expected.contact}.",
                  f"Intent: {expected.intent}; primary: {expected.primary_request_kind}; purchase authorized: {expected.purchase_authorized}.",
                  f"Requested date: {expected.requested_date}; urgency: {expected.urgency}.", ""]
        if expected.line_items:
            lines += ["| SKU | Description | Quantity | Unit |", "| --- | --- | ---: | --- |"]
            for item in expected.line_items:
                lines.append(f"| {item.sku or 'null'} | {item.description or 'not supplied'} | {item.quantity if item.quantity is not None else 'null'} | {item.unit or 'null'} |")
        else:
            lines.append("Line items: none identifiable from the email.")
        lines += ["", "Requests:"]
        for request in expected.requests:
            lines.append(f"- {request.kind}: {request.description}")
        lines += ["", f"Ambiguity/review note: {label.notes}", "", "- [ ] Human checked against the source and corrected the draft JSON if needed.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
