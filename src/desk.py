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
import time
from contextlib import nullcontext
import presentation as ui
from telemetry import combine_usage, workflow_usage, response_stats, current_turn

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
    "Tell me what you need, including an email folder when using a skill. Type / for shortcuts."
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
    with ui.assistant_stream():
        text, usage, latency, attempts, stop = call_model(
            client, model, question, args.temperature, max_tokens
        )
    if ui.enabled():
        context = ui.current_conversation()
        ui.answer(text or "I didn't receive a complete response. Please try again.",
                  response_stats(usage, latency=latency, attempts=attempts,
                                 state=context["state"] if context else None))
    else:
        print(text if text else "(model returned no text; try a larger DESK_MAX_TOKENS)")
    if stop == "max_tokens":
        print("\n[warning: output was cut off at max tokens]", file=sys.stderr)
    if not ui.enabled() and current_turn() is None:
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
        if current_turn() is not None:
            current_turn().ensure_usage(usage)
        else:
            state["total_in"] += _sent_tokens(usage)
            state["total_out"] += usage.get("outputTokens", 0)
    history_limit = _session_history_limit(state)
    dropped = trim_history(messages, history_limit)
    if dropped and not ui.enabled():
        print(
            f"[window: dropped {dropped} oldest turn(s); kept first exchange + "
            f"{len(messages) - 2} recent messages, ~{_estimate_tokens(messages)} tok]"
        )


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
            _chat_notice("I'm ready. Tell me what you need, or use /reset for a fresh conversation.")
    elif cmd == "/reset":
        state["messages"].clear()
        state["total_in"] = state["total_out"] = 0
        _chat_notice("I've started a fresh conversation.", "[history cleared; the next message starts a fresh conversation]")
    elif cmd in ("/save", "/load") and not arg:
        _chat_notice(f"Give this conversation a name with {cmd} <name>.", f"usage: {cmd} <name>")
    elif cmd == "/save":
        try:
            path = save_session(arg, state)
            _chat_notice(f"I've saved this conversation to {path}.", f"[saved {len(state['messages'])} messages to {path}]")
        except DeskError as err:
            if ui.enabled():
                ui.message(str(err), title="Desk · Couldn't save", error=True)
            else:
                print(f"desk: {err}", file=sys.stderr)
    elif cmd == "/load":
        try:
            data = load_session(arg)
        except DeskError as err:
            if ui.enabled():
                ui.message(str(err), title="Desk · Couldn't open", error=True)
            else:
                print(f"desk: {err}", file=sys.stderr)
            return True
        state["messages"][:] = data["messages"]
        state["total_in"] = data.get("total_in", 0)
        state["total_out"] = data.get("total_out", 0)
        _chat_notice(f"I've opened '{arg}'. We can continue where you left off.", f"[loaded '{arg}': {len(state['messages'])} messages, saved {data.get('saved_at', '?')}]")
        if state["messages"] and not ui.enabled():
            last = state["messages"][-1]["content"][0].get("text", "")
            print(f"[last {state['messages'][-1]['role']} message: {last[:120]}]")
    elif cmd[1:] in commands:
        command = commands[cmd[1:]]
        # Preserve unquoted Windows backslashes and quoted paths with spaces.
        try:
            tokens = [token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"
                      else token for token in shlex.split(arg, posix=False)]
            if cmd == "/structured-output":
                if not tokens:
                    state["pending_user_input"] = line
                    return True
                # Valid shortcut arguments remain local. Ordinary words after
                # a skill selection are interpreted by the LLM, not argparse.
                _, remaining = command.parser.parse_known_args(tokens)
                if remaining and not any(token.startswith("-") for token in remaining):
                    state["pending_user_input"] = line
                    return True
            if not tokens and any(a.required and not a.option_strings for a in command.parser._actions):
                command.parser.print_help()
                return True
            supports_model = any("--model" in a.option_strings for a in command.parser._actions)
            if supports_model and state.get("model") and not any(token == "--model" or token.startswith("--model=") for token in tokens):
                tokens += ["--model", state["model"]]
            with ui.conversation(state, line):
                exit_code, result = _dispatch_cli([command.cli_command, *tokens])
            if exit_code == 0 and isinstance(result, dict):
                if result.get("command") == "ask" and result.get("text"):
                    _record_session_turn(state, line, result["text"], usage=result.get("usage"))
                elif result.get("command") == "structured-output":
                    budget = max(_session_history_limit(state) * 2, 16000)
                    summary = _format_structured_session_note(result["workflow"], result["args"], max_chars=budget)
                    _record_session_turn(state, line, summary, usage=result.get("usage"))
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
            _chat_notice(f"I don't recognize {cmd}. Type / to choose an available shortcut.",
                         f"Unknown command: {cmd}. Type / to see available commands.")
    return True


