"""Assistant presentation keeps source facts, aggregate scores and usage intact."""

import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from rich.cells import cell_len
from rich.console import Console

from challenges.challenge3.test_structured_output import EMAIL, MODEL, FakeClient, OfflineFixture, candidate, ledger, native_response
import desk
from challenge3_structured_output import extraction
from challenge3_structured_output import grounding
import model
import presentation as ui
from telemetry import response_stats


def score_report():
    return dict(measurement_kind="assistant_draft_agreement", overall=dict(score=108 / 109, correct=108, total=109),
                coverage=dict(labels=15, validated=15, needs_review=0, missing=0),
                fields={"quantity": dict(correct=8, total=9, score=8 / 9)})


class RenderTests(unittest.TestCase):
    def render(self, fn, width=90):
        output = io.StringIO()
        console = Console(file=output, width=width, height=25, record=True, force_terminal=True, color_system="truecolor", legacy_windows=False)
        with ui.use_console(console):
            fn()
        return console.export_text()

    def test_overall_score_uses_all_labelled_checks_separate_from_batch_count(self):
        stats = response_stats(dict(inputTokens=1200, outputTokens=300), latency=12.3, first_token=0.4,
                               state=dict(total_in=100, total_out=50))
        stats.update(context_tokens=450, context_limit=64000)
        output = self.render(lambda: ui.score_panel(score_report(), manifest=dict(
            sources=[dict(status="validated")] * 30), stats=stats))
        for value in ["99.1%", "Overall draft agreement", "I checked 30 emails", "30 validated",
                      "Based on 15 labelled emails", "Human review pending", "108 of 109", "Latency 12.30s",
                      "First token 0.40s", "Input 1.2k", "Output 300", "Session 1.3k in/350", "Context"]:
            self.assertIn(value, output)
        self.assertNotIn("field |", output)
        self.assertNotIn("15/15", output)
        self.assertEqual(output.count("99.1%"), 1)

    def test_missing_labels_do_not_turn_validation_into_accuracy(self):
        output = self.render(lambda: ui.score_panel(None, manifest=dict(sources=[dict(status="validated")])))
        self.assertIn("Unmeasured", output)
        self.assertNotIn("100.0%", output)

    def test_narrow_email_cards_wrap_and_show_only_the_six_fields(self):
        value = candidate()
        value["customer"] = "Very long workshop customer name " * 3
        value["line_items"][0].update(sku="LONG-SKU-" * 9, description="[red] literal product name " * 5, unit=None)
        output = self.render(lambda: ui.email_result(dict(email_id="TEST-001", status="validated", result=value)), width=48)
        self.assertTrue(all(cell_len(line) <= 48 for line in output.splitlines()))
        self.assertIn("Not stated", output)
        self.assertIn("[red]", output)
        self.assertNotIn("purchase_authorized", output)

    def test_review_card_never_displays_an_unaccepted_prediction(self):
        output = self.render(lambda: ui.email_result(dict(email_id="TEST-002", status="needs_review",
            reason="validation_exhausted", result=dict(customer="UNACCEPTED FACT"))))
        self.assertIn("NEEDS REVIEW", output)
        self.assertNotIn("UNACCEPTED FACT", output)

    def test_stream_callback_preserves_reply_without_raw_duplicate_prints(self):
        stream = [{"contentBlockDelta": {"delta": {"text": "Hello "}}},
                  {"contentBlockDelta": {"delta": {"text": "again"}}},
                  {"messageStop": {"stopReason": "end_turn"}},
                  {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 4}}}]
        chunks, output = [], io.StringIO()
        with contextlib.redirect_stdout(output):
            result = model._render_stream(stream, 0, on_text=chunks.append)
        self.assertEqual(("".join(chunks), result[0], output.getvalue()), ("Hello again", "Hello again", ""))

    def test_plain_validation_report_is_overall_only(self):
        report = score_report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            desk.print_accuracy_report("report.json", report, include_emails=False)
        self.assertIn("99.1%", output.getvalue())
        self.assertNotIn("field |", output.getvalue())
        self.assertNotIn("quantity |", output.getvalue())


