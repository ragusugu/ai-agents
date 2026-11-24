"""Desk, Challenge 2: multi-turn conversation and streaming CLI.

Usage:
    desk ask "your question" [--model ID] [--temperature T]     (desk.cmd launcher)
    desk chat [--model ID] [--temperature T]
    python src/desk.py ask|chat ...                             (direct)

Provider: Amazon Bedrock via the raw boto3 SDK (Converse / ConverseStream API).
"""

import argparse
import os
import sys

# Ensure src directory is on sys.path for internal imports
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from constants import (
    CHAT_SYSTEM_PROMPT,
    MAX_HISTORY_TOKENS,
)
from model import (
    DeskError,
    call_model,
    estimate_cost,
    make_client,
    stream_model,
)
from terminal import Terminal
from session import (
    _estimate_tokens,
    _sent_tokens,
    load_session,
    save_session,
    trim_history,
)

# Re-exports for backwards compatibility
__all__ = [
    "DeskError",
    "make_client",
    "call_model",
    "stream_model",
    "estimate_cost",
    "save_session",
    "load_session",
    "trim_history",
    "cmd_ask",
    "cmd_chat",
    "main",
]


def load_dotenv(path=None):
    """Load variables from a .env file into os.environ if not already present."""
    if path is None:
        # Check project root (.env in parent of src)
        root_dir = os.path.dirname(SRC_DIR)
        path = os.path.join(root_dir, ".env")
        if not os.path.exists(path):
            path = os.path.join(SRC_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v


load_dotenv()

CHAT_HELP = (
    "Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit"
)


def cmd_ask(args):
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError(
            "DESK_MODEL environment variable is not set. "
            "Please specify it in your .env file or pass --model."
        )
    max_tokens = int(os.environ.get("DESK_MAX_TOKENS", "4000"))
    client = make_client()
    text, usage, latency, attempts, stop = call_model(
        client, model, args.question, args.temperature, max_tokens
    )
    print(text if text else "(model returned no text; try a larger DESK_MAX_TOKENS)")
    if stop == "max_tokens":
        print("\n[warning: output was cut off at max tokens]", file=sys.stderr)
    print(
        f"\n--\nmodel: {model} | in: {usage['inputTokens']} tok | out: {usage['outputTokens']} tok "
        f"| latency: {latency:.2f}s | cost: {estimate_cost(usage)}"
        + (f" | attempts: {attempts}" if attempts > 1 else "")
    )


def handle_command(line, state):
    """Run a /command locally (never sent to the model). Returns False to end the chat."""
    cmd, _, arg = line.partition(" ")
    cmd, arg = cmd.lower(), arg.strip()
    if cmd in ("/exit", "/quit"):
        return False
    if cmd == "/help":
        print(CHAT_HELP)
    elif cmd == "/reset":
        state["messages"].clear()
        state["total_in"] = state["total_out"] = 0
        print("[history cleared; the next message starts a fresh conversation]")
    elif cmd in ("/save", "/load") and not arg:
        print(f"usage: {cmd} <name>")
    elif cmd == "/save":
        try:
            path = save_session(arg, state)
            print(f"[saved {len(state['messages'])} messages to {path}]")
        except DeskError as err:
            print(f"desk: {err}", file=sys.stderr)
    elif cmd == "/load":
        try:
            data = load_session(arg)
        except DeskError as err:
            print(f"desk: {err}", file=sys.stderr)
            return True
        state["messages"][:] = data["messages"]
        state["total_in"] = data.get("total_in", 0)
        state["total_out"] = data.get("total_out", 0)
        print(f"[loaded '{arg}': {len(state['messages'])} messages, saved {data.get('saved_at', '?')}]")
        if state["messages"]:
            last = state["messages"][-1]["content"][0].get("text", "")
            print(f"[last {state['messages'][-1]['role']} message: {last[:120]}]")
    else:
        print(f"Unknown command: {cmd}. {CHAT_HELP}")
    return True


def cmd_chat(args):
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError(
            "DESK_MODEL environment variable is not set. "
            "Please specify it in your .env file or pass --model."
        )
    max_tokens = int(os.environ.get("DESK_MAX_TOKENS", "4000"))
    history_limit = int(os.environ.get("DESK_HISTORY_TOKENS", MAX_HISTORY_TOKENS))
    client = make_client()
    # Everything the chat remembers lives here; /save and /load read and write it.
    state = {"model": model, "messages": [], "total_in": 0, "total_out": 0}
    messages = state["messages"]

    terminal = Terminal()
    terminal.banner()

    while True:
        try:
            # Windows PowerShell prefixes piped input with a BOM, which would hide a leading "/".
            user_input = input(terminal.prompt()).lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if user_input.startswith("/"):
            if not handle_command(user_input, state):
                print("Goodbye!")
                break
            continue

        # Append user turn to message history
        messages.append({"role": "user", "content": [{"text": user_input}]})

        dropped = trim_history(messages, history_limit)
        if dropped:
            print(
                f"[window: dropped {dropped} oldest turn(s); kept first exchange + "
                f"{len(messages) - 2} recent messages, ~{_estimate_tokens(messages)} tok]"
            )

        terminal.assistant()
        try:
            text, usage, latency, first_token, attempts, stop = stream_model(
                client, model, messages, args.temperature, max_tokens, CHAT_SYSTEM_PROMPT
            )
        except DeskError as err:
            print(f"desk: {err}", file=sys.stderr)
            messages.pop()
            continue

        if not text:
            # An empty assistant turn would make every later request fail validation.
            print("(model returned no text; try a larger DESK_MAX_TOKENS)", file=sys.stderr)
            messages.pop()
            continue
        if stop == "max_tokens":
            print("\n[warning: output was cut off at max tokens]", file=sys.stderr)

        # Append assistant response to message history
        messages.append({"role": "assistant", "content": [{"text": text}]})

        # Track usage
        sent = _sent_tokens(usage)
        cached = usage.get("cacheReadInputTokens", 0)
        state["total_in"] += sent
        state["total_out"] += usage.get("outputTokens", 0)

        terminal.usage(
            sent, usage.get("outputTokens", 0), cached, latency, first_token,
            state["total_in"], state["total_out"], _estimate_tokens(messages),
            history_limit, attempts,
        )


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="desk", description="Desk: Meridian Supply Co. assistant")
    sub = parser.add_subparsers(dest="command")

    ask = sub.add_parser("ask", help="send one question to the model")
    ask.add_argument("question")
    ask.add_argument("--model", help="override DESK_MODEL")
    ask.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    ask.set_defaults(func=cmd_ask)

    chat = sub.add_parser("chat", help="start an interactive conversation session")
    chat.add_argument("--model", help="override DESK_MODEL")
    chat.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    chat.set_defaults(func=cmd_chat)
    if argv is None and len(sys.argv) == 1:
        parser.print_help()
        print("\nExample:\n  desk ask \"What is a ball valve?\"")
        return 0
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        args.func(args)
    except DeskError as exc:
        print(f"desk: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