def cmd_chat(args):
    from chat_commands import chat_reader, command_catalog
    from skill_tools import tool_config
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

    if ui.enabled():
        ui.welcome()
    else:
        print("Desk Chat (Meridian Supply Co.)")
        print(CHAT_HELP + "\n")
    read_line = chat_reader(lambda: command_catalog(build_parser()))

    while True:
        try:
            # Windows PowerShell prefixes piped input with a BOM, which would hide a leading "/".
            user_input = read_line("> ").lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            _chat_notice("Talk soon.", "\nGoodbye!")
            break

        if not user_input:
            continue

        with ui.turn_details(state, model):
            if user_input.lower() in ("exit", "quit"):
                _chat_notice("Talk soon.", "Goodbye!")
                break

            if user_input.startswith("/"):
                if not handle_command(user_input, state):
                    _chat_notice("Talk soon.", "Goodbye!")
                    break
                user_input = state.pop("pending_user_input", "")
                if not user_input:
                    continue

            # Append user turn to message history
            messages.append({"role": "user", "content": [{"text": user_input}]})

            dropped = trim_history(messages, history_limit)
            if dropped and not ui.enabled():
                print(
                    f"[window: dropped {dropped} oldest turn(s); kept first exchange + "
                    f"{len(messages) - 2} recent messages, ~{_estimate_tokens(messages)} tok]"
                )

            print()
            tool_uses = []
            try:
                if client is None:
                    client = make_client()
                with ui.assistant_stream() as display:
                    text, usage, latency, first_token, attempts, stop = stream_model(
                        client, model, messages, args.temperature, max_tokens, CHAT_SYSTEM_PROMPT,
                        tool_config=tool_config(), tool_uses=tool_uses,
                        on_text=display.write if display is not None else None,
                    )
                    if display is not None:
                        display.discard = bool(tool_uses)
                        display.stats = response_stats(usage, latency=latency, first_token=first_token, attempts=attempts, state=state)
                        display.stats.update(context_tokens=_estimate_tokens(messages), context_limit=history_limit)
            except DeskError as err:
                if ui.enabled():
                    ui.message(str(err), title="Desk · Couldn't complete", error=True)
                else:
                    print(f"desk: {err}", file=sys.stderr)
                messages.pop()
                continue

            if tool_uses:
                # Keep canonical user/assistant text in session memory, without an
                # unanswered native tool-use block or a second model rewriting results.
                used_context = _estimate_tokens(messages)
                messages.pop()
                _run_chat_skill(tool_uses, user_input, state, usage=usage,
                    routing=dict(usage=usage, latency_s=latency, first_token_s=first_token, attempts=attempts,
                                 context_tokens=used_context, context_limit=history_limit))
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
            if current_turn() is None:
                state["total_in"] += sent
                state["total_out"] += usage.get("outputTokens", 0)

            first = f"{first_token:.2f}s" if first_token is not None else "n/a"
            if not ui.enabled() and current_turn() is None:
                print(
                    f"\n--\nTurn: in {sent} tok" + (f" ({cached} cached)" if cached else "")
                    + f" | out {usage.get('outputTokens', 0)} tok "
                    f"| first token: {first} | total: {latency:.2f}s "
                    f"| Session Total: in {state['total_in']} tok | out {state['total_out']} tok "
                    f"| history: ~{_estimate_tokens(messages)}/{history_limit} tok"
                    + (f" | attempts: {attempts}" if attempts > 1 else "")
                )
            print()


