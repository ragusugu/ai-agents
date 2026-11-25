"""Skill workflow: selected emails -> extraction -> local field report."""

import os
from pathlib import Path

from accuracy import DEFAULT_LABELS, ROOT, LabelSet, accuracy_report, label_source, load_labels, write_label_review
from batch import create_plan, execute_plan
from model import DeskError


def run_workflow(source, model, *, max_tokens=4000, output_dir=None, labels_path=None,
                 project_root=ROOT, plan_only=False, retry_review=False, expected_count=None,
                 require_reviewed=False, progress=None, extractor=None):
    """Preflight sources/labels, then process sequentially with the stored schema.

    Supplying a path to this workflow is an execution request. plan_only is the
    explicit offline option. An extractor can be injected for offline tests.
    """
    plan_path, plan = create_plan(source, model, output_dir=output_dir,
                                  expected_count=expected_count, retry_review=retry_review,
                                  max_tokens=max_tokens)
    labels = None
    explicit_labels = labels_path is not None
    candidate = Path(labels_path) if explicit_labels else Path(DEFAULT_LABELS)
    note = "No matching labels selected; extraction runs without an accuracy claim."
    if explicit_labels or candidate.exists():
        # Inspect declared membership before touching sources belonging to an
        # unrelated default label set (especially for an external email path).
        try:
            label_set = LabelSet.model_validate_json(candidate.read_text(encoding="utf-8"))
            declared = {os.path.normcase(str(label_source(label, project_root))) for label in label_set.labels}
        except (OSError, ValueError) as exc:
            raise DeskError(f"Cannot read label file: {candidate}") from exc
        selected = {os.path.normcase(entry["source"]["path"]) for entry in plan["sources"]}
        if declared <= selected:
            label_set = load_labels(candidate, project_root=project_root)
            labels = candidate
            reviewed = label_set.provenance.human_review.status == "approved"
            if require_reviewed and not reviewed:
                raise DeskError("Human label review is pending; no model calls made.")
            note = f"Evaluation: {len(label_set.labels)} {'human-reviewed' if reviewed else 'assistant-draft'} labels."
        elif explicit_labels:
            raise DeskError("Labels include emails outside the selected input; no model calls made.")
    if require_reviewed and labels is None:
        raise DeskError("Provide reviewed labels for the selected emails; no model calls made.")
    result = {"plan_path": plan_path, "plan": plan, "label_note": note,
              "manifest_path": None, "manifest": None, "report_path": None,
              "report": None, "review_path": None}
    if plan_only:
        return result
    manifest_path, manifest = execute_plan(plan_path, model, output_dir=output_dir,
        max_tokens=max_tokens, allow_provider_calls=True, progress=progress, extractor=extractor)
    result.update(manifest_path=manifest_path, manifest=manifest)
    if labels is not None:
        report_path, report = accuracy_report(labels, model=model, project_root=project_root,
            output_dir=plan["output_dir"], require_reviewed=require_reviewed)
        result.update(report_path=report_path, report=report)
        if report["label_provenance"]["human_review"]["status"] != "approved":
            result["review_path"] = write_label_review(labels, project_root=project_root)
    return result
