"""Observable-before-completion checks; providers are controlled event streams."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import desk
import model
import presentation as ui
import session
from botocore.exceptions import ReadTimeoutError
from rich.console import Console
from naive_rag.retrieval import RetrievedChunk
from naive_rag.ingest import ingest_policies
from naive_rag.vector_store import PolicyStore
from challenges.challenge4.test_ingest import FakeEmbeddings
from challenges.challenge3.test_structured_output import OfflineFixture, EMAIL, FakeClient, candidate, ledger, native_response
from challenge3_structured_output import extraction, grounding


class Output(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushed = ""

    def flush(self):
        self.flushed = self.getvalue()


class Events:
    def __init__(self, generate):
        self.generate, self.closed = generate, False

    def __iter__(self):
        return self.generate()

    def close(self):
        self.closed = True


def delta(text):
    return {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}}


def finish(stop="end_turn"):
    yield {"messageStop": {"stopReason": stop}}
    yield {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 4}}}


class AskStreamingTests(unittest.TestCase):
    def state(self):
        return dict(model="same-model", messages=[], total_in=0, total_out=0, history_limit=64000)

    def test_plain_deltas_flush_before_next_event_and_history_usage_once(self):
        output, state = Output(), self.state()
        def generate():
            yield delta("First ")
            self.assertIn("First ", output.flushed)
            self.assertNotIn("second", output.getvalue())
            self.assertEqual(state["messages"], [])
            yield delta("second")
            yield from finish()
        events = Events(generate)
        client = SimpleNamespace(converse_stream=Mock(return_value={"stream": events}))
        with patch.object(desk, "make_client", return_value=client), contextlib.redirect_stdout(output):
            with ui.turn_details(state, "same-model"):
                desk.handle_command("/ask --no-rag question", state)
        self.assertTrue(events.closed)
        self.assertEqual(output.getvalue().count("First second"), 1)
        self.assertEqual((state["total_in"], state["total_out"]), (7, 4))
        self.assertEqual(len(state["messages"]), 2)
        self.assertEqual(state["messages"][-1]["content"][0]["text"], "First second")
        self.assertEqual(output.getvalue().count("Conversation details:"), 1)
        self.assertIn("first token", output.getvalue())

    def test_rich_draft_is_visible_before_completion_and_final_render_once(self):
        output = Output()
        console = Console(file=output, width=100, force_terminal=True, force_interactive=True,
                          legacy_windows=False, _environ={"TERM": "xterm"})
        chunks = [RetrievedChunk("policy.md#1", "policy.md", 1, .8, "Policy source")]
        def generate():
            yield delta("First")
            self.assertIn("First", output.getvalue())
            yield delta(" final [policy.md#1]")
            yield from finish()
        events = Events(generate)
        client = SimpleNamespace(converse_stream=Mock(return_value={"stream": events}))
        with ui.use_console(console), patch("naive_rag.retrieval.retrieve_chunks", return_value=chunks), \
             patch.object(desk, "make_client", return_value=client), patch.object(ui, "answer", wraps=ui.answer) as final:
            code, result = desk._dispatch_cli(["ask", "question", "--model", "same-model", "--debug"])
        self.assertEqual(code, 0)
        self.assertEqual(result["text"], "First final [policy.md#1]")
        final.assert_called_once()
        self.assertIn("streaming draft", output.getvalue())
        self.assertTrue(events.closed)

    def test_noninteractive_rich_console_emits_deltas_without_buffering_or_reprint(self):
        output = Output()
        def generate():
            yield delta("First piece")
            self.assertIn("First piece", output.flushed)
            yield delta(" then last")
            yield from finish()
        client = SimpleNamespace(converse_stream=Mock(return_value={"stream": Events(generate)}))
        with ui.use_console(Console(file=output, force_terminal=False)), patch.object(desk, "make_client", return_value=client):
            code, result = desk._dispatch_cli(["ask", "--no-rag", "question", "--model", "same-model"])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().count("First piece then last"), 1)

    def test_debug_includes_entire_chunk_not_a_truncated_preview(self):
        chunk = RetrievedChunk("policy.md#1", "policy.md", 1, .8, "Policy text " * 40 + "FINAL_MARKER")
        for rich in (False, True):
            output = Output()
            surface = ui.use_console(Console(file=output, width=100, force_terminal=False)) if rich else contextlib.nullcontext()
            with surface, contextlib.redirect_stdout(output):
                ui.retrieved_chunks([chunk])
            self.assertIn("FINAL_MARKER", output.getvalue())

    def test_invalid_citation_visible_but_rejected_not_saved_and_usage_retained(self):
        for rich in (False, True):
            with self.subTest(rich=rich):
                output, errors, state = Output(), Output(), self.state()
                def generate():
                    yield delta("Uncited claim")
                    self.assertIn("Uncited claim", output.getvalue())
                    yield from finish()
                events = Events(generate)
                client = SimpleNamespace(converse_stream=Mock(return_value={"stream": events}))
                console = Console(file=output, width=110, force_terminal=True, legacy_windows=False)
                surface = ui.use_console(console) if rich else contextlib.nullcontext()
                with surface, contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), \
                     patch("naive_rag.retrieval.retrieve_chunks", return_value=[RetrievedChunk("policy.md#1", "policy.md", 1, .8, "Source")]), \
                     patch.object(desk, "make_client", return_value=client), patch.object(ui, "answer") as final:
                    with ui.turn_details(state, "same-model"):
                        desk.handle_command("/ask question", state)
                self.assertEqual(state["messages"], [])
                self.assertEqual((state["total_in"], state["total_out"]), (7, 4))
                self.assertIn("rejected", output.getvalue() + errors.getvalue())
                final.assert_not_called()

    def test_empty_truncated_missing_stop_and_interrupt_are_not_saved(self):
        cases = ("empty", "truncated", "missing-stop", "missing-usage", "interrupt", "network")
        for kind in cases:
            with self.subTest(kind=kind):
                output, errors, state = Output(), Output(), self.state()
                def generate():
                    if kind != "empty":
                        yield delta("Partial draft")
                    if kind == "interrupt":
                        raise KeyboardInterrupt()
                    if kind == "network":
                        raise ReadTimeoutError(endpoint_url="offline")
                    if kind == "missing-usage":
                        yield {"messageStop": {"stopReason": "end_turn"}}
                    elif kind != "missing-stop":
                        yield from finish("max_tokens" if kind == "truncated" else "end_turn")
                events = Events(generate)
                client = SimpleNamespace(converse_stream=Mock(return_value={"stream": events}))
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), patch.object(desk, "make_client", return_value=client):
                    desk.handle_command("/ask --no-rag question", state)
                self.assertEqual(state["messages"], [])
                self.assertTrue(events.closed)
                self.assertEqual(client.converse_stream.call_count, 1)
                self.assertIn("not saved", errors.getvalue())

    def test_retry_before_text_closes_stream_and_does_not_replay_partial_output(self):
        def failed():
            raise ReadTimeoutError(endpoint_url="offline")
            yield  # generator shape
        def success():
            yield delta("Only answer")
            yield from finish()
        streams = [Events(failed), Events(success)]
        client = SimpleNamespace(converse_stream=Mock(side_effect=[{"stream": stream} for stream in streams]))
        output = Output()
        with patch.object(desk, "make_client", return_value=client), patch.object(model.time, "sleep"), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(Output()):
            code, result = desk._dispatch_cli(["ask", "--no-rag", "question", "--model", "same-model"])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().count("Only answer"), 1)
        self.assertEqual(client.converse_stream.call_count, 2)
        self.assertTrue(all(stream.closed for stream in streams))


class WorkflowStreamingTests(OfflineFixture, unittest.TestCase):
    def test_ingest_phases_and_real_db_batches_are_observable_before_completion(self):
        source = self.base / "policies"
        source.mkdir()
        (source / "policy.md").write_text("return stock policy " * 30, encoding="utf-8")
        db = self.base / "vector-db"
        embedder, output, observed = FakeEmbeddings(), Output(), []
        embedder.batch_size = 2
        original = embedder.embed_documents
        calls = []
        def embed(texts):
            self.assertIn("[embedding]", output.flushed)
            if calls:
                self.assertIn("[embedded_batch]", output.flushed)
            calls.append(texts)
            return original(texts)
        def progress(event):
            observed.append(event["kind"])
            ui.progress_event(event)
            if event["kind"] == "stored_batch":
                self.assertFalse((db / "desk-policies.json").exists())
                self.assertTrue((db / "desk-policies.pending").exists())
        try:
            with contextlib.redirect_stdout(output), patch.object(embedder, "embed_documents", side_effect=embed):
                result = ingest_policies(source, db_dir=db, embedder=embedder, chunk_size=12, overlap=2, progress=progress)
            self.assertGreater(len(calls), 1)
            self.assertIn("stored_batch", observed)
            self.assertEqual(observed[-1], "ingest_complete")
            self.assertTrue((db / "desk-policies.json").exists())
            self.assertEqual(result["files_updated"], 1)
        finally:
            if db.exists():
                PolicyStore(db).client._system.stop()

    def test_validated_email_result_visible_before_next_email_not_duplicated(self):
        for rich, summary_only, limit in ((False, False, 2), (True, False, 2), (False, False, 1),
                                          (True, False, 1), (False, True, 2), (True, True, 2)):
            with self.subTest(rich=rich, summary_only=summary_only, limit=limit):
                suffix = f"{rich}-{summary_only}-{limit}"
                folder = self.base / ("emails-" + suffix)
                folder.mkdir()
                for name in ("one.eml", "two.eml"):
                    (folder / name).write_text(EMAIL, encoding="utf-8")
                destination = self.base / ("results-" + suffix)
                output, calls = Output(), []
                console = Console(file=output, width=100, force_terminal=True, legacy_windows=False)
                real_display = ui.email_result
                seen = []
                def display(value):
                    seen.append(value)
                    real_display(value)
                def extract(*args, **kwargs):
                    if calls:
                        if summary_only:
                            self.assertEqual(seen, [])
                            self.assertNotIn('"email_id": "one"', output.getvalue())
                        elif rich:
                            self.assertEqual(len(seen), 1)
                        else:
                            self.assertIn('"email_id": "one"', output.flushed)
                        self.assertNotIn('"email_id": "two"', output.getvalue())
                    calls.append(True)
                    return native_response(candidate())
                def verify(client, model_id, messages, *args, **kwargs):
                    envelope = json.loads(messages[0]["content"][0]["text"])
                    return native_response(ledger(envelope["email"], envelope["candidate"]))
                surface = ui.use_console(console) if rich else contextlib.nullcontext()
                with surface, contextlib.redirect_stdout(output), patch.object(ui, "email_result", side_effect=display), \
                     patch.object(extraction, "make_client", side_effect=lambda **kwargs: FakeClient()), \
                     patch.object(extraction, "call_structured_model", side_effect=extract), \
                     patch.object(grounding, "call_structured_model", side_effect=verify):
                    argv = ["structured-output", str(folder), "--output-dir", str(destination), "--model", "offline-test-model",
                            "--sample-size", str(limit)]
                    if summary_only:
                        argv.append("--summary-only")
                    code, result = desk._dispatch_cli(argv)
                self.assertEqual(code, 0)
                self.assertEqual(len(calls), 2)
                if rich:
                    self.assertEqual(len(seen), 0 if summary_only else min(limit, 2))
                else:
                    self.assertEqual(output.getvalue().count('"email_id": "one"'), 0 if summary_only else 1)
                    self.assertEqual(output.getvalue().count('"email_id": "two"'), 0 if summary_only or limit < 2 else 1)
                self.assertTrue(all(item["status"] == "validated" for item in result["workflow"]["manifest"]["sources"]))

    def test_local_commands_flush_immediate_results_without_provider(self):
        output = Output()
        state = dict(model="same-model", messages=[dict(role="user", content=[dict(text="Hello")]),
                       dict(role="assistant", content=[dict(text="Hi")])], total_in=0, total_out=0, history_limit=64000)
        with patch.object(session, "SAVE_DIR", str(self.base / "sessions")), \
             patch.object(desk, "make_client", side_effect=AssertionError("No provider")), contextlib.redirect_stdout(output):
            desk.handle_command("/save sample", state)
            self.assertIn("saved", output.flushed)
            desk.handle_command("/reset", state)
            self.assertIn("history cleared", output.flushed)
            desk.handle_command("/load sample", state)
            self.assertIn("loaded 'sample'", output.flushed)
            self.assertEqual(len(state["messages"]), 2)
            self.assertFalse(desk.handle_command("/exit", state))


if __name__ == "__main__":
    unittest.main()