def _run_chat_skill(tool_uses, user_input, state, *, usage=None, routing=None):
    from skill_tools import workflow_argv
    try:
        if len(tool_uses) != 1:
            raise DeskError("Please select one email file or folder per skill request.")
        argv = workflow_argv(tool_uses[0])
        argv.extend(["--model", state["model"]])
        if ui.enabled():
            ui.message(f"I'll use Structured Output to check the emails in {argv[1]}.")
        else:
            print(f"Using structured-output on {argv[1]}.")
        with ui.conversation(state, user_input, routing or dict(usage=usage or {})):
            exit_code, result = _dispatch_cli(argv, raise_errors=True)
            if exit_code or not isinstance(result, dict):
                raise DeskError("The structured-output workflow did not complete. Check the reported source or storage error before retrying.")
            budget = max(_session_history_limit(state) * 2, 16000)
            summary = _format_structured_session_note(result["workflow"], result["args"], max_chars=budget)
        usage = combine_usage(usage, result.get("usage"))
    except DeskError as exc:
        summary = str(exc)
        if ui.enabled():
            ui.message(summary, title="Desk · Couldn't complete", error=True)
        else:
            print(summary)
    _record_session_turn(state, user_input, summary, usage=usage)


def cmd_rebuild_output(args):
    from extraction import rebuild_outputs
    rebuild_outputs()
    _chat_notice("I've recovered the saved output tracking. No model request was needed.",
                 "Recovered local output tracking; no model call was made.")


def _chat_notice(value, plain=None):
    if ui.enabled():
        ui.message(value)
    else:
        print(plain if plain is not None else value)


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


def _validation_summary(manifest):
    sources = manifest["sources"]
    validated = sum(row["status"] == "validated" for row in sources)
    review = sum(row["status"] == "needs_review" for row in sources)
    return (f"Validation: {validated + review}/{len(sources)} accounted for | "
            f"validated: {validated} | needs_review: {review}")


def _accuracy_summary(report):
    if report is None:
        return "Accuracy: unmeasured (no matching labels available)."
    label = ("Human-reviewed field accuracy" if report["measurement_kind"] == "human_reviewed_field_accuracy"
             else "Assistant draft agreement (human review pending)")
    overall, coverage = report["overall"], report["coverage"]
    score = "unmeasured" if overall["score"] is None else f"{overall['score']:.1%}"
    return (f"{label}: {score} ({overall['correct']}/{overall['total']} field checks; "
            f"{coverage['validated']}/{coverage['labels']} labelled emails validated)")


def _workflow_stats(result):
    context = ui.current_conversation()
    routing = context["routing"] if context else {}
    usage = combine_usage(routing.get("usage"), workflow_usage(result))
    if current_turn() is not None:
        current_turn().ensure_usage(usage)
        return current_turn().snapshot()
    attempts = (result.get("manifest") or {}).get("metrics", {}).get("provider_attempts", 0)
    stats = response_stats(usage, latency=result.get("elapsed_s", 0) + (routing.get("latency_s") or 0),
        first_token=routing.get("first_token_s"), attempts=attempts + routing.get("attempts", 0),
        state=context["state"] if context else None)
    if routing.get("context_tokens") is not None:
        stats.update(context_tokens=routing["context_tokens"], context_limit=routing["context_limit"])
    return stats


