"""Challenge 3 acceptance checks using synthetic sources and mocked Bedrock I/O."""

import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from challenges.challenge3.test_structured_output import (
    EMAIL, MODEL, FakeClient, OfflineFixture, candidate, ledger, native_response,
)

from challenge3_structured_output import accuracy
from challenge3_structured_output import batch
from challenge3_structured_output import extraction
from challenge3_structured_output import grounding
import model
import desk
from challenge3_structured_output import source_map
from challenge3_structured_output import structured_output
from botocore.exceptions import ClientError
from pydantic import ValidationError
from schemas import OrderRequest, bedrock_schema


def expected_fields(value=None):
    value = copy.deepcopy(candidate() if value is None else value)
    value.pop("confidence")
    value["line_items"] = [dict(item, description_terms=[["steel"], ["clips"]])
                           for item in value["line_items"]]
    return accuracy.ExpectedFields.model_validate_json(json.dumps(value))


class SchemaTests(unittest.TestCase):
    def test_numeric_types_bounds_and_unknown_keys(self):
        for quantity in ["7", "seven", True, 0, -1, float("nan"), float("inf")]:
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                value = candidate()
                value["line_items"][0]["quantity"] = quantity
                OrderRequest.model_validate_json(json.dumps(value))
        for confidence in [-0.1, 1.1, True, "0.8", float("nan"), float("inf")]:
            with self.subTest(confidence=confidence), self.assertRaises(ValidationError):
                value = candidate(); value["confidence"] = confidence
                OrderRequest.model_validate_json(json.dumps(value))
        for change in [dict(unexpected="extra"), dict(requested_date="2026-02-30"), dict(urgency="ASAP")]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                OrderRequest.model_validate_json(json.dumps({**candidate(), **change}))

    def test_missing_product_identity_and_order_number_are_rejected(self):
        for item in [dict(sku=None, description=None), dict(sku="MS-10001", description="order reference")]:
            with self.subTest(item=item), self.assertRaises(ValidationError):
                value = candidate(); value["line_items"] = [item]
                OrderRequest.model_validate_json(json.dumps(value))

    def test_exact_six_field_contract_and_primary_intent_policy(self):
        expected = {"customer", "intent", "line_items", "requested_date", "urgency", "confidence"}
        self.assertEqual(set(OrderRequest.model_fields), expected)
        self.assertEqual(set(bedrock_schema()["properties"]), expected)
        self.assertIn("return, complaint, order, status, other", OrderRequest.model_json_schema()["properties"]["intent"]["description"])
        for intent in ["order", "status", "complaint", "return", "other"]:
            value = candidate(); value["intent"] = intent
            self.assertEqual(OrderRequest.model_validate_json(json.dumps(value)).intent, intent)
        for field, extra in [("contact", "Lee Vale"), ("primary_request", {}),
                             ("secondary_requests", []), ("purchase_authorized", False)]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                OrderRequest.model_validate_json(json.dumps({**candidate(), field: extra}))

    def test_native_schema_requires_all_fields_and_retains_local_constraints(self):
        schema = bedrock_schema()
        def check(node):
            if isinstance(node, list):
                for child in node: check(child)
            elif isinstance(node, dict):
                self.assertFalse(set(node) & {"minimum", "maximum", "exclusiveMinimum", "minLength", "default"})
                if node.get("type") == "object":
                    self.assertFalse(node["additionalProperties"])
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for child in node.values(): check(child)
        check(schema)


class ScoringTests(unittest.TestCase):
    def test_legacy_label_metadata_is_ignored_by_six_field_scoring(self):
        value = expected_fields().model_dump(mode="json")
        value.update(contact="Old contact", primary_request_kind="quote", purchase_authorized=False,
                     requests=[dict(kind="quote", description="Old request metadata")])
        expected = accuracy.ExpectedFields.model_validate_json(json.dumps(value))
        checks = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(candidate())))
        self.assertTrue(all(check["correct"] for check in checks))
        self.assertFalse(any(check["field"].startswith(("contact", "requests", "primary_request", "purchase_authorized")) for check in checks))

    def test_missing_prediction_has_no_null_credit_and_confidence_is_not_scored(self):
        expected = expected_fields()
        self.assertTrue(all(not c["correct"] for c in accuracy.score_fields(expected, None)))
        low = candidate(); low["confidence"] = 0
        high = candidate(); high["confidence"] = 1
        left = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(low)))
        right = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(high)))
        self.assertEqual(left, right)
        self.assertTrue(all(c["correct"] for c in left))

    def test_reordered_repeated_sku_lines_keep_identical_scores(self):
        value = candidate()
        value["line_items"].append({**value["line_items"][0], "quantity": 12, "unit": "box"})
        expected = expected_fields(value)
        correct = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(value)))
        value["line_items"].reverse()
        reversed_scores = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(value)))
        self.assertTrue(all(c["correct"] for c in correct))
        self.assertEqual(correct, reversed_scores)

    def test_one_prediction_cannot_cover_two_lines_and_extras_are_penalized(self):
        value = candidate()
        expected = expected_fields(value)
        value["line_items"].append({**value["line_items"][0], "quantity": 12})
        scores = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(value)))
        self.assertIn({"field": "line_items.extra", "correct": False, "covered": True}, scores)
        expected = expected_fields(value)
        scores = accuracy.score_fields(expected, OrderRequest.model_validate_json(json.dumps(candidate())))
        self.assertEqual(sum(c["correct"] for c in scores if c["field"] == "line_items.quantity"), 1)


