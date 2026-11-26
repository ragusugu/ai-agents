"""Reported provider usage and timing shared by chat and skill responses."""

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar

_turn = ContextVar("desk_turn_metrics", default=None)

USAGE_KEYS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens")


def sent_tokens(usage):
    return sum(usage.get(key, 0) for key in ("inputTokens", "cacheReadInputTokens", "cacheWriteInputTokens"))


def current_turn():
    return _turn.get()


class ConversationTurn:
    def __init__(self, state=None, model=None):
        self.started = time.perf_counter()
        self.state, self.model = state, model or (state or {}).get("model")
        self.usage = combine_usage()
        self.attempts = 0
        self.first_token = None
        self.settled = False
        self.usage_incomplete = False

    def ensure_usage(self, usage):
        # A command may report a whole-turn aggregate (including a test adapter).
        # Gateway observations and that aggregate must never count twice.
        self.usage = {key: max(self.usage[key], (usage or {}).get(key, 0)) for key in USAGE_KEYS}

    def settle(self):
        if self.state is not None and not self.settled:
            self.state["total_in"] += sent_tokens(self.usage)
            self.state["total_out"] += self.usage["outputTokens"]
        self.settled = True

    def snapshot(self):
        state = None if self.settled else self.state
        stats = response_stats(self.usage, latency=time.perf_counter() - self.started,
                               first_token=self.first_token, attempts=self.attempts, state=state)
        if self.settled and self.state is not None:
            stats.update(session_input=self.state["total_in"], session_output=self.state["total_out"])
        if self.state is not None:
            from session import _estimate_tokens
            stats.update(context_tokens=_estimate_tokens(self.state["messages"]),
                         context_limit=self.state.get("history_limit", 64000))
        stats["model"] = self.model
        stats["usage_incomplete"] = self.usage_incomplete
        if self.usage_incomplete:
            stats.pop("estimated_cost", None)
        return stats


@contextmanager
def conversation_turn(state=None, model=None):
    existing = current_turn()
    if existing is not None:
        # Nested commands share usage, but can select a model for this turn.
        # Keep the selection for the outer footer without changing session state.
        if model:
            existing.model = model
        yield existing, False
        return
    turn = ConversationTurn(state, model)
    token = _turn.set(turn)
    try:
        yield turn, True
    finally:
        turn.settle()
        _turn.reset(token)


def note_response(usage, *, started=None, first_token=None, attempts=1):
    turn = current_turn()
    if turn is not None:
        turn.usage = combine_usage(turn.usage, usage)
        turn.attempts += attempts
        if first_token is not None and turn.first_token is None:
            turn.first_token = max(0, (started or turn.started) - turn.started + first_token)


def note_failure(attempts):
    turn = current_turn()
    if turn is not None:
        turn.attempts += attempts
        turn.usage_incomplete = True


def combine_usage(*usages):
    return {key: sum((usage or {}).get(key, 0) for usage in usages) for key in USAGE_KEYS}


def record_usage(record):
    responses = [*record.get("attempts", []),
                 *(attempt["response"] for attempt in record.get("verification_attempts", []))]
    return combine_usage(*(response.get("usage", {}) for response in responses))


def workflow_usage(result):
    return (result.get("manifest") or {}).get("metrics", {}).get("usage", {})


def response_stats(usage=None, *, latency=None, first_token=None, attempts=1, state=None):
    usage = usage or {}
    incoming = sent_tokens(usage)
    outgoing = usage.get("outputTokens", 0)
    stats = dict(input_tokens=incoming, output_tokens=outgoing, latency_s=latency,
                first_token_s=first_token, attempts=attempts,
                session_input=(state.get("total_in", 0) + incoming) if state is not None else None,
                session_output=(state.get("total_out", 0) + outgoing) if state is not None else None)
    if os.environ.get("DESK_PRICE_IN") and os.environ.get("DESK_PRICE_OUT"):
        try:
            from model import estimate_cost
            stats["estimated_cost"] = estimate_cost(usage)
        except (ValueError, KeyError):
            pass
    return stats