def _format_structured_session_note(result, args, *, max_chars=96000):
    """Format workflow summary, accuracy report, and outcomes for unified chat memory."""
    plan = result["plan"]
    lines = [
        f"Emails: {plan['source_count']} | reusable: {plan['reused_count']} | new requests: {plan['new_email_payloads']}",
        f"Input: {plan.get('input_file') or plan['input_dir']}",
        result["label_note"],
    ]
    if args.plan_only:
        lines.append(f"Offline plan: {result['plan_path']} | no model calls made")
        return "\n".join(lines)

    manifest = result["manifest"]
    lines.append(f"Batch: {manifest['status']} | manifest: {result['manifest_path']}")
    lines.append(f"Outputs: {plan['output_dir']}/results.jsonl")
    footer = []
    report = result.get("report")
    if report is not None:
        cov = report["coverage"]
        overall = report["overall"]
        overall_pct = "unmeasured" if overall["score"] is None else f"{overall['score']:.1%}"
        footer.append(
            f"Evaluation ({report['measurement_kind']}): validated {cov['validated']}/{cov['labels']}, "
            f"missing {cov['missing']}, review {cov['needs_review']}, "
            f"overall {overall['correct']}/{overall['total']} ({overall_pct}), report: {result['report_path']}"
        )
    if result.get("review_path"):
        footer.append(f"Human label review: {result['review_path']}")
    stats = _workflow_stats(result)
    footer.append(f"Response metrics: latency {stats['latency_s']:.2f}s, input {stats['input_tokens']} tokens, output {stats['output_tokens']} tokens.")
    footer.extend([_validation_summary(manifest), _accuracy_summary(report)])

    outcomes = _ordered_outcomes(manifest, output_dir=plan["output_dir"])
    shown = 0 if args.summary_only else min(args.sample_size, len(outcomes))
    lines.append(f"Terminal displayed first {shown} of {len(outcomes)} emails. Processed outcomes:")
    # Reserve space for evaluation so a long outcome sample cannot hide it.
    used_chars = sum(len(line) + 1 for line in [*lines, *footer])
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
    return "\n".join([*lines, *footer])


def print_accuracy_report(path, report, *, show_results=False, output_dir=None,
                          sample_size=DEFAULT_SAMPLE_SIZE, include_emails=True, stats=None,
                          field_level=False):
    if ui.enabled():
        if show_results:
            from extraction import read_run_history
            _, rows = read_run_history(output_dir)
            by_run = {row["run_id"]: row for row in rows}
            for email in report["emails"][:sample_size]:
                row = by_run.get(email["run_id"])
                if row is not None:
                    ui.email_result(dict(email_id=email["source_id"], status=row["status"], result=row["data"], reason=row.get("reason")))
        ui.console().print(ui.text(f"Detailed report: {path}", style="#94a3b8"))
        if field_level:
            from rich.table import Table
            title = ("Human-reviewed field accuracy" if report["measurement_kind"] == "human_reviewed_field_accuracy"
                     else "Assistant draft agreement per field (human review pending)")
            table = Table(title=title, header_style="#94a3b8", border_style="#334155")
            table.add_column("Field")
            table.add_column("Correct / total", justify="right")
            table.add_column("Score", justify="right")
            for field, values in report["fields"].items():
                score = "unmeasured" if values["score"] is None else f"{values['score']:.1%}"
                table.add_row(field, f"{values['correct']} / {values['total']}", score)
            ui.console().print(table)
        ui.score_panel(report, stats=stats)
        return
    if not include_emails:
        print(f"Detailed report: {path}")
        print(_accuracy_summary(report))
        return
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
    print(_accuracy_summary(report))


def cmd_structured_output(args):
    from schemas import SCHEMA_PATH
    from structured_output import run_workflow
    model, max_tokens = _batch_options(args)
    if not ui.enabled():
        print(f"Schema template: {SCHEMA_PATH}")
    with ui.batch_progress() as progress:
        result = run_workflow(args.source, model, max_tokens=max_tokens, labels_path=args.labels,
            plan_only=args.plan_only, retry_review=args.retry_review, expected_count=args.expected_count,
            require_reviewed=args.require_reviewed, progress=progress or _show_batch_progress, output_dir=args.output_dir)
    plan = result["plan"]
    if ui.enabled():
        outcomes = _ordered_outcomes(result["manifest"], output_dir=plan["output_dir"]) if result["manifest"] else []
        ui.workflow_result(result, args, outcomes, _workflow_stats(result))
        return {"command": "structured-output", "workflow": result, "args": args, "usage": workflow_usage(result)}
    print(f"Emails: {plan['source_count']} | reusable: {plan['reused_count']} | new requests: {plan['new_email_payloads']}")
    print(result["label_note"])
    if args.plan_only:
        print(f"Offline plan: {result['plan_path']} | no model calls made")
        return {"command": "structured-output", "workflow": result, "args": args}
    print(f"Batch: {result['manifest']['status']} | {result['manifest_path']}")
    print(f"Outputs: {plan['output_dir']}/results.jsonl and needs_review.jsonl (when needed)")
    if not args.summary_only:
        print_result_sample(result["manifest"], sample_size=args.sample_size, output_dir=plan["output_dir"])
    if result["review_path"]:
        print(f"Human label review: {result['review_path']}")
    print(_validation_summary(result["manifest"]))
    stats = _workflow_stats(result)
    if current_turn() is None:
        print(f"Response metrics: latency {stats['latency_s']:.2f}s | input {stats['input_tokens']} tokens | output {stats['output_tokens']} tokens")
    if result["report"] is not None:
        print_accuracy_report(result["report_path"], result["report"], include_emails=False)
    else:
        print(_accuracy_summary(None))
    return {"command": "structured-output", "workflow": result, "args": args, "usage": workflow_usage(result)}


