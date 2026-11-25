"""Offline integration regressions. Native extraction/verifier transport is mocked.

These exercise the grounding protocol and failure handling, not live semantic
accuracy. All writes use disposable directories; saved corpus evidence is read only.
"""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accuracy
import batch
import chat_commands
import desk
import extraction
import grounding
import model
from schemas import GroundingReport, OrderRequest, bedrock_schema

MODEL = "offline-test-model"
EMAIL = "Subject: Quotation\n\nQuote 7 units of ZX-49, steel clips. Do not place an order.\nThanks,\nLee Vale\nAcme Works"


def candidate():
    return dict(customer="Acme Works", contact="Lee Vale", intent="other",
                primary_request=dict(intent="other", kind="quote", description="Quote seven units of steel clips; purchase is not authorized."),
                secondary_requests=[], line_items=[dict(sku="ZX-49", description="steel clips", quantity=7, unit="units")],
                requested_date=None, urgency=None, confidence=0.8, purchase_authorized=False)


def ledger(email, value):
    # A stubbed verifier response; not a source-label dataset or semantic oracle.
    fields = grounding.candidate_fields(value)
    return dict(verdict="pass", field_checks=[dict(path=path, verdict="supported", source_quotes=[email],
                explanation="Offline transport fixture") for path in fields],
                source_checks=[dict(segment=i, verdict="covered", candidate_paths=["/primary_request/description"],
                explanation="Offline transport fixture") for i, _ in enumerate(grounding.source_segments(email))])


def native_response(value, stop="end_turn", attempts=1):
    return dict(raw_text=value if isinstance(value, str) else json.dumps(value), stop_reason=stop,
                transport_attempts=attempts, usage={"inputTokens": 5, "outputTokens": 3}, latency_s=0, request_id="offline")


