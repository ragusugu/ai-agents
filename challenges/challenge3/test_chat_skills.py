"""Native model-selected skill calls: stream parsing, dispatch and chat memory."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from challenges.challenge3.test_structured_output import MODEL, OfflineFixture
from challenges.challenge3.test_challenge3_contract import expected_fields
import chat_commands
import desk
import model
import skill_tools
from challenge3_structured_output import structured_output


class EventStream(list):
    closed = False

    def close(self):
        self.closed = True


def tool_stream(args, *, stop="tool_use", name="structured_output", complete=True):
    raw = args if isinstance(args, str) else json.dumps(args)
    split = len(raw) // 2
    events = [
        {"contentBlockStart": {"contentBlockIndex": 1, "start": {"toolUse": {"toolUseId": "call-1", "name": name}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": raw[:split]}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": raw[split:]}}}},
    ]
    if complete:
        events.append({"contentBlockStop": {"contentBlockIndex": 1}})
    events.extend([{"messageStop": {"stopReason": stop}},
                   {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5}}}])
    return EventStream(events)


def text_stream(text, usage=None):
    return EventStream([
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}},
        {"messageStop": {"stopReason": "end_turn"}},
        {"metadata": {"usage": usage or {"inputTokens": 4, "outputTokens": 2}}},
    ])


class StreamTests(unittest.TestCase):
    def test_fragmented_arguments_are_collected_without_printing_them(self):
        tools, output = [], io.StringIO()
        with contextlib.redirect_stdout(output):
            text, usage, _, _, stop = model._render_stream(tool_stream({"source": "folder with spaces"}), time.perf_counter(), tool_uses=tools)
        self.assertEqual((text, stop, usage["inputTokens"]), ("", "tool_use", 10))
        self.assertEqual(tools[0]["input"], {"source": "folder with spaces"})
        self.assertNotIn("folder with spaces", output.getvalue())

    def test_incomplete_malformed_and_non_object_tool_inputs_never_escape(self):
        for args, stop, complete in [("{", "max_tokens", True), ("{", "tool_use", True),
                                     ("[]", "tool_use", True), ({"source": "x"}, "end_turn", True),
                                     ({"source": "x"}, "tool_use", False)]:
            with self.subTest(args=args, stop=stop, complete=complete):
                tools = []
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(model.DeskError):
                    model._render_stream(tool_stream(args, stop=stop, complete=complete), time.perf_counter(), tool_uses=tools)
                self.assertEqual(tools, [])

    def test_stream_failure_does_not_publish_or_duplicate_a_partial_tool(self):
        from botocore.exceptions import ReadTimeoutError
        calls, tools = [], []
        def failed():
            yield tool_stream({"source": "x"})[0]
            raise ReadTimeoutError(endpoint_url="offline")
        good = tool_stream({"source": "x"})
        streams = iter([failed(), good])
        def converse(**kwargs):
            calls.append(kwargs)
            return {"stream": next(streams)}
        client = SimpleNamespace(converse_stream=converse)
        with patch.object(model.time, "sleep"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = model.stream_model(client, MODEL, [], None, 1000, "test",
                tool_config=skill_tools.tool_config(), tool_uses=tools)
        self.assertEqual(response[4], 2)
        self.assertEqual(len(tools), 1)
        self.assertTrue(good.closed)
        self.assertEqual(calls[0]["toolConfig"]["tools"][0]["toolSpec"]["name"], "structured_output")


class ChatSkillTests(OfflineFixture, unittest.TestCase):
    def state(self):
        return dict(model=MODEL, messages=[], total_in=0, total_out=0, history_limit=64000)

    def test_selected_skill_with_natural_arguments_is_forwarded_to_llm(self):
        for text in ["/structured-output data/emails source and store in the output folder", "/structured-output"]:
            state = self.state()
            with self.subTest(text=text), patch.object(desk, "_dispatch_cli") as dispatch:
                self.assertTrue(desk.handle_command(text, state))
                self.assertEqual(state["pending_user_input"], text)
                dispatch.assert_not_called()

    def test_selected_skill_with_valid_options_remains_a_local_shortcut(self):
        state = self.state()
        with patch.object(desk, "_dispatch_cli", return_value=(0, None)) as dispatch:
            desk.handle_command('/structured-output "data/emails" --output-dir "output"', state)
        self.assertNotIn("pending_user_input", state)
        self.assertEqual(dispatch.call_args.args[0][:5], ["structured-output", "data/emails", "--output-dir", "output", "--model"])

    def test_misspelled_cli_option_is_reported_without_sending_it_to_model(self):
        state = self.state()
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            desk.handle_command("/structured-output data/emails --unknown-flag", state)
        self.assertNotIn("pending_user_input", state)
        self.assertIn("unrecognized arguments", error.getvalue())

    def labels(self):
        path = self.base / "labels.json"
        path.write_text(json.dumps(dict(version=1, provenance=dict(kind="assistant_source_draft", author="synthetic test",
            created_on="2026-11-26", method="Synthetic fixture", human_review=dict(status="pending", reviewer=None, reviewed_on=None)),
            labels=[dict(source=dict(id=self.email.stem, relative_path=str(self.email), sha256=hashlib.sha256(self.email.read_bytes()).hexdigest()),
                         expected=expected_fields().model_dump(mode="json"), notes="Synthetic fixture")])), encoding="utf-8")
        return path

    def test_paths_with_spaces_and_flags_use_argv_not_a_shell(self):
        source = self.base / "email folder"; source.mkdir()
        args = skill_tools.workflow_argv(dict(name="structured_output", input=dict(source=str(source),
            output_dir=str(self.base / "output folder"), sample_size=2, plan_only=True)))
        parsed = desk.build_parser().parse_args(args)
        self.assertEqual(parsed.source, str(source))
        self.assertEqual(parsed.output_dir, str(self.base / "output folder"))
        self.assertTrue(parsed.plan_only)
        self.assertEqual(parsed.sample_size, 2)

    def test_invalid_unknown_or_multiple_tools_never_dispatch(self):
        cases = [[dict(name="shell", input={})],
                 [dict(name="structured_output", input=dict(source=str(self.email), model="other-model"))],
                 [dict(name="structured_output", input=dict(source=str(self.email), sample_size=True))],
                 [dict(name="structured_output", input={})],
                 [dict(name="structured_output", input=dict(source=str(self.email)))] * 2]
        for tools in cases:
            with self.subTest(tools=tools), patch.object(desk, "_dispatch_cli") as dispatch, contextlib.redirect_stdout(io.StringIO()):
                state = self.state()
                desk._run_chat_skill(tools, "Use the skill", state)
                dispatch.assert_not_called()
                self.assertEqual(len(state["messages"]), 2)

    def test_missing_singular_folder_suggests_plural_without_running_it(self):
        (self.base / "emails").mkdir()
        with self.assertRaisesRegex(model.DeskError, "Did you mean"):
            skill_tools.workflow_argv(dict(name="structured_output", input=dict(source=str(self.base / "email"))))

    def test_workflow_failure_is_remembered_as_an_error_not_completion(self):
        state = self.state()
        with patch.object(desk, "_dispatch_cli", side_effect=model.DeskError("Output storage is locked; no further emails were sent.")), \
             contextlib.redirect_stdout(io.StringIO()):
            desk._run_chat_skill([dict(name="structured_output", input=dict(source=str(self.email)))],
                                 "Use the skill on my email", state)
        self.assertEqual(state["messages"][-1]["content"][0]["text"], "Output storage is locked; no further emails were sent.")

    def test_model_selected_skill_runs_workflow_and_remembers_real_accuracy(self):
        out = self.base / "reused results"
        self.run_extraction(output=out)
        labels = self.labels()
        request = f'Use tis skill and data in "{self.email}", keep results in "{out}" and show accuracy.'
        calls = []
        streams = iter([tool_stream(dict(source=str(self.email), output_dir=str(out), labels=str(labels), summary_only=True)),
                        text_stream("The saved source was the email file you supplied.")])
        def converse(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            return dict(stream=next(streams))
        client = SimpleNamespace(converse_stream=converse)
        inputs = iter([request, "Which source did you process?", "/exit"])
        output = io.StringIO()
        with patch.object(desk, "make_client", return_value=client), \
             patch.object(chat_commands, "chat_reader", return_value=lambda _: next(inputs)), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            desk.cmd_chat(SimpleNamespace(model=MODEL, temperature=None))
        self.assertEqual(len(calls), 2)
        history = calls[1]["messages"]
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "user"])
        self.assertEqual(history[0]["content"][0]["text"], request)
        self.assertIn("Assistant draft agreement (human review pending): 100.0%", history[1]["content"][0]["text"])
        self.assertIn(str(self.email), history[1]["content"][0]["text"])
        self.assertTrue(all(set(block) == {"text"} for m in history for block in m["content"]))
        self.assertIn("new requests: 0", output.getvalue())

    def test_chat_without_explicit_labels_never_checks_project_drafts(self):
        out = self.base / "unlabelled results"
        self.run_extraction(output=out)
        labels = self.labels()
        for route in ("slash", "tool"):
            with self.subTest(route=route):
                state = self.state()
                output = io.StringIO()
                # A matching draft file exists, but the workflow must not even
                # resolve it unless the caller supplies a label-file path.
                with patch.object(structured_output, "Path", return_value=labels) as label_path, \
                     patch.object(structured_output, "accuracy_report") as score, \
                     patch.object(structured_output, "write_label_review") as review, \
                     contextlib.redirect_stdout(output):
                    if route == "slash":
                        desk.handle_command(
                            f'/structured-output "{self.email}" --output-dir "{out}" --summary-only', state)
                    else:
                        desk._run_chat_skill([dict(name="structured_output", input=dict(
                            source=str(self.email), output_dir=str(out), summary_only=True))],
                            "Use the structured-output skill on my email", state)
                label_path.assert_not_called()
                score.assert_not_called()
                review.assert_not_called()
                self.assertEqual(len(state["messages"]), 2)
                note = state["messages"][-1]["content"][0]["text"]
                self.assertIn("Validation: 1/1 accounted for", note)
                self.assertIn("Accuracy: unmeasured", note)
                self.assertNotIn("Assistant draft agreement", note)
                self.assertNotIn("Assistant draft agreement", output.getvalue())
                self.assertFalse((out / "accuracy-report.json").exists())

    def test_normal_reply_and_clarification_do_not_execute_workflows(self):
        streams = iter([text_stream("Which email folder should I use?"), text_stream("I can explain the skill without running it.")])
        client = SimpleNamespace(converse_stream=lambda **kw: dict(stream=next(streams)))
        inputs = iter(["Use the structured-output skill", "Just explain it, do not run it", "exit"])
        with patch.object(desk, "make_client", return_value=client), \
             patch.object(chat_commands, "chat_reader", return_value=lambda _: next(inputs)), \
             patch.object(desk, "_run_chat_skill") as run, contextlib.redirect_stdout(io.StringIO()):
            desk.cmd_chat(SimpleNamespace(model=MODEL, temperature=None))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
