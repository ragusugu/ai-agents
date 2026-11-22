"""Session persistence, conversation history trimming (sliding window), and token accounting."""

import json
import os
import re
import time

from model import DeskError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(ROOT_DIR, "save")
SESSIONS_DIR = SAVE_DIR  # Backwards compatibility alias


def _session_path(name):
    """save/<name>.json, refusing names that could escape the save folder."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
        raise DeskError("Session name may only use letters, digits, '_' and '-'.")
    return os.path.join(SAVE_DIR, f"{name}.json")


def save_session(name, state):
    """Write the conversation and its token totals to save/<name>.json."""
    path = _session_path(name)
    os.makedirs(SAVE_DIR, exist_ok=True)
    data = {
        "model": state["model"],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_in": state["total_in"],
        "total_out": state["total_out"],
        "messages": state["messages"],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_session(name):
    """Read a saved session back from save/<name>.json. Returns the parsed dict."""
    path = _session_path(name)
    if not os.path.exists(path):
        legacy_path = os.path.join(ROOT_DIR, "sessions", f"{name}.json")  # pre-`save/` location
        if os.path.exists(legacy_path):
            path = legacy_path
        else:
            raise DeskError(f"No saved session named '{name}' (looked in {path}).")
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise DeskError(f"Session file {path} is not valid JSON: {exc}") from exc
    if not isinstance(data.get("messages"), list):
        raise DeskError(f"Session file {path} has no message list.")
    return data


def _sent_tokens(usage):
    """All input tokens the request carried. Bedrock reports cached prefix tokens separately."""
    return (
        usage.get("inputTokens", 0)
        + usage.get("cacheReadInputTokens", 0)
        + usage.get("cacheWriteInputTokens", 0)
    )


def _estimate_tokens(messages):
    """Rough token count of the history: about 4 characters per token for English."""
    chars = sum(len(block.get("text", "")) for m in messages for block in m["content"])
    return chars // 4 + 1


def trim_history(messages, limit):
    """Sliding window: drop the oldest user/assistant pairs until history fits `limit`.

    messages looks like [u0, a0, u1, a1, ..., u_new]. The first pair (u0, a0) is pinned
    (stretch goal), so trimming starts at index 2. Pairs are dropped together because
    Bedrock requires user/assistant turns to alternate. The system prompt is sent
    separately on every call, so it is always kept. Returns the number of pairs dropped.
    """
    dropped = 0
    while _estimate_tokens(messages) > limit and len(messages) > 3:
        del messages[2:4]
        dropped += 1
    return dropped