class FakeClient:
    def __init__(self):
        self.meta = SimpleNamespace(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")
        self.closed = False

    def close(self):
        self.closed = True


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".challenge3-test-", dir=ROOT)
        self.base = Path(self.temp.name).resolve()
        assert self.base.is_relative_to(ROOT)
        self.addCleanup(self.temp.cleanup)
        guard = patch("boto3.client", side_effect=AssertionError("Network/provider clients forbidden in offline tests"))
        guard.start()
        self.addCleanup(guard.stop)
        self.email = self.base / "arbitrary-message.eml"
        self.email.write_text(EMAIL, encoding="utf-8")
        self.client = FakeClient()

    def run_extraction(self, values=None, reports=None, output=None):
        values = [candidate()] if values is None else values
        reports = [] if reports is None else reports
        extraction_calls, verifier_calls = [], []

        def extract(c, m, messages, *args, **kwargs):
            extraction_calls.append(json.loads(messages[0]["content"][0]["text"]))
            value = values[min(len(extraction_calls) - 1, len(values) - 1)]
            return value if isinstance(value, dict) and "raw_text" in value else native_response(value)

        def verify(c, m, messages, *args, **kwargs):
            envelope = json.loads(messages[0]["content"][0]["text"])
            verifier_calls.append(envelope)
            self.assertEqual(kwargs["schema_name"], "source_grounding")
            value = reports[min(len(verifier_calls) - 1, len(reports) - 1)] if reports else ledger(envelope["email"], envelope["candidate"])
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, dict) and "raw_text" in value else native_response(value)

        with patch.object(extraction, "call_structured_model", side_effect=extract), patch.object(grounding, "call_structured_model", side_effect=verify):
            _, record = extraction.extract_email(self.email, MODEL, output_dir=output or self.base / "out",
                                                 client_factory=lambda: self.client)
        self.assertTrue(self.client.closed)
        return record, extraction_calls, verifier_calls

    def test_verified_success_has_receipt_and_isolated_context(self):
        record, calls, checks = self.run_extraction()
        self.assertEqual(record["status"], "validated")
        self.assertEqual(set(calls[0]), {"email"})
        self.assertEqual(set(checks[0]), {"email", "candidate", "extraction_policy", "required_paths", "source_segments"})
        self.assertEqual(checks[0]["email"], EMAIL)
        self.assertNotIn(str(self.email), json.dumps(checks[0]))
        _, rows = extraction.read_run_history(self.base / "out")
        self.assertEqual(len(rows), 1)
        receipt = json.loads(next((self.base / "out/verifications").glob("*.json")).read_text())
        self.assertEqual((receipt["responses_received"], receipt["verification_requests"], receipt["transport_attempts"]), (1, 1, 2))
        self.assertEqual(receipt["payload_sha256"], extraction._payload_hash(candidate()))

    def test_semantic_feedback_repairs_unsupported_prose_without_new_context(self):
        bad = candidate(); bad["primary_request"]["description"] += " The shipment has already departed."
        report = ledger(EMAIL, bad); report["verdict"] = "fail"
        next(c for c in report["field_checks"] if c["path"] == "/primary_request/description").update(
            verdict="unsupported", explanation="No source evidence that a shipment departed; remove that assertion.")
        record, calls, _ = self.run_extraction([bad, candidate()], [report, ledger(EMAIL, candidate())])
        self.assertEqual((record["status"], record["repair_requests"]), ("validated", 1))
        self.assertEqual(set(calls[1]), {"email", "previous_output", "validation_errors"})
        self.assertIn("remove that assertion", str(calls[1]["validation_errors"]))
        self.assertEqual(json.loads(calls[1]["previous_output"]), bad)

    def test_faithful_paraphrase_does_not_require_verbatim_description(self):
        value = candidate(); value["line_items"][0]["description"] = "clips made from steel"
        record, _, _ = self.run_extraction([value])
        self.assertEqual(record["status"], "validated")

    def test_denial_unit_and_ambiguity_findings_use_shared_two_repair_budget(self):
        for path, explanation in [("/purchase_authorized", "Explicit denial must be false, not null."),
                                  ("/line_items/0/unit", "Preserve the explicit unit in its dedicated field."),
                                  ("/primary_request/description", "Do not turn an ambiguous question into a confirmed existing order.")]:
            with self.subTest(path=path):
                value = candidate()
                if path == "/purchase_authorized":
                    value["primary_request"]["kind"] = "other"; value["purchase_authorized"] = None
                elif path.endswith("/unit"):
                    value["line_items"][0]["unit"] = None
                else:
                    value["primary_request"]["description"] = "Confirmed existing order is delayed."
                report = ledger(EMAIL, value); report["verdict"] = "fail"
                next(c for c in report["field_checks"] if c["path"] == path).update(verdict="unsupported", explanation=explanation)
                record, calls, checks = self.run_extraction([value], [report], self.base / str(len(explanation)))
                self.assertEqual((record["status"], record["repair_requests"], len(calls), len(checks)), ("needs_review", 2, 3, 3))
                self.assertEqual(record["transport_attempts"], 6)

    def test_missing_topic_or_return_routing_is_actionable(self):
        report = ledger(EMAIL, candidate()); report["verdict"] = "fail"
        report["source_checks"][0].update(verdict="omitted", candidate_paths=[],
            explanation="Separate the independent return eligibility enquiry from the stock and quote topics.")
        record, calls, _ = self.run_extraction(reports=[report])
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("return eligibility", str(calls[1]["validation_errors"]))

    def test_uncertain_verdict_never_becomes_success(self):
        report = ledger(EMAIL, candidate()); report["verdict"] = "uncertain"
        record, _, _ = self.run_extraction(reports=[report])
        self.assertEqual((record["status"], record["repair_requests"]), ("needs_review", 2))

    def test_verifier_refusal_truncation_and_malformed_report_fail_closed(self):
        for value in [native_response("", "refusal"), native_response("{}", "max_tokens"), native_response("not JSON")]:
            with self.subTest(value=value):
                record, calls, checks = self.run_extraction(reports=[value], output=self.base / str(len(str(value))))
                self.assertEqual((record["status"], record["reason"], len(calls), len(checks)), ("needs_review", "verification_unavailable", 1, 1))

    def test_verifier_provider_and_local_errors_fail_closed(self):
        for error in [model.StructuredRequestError("offline", attempts=3, code="AccessDeniedException"), RuntimeError("offline")]:
            with self.subTest(error=type(error).__name__):
                record, calls, checks = self.run_extraction(reports=[error], output=self.base / type(error).__name__)
                self.assertEqual((record["status"], record["reason"]), ("needs_review", "verification_unavailable"))
                self.assertEqual(len(calls), 1)
                if isinstance(error, model.StructuredRequestError):
                    self.assertEqual(record["transport_attempts"], 4)

    def test_schema_repair_and_semantic_repair_share_budget(self):
        report = ledger(EMAIL, candidate()); report["verdict"] = "fail"
        record, calls, checks = self.run_extraction(["bad JSON", candidate(), candidate()], [report])
        self.assertEqual((len(calls), len(checks), record["repair_requests"]), (3, 2, 2))
        self.assertEqual(record["status"], "needs_review")

    def test_complete_ledger_and_literal_evidence_are_enforced_locally(self):
        for mutate in [lambda r: r["field_checks"].pop(), lambda r: r["source_checks"].pop(),
                       lambda r: r["field_checks"].append(r["field_checks"][0]),
                       lambda r: r["field_checks"][0].update(source_quotes=["absent text"]),
                       lambda r: r["field_checks"][0].update(source_quotes=[]),
                       lambda r: r["source_checks"][0].update(candidate_paths=["/unknown"])]:
            report = ledger(EMAIL, candidate()); mutate(report)
            parsed = GroundingReport.model_validate_json(json.dumps(report))
            self.assertTrue(grounding.report_errors(parsed, EMAIL, candidate()))

    def test_uncertain_and_alternative_quantities_remain_null(self):
        self.email.write_text("Quote a blue compound; maybe 9, quantity unconfirmed. Alternatively quote 20 or 80 only, not both.", encoding="utf-8")
        value = candidate(); value["customer"] = value["contact"] = None
        value["line_items"] = [dict(sku=None, description="blue compound; maybe 9 unconfirmed, or mutually exclusive 20/80 quote options", quantity=None, unit=None)]
        record, _, _ = self.run_extraction([value])
        self.assertIsNone(record["data"]["line_items"][0]["quantity"])

    def test_missing_receipt_and_tampered_payload_are_rejected(self):
        record, _, _ = self.run_extraction()
        receipt = self.base / "out/verifications" / (record["run_id"] + ".json")
        receipt.unlink()
        with self.assertRaisesRegex(model.DeskError, "receipt"):
            extraction.read_run_history(self.base / "out")

    def test_old_contract_and_changed_verifier_are_not_reused(self):
        record, _, _ = self.run_extraction()
        _, rows = extraction.read_run_history(self.base / "out")
        source = batch._snapshot(self.email); fp = extraction.extraction_fingerprint()
        self.assertIsNotNone(batch.reusable_record(rows, source, MODEL, fp))
        changed = dict(fp, verifier_sha256="0" * 64)
        self.assertIsNone(batch.reusable_record(rows, source, MODEL, changed))
        del rows[0]["verifier_sha256"]
        self.assertIsNone(batch.reusable_record(rows, source, MODEL, fp))

    def test_current_corpus_old_outputs_remain_readable_but_not_current(self):
        marker = json.loads((ROOT / "output/latest-provider-rerun.json").read_text())
        _, rows = extraction.read_run_history(marker["output_dir"])
        self.assertEqual(len(rows), 30)
        for row in rows:
            OrderRequest.model_validate_json(json.dumps(row["data"]))
            self.assertIsNone(batch.reusable_record([row], batch._snapshot(Path(row["source"]["path"])), row["model"], extraction.extraction_fingerprint()))

    def test_arbitrary_forty_inputs_reuse_and_fifteen_sample(self):
        source = self.base / "messages"; source.mkdir()
        for i in range(40):
            (source / f"customer-note-{i}.txt").write_text(EMAIL, encoding="utf-8")
        out = self.base / "batch"
        def extract(c, m, messages, *a, **kw):
            self.assertEqual(set(json.loads(messages[0]["content"][0]["text"])), {"email"})
            return native_response(candidate())
        def verify(c, m, messages, *a, **kw):
            envelope = json.loads(messages[0]["content"][0]["text"])
            return native_response(ledger(envelope["email"], envelope["candidate"]))
        p, plan = batch.create_plan(source, MODEL, output_dir=out)
        self.assertEqual((plan["source_count"], plan["max_response_requests"], plan["max_transport_attempts"]), (40, 240, 720))
        with patch.object(extraction, "make_client", side_effect=lambda **kw: FakeClient()), patch.object(extraction, "call_structured_model", side_effect=extract) as calls, patch.object(grounding, "call_structured_model", side_effect=verify) as checks:
            _, manifest = batch.execute_plan(p, MODEL, output_dir=out, allow_provider_calls=True)
        self.assertEqual((manifest["status"], calls.call_count, checks.call_count), ("complete", 40, 40))
        p2, plan2 = batch.create_plan(source, MODEL, output_dir=out)
        self.assertEqual((plan2["reused_count"], plan2["new_email_payloads"]), (40, 0))
        with patch.object(extraction, "call_structured_model", side_effect=AssertionError("No repeated requests")):
            batch.execute_plan(p2, MODEL, output_dir=out, allow_provider_calls=True)
        self.assertEqual(len(extraction.read_run_history(out)[1]), 40)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            desk.print_result_sample(manifest, output_dir=out)
        self.assertEqual(sum(line.startswith("{") for line in stream.getvalue().splitlines()), 15)

    def test_seven_chat_commands_and_new_cli_selection(self):
        parser = desk.build_parser()
        self.assertEqual(set(chat_commands.command_catalog(parser)), {"ask", "chat", "reset", "exit", "load", "save", "structured-output"})
        args = parser.parse_args(["accuracy", "--output-dir", "somewhere", "--allow-historical", "--config", "abc"])
        self.assertEqual((args.output_dir, args.allow_historical, args.config), ("somewhere", True, "abc"))

    def test_native_verifier_schema_and_no_network_fallback(self):
        client = FakeClient()
        client.meta.service_model = SimpleNamespace(operation_model=lambda _: SimpleNamespace(input_shape=SimpleNamespace(members={"outputConfig": 1})))
        client.converse = lambda **kw: {"output": {"message": {"content": [{"text": "{}"}]}}, "stopReason": "end_turn"}
        with patch.object(client, "converse", wraps=client.converse) as call:
            model.call_structured_model(client, MODEL, [], bedrock_schema(GroundingReport), 4000, "verify", schema_name="source_grounding")
        self.assertEqual(call.call_args.kwargs["outputConfig"]["textFormat"]["type"], "json_schema")
        self.assertEqual(call.call_args.kwargs["outputConfig"]["textFormat"]["structure"]["jsonSchema"]["name"], "source_grounding")