def cmd_accuracy(args):
    from accuracy import DEFAULT_LABELS, accuracy_report, write_label_review
    started = time.perf_counter()
    model = args.model or os.environ.get("DESK_MODEL")
    if not model:
        raise DeskError("Set DESK_MODEL or pass --model for result provenance selection.")
    labels = args.labels or DEFAULT_LABELS
    if args.write_review:
        print(f"Label review checklist: {write_label_review(labels)}")
    path, report = accuracy_report(labels, model=model, require_reviewed=args.require_reviewed,
        output_dir=args.output_dir, allow_historical=args.allow_historical, config_id=args.config)
    if not ui.enabled():
        print(f"Selected outputs: {report['output_dir']} | config: {report['selected_config']}")
    if report["historical"]:
        _chat_notice("This is a historical score. It does not verify the current extraction schema or policy.",
                     "Historical output: this score does not validate the current extraction/verifier policy.")
    print_accuracy_report(path, report, show_results=args.show_results, sample_size=args.sample_size,
                          output_dir=report["output_dir"], stats=response_stats(latency=time.perf_counter() - started),
                          field_level=getattr(args, "field_level", False))


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
    # Also parsed directly for intermixed flags, bypassing the root subparser.
    ask.set_defaults(command="ask", func=cmd_ask)

    chat = sub.add_parser("chat", help="start an interactive conversation session")
    chat.add_argument("--model", help="override DESK_MODEL")
    chat.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    chat.set_defaults(func=cmd_chat)

    recover = sub.add_parser("rebuild-output", help="recover interrupted local tracking without calling the model")
    recover.set_defaults(func=cmd_rebuild_output)

    structured = sub.add_parser("structured-output", help="run the skill workflow on one email or a folder; sends selected emails to Bedrock")
    structured.add_argument("source", help="UTF-8 .txt/.eml email or folder containing emails (non-recursive)")
    structured.add_argument("--labels", help="explicit label JSON for optional evaluation; no labels are selected automatically")
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
    accuracy.add_argument("--field-level", action="store_true", help="also show the per-field table in the interactive terminal")
    accuracy.add_argument("--sample-size", type=_positive_count, default=DEFAULT_SAMPLE_SIZE,
                          help="limit displayed email details (default: 15); all labels are scored")
    accuracy.set_defaults(func=cmd_accuracy)
    return parser


def _dispatch_cli(argv=None, *, raise_errors=False):
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
    details = ui.turn_details(model=getattr(args, "model", None) or os.environ.get("DESK_MODEL")) if args.command != "chat" else nullcontext()
    with details:
        try:
            result = args.func(args)
            if isinstance(result, dict) and current_turn() is not None:
                current_turn().ensure_usage(result.get("usage"))
            return 0, result
        except DeskError as exc:
            if raise_errors:
                raise
            if ui.enabled():
                ui.message(str(exc), title="Desk · Couldn't complete", error=True)
            else:
                print(f"desk: {exc}", file=sys.stderr)
            return 1, None



def main(argv=None):
    exit_code, _ = _dispatch_cli(argv)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
