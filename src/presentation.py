"""Dark assistant messages for interactive Desk; saved JSON stays unchanged."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
import sys

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from telemetry import conversation_turn, current_turn

THEME = Theme({"desk": "bold #8fd4de", "muted": "#94a3b8", "good": "#92d5ac", "review": "#e8be83"})
_console = ContextVar("desk_console", default=None)
_conversation = ContextVar("desk_conversation", default=None)


def enabled():
    return _console.get() is not None or bool(getattr(sys.stdout, "isatty", lambda: False)())


def console():
    return _console.get() or Console(file=sys.stdout, theme=THEME, highlight=False)


@contextmanager
def use_console(value):
    token = _console.set(value)
    try:
        yield value
    finally:
        _console.reset(token)


@contextmanager
def conversation(state, user_input, routing=None):
    token = _conversation.set(dict(state=state, user_input=user_input, routing=routing or {}))
    try:
        yield
    finally:
        _conversation.reset(token)


def current_conversation():
    return _conversation.get()


@contextmanager
def turn_details(state=None, model=None):
    """Every chat/command uses this default, including future command handlers."""
    with conversation_turn(state, model) as (turn, owner):
        try:
            yield turn
        finally:
            if owner:
                turn.settle()
                stats = turn.snapshot()
                if enabled():
                    console().print(card(metric_lines(stats), "Conversation details", border="#2b3b49", padding=(0, 2)))
                else:
                    details = (f"Conversation details: latency {duration(stats['latency_s'])} | "
                               f"input {compact_count(stats['input_tokens'])} tokens | output {compact_count(stats['output_tokens'])} tokens")
                    if stats.get("first_token_s") is not None:
                        details += f" | first token {duration(stats['first_token_s'])}"
                    if stats.get("session_input") is not None:
                        details += f" | session {compact_count(stats['session_input'])} input / {compact_count(stats['session_output'])} output tokens"
                    if stats.get("context_tokens") is not None:
                        details += f" | context ~{compact_count(stats['context_tokens'])}/{compact_count(stats['context_limit'])} tokens"
                    if stats.get("model"):
                        details += f" | model {stats['model']}"
                    if stats.get("estimated_cost"):
                        details += f" | estimated cost {stats['estimated_cost']}"
                    if stats.get("attempts", 0) > 1:
                        details += f" | attempts {stats['attempts']}"
                    if stats.get("usage_incomplete"):
                        details += " | failed-request usage unavailable; reported tokens only"
                    print(details)


def text(value, *, style=""):
    value = "Not stated" if value is None else str(value)
    return Text(re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", value), style=style, overflow="fold")


def card(content, title="Desk", *, border="#3f6b76", padding=(1, 2)):
    return Panel(content, title=Text(title, style="bold #8fd4de"), title_align="left",
                 border_style=border, box=box.ROUNDED, padding=padding, style="#e2e8f0 on #111923")


def welcome():
    console().print(card(Group(Text("Your customer-operations assistant.", style="bold"), Text(""),
        text("Tell me what you need. I can turn your emails into validated order data."),
        Text("Type / anywhere to choose a skill. Your conversation stays in this session.", style="#94a3b8")),
        "DESK  /  AI ASSISTANT"))


def message(value, *, title="Desk", error=False, markdown=False):
    console().print(card(Markdown(value) if markdown else text(value), title,
                         border="#b78b5d" if error else "#3f6b76"))


def duration(value):
    if value is None:
        return "—"
    if value >= 60:
        return f"{int(value // 60)}m {value % 60:.1f}s"
    return f"{value:.2f}s"


def compact_count(value):
    amount, suffix = value, ""
    for candidate in ("k", "m", "b"):
        if abs(amount) < 999.95:
            break
        amount /= 1000
        suffix = candidate
    return f"{amount:.1f}".rstrip("0").rstrip(".") + suffix if suffix else str(value)


def metric_lines(stats):
    if not stats:
        return Text("")
    first = f" · First token {duration(stats['first_token_s'])}" if stats.get("first_token_s") is not None else ""
    line = (f"Latency {duration(stats.get('latency_s'))}{first} · "
            f"Input {compact_count(stats.get('input_tokens', 0))} · Output {compact_count(stats.get('output_tokens', 0))}")
    rows = [text(line, style="#94a3b8")]
    if stats.get("session_input") is not None:
        rows.append(text(f"Session {compact_count(stats['session_input'])} in/{compact_count(stats['session_output'])} out", style="#94a3b8"))
    if stats.get("context_tokens") is not None:
        rows.append(text(f"Context ~{compact_count(stats['context_tokens'])}/{compact_count(stats['context_limit'])}", style="#94a3b8"))
    if stats.get("model"):
        rows.append(text(f"Model: {stats['model']}", style="#94a3b8"))
    if stats.get("attempts", 1) > 1:
        rows.append(text(f"Provider attempts: {stats['attempts']}", style="#94a3b8"))
    if stats.get("estimated_cost"):
        rows.append(text(f"Estimated cost: {stats['estimated_cost']}", style="#94a3b8"))
    if stats.get("usage_incomplete"):
        rows.append(text("Some failed requests did not return usage; showing reported tokens only.", style="#e8be83"))
    return Text(" · ", style="#94a3b8").join(rows)


def answer(value, stats=None):
    if current_turn() is not None:
        stats = None
    body = [Markdown(value)]
    if stats:
        body.extend([Text(""), Rule(style="#2b3b49"), metric_lines(stats)])
    console().print(card(Group(*body)))


class AssistantStream:
    def __init__(self, output):
        self.output, self.parts, self.stats, self.discard = output, [], None, False

    def write(self, chunk):
        self.parts.append(chunk)
        self.live.update(card(Markdown("".join(self.parts))))

    def __enter__(self):
        self.live = Live(card(Text("Thinking…", style="#94a3b8")), console=self.output,
                         refresh_per_second=8, transient=True)
        self.live.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.live.stop()
        if self.parts and not self.discard:
            value = "".join(self.parts)
            if exc_type:
                self.output.print(card(Group(Markdown(value), text("Response interrupted.", style="#e8be83")),
                                       "Desk · interrupted", border="#b78b5d"))
            else:
                answer(value, self.stats)


@contextmanager
def assistant_stream():
    if not enabled():
        yield None
        return
    with use_console(console()), AssistantStream(console()) as stream:
        yield stream


@contextmanager
def batch_progress():
    if not enabled():
        yield None
        return
    output = console()
    with use_console(output), Progress(SpinnerColumn(style="#8fd4de"), TextColumn("{task.description}"),
        BarColumn(bar_width=None, complete_style="#619d99"), TaskProgressColumn(), TimeElapsedColumn(),
        console=output, transient=True) as progress:
        task = progress.add_task("Reading your emails…", total=None)
        def update(event):
            if event["kind"] == "email_complete":
                counts = event["counts"]
                valid = counts["reused"] + counts["newly_validated"]
                progress.update(task, total=event["total"], completed=event["completed"],
                    description=f"Checking emails · {valid} ready · {counts['needs_review']} need review")
        yield update


def email_result(value):
    output = console()
    identifier = value["email_id"]
    if value["status"] == "needs_review":
        reason = str(value.get("reason") or "Unresolved validation").replace("_", " ")
        output.print(card(Group(text("This email needs review before its data can be accepted.", style="#e8be83"),
                                text(reason)), f"{identifier} · NEEDS REVIEW", border="#b78b5d"))
        return
    result = value["result"]
    details = Table.grid(padding=(0, 2), expand=True)
    details.add_column(style="#94a3b8", no_wrap=True)
    details.add_column(ratio=1, overflow="fold")
    for label, key in [("Customer", "customer"), ("Intent", "intent"), ("Requested date", "requested_date"),
                       ("Urgency", "urgency"), ("Confidence", "confidence")]:
        details.add_row(label, text(result.get(key)))
    content = [details, Text("")]
    if not result["line_items"]:
        content.append(text("No identifiable products were stated.", style="#94a3b8"))
    elif output.width < 76:
        for index, item in enumerate(result["line_items"], 1):
            content.extend([text(f"{index}. {item['description'] or item['sku']}", style="bold"),
                            text(f"SKU: {item['sku'] or 'Not stated'}  ·  Quantity: {item['quantity'] if item['quantity'] is not None else 'Not stated'}  ·  Unit: {item['unit'] or 'Not stated'}")])
    else:
        items = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False,
                      header_style="bold #94a3b8", border_style="#2b3b49")
        for label, ratio in [("SKU", 2), ("Description", 5), ("Qty", 1), ("Unit", 2)]:
            items.add_column(label, ratio=ratio, overflow="fold")
        for item in result["line_items"]:
            items.add_row(*(text(item[key]) for key in ("sku", "description", "quantity", "unit")))
        content.append(items)
    output.print(card(Group(*content), f"{identifier} · VALIDATED", border="#365a50"))


def score_panel(report, *, manifest=None, stats=None):
    if current_turn() is not None:
        stats = None
    body = []
    if manifest is not None:
        sources = manifest["sources"]
        good = sum(row["status"] == "validated" for row in sources)
        review = sum(row["status"] == "needs_review" for row in sources)
        body.extend([text(f"I checked {len(sources)} emails.", style="bold"),
                     text(f"{good} validated  ·  {review} need review", style="#92d5ac" if not review else "#e8be83"), Text("")])
    if stats:
        body.extend([metric_lines(stats), Text(""), Rule(style="#2b3b49"), Text("")])
    if report is None:
        body.extend([text("Unmeasured", style="bold #8fd4de"), text("Overall accuracy · no matching labels available.", style="#94a3b8")])
    else:
        overall, cov = report["overall"], report["coverage"]
        reviewed = report["measurement_kind"] == "human_reviewed_field_accuracy"
        score = "Unmeasured" if overall["score"] is None else f"{overall['score']:.1%}"
        body.extend([text(score, style="bold #8fd4de"),
                     text("Overall field accuracy" if reviewed else "Overall draft agreement", style="bold"),
                     text(f"{overall['correct']:,} of {overall['total']:,} labelled field checks matched."),
                     text(f"Based on {cov['labels']} labelled emails." + (" Human review pending." if not reviewed else " Human-reviewed labels."), style="#94a3b8")])
    console().print(card(Group(*body), "Desk · Results"))


def workflow_result(result, args, outcomes, stats):
    plan = result["plan"]
    if args.plan_only:
        message(f"I found {plan['source_count']} emails. {plan['reused_count']} saved outcomes can be reused; "
                f"{plan['new_email_payloads']} need a new extraction. No emails were sent to the model.", title="Desk · Preview")
        console().print(text(f"Plan saved to {result['plan_path']}", style="#94a3b8"))
        if current_turn() is None:
            console().print(metric_lines(stats))
        return
    shown = [] if args.summary_only else outcomes[:args.sample_size]
    if shown:
        console().print(text(f"Showing {len(shown)} of {len(outcomes)} email outcomes", style="#94a3b8"))
        for value in shown:
            email_result(value)
    files = [("Results", Path(plan["output_dir"]) / "results.jsonl")]
    if any(row["status"] == "needs_review" for row in outcomes):
        files.append(("Review pile", Path(plan["output_dir"]) / "needs_review.jsonl"))
    if result.get("report_path"):
        files.append(("Detailed report", result["report_path"]))
    for label, path in files:
        console().print(text(f"{label}: {path}", style="#94a3b8"))
    if result.get("review_path"):
        console().print(text(f"Label review: {result['review_path']}", style="#94a3b8"))
    score_panel(result.get("report"), manifest=result["manifest"], stats=stats)
