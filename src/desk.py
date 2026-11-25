"""Desk: questions, streaming chat and schema-validated email extraction.

Usage:
    desk                                                     (start chat)
    desk ask "your question" [--model ID] [--temperature T]     (desk.cmd launcher)
    desk chat [--model ID] [--temperature T]
    desk structured-output path/to/emails [--labels path/to/labels.json]
    python src/desk.py ask|chat ...                             (direct)

Provider: Amazon Bedrock via the raw boto3 SDK (Converse / ConverseStream API).
"""

import argparse
import json
import os
import shlex
import sys

# Ensure src directory is on sys.path for internal imports
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from constants import (
    CHAT_SYSTEM_PROMPT,
    DEFAULT_CHAT_MAX_TOKENS,
    MAX_HISTORY_TOKENS,
)
from model import (
    DeskError,
    call_model,
    estimate_cost,
    make_client,
    stream_model,
)
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
    "Type / for commands. Use arrows + Tab to select; Esc to close."
)
DEFAULT_SAMPLE_SIZE = 15


def cmd_ask(args):
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError(
            "DESK_MODEL environment variable is not set. "
            "Please specify it in your .env file or pass --model."
        )
    max_tokens = int(os.environ.get("DESK_MAX_TOKENS", DEFAULT_CHAT_MAX_TOKENS))
    client = make_client()
    question = " ".join(args.question) if isinstance(args.question, list) else args.question
    text, usage, latency, attempts, stop = call_model(
        client, model, question, args.temperature, max_tokens
    )
    print(text if text else "(model returned no text; try a larger DESK_MAX_TOKENS)")
    if stop == "max_tokens":
        print("\n[warning: output was cut off at max tokens]", file=sys.stderr)
    print(
        f"\n--\nmodel: {model} | in: {usage['inputTokens']} tok | out: {usage['outputTokens']} tok "
        f"| latency: {latency:.2f}s | cost: {estimate_cost(usage)}"
        + (f" | attempts: {attempts}" if attempts > 1 else "")
    )
    return {"command": "ask", "question": question, "text": text, "usage": usage}


def _session_history_limit(state):
    return state.get("history_limit", int(os.environ.get("DESK_HISTORY_TOKENS", MAX_HISTORY_TOKENS)))


def _record_session_turn(state, user_text, assistant_text, *, usage=None):
    """Store a slash-command exchange in unified chat memory and apply the sliding window."""
    if not user_text or not assistant_text:
        return
    messages = state["messages"]
    messages.append({"role": "user", "content": [{"text": user_text}]})
    messages.append({"role": "assistant", "content": [{"text": assistant_text}]})
    if usage is not None:
        state["total_in"] += _sent_tokens(usage)
        state["total_out"] += usage.get("outputTokens", 0)
    history_limit = _session_history_limit(state)
    dropped = trim_history(messages, history_limit)
    if dropped:
        print(
            f"[window: dropped {dropped} oldest turn(s); kept first exchange + "
            f"{len(messages) - 2} recent messages, ~{_estimate_tokens(messages)} tok]"
        )
    print(f"[saved to session memory | history: ~{_estimate_tokens(messages)}/{history_limit} tok]")


def handle_command(line, state):
    """Dispatch the seven supported chat commands. False exits chat."""
    from chat_commands import command_catalog, print_command_menu
    commands = command_catalog(build_parser())
    parts = line.split(maxsplit=1)
    cmd, arg = parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""
    if cmd == "/exit":
        return False
    if cmd == "/":
        print_command_menu(commands)
    elif cmd == "/chat":
        if arg:
            state["pending_user_input"] = arg
        else:
            print("You're in chat. Enter a message, or use /reset to start fresh.")
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
    elif cmd[1:] in commands:
        command = commands[cmd[1:]]
        # Preserve unquoted Windows backslashes and quoted paths with spaces.
        try:
            tokens = [token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"
                      else token for token in shlex.split(arg, posix=False)]
            if not tokens and any(a.required and not a.option_strings for a in command.parser._actions):
                command.parser.print_help()
                return True
            supports_model = any("--model" in a.option_strings for a in command.parser._actions)
            if supports_model and state.get("model") and not any(token == "--model" or token.startswith("--model=") for token in tokens):
                tokens += ["--model", state["model"]]
            exit_code, result = _dispatch_cli([command.cli_command, *tokens])
            if exit_code == 0 and isinstance(result, dict):
                if result.get("command") == "ask" and result.get("text"):
                    _record_session_turn(state, line, result["text"], usage=result.get("usage"))
                elif result.get("command") == "structured-output":
                    budget = max(_session_history_limit(state) * 2, 16000)
                    summary = _format_structured_session_note(result["workflow"], result["args"], max_chars=budget)
                    _record_session_turn(state, line, summary)
        except ValueError as err:
            print(f"desk: {err}", file=sys.stderr)
        except SystemExit:
            # argparse usage errors must not terminate an interactive chat.
            pass
    else:
        matches = [name for name in commands if name.startswith(cmd[1:])]
        if matches:
            print_command_menu(commands, prefix=cmd[1:])
        else:
            print(f"Unknown command: {cmd}. Type / to see available commands.")
    return True