class SelectionTests(OfflineTests):
    # Inherit the offline transport guard and fixture helpers, not the test cases.
    def labels(self):
        expected = candidate(); request = expected.pop("primary_request")
        expected.pop("confidence"); expected.pop("secondary_requests")
        expected["primary_request_kind"] = request["kind"]
        expected["requests"] = [{**request, "description_terms": [["quote"], ["clips"]]}]
        value = dict(version=1, provenance=dict(kind="assistant_source_draft", author="test", created_on="2026-11-25", method="offline synthetic fixture",
            human_review=dict(status="pending", reviewer=None, reviewed_on=None)), labels=[dict(
            source=dict(id=self.email.stem, relative_path=str(self.email), sha256=hashlib.sha256(self.email.read_bytes()).hexdigest()),
            expected=expected, notes="offline fixture")])
        path = self.base / "labels.json"; path.write_text(json.dumps(value));return path

    def test_latest_and_explicit_current_output_selection(self):
        labels = self.labels(); root = self.base / "runs"
        a, b = root / "first", root / "second"
        self.run_extraction(output=a); self.run_extraction(output=b)
        os.utime(a / "source-map.jsonl", ns=(100, 100)); os.utime(b / "source-map.jsonl", ns=(200, 200))
        with patch.object(accuracy, "OUTPUT_DIR", root):
            _, report = accuracy.accuracy_report(labels, model=MODEL)
            self.assertEqual(report["output_dir"], str(b)); self.assertFalse(report["historical"])
            _, report = accuracy.accuracy_report(labels, model=MODEL, output_dir=a)
            self.assertEqual(report["coverage"]["validated"], 1)
            self.assertEqual(report["output_dir"], str(a))

    def test_historical_and_model_mismatch_require_explicit_selection(self):
        labels = self.labels(); out = self.base / "old"
        old = {"schema_sha256": "a" * 64, "prompt_sha256": "b" * 64}
        with patch.object(extraction, "extraction_fingerprint", return_value=old):
            self.run_extraction(output=out)
        with self.assertRaises(model.DeskError):
            accuracy.accuracy_report(labels, model=MODEL, output_dir=out)
        _, report = accuracy.accuracy_report(labels, model=MODEL, output_dir=out, allow_historical=True)
        self.assertTrue(report["historical"])
        with self.assertRaises(model.DeskError):
            accuracy.accuracy_report(labels, model="different", output_dir=out, allow_historical=True)
        with self.assertRaises(model.DeskError):
            accuracy.accuracy_report(labels, model=MODEL, allow_historical=True)

    def test_ambiguous_config_and_latest_timestamp_fail_clearly(self):
        labels = self.labels(); root = self.base / "runs"; a, b = root / "a", root / "b"
        self.run_extraction(output=a); self.run_extraction(output=b)
        os.utime(a / "source-map.jsonl", ns=(100, 100));os.utime(b / "source-map.jsonl", ns=(100, 100))
        with patch.object(accuracy, "OUTPUT_DIR", root), self.assertRaisesRegex(model.DeskError, "ambiguous"):
            accuracy.accuracy_report(labels, model=MODEL)
        fp = extraction.extraction_fingerprint()
        with patch.object(extraction, "extraction_fingerprint", return_value={**fp, "prompt_sha256": "f" * 64}):
            self.run_extraction(output=a)
        with self.assertRaisesRegex(model.DeskError, "Multiple extraction configurations"):
            accuracy.accuracy_report(labels, model=MODEL, output_dir=a, allow_historical=True)
        config = extraction.read_run_history(a)[1][0]["config_id"]
        _, report = accuracy.accuracy_report(labels, model=MODEL, output_dir=a, allow_historical=True, config_id=config)
        self.assertEqual(report["coverage"]["validated"], 1)

    def test_human_review_is_not_automatically_approved(self):
        labels = self.labels();self.run_extraction(output=self.base / "run")
        before = labels.read_bytes()
        with self.assertRaisesRegex(model.DeskError, "human must review"):
            accuracy.accuracy_report(labels, model=MODEL, output_dir=self.base / "run", require_reviewed=True)
        self.assertEqual(labels.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