class UsageTests(OfflineFixture, unittest.TestCase):
    def test_ask_dispatch_accepts_flags_anywhere_and_reports_usage_once(self):
        from challenges.challenge3.test_chat_skills import text_stream
        response = dict(output=dict(message=dict(content=[dict(text="Ask reply")])),
                        usage=dict(inputTokens=7, outputTokens=4), stopReason="end_turn")
        options = ["--model", MODEL, "--temperature", "0.2", "--no-rag"]
        for arguments in [options + ["Explain", "token", "totals"],
                          ["Explain", *options, "token", "totals"],
                          ["Explain", "token", "totals", *options]]:
            with self.subTest(arguments=arguments):
                client = SimpleNamespace(converse_stream=Mock(return_value={"stream": text_stream("Ask reply", response["usage"])}))
                output = io.StringIO()
                with patch.object(desk, "make_client", return_value=client), \
                     contextlib.redirect_stdout(output):
                    code, result = desk._dispatch_cli(["ask", *arguments])
                self.assertEqual(code, 0)
                self.assertEqual(result["question"], "Explain token totals")
                request = client.converse_stream.call_args.kwargs
                self.assertEqual(request["modelId"], MODEL)
                self.assertEqual(request["inferenceConfig"]["temperature"], 0.2)
                self.assertEqual(request["messages"][0]["content"], [dict(text="Explain token totals")])
                self.assertEqual(output.getvalue().count("Ask reply"), 1)
                self.assertEqual(output.getvalue().count("Conversation details:"), 1)
                self.assertIn("input 7 tokens | output 4 tokens", output.getvalue())

    def test_chat_ask_override_preserves_default_history_and_counts_usage_once(self):
        from challenges.challenge3.test_chat_skills import text_stream
        override = "override-test-model"
        requests = []
        def stream(**kwargs):
            if kwargs["modelId"] == override:
                return dict(stream=text_stream("Ask reply", dict(inputTokens=7, outputTokens=4)))
            requests.append(json.loads(json.dumps(kwargs)))
            return dict(stream=text_stream("You asked about token totals."))
        client = SimpleNamespace(converse=Mock(return_value=dict(
            output=dict(message=dict(content=[dict(text="Ask reply")])),
            usage=dict(inputTokens=7, outputTokens=4), stopReason="end_turn")),
            converse_stream=Mock(side_effect=stream))
        command = f"/ask Explain --temperature 0.2 --model {override} --no-rag token totals"
        inputs = iter([command, "What did I ask?", "/exit"])
        output = io.StringIO()
        with patch.object(desk, "make_client", return_value=client), \
             patch("chat_commands.chat_reader", return_value=lambda _: next(inputs)), \
             contextlib.redirect_stdout(output):
            self.assertEqual(desk.main(["chat", "--model", MODEL]), 0)
        self.assertEqual(client.converse_stream.call_count, 2)
        self.assertEqual(client.converse_stream.call_args_list[0].kwargs["modelId"], override)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["modelId"], MODEL)
        self.assertEqual(requests[0]["messages"], [
            dict(role="user", content=[dict(text=command)]),
            dict(role="assistant", content=[dict(text="Ask reply")]),
            dict(role="user", content=[dict(text="What did I ask?")]),
        ])
        self.assertEqual(output.getvalue().count("Ask reply"), 1)
        self.assertEqual(output.getvalue().count("Conversation details:"), 3)
        details = [line for line in output.getvalue().splitlines() if line.startswith("Conversation details:")]
        self.assertIn(f"model {override}", details[0])
        self.assertIn(f"model {MODEL}", details[1])
        self.assertIn(f"model {MODEL}", details[2])
        self.assertIn("session 7 input / 4 output tokens", output.getvalue())
        self.assertIn("session 11 input / 6 output tokens", output.getvalue())

    def test_structured_output_override_reports_selected_model_without_changing_default(self):
        state = dict(model="session-default-model", messages=[], total_in=0, total_out=0, history_limit=64000)
        output = io.StringIO()
        out = self.base / "override results"
        command = f'/structured-output "{self.email}" --output-dir "{out}" --model {MODEL} --summary-only'
        def verify(c, m, messages, *a, **kw):
            envelope = json.loads(messages[0]["content"][0]["text"])
            return native_response(ledger(envelope["email"], envelope["candidate"]))
        with patch.object(extraction, "make_client", return_value=FakeClient()), \
             patch.object(extraction, "call_structured_model", return_value=native_response(candidate())) as extract, \
             patch.object(grounding, "call_structured_model", side_effect=verify) as verification, \
             contextlib.redirect_stdout(output):
            with ui.turn_details(state):
                self.assertTrue(desk.handle_command(command, state))
        self.assertEqual(extract.call_args.args[1], MODEL)
        self.assertEqual(verification.call_args.args[1], MODEL)
        self.assertEqual(state["model"], "session-default-model")
        self.assertEqual((state["total_in"], state["total_out"]), (10, 6))
        details = [line for line in output.getvalue().splitlines() if line.startswith("Conversation details:")]
        self.assertEqual(len(details), 1)
        self.assertIn(f"model {MODEL}", details[0])
        self.assertNotIn("model session-default-model", details[0])

    def test_failed_gateway_request_reports_missing_usage_without_inventing_cost(self):
        from botocore.exceptions import ClientError
        from telemetry import current_turn
        def reject(**kwargs):
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "offline test"}}, "Converse")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), ui.turn_details() as turn:
            with self.assertRaises(model.DeskError):
                model.call_model(SimpleNamespace(converse=reject), MODEL, "test", None, 200)
            self.assertTrue(turn.snapshot()["usage_incomplete"])
            self.assertNotIn("estimated_cost", turn.snapshot())
            self.assertEqual(turn.snapshot()["attempts"], 1)

    def test_universal_turn_counts_gateway_calls_once_and_keeps_session_totals(self):
        usage = dict(inputTokens=5, outputTokens=3, cacheReadInputTokens=2, cacheWriteInputTokens=1)
        client = SimpleNamespace(converse=lambda **kw: dict(output=dict(message=dict(content=[dict(text="Hello")])),
            usage=usage, stopReason="end_turn"), meta=SimpleNamespace(service_model=SimpleNamespace(
                operation_model=lambda _: SimpleNamespace(input_shape=SimpleNamespace(members={"outputConfig": 1})))))
        state = dict(model=MODEL, messages=[], total_in=10, total_out=4, history_limit=64000)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), ui.turn_details(state):
            model.call_model(client, MODEL, "Hello", None, 200)
            with ui.turn_details(state):
                model.call_structured_model(client, MODEL, [], {}, 200, "test")
            desk._record_session_turn(state, "Hello", "Done", usage=dict(inputTokens=10, outputTokens=6,
                cacheReadInputTokens=4, cacheWriteInputTokens=2))
        self.assertEqual((state["total_in"], state["total_out"]), (26, 10))
        self.assertEqual(output.getvalue().count("Conversation details:"), 1)
        self.assertIn("input 16 tokens", output.getvalue())
        self.assertIn("session 26 input / 10 output", output.getvalue())

    def test_future_command_gets_conversation_details_without_adding_its_own_reporting(self):
        parser = desk.build_parser()
        from chat_commands import subcommands
        action = next(a for a in parser._actions if getattr(a, "choices", None) and "ask" in a.choices)
        future = action.add_parser("future-feature")
        client = SimpleNamespace(converse=lambda **kw: dict(output=dict(message=dict(content=[dict(text="Future reply")])),
            usage=dict(inputTokens=7, outputTokens=4), stopReason="end_turn"))
        future.set_defaults(func=lambda args: model.call_model(client, MODEL, "New feature", None, 200))
        output = io.StringIO()
        with patch.object(desk, "build_parser", return_value=parser), contextlib.redirect_stdout(output):
            code, _ = desk._dispatch_cli(["future-feature"])
        self.assertEqual(code, 0)
        self.assertIn("Conversation details:", output.getvalue())
        self.assertIn("input 7 tokens", output.getvalue())

    def test_malformed_tool_keeps_reported_usage_even_when_execution_is_rejected(self):
        from challenges.challenge3.test_chat_skills import tool_stream
        client = SimpleNamespace(converse_stream=lambda **kw: dict(stream=tool_stream("{")))
        state = dict(model=MODEL, messages=[], total_in=0, total_out=0, history_limit=64000)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), ui.turn_details(state):
            with self.assertRaises(model.DeskError):
                model.stream_model(client, MODEL, [], None, 200, "test", tool_uses=[])
        self.assertEqual((state["total_in"], state["total_out"]), (10, 5))
        self.assertIn("Conversation details:", output.getvalue())

    def test_skill_usage_includes_extraction_verification_and_session_without_rebilling_reuse(self):
        sources = self.base / "emails"; sources.mkdir()
        for i in range(2):
            (sources / f"note-{i}.txt").write_text(EMAIL, encoding="utf-8", newline="")
        out = self.base / "out"
        tool = dict(name="structured_output", input=dict(source=str(sources), output_dir=str(out), summary_only=True))
        state = dict(model=MODEL, messages=[], total_in=100, total_out=50, history_limit=64000)
        routing = dict(usage=dict(inputTokens=3, outputTokens=2), latency_s=0.2, attempts=1)
        def verify(c, m, messages, *a, **kw):
            envelope = json.loads(messages[0]["content"][0]["text"])
            return native_response(ledger(envelope["email"], envelope["candidate"]))
        output = io.StringIO()
        console = Console(file=output, width=90, record=True, force_terminal=True)
        with ui.use_console(console), patch.object(extraction, "make_client", side_effect=lambda **kw: FakeClient()), \
             patch.object(extraction, "call_structured_model", return_value=native_response(candidate())), \
             patch.object(grounding, "call_structured_model", side_effect=verify):
            desk._run_chat_skill([tool], "Use the skill", state, usage=routing["usage"], routing=routing)
        self.assertEqual((state["total_in"], state["total_out"]), (123, 64))
        manifest = json.loads(next(out.glob("batch-run-*.json")).read_text())
        self.assertEqual((manifest["metrics"]["usage"]["inputTokens"], manifest["metrics"]["usage"]["outputTokens"]), (20, 12))
        self.assertEqual(manifest["metrics"]["provider_attempts"], 4)
        self.assertIn("Input 23", console.export_text())
        self.assertIn("input 23 tokens", state["messages"][-1]["content"][0]["text"])
        with ui.use_console(console), patch.object(extraction, "make_client", side_effect=AssertionError("No sends on reuse")):
            desk._run_chat_skill([tool], "Use the same saved results", state, usage=routing["usage"], routing=routing)
        self.assertEqual((state["total_in"], state["total_out"]), (126, 66))
        latest = max(out.glob("batch-run-*.json"), key=lambda p: p.stat().st_mtime_ns)
        self.assertEqual(json.loads(latest.read_text())["metrics"]["usage"]["inputTokens"], 0)


if __name__ == "__main__":
    unittest.main()