def cmd_chat(args):
    from chat_commands import chat_reader, command_catalog
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError(
            "DESK_MODEL environment variable is not set. "
            "Please specify it in your .env file or pass --model."
        )
    max_tokens = int(os.environ.get("DESK_MAX_TOKENS", DEFAULT_CHAT_MAX_TOKENS))
    history_limit = int(os.environ.get("DESK_HISTORY_TOKENS", MAX_HISTORY_TOKENS))
    client = None  # Local slash commands do not need AWS access.
    # Everything the chat remembers lives here; /save and /load read and write it.
    state = {"model": model, "messages": [], "total_in": 0, "total_out": 0, "history_limit": history_limit}
    messages = state["messages"]

    print("Desk Chat (Meridian Supply Co.)")
    print(CHAT_HELP + "\n")
    read_line = chat_reader(lambda: command_catalog(build_parser()))

    while True:
        try:
            # Windows PowerShell prefixes piped input with a BOM, which would hide a leading "/".
            user_input = read_line("> ").lstrip("﻿").strip()
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
            user_input = state.pop("pending_user_input", "")
            if not user_input:
                continue

        # Append user turn to message history
        messages.append({"role": "user", "content": [{"text": user_input}]})

        dropped = trim_history(messages, history_limit)
        if dropped:
            print(
                f"[window: dropped {dropped} oldest turn(s); kept first exchange + "
                f"{len(messages) - 2} recent messages, ~{_estimate_tokens(messages)} tok]"
            )

        print()
        try:
            if client is None:
                client = make_client()
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

        first = f"{first_token:.2f}s" if first_token is not None else "n/a"
        print(
            f"\n--\nTurn: in {sent} tok" + (f" ({cached} cached)" if cached else "")
            + f" | out {usage.get('outputTokens', 0)} tok "
            f"| first token: {first} | total: {latency:.2f}s "
            f"| Session Total: in {state['total_in']} tok | out {state['total_out']} tok "
            f"| history: ~{_estimate_tokens(messages)}/{history_limit} tok"
            + (f" | attempts: {attempts}" if attempts > 1 else "")
        )
        print()


def cmd_rebuild_output(args):
    from extraction import rebuild_outputs
    rebuild_outputs()
    print("Recovered local output tracking; no model call was made.")


def _batch_options(args):
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError("Set DESK_MODEL or pass --model.")
    try:
        max_tokens = args.max_tokens if args.max_tokens is not None else int(os.environ.get("DESK_MAX_TOKENS", "4000"))
    except ValueError as exc:
        raise DeskError("DESK_MAX_TOKENS must be a positive integer.") from exc
    if max_tokens <= 0:
        raise DeskError("max-tokens must be positive.")
    return model, max_tokens


def _show_batch_progress(event):
    if event["kind"] == "email_complete":
        print(f"[{event['completed']}/{event['total']}] {event['source_id']}: {event['status']} ({event['action']})", flush=True)


def _ordered_outcomes(manifest, *, output_dir=None):
    """Collect persisted outcomes in manifest order without altering tracking."""
    from extraction import read_run_history
    _, rows = read_run_history(output_dir)
    by_run = {row["run_id"]: row for row in rows}
    outcomes = []
    for email in manifest["sources"]:
        row = by_run.get(email["run_id"])
        if row is None:
            raise DeskError("Sample outcome is missing from tracking; inspect the batch manifest.")
        value = {"email_id": email["id"], "status": row["status"], "result": row["data"]}
        if row["status"] == "needs_review":
            value["reason"] = row["reason"]
        outcomes.append(value)
    return outcomes


def print_result_sample(manifest, *, sample_size=DEFAULT_SAMPLE_SIZE, output_dir=None):
    """Display a bounded sample without changing extraction or stored results."""
    outcomes = _ordered_outcomes(manifest, output_dir=output_dir)
    selected = outcomes[:sample_size]
    print(f"\nSample outputs: {len(selected)} of {len(outcomes)} processed emails")
    for value in selected:
        print(json.dumps(value, ensure_ascii=False))