class ProviderTests(unittest.TestCase):
    def client(self, effect):
        from unittest.mock import Mock
        return SimpleNamespace(meta=SimpleNamespace(service_model=SimpleNamespace(
            operation_model=lambda _: SimpleNamespace(input_shape=SimpleNamespace(members={"outputConfig": 1})))),
            converse=Mock(side_effect=effect))

    def test_native_request_and_transport_retry_bounds(self):
        throttle = ClientError({"Error": {"Code": "ThrottlingException", "Message": "test"}}, "Converse")
        client = self.client([throttle, throttle, {"output": {"message": {"content": [{"text": "{}"}]}},
                                                  "stopReason": "end_turn"}])
        with patch.object(model.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            response = model.call_structured_model(client, MODEL, [], bedrock_schema(), 4000, "extract")
        self.assertEqual((response["transport_attempts"], client.converse.call_count), (3, 3))
        self.assertEqual(client.converse.call_args.kwargs["outputConfig"]["textFormat"]["type"], "json_schema")
        client = self.client(throttle)
        with patch.object(model.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(model.StructuredRequestError) as caught:
                model.call_structured_model(client, MODEL, [], bedrock_schema(), 4000, "extract")
        self.assertEqual((caught.exception.attempts, client.converse.call_count), (3, 3))

    def test_unsupported_schema_is_reviewable_without_prompt_fallback(self):
        error = ClientError({"Error": {"Code": "ValidationException", "Message": "unsupported"}}, "Converse")
        client = self.client(error)
        with self.assertRaises(model.StructuredRequestError) as caught:
            model.call_structured_model(client, MODEL, [], bedrock_schema(), 4000, "extract")
        self.assertEqual((caught.exception.category, client.converse.call_count), ("capability_error", 1))


class WorkflowTests(OfflineFixture, unittest.TestCase):
    def test_extra_output_fields_are_repaired_and_never_saved(self):
        value = candidate(); value["contact"] = "Lee Vale"
        record, calls, checks = self.run_extraction([value, candidate()])
        self.assertEqual((record["status"], record["repair_requests"], len(calls), len(checks)), ("validated", 1, 2, 1))
        payload = json.loads((self.base / "out/results.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"customer", "intent", "line_items", "requested_date", "urgency", "confidence"})
        self.assertIn("extra_forbidden", str(calls[1]["validation_errors"]))
        self.assertTrue(all(not path.startswith("/contact") for path in checks[0]["required_paths"]))

    def test_historical_rich_output_scores_only_the_explicit_core_subset(self):
        out = self.base / "legacy-rich"
        value = candidate(); value.update(contact="Lee Vale", primary_request={}, secondary_requests=[], purchase_authorized=False)
        source = batch._snapshot(self.email)
        record = dict(run_id="old-rich-output", model=MODEL, source=source, schema_sha256="a" * 64, prompt_sha256="b" * 64)
        config = extraction._config(record, out)
        entry = dict(run_id=record["run_id"], source=extraction._source_ref(source), config=config,
                     status="validated", sha256=extraction._payload_hash(value))
        extraction._commit(out, entry, value)
        _, report = accuracy.accuracy_report(self.labels([self.email]), model=MODEL, output_dir=out, allow_historical=True)
        self.assertTrue(report["historical"])
        self.assertEqual(report["coverage"]["validated"], 1)
        self.assertEqual(report["overall"]["score"], 1)
        self.assertNotIn("contact", report["fields"])
        self.assertEqual(json.loads((out / "results.jsonl").read_text())["contact"], "Lee Vale")

    def test_validation_command_and_saved_chat_end_with_accuracy(self):
        out = self.base / "footer"
        self.run_extraction(output=out)
        labels = self.labels([self.email])
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code, result = desk._dispatch_cli(["structured-output", str(self.email), "--model", MODEL,
                "--output-dir", str(out), "--labels", str(labels), "--summary-only"])
        self.assertEqual(code, 0)
        last_line = next(line for line in stream.getvalue().splitlines() if line.startswith("Assistant draft agreement (human review pending):"))
        self.assertIn("Assistant draft agreement (human review pending): 100.0%", last_line)
        self.assertIn("1/1 labelled emails validated", last_line)
        self.assertIn("Validation: 1/1 accounted for | validated: 1 | needs_review: 0", stream.getvalue())
        note = desk._format_structured_session_note(result["workflow"], result["args"], max_chars=1500)
        self.assertEqual(note.splitlines()[-1], last_line)

    def test_validation_without_labels_ends_with_unmeasured_accuracy(self):
        out = self.base / "unlabelled-footer"
        self.run_extraction(output=out)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code, result = desk._dispatch_cli(["structured-output", str(self.email), "--model", MODEL,
                "--output-dir", str(out)])
        self.assertEqual(code, 0)
        last_line = "Accuracy: unmeasured (no matching labels available)."
        self.assertIn(last_line, stream.getvalue().splitlines())
        note = desk._format_structured_session_note(result["workflow"], result["args"])
        self.assertEqual(note.splitlines()[-1], last_line)

    def test_later_review_supersedes_success_for_resume_and_accuracy(self):
        out = self.base / "superseded"
        self.run_extraction(output=out)
        review, _, _ = self.run_extraction([native_response("", "refusal")], output=out)
        labels = self.labels([self.email])
        _, plan = batch.create_plan(self.email, MODEL, output_dir=out)
        self.assertEqual((plan["reused_count"], plan["new_email_payloads"]), (1, 0))
        self.assertEqual(plan["sources"][0]["reuse_run_id"], review["run_id"])
        _, report = accuracy.accuracy_report(labels, model=MODEL, output_dir=out)
        self.assertEqual((report["coverage"]["validated"], report["coverage"]["needs_review"]), (0, 1))
        self.assertEqual(report["emails"][0]["run_id"], review["run_id"])
        self.assertEqual(report["overall"]["correct"], 0)

    def test_source_map_retries_temporary_windows_replace_denials(self):
        path = self.base / "source-map.jsonl"
        replace = source_map.os.replace
        attempts = 0
        def briefly_denied(source, target):
            nonlocal attempts
            attempts += 1
            if attempts <= 3:
                raise PermissionError("Temporary reader/scanner lock")
            return replace(source, target)
        with patch.object(source_map.os, "replace", side_effect=briefly_denied), \
             patch.object(source_map.time, "sleep"):
            source_map._write_entries(path, [])
        self.assertEqual(attempts, 4)
        self.assertEqual(path.read_bytes(), b"")

    def test_source_map_permanent_denial_is_bounded_and_preserves_old_file(self):
        path = self.base / "source-map.jsonl"
        path.write_bytes(b"old data")
        with patch.object(source_map.os, "replace", side_effect=PermissionError("Permanent denial")) as replace, \
             patch.object(source_map.time, "sleep"):
            with self.assertRaises(PermissionError):
                source_map._write_entries(path, [])
        self.assertEqual(replace.call_count, 6)
        self.assertEqual(path.read_bytes(), b"old data")

    def labels(self, sources):
        import hashlib
        path = self.base / "labels.json"
        path.write_text(json.dumps(dict(version=1, provenance=dict(
            kind="assistant_source_draft", author="synthetic test", created_on="2026-11-26",
            method="Synthetic fixtures, unrelated to the project label set.",
            human_review=dict(status="pending", reviewer=None, reviewed_on=None)),
            labels=[dict(source=dict(id=p.stem, relative_path=str(p),
                                     sha256=hashlib.sha256(p.read_bytes()).hexdigest()),
                         expected=expected_fields().model_dump(mode="json"), notes="Synthetic test fixture")
                    for p in sources])), encoding="utf-8")
        return path

    def test_one_command_scores_all_fifteen_with_missing_and_review_denominators(self):
        sources = []
        out = self.base / "scored"
        for i in range(15):
            self.email = self.base / f"sample-{i:02}.txt"
            self.email.write_text(EMAIL, encoding="utf-8", newline="")
            sources.append(self.email)
            if i < 13:
                self.run_extraction(output=out)
            elif i == 13:
                self.run_extraction([native_response("", "refusal")], output=out)
        labels = self.labels(sources)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = desk.main(["accuracy", "--labels", str(labels), "--model", MODEL,
                              "--output-dir", str(out), "--sample-size", "1", "--show-results"])
        self.assertEqual(code, 0)
        report = json.loads((out / "accuracy-report.json").read_text(encoding="utf-8"))
        self.assertEqual((report["coverage"]["labels"], report["coverage"]["validated"],
                          report["coverage"]["needs_review"], report["coverage"]["missing"]), (15, 13, 1, 1))
        self.assertEqual((report["fields"]["customer"]["correct"], report["fields"]["customer"]["total"]), (13, 15))
        self.assertEqual(report["measurement_kind"], "assistant_draft_agreement")
        self.assertEqual(len(report["emails"]), 15)
        self.assertIn("Evaluation sample: 1 of 15", stream.getvalue())

    def test_labels_outside_selection_and_stale_checksums_fail_before_calls(self):
        labels = self.labels([self.email])
        other = self.base / "other.txt"; other.write_text(EMAIL, encoding="utf-8", newline="")
        with patch.object(extraction, "call_structured_model", side_effect=AssertionError("No send")) as calls:
            with self.assertRaisesRegex(model.DeskError, "outside the selected input"):
                structured_output.run_workflow(other, MODEL, labels_path=labels, output_dir=self.base / "other-run")
            self.email.write_text("Changed source", encoding="utf-8")
            with self.assertRaisesRegex(model.DeskError, "hash differs"):
                structured_output.run_workflow(self.email, MODEL, labels_path=labels, output_dir=self.base / "stale-run")
        calls.assert_not_called()

    def test_invalid_json_repairs_and_exhaustion_are_persisted(self):
        for output in ["prose", "```json\n{}\n```", "{}"]:
            with self.subTest(output=output):
                record, calls, checks = self.run_extraction([output], output=self.base / str(len(output)))
                self.assertEqual((record["status"], record["repair_requests"], len(calls), len(checks)),
                                 ("needs_review", 2, 3, 0))
                self.assertTrue(calls[1]["validation_errors"])

    def test_extraction_refusal_is_not_retried(self):
        record, calls, checks = self.run_extraction([native_response("", "refusal")])
        self.assertEqual((record["status"], record["reason"], len(calls), len(checks)),
                         ("needs_review", "refusal", 1, 0))

    def test_storage_failure_stops_before_the_next_email_until_offline_recovery(self):
        sources = self.base / "emails"; sources.mkdir()
        for i in range(2):
            (sources / f"mail-{i}.txt").write_text(EMAIL, encoding="utf-8", newline="")
        out = self.base / "run"
        plan_path, _ = batch.create_plan(sources, MODEL, output_dir=out)
        writer = extraction._atomic_write
        failed = False
        def fail_result_once(path, text):
            nonlocal failed
            if path.name == "results.jsonl" and not failed:
                failed = True
                raise model.DeskError("Transient storage failure")
            return writer(path, text)
        def verify(c, m, messages, *a, **kw):
            envelope = json.loads(messages[0]["content"][0]["text"])
            return native_response(ledger(envelope["email"], envelope["candidate"]))
        with patch.object(extraction, "make_client", return_value=FakeClient()), \
             patch.object(extraction, "call_structured_model", return_value=native_response(candidate())) as calls, \
             patch.object(grounding, "call_structured_model", side_effect=verify), \
             patch.object(extraction, "_atomic_write", side_effect=fail_result_once):
            with self.assertRaises(model.DeskError):
                batch.execute_plan(plan_path, MODEL, output_dir=out, allow_provider_calls=True)
        self.assertEqual(calls.call_count, 1)
        self.assertTrue(list((out / "pending").glob("*.json")))
        extraction.rebuild_outputs(output_dir=out)
        rows = extraction.read_run_history(out)[1]
        self.assertEqual((len(rows), rows[0]["status"], rows[0]["reason"]), (1, "needs_review", "interrupted_run"))

    def test_all_thirty_inputs_have_an_outcome_including_invalid_sources(self):
        sources = self.base / "emails"; sources.mkdir()
        for i in range(30):
            (sources / f"mail-{i:02}.txt").write_text(EMAIL if i else "", encoding="utf-8", newline="")
        def extract(c, m, messages, *a, **kw):
            return native_response(candidate())
        def verify(c, m, messages, *a, **kw):
            envelope = json.loads(messages[0]["content"][0]["text"])
            return native_response(ledger(envelope["email"], envelope["candidate"]))
        with patch.object(extraction, "make_client", side_effect=lambda **kw: FakeClient()), \
             patch.object(extraction, "call_structured_model", side_effect=extract) as calls, \
             patch.object(grounding, "call_structured_model", side_effect=verify):
            result = structured_output.run_workflow(sources, MODEL, output_dir=self.base / "run")
        rows = extraction.read_run_history(self.base / "run")[1]
        self.assertEqual((len(rows), len(result["manifest"]["sources"]), calls.call_count), (30, 30, 29))
        self.assertEqual(result["manifest"]["status"], "complete_with_review")
        self.assertEqual(sum(r["status"] == "validated" for r in rows), 29)
        self.assertEqual(sum(r["status"] == "needs_review" for r in rows), 1)


if __name__ == "__main__":
    unittest.main()
