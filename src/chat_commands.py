"""Seven-command chat menu, CLI option completion and terminal styling."""

import argparse
import sys
from dataclasses import dataclass

from model import DeskError

CHAT_COMMANDS = {
    "ask": ("Ask a single question", "<question>"),
    "chat": ("Continue the conversation", "[message]"),
    "reset": ("Start a fresh conversation", ""),
    "exit": ("Leave Desk", ""),
    "load": ("Open a saved session", "<name>"),
    "save": ("Save this session", "<name>"),
    "structured-output": ("Extract emails into JSON", "<path> [options]"),
}


@dataclass
class ChatCommand:
    name: str
    description: str
    usage: str = ""
    parser: argparse.ArgumentParser | None = None
    cli_command: str | None = None


def subcommands(parser):
    return {name: child for action in parser._actions if isinstance(action, argparse._SubParsersAction)
            for name, child in action.choices.items()}


def command_catalog(parser):
    """Expose the seven chat commands; retain CLI parsers for option completion."""
    cli = subcommands(parser)
    commands = {name: ChatCommand(name, description, usage,
                                  cli.get(name) if name in {"ask", "structured-output"} else None,
                                  name if name in {"ask", "structured-output"} else None)
                for name, (description, usage) in CHAT_COMMANDS.items()}
    return commands


def print_command_menu(commands, prefix=""):
    print("\n  DESK / commands\n")
    for name, command in commands.items():
        if not name.startswith(prefix):
            continue
        print(f"  {'/' + name:<22} {command.description}")
    print("\n  /save <name>  /load <name>  /structured-output <path>\n")


def create_completer(catalog_provider):
    from prompt_toolkit.completion import Completer, Completion

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            commands = catalog_provider()
            if not any(c.isspace() for c in text):
                for name, command in commands.items():
                    if name.startswith(text[1:].lower()):
                        yield Completion("/" + name, start_position=-len(text),
                                         display_meta=command.description)
                return
            name = text.split()[0][1:].lower()
            command = commands.get(name)
            if command is None or command.parser is None:
                return
            token = text.split()[-1] if not text[-1].isspace() else ""
            options = {flag: action.help or "" for action in command.parser._actions for flag in action.option_strings}
            for child, parser in subcommands(command.parser).items():
                options[child] = parser.description or "subcommand"
            for option, description in options.items():
                if option.startswith(token):
                    yield Completion(option, start_position=-len(token), display_meta=description)

    return SlashCompleter()


def create_prompt_session(catalog_provider, **kwargs):
    from prompt_toolkit import PromptSession
    from prompt_toolkit.styles import Style
    from prompt_toolkit.application import get_app

    style = Style.from_dict({
        "prompt": "#7dd3fc bold",
        "completion-menu": "bg:#1c222b #dbe4ee",
        "completion-menu.completion": "bg:#1c222b #dbe4ee",
        "completion-menu.completion.current": "bg:#173f50 #e0f2fe bold noreverse",
        "completion-menu.meta.completion": "bg:#1c222b #8c9aaa",
        "completion-menu.meta.completion.current": "bg:#173f50 #a5d8ee noreverse",
        "scrollbar.background": "bg:#1c222b",
        "scrollbar.button": "bg:#3c4b5c",
        "bottom-toolbar": "bg:default #7b8a9b noreverse",
    })

    def toolbar():
        if get_app().current_buffer.text.startswith("/"):
            return "  Arrows: select   Tab: complete   Enter: run   Esc: close"
        return ""

    return PromptSession(completer=create_completer(catalog_provider), complete_while_typing=True,
                         enable_history_search=False, reserve_space_for_menu=7,
                         style=style, bottom_toolbar=toolbar, **kwargs)


def chat_reader(catalog_provider):
    # Keep redirected input and tests compatible with the original input() loop.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return input
    try:
        session = create_prompt_session(catalog_provider)
    except ImportError as exc:
        raise DeskError("Install requirements.txt to enable the interactive slash menu.") from exc
    return lambda _message: session.prompt([("class:prompt", "> ")])