def _format_structured_session_note(result, args, *, max_chars=96000):
    """Format workflow summary, accuracy report, and outcomes for unified chat memory."""
    plan = result["plan"]
    lines = [
        f"Emails: {plan['source_count']} | reusable: {plan['reused_count']} | new requests: {plan['new_email_payloads']}",
        result["label_note"],
    ]
    if args.plan_only:
        lines.append(f"Offline plan: {result['plan_path']} | no model calls made")
        return "\n".join(lines)

    manifest = result["manifest"]
    lines.append(f"Batch: {manifest['status']} | manifest: {result['manifest_path']}")
    lines.append(f"Outputs: {plan['output_dir']}/results.jsonl")
    report = result.get("report")
    if report is not None:
        cov = report["coverage"]
        overall = report["overall"]
        overall_pct = "unmeasured" if overall["score"] is None else f"{overall['score']:.1%}"
        lines.append(
            f"Evaluation ({report['measurement_kind']}): validated {cov['validated']}/{cov['labels']}, "
            f"missing {cov['missing']}, review {cov['needs_review']}, "
            f"overall {overall['correct']}/{overall['total']} ({overall_pct}), report: {result['report_path']}"
        )
        field_summary = ", ".join(
            f"{k}: {v['correct']}/{v['total']}" for k, v in report["fields"].items()
        )
        lines.append(f"Field scores: {field_summary}")
    if result.get("review_path"):
        lines.append(f"Human label review: {result['review_path']}")

    outcomes = _ordered_outcomes(manifest, output_dir=plan["output_dir"])
    shown = 0 if args.summary_only else min(args.sample_size, len(outcomes))
    lines.append(f"Terminal displayed first {shown} of {len(outcomes)} emails. Processed outcomes:")
    used_chars = sum(len(line) + 1 for line in lines)
    included = 0
    for value in outcomes:
        row_text = json.dumps(value, ensure_ascii=False)
        if used_chars + len(row_text) + 1 > max_chars:
            lines.append(
                f"... ({len(outcomes) - included} more outcomes omitted to fit session history budget; "
                f"full results at {plan['output_dir']}/results.jsonl)"
            )
            break
        lines.append(row_text)
        used_chars += len(row_text) + 1
        included += 1
    return "\n".join(lines)


def print_accuracy_report(path, report, *, show_results=False, output_dir=None,
                          sample_size=DEFAULT_SAMPLE_SIZE, include_emails=True):
    coverage = report["coverage"]
    print(f"\n{report['measurement_kind']} | validated coverage: {coverage['validated']}/{coverage['labels']} "
          f"| missing: {coverage['missing']} | review: {coverage['needs_review']}")
    predictions = {}
    if show_results and include_emails:
        from extraction import read_run_history
        _, rows = read_run_history(output_dir)
        predictions = {row["run_id"]: row for row in rows}
    emails = report["emails"][:sample_size] if include_emails else []
    if include_emails:
        print(f"Evaluation sample: {len(emails)} of {len(report['emails'])} labelled emails (all labels scored)")
        print("email | status | incorrect fields")
    for email in emails:
        incorrect = ", ".join(email["incorrect_fields"]) or "none"
        print(f"{email['source_id']} | {email['status']} | {incorrect}")
        if show_results:
            row = predictions.get(email["run_id"])
            print(json.dumps({"email_id": email["source_id"], "status": email["status"],
                              "result": row["data"] if row else None}, ensure_ascii=False))
    print("\nfield | correct / total | score")
    for field, values in report["fields"].items():
        score = "unmeasured" if values["score"] is None else f"{values['score']:.1%}"
        print(f"{field} | {values['correct']} / {values['total']} | {score}")
    print(f"Report: {path}")
    if report["label_provenance"]["human_review"]["status"] != "approved":
        print("Assistant draft labels await human review; this is not a human-labelled accuracy claim.")


def cmd_structured_output(args):
    from schemas import SCHEMA_PATH
    from structured_output import run_workflow
    model, max_tokens = _batch_options(args)
    print(f"Schema template: {SCHEMA_PATH}")
    result = run_workflow(args.source, model, max_tokens=max_tokens, labels_path=args.labels,
        plan_only=args.plan_only, retry_review=args.retry_review, expected_count=args.expected_count,
        require_reviewed=args.require_reviewed, progress=_show_batch_progress, output_dir=args.output_dir)
    plan = result["plan"]
    print(f"Emails: {plan['source_count']} | reusable: {plan['reused_count']} | new requests: {plan['new_email_payloads']}")
    print(result["label_note"])
    if args.plan_only:
        print(f"Offline plan: {result['plan_path']} | no model calls made")
        return {"command": "structured-output", "workflow": result, "args": args}
    print(f"Batch: {result['manifest']['status']} | {result['manifest_path']}")
    print(f"Outputs: {plan['output_dir']}/results.jsonl and needs_review.jsonl (when needed)")
    if not args.summary_only:
        print_result_sample(result["manifest"], sample_size=args.sample_size, output_dir=plan["output_dir"])
    if result["report"] is not None:
        print_accuracy_report(result["report_path"], result["report"], include_emails=False)
    if result["review_path"]:
        print(f"Human label review: {result['review_path']}")
    return {"command": "structured-output", "workflow": result, "args": args}


