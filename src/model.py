"""Amazon Bedrock client setup, Converse and ConverseStream API calling, retries and cost estimation."""

import os
import random
import sys
import time

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from constants import (
    BASE_DELAY_S,
    MAX_ATTEMPTS,
    RETRYABLE_CODES,
    SYSTEM_PROMPT,
)


class DeskError(Exception):
    """A failure Desk reports to the user in one clear line."""


def make_client():
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    # boto3's own retries are switched off (max_attempts=1) so the backoff below is the
    # only retry layer and every attempt is visible to the user.
    cfg = Config(
        region_name=region,
        connect_timeout=10,
        read_timeout=120,
        retries={"max_attempts": 1, "mode": "standard"},
    )
    return boto3.client("bedrock-runtime", config=cfg)


def _simulate_failure():
    mode = os.environ.get("DESK_SIMULATE", "").lower()
    if mode == "429":
        raise ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Simulated 429: too many requests"}},
            "Converse",
        )
    if mode == "timeout":
        raise ReadTimeoutError(endpoint_url="simulated", error="Simulated read timeout")


def _describe(exc):
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        return f"{err.get('Code', 'ClientError')}: {err.get('Message', '')}".strip()
    return f"{type(exc).__name__}: {exc}"


def call_model(client, model, messages, temperature, max_tokens):
    """One Converse call with retry. messages can be a question string or list of dicts."""
    if isinstance(messages, str):
        message_list = [{"role": "user", "content": [{"text": messages}]}]
    else:
        message_list = messages

    inference = {"maxTokens": max_tokens}
    if temperature is not None:
        inference["temperature"] = temperature

    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            _simulate_failure()
            resp = client.converse(
                modelId=model,
                system=[{"text": SYSTEM_PROMPT}],
                messages=message_list,
                inferenceConfig=inference,
            )
            latency = time.perf_counter() - start
            blocks = resp["output"]["message"]["content"]
            text = "".join(b["text"] for b in blocks if "text" in b).strip()
            return text, resp["usage"], latency, attempt, resp.get("stopReason")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in RETRYABLE_CODES:
                raise DeskError(f"Request failed (not retryable): {_describe(exc)}") from exc
            last = exc
        except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
            last = exc

        if attempt < MAX_ATTEMPTS:
            delay = BASE_DELAY_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            print(
                f"[attempt {attempt}/{MAX_ATTEMPTS} failed: {_describe(last)}; retrying in {delay:.1f}s]",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise DeskError(
        f"Giving up after {MAX_ATTEMPTS} attempts. Last error: {_describe(last)}. "
        "Check your network and AWS credentials, or wait a minute if you are being rate limited."
    )


def _render_stream(stream, start):
    """Print text chunks as they arrive. Returns (text, usage, latency, first_token_s, stop)."""
    parts = []
    usage = {}
    stop = None
    first_token = None
    reasoning_chunks = 0
    try:
        for event in stream:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "reasoningContent" in delta and not parts:
                    # Reasoning models think before answering. Show progress dots on stderr
                    # instead of a blank terminal; the reasoning text itself is not kept.
                    if reasoning_chunks == 0:
                        print("(thinking", end="", file=sys.stderr, flush=True)
                    reasoning_chunks += 1
                    if reasoning_chunks % 100 == 0:
                        print(".", end="", file=sys.stderr, flush=True)
                chunk = delta.get("text")
                if chunk:
                    if first_token is None:
                        first_token = time.perf_counter() - start
                        if reasoning_chunks:
                            print(")", file=sys.stderr, flush=True)
                    print(chunk, end="", flush=True)  # flush, or the terminal buffers it
                    parts.append(chunk)
            elif "messageStop" in event:
                stop = event["messageStop"].get("stopReason")
            elif "metadata" in event:
                usage = event["metadata"].get("usage", {})  # token counts arrive last
            else:
                for key, val in event.items():
                    if key.endswith("Exception"):
                        raise DeskError(f"Stream error: {key}: {val.get('message', '')}")
    except (ClientError, ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
        if not parts:
            if reasoning_chunks:
                print(")", file=sys.stderr, flush=True)
            raise  # no answer text printed yet, so the caller may safely retry
        print()
        raise DeskError(f"Stream broke mid-reply: {_describe(exc)}") from exc
    if reasoning_chunks and first_token is None:
        print(")", file=sys.stderr, flush=True)  # thought but produced no answer text
    print()
    return "".join(parts).strip(), usage, time.perf_counter() - start, first_token, stop


def stream_model(client, model, messages, temperature, max_tokens, system_prompt):
    """Streaming Converse call with the same retry rules as call_model.

    Returns (text, usage, latency_s, first_token_s, attempts, stop_reason).
    """
    inference = {"maxTokens": max_tokens}
    if temperature is not None:
        inference["temperature"] = temperature

    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            _simulate_failure()
            resp = client.converse_stream(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=messages,
                inferenceConfig=inference,
            )
            text, usage, latency, first_token, stop = _render_stream(resp["stream"], start)
            return text, usage, latency, first_token, attempt, stop
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in RETRYABLE_CODES:
                raise DeskError(f"Request failed (not retryable): {_describe(exc)}") from exc
            last = exc
        except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
            last = exc

        if attempt < MAX_ATTEMPTS:
            delay = BASE_DELAY_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            print(
                f"[attempt {attempt}/{MAX_ATTEMPTS} failed: {_describe(last)}; retrying in {delay:.1f}s]",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise DeskError(
        f"Giving up after {MAX_ATTEMPTS} attempts. Last error: {_describe(last)}. "
        "Check your network and AWS credentials, or wait a minute if you are being rate limited."
    )


def estimate_cost(usage):
    p_in = os.environ.get("DESK_PRICE_IN")
    p_out = os.environ.get("DESK_PRICE_OUT")
    if not (p_in and p_out):
        return "n/a (set DESK_PRICE_IN / DESK_PRICE_OUT, USD per 1M tokens)"
    cost = (usage["inputTokens"] * float(p_in) + usage["outputTokens"] * float(p_out)) / 1_000_000
    return f"${cost:.6f}"
