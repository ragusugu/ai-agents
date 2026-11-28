"""Slash completion at the cursor, including skill mentions inside a sentence."""

import asyncio
import contextlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from chat_commands import command_catalog, create_completer, create_prompt_session
from desk import build_parser


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.commands = command_catalog(build_parser())
        self.completer = create_completer(lambda: self.commands)

    def complete(self, text, cursor=None):
        return list(self.completer.get_completions(Document(text, cursor_position=cursor), CompleteEvent(text_inserted=True)))

    def test_slash_at_start_or_inside_sentence_shows_same_eight_commands(self):
        expected = {"/" + name for name in self.commands}
        self.assertEqual(len(expected), 8)
        for text in ["/", "I need to structure my email by using /", "Please use (/", "Use\n/"]:
            with self.subTest(text=text):
                self.assertEqual({c.text for c in self.complete(text)}, expected)

    def test_screenshot_prefix_filters_inline_commands(self):
        values = self.complete("i need to structure my email by using /s")
        self.assertEqual({c.text for c in values}, {"/save", "/structured-output"})
        self.assertTrue(all(c.start_position == -2 for c in values))

    def test_selection_preserves_text_before_and_after_cursor(self):
        text = "Please use /st with data/emails and save in output"
        cursor = len("Please use /st")
        completion = next(c for c in self.complete(text, cursor) if c.text == "/structured-output")
        buffer = Buffer(document=Document(text, cursor_position=cursor))
        buffer.apply_completion(completion)
        self.assertEqual(buffer.text, "Please use /structured-output with data/emails and save in output")
        self.assertEqual(buffer.cursor_position, len("Please use /structured-output"))

    def test_path_url_and_escaped_slashes_do_not_trigger_menu(self):
        for text in ["data/emails", "data/s", "https://", "https://example.test/s", "C:/s", "./s", r"use \/s", "3/4"]:
            with self.subTest(text=text):
                self.assertEqual(self.complete(text), [])

    def test_flags_complete_after_inline_skill_without_popup_in_prose(self):
        values = self.complete("Please use /structured-output data/emails --s")
        self.assertEqual({c.text for c in values}, {"--sample-size", "--summary-only"})
        self.assertEqual(self.complete("Please use /structured-output and save "), [])
        self.assertEqual({c.text for c in self.complete("/structured-output data/emails --s")},
                         {"--sample-size", "--summary-only"})

    def test_last_slash_selection_controls_current_completion(self):
        values = self.complete("Explain /ask first, then use /st")
        self.assertEqual([c.text for c in values], ["/structured-output"])


class InteractiveCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_opens_while_typing_inside_real_prompt_session(self):
        commands = command_catalog(build_parser())
        with create_pipe_input() as pipe:
            session = create_prompt_session(lambda: commands, input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async("> "))
            try:
                pipe.send_text("i need to structure my email by using /s")
                for _ in range(100):
                    state = session.default_buffer.complete_state
                    if state is not None and state.completions:
                        break
                    await asyncio.sleep(0.02)
                self.assertIsNotNone(state)
                completion = next(c for c in state.completions if c.text == "/structured-output")
                session.default_buffer.apply_completion(completion)
                pipe.send_text("\r")
                result = await asyncio.wait_for(task, timeout=3)
                self.assertEqual(result, "i need to structure my email by using /structured-output")
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task


if __name__ == "__main__":
    unittest.main()