def cmd_accuracy(args):
    from accuracy import DEFAULT_LABELS, accuracy_report, write_label_review
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError("Set DESK_MODEL or pass --model for result provenance selection.")
    labels = args.labels or DEFAULT_LABELS
    if args.write_review:
        print(f"Label review checklist: {write_label_review(labels)}")
    path, report = accuracy_report(labels, model=model, require_reviewed=args.require_reviewed,
        output_dir=args.output_dir, allow_historical=args.allow_historical, config_id=args.config)
    print(f"Selected outputs: {report['output_dir']} | config: {report['selected_config']}")
    if report["historical"]:
        print("Historical output: this score does not validate the current extraction/verifier policy.")
    print_accuracy_report(path, report, show_results=args.show_results, sample_size=args.sample_size,
                          output_dir=report["output_dir"])


def _positive_count(value):
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if count <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return count


def build_parser():
    """The CLI and chat suggestions share this command/option definition."""
    parser = argparse.ArgumentParser(prog="desk", description="Desk: Meridian Supply Co. assistant")
    sub = parser.add_subparsers(dest="command")

    ask = sub.add_parser("ask", help="send one question to the model")
    ask.add_argument("question", nargs="+")
    ask.add_argument("--model", help="override DESK_MODEL")
    ask.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    ask.set_defaults(func=cmd_ask)

    chat = sub.add_parser("chat", help="start an interactive conversation session")
    chat.add_argument("--model", help="override DESK_MODEL")
    chat.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    chat.set_defaults(func=cmd_chat)

    recover = sub.add_parser("rebuild-output", help="recover interrupted local tracking without calling the model")
    recover.set_defaults(func=cmd_rebuild_output)

    structured = sub.add_parser("structured-output", help="run the skill workflow on one email or a folder; sends selected emails to Bedrock")
    structured.add_argument("source", help="UTF-8 .txt/.eml email or folder containing emails (non-recursive)")
    structured.add_argument("--labels", help="human labels or clearly identified draft labels; auto-selects project labels when applicable")
    structured.add_argument("--output-dir", help="output directory for this run; existing evidence is preserved")
    structured.add_argument("--model", help="override DESK_MODEL")
    structured.add_argument("--max-tokens", type=int, help="max output tokens per response")
    structured.add_argument("--expected-count", type=_positive_count, help="optional input-count assertion; default processes every email")
    structured.add_argument("--sample-size", type=_positive_count, default=DEFAULT_SAMPLE_SIZE,
                            help="number of email outputs to display (default: 15); every email is processed and saved")
    structured.add_argument("--plan-only", action="store_true", help="inspect sources/reuse locally without model calls")
    structured.add_argument("--retry-review", action="store_true", help="explicitly retry previous needs_review outcomes once")
    structured.add_argument("--require-reviewed", action="store_true", help="require actual human label review before any model calls")
    structured.add_argument("--summary-only", action="store_true", help="omit sample JSON; print only batch and accuracy summaries")
    structured.set_defaults(func=cmd_structured_output)

    accuracy = sub.add_parser("accuracy", help="local field report with coverage and label-review provenance; no model calls")
    accuracy.add_argument("--labels", help="label JSON path (default: evaluation/challenge3_labels.draft.json)")
    accuracy.add_argument("--model", help="select outputs from this model")
    accuracy.add_argument("--output-dir", help="select a run directory; default finds latest compatible current run")
    accuracy.add_argument("--config", help="select a shared config ID when a run contains multiple configurations")
    accuracy.add_argument("--allow-historical", action="store_true", help="score an explicitly selected older contract; does not validate current behavior")
    accuracy.add_argument("--write-review", action="store_true", help="generate/update the human-readable source-label checklist")
    accuracy.add_argument("--require-reviewed", action="store_true", help="refuse assistant drafts without actual human review")
    accuracy.add_argument("--show-results", action="store_true", help="also print the evaluated emails' extracted JSON")
    accuracy.add_argument("--sample-size", type=_positive_count, default=DEFAULT_SAMPLE_SIZE,
                          help="limit displayed email details (default: 15); all labels are scored")
    accuracy.set_defaults(func=cmd_accuracy)
    return parser


def _dispatch_cli(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    arguments = (sys.argv[1:] if argv is None else argv) or ["chat"]
    if arguments[0] == "ask":
        # This leaf parser supports options before, after or inside the question.
        from chat_commands import subcommands
        args = subcommands(parser)["ask"].parse_intermixed_args(arguments[1:])
    else:
        args = parser.parse_args(arguments)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0, None
    try:
        return 0, args.func(args)
    except DeskError as exc:
        print(f"desk: {exc}", file=sys.stderr)
        return 1, None


def main(argv=None):
    exit_code, _ = _dispatch_cli(argv)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
