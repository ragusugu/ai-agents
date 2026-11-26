"""Amazon Bedrock client setup, Converse and ConverseStream API calling, retries and cost estimation."""

import json
import os
import random
import sys
import time
from telemetry import note_response, note_failure

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
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


class StructuredRequestError(DeskError):
    """Provider failure, kept separate from JSON/schema repair failures."""

    def __init__(self, message, *, attempts, code, category="provider_error"):
        super().__init__(message)
        self.attempts = attempts
        self.code = code
        self.category = category


def make_client(*, single_attempt=False):
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    # Extraction uses total_max_attempts=1, so its counters include every request.
    # Existing ask/chat calls keep their previous SDK retry configuration.
    cfg = Config(
        region_name=region,
        connect_timeout=10,
        read_timeout=120,
        retries=({"total_max_attempts": 1, "mode": "standard"} if single_attempt else
                 {"max_attempts": 1, "mode": "standard"}),
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
            note_response(resp["usage"], started=start, attempts=attempt)
            return text, resp["usage"], latency, attempt, resp.get("stopReason")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in RETRYABLE_CODES:
                note_failure(attempt)
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

    note_failure(MAX_ATTEMPTS)
    raise DeskError(
        f"Giving up after {MAX_ATTEMPTS} attempts. Last error: {_describe(last)}. "
        "Check your network and AWS credentials, or wait a minute if you are being rate limited."
    )


def _render_stream(stream, start, *, tool_uses=None, on_text=None, on_usage=None):
    """Print text chunks as they arrive. Returns (text, usage, latency, first_token_s, stop)."""
    parts = []
    usage = {}
    stop = None
    first_token = None
    reasoning_chunks = 0
    tools = {}
    try:
        for event in stream:
            if "contentBlockStart" in event:
                block = event["contentBlockStart"]
                tool = block.get("start", {}).get("toolUse")
                if tool is not None:
                    index = block["contentBlockIndex"]
                    if tool_uses is None or index in tools:
                        raise DeskError("Unexpected skill request; no workflow was run.")
                    tools[index] = {**tool, "input": "", "complete": False}
            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "toolUse" in delta:
                    index = event["contentBlockDelta"]["contentBlockIndex"]
                    if index not in tools or tools[index]["complete"]:
                        raise DeskError("Malformed skill request; no workflow was run.")
                    if first_token is None:
                        first_token = time.perf_counter() - start
                        if reasoning_chunks and on_text is None:
                            print(")", file=sys.stderr, flush=True)
                    tools[index]["input"] += delta["toolUse"].get("input", "")
                if "reasoningContent" in delta and not parts:
                    # Reasoning models think before answering. Show progress dots on stderr
                    # instead of a blank terminal; the reasoning text itself is not kept.
                    if reasoning_chunks == 0 and on_text is None:
                        print("(thinking", end="", file=sys.stderr, flush=True)
                    reasoning_chunks += 1
                    if reasoning_chunks % 100 == 0 and on_text is None:
                        print(".", end="", file=sys.stderr, flush=True)
                chunk = delta.get("text")
                if chunk:
                    if first_token is None:
                        first_token = time.perf_counter() - start
                        if reasoning_chunks and on_text is None:
                            print(")", file=sys.stderr, flush=True)
                    if on_text is None:
                        print(chunk, end="", flush=True)
                    else:
                        on_text(chunk)
                    parts.append(chunk)
            elif "contentBlockStop" in event:
                index = event["contentBlockStop"]["contentBlockIndex"]
                if index in tools:
                    tools[index]["complete"] = True
            elif "messageStop" in event:
                stop = event["messageStop"].get("stopReason")
            elif "metadata" in event:
                usage = event["metadata"].get("usage", {})  # token counts arrive last
                if on_usage is not None:
                    on_usage(usage, first_token)
            else:
                for key, val in event.items():
                    if key.endswith("Exception"):
                        raise DeskError(f"Stream error: {key}: {val.get('message', '')}")
    except (ClientError, ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
        if not parts:
            if reasoning_chunks and on_text is None:
                print(")", file=sys.stderr, flush=True)
            raise  # no answer text printed yet, so the caller may safely retry
        print()
        raise DeskError(f"Stream broke mid-reply: {_describe(exc)}") from exc
    if reasoning_chunks and first_token is None and on_text is None:
        print(")", file=sys.stderr, flush=True)  # thought but produced no answer text
    if tools or stop == "tool_use":
        if stop != "tool_use" or not tools or not all(tool["complete"] for tool in tools.values()):
            raise DeskError("The skill request was incomplete; no workflow was run. Please try again.")
        parsed = []
        for tool in tools.values():
            try:
                value = json.loads(tool["input"])
                if not isinstance(value, dict) or not tool.get("name") or not tool.get("toolUseId"):
                    raise ValueError("Invalid tool arguments.")
            except (ValueError, TypeError) as exc:
                raise DeskError("The model returned invalid skill arguments; no workflow was run.") from exc
            parsed.append({"name": tool["name"], "toolUseId": tool["toolUseId"], "input": value})
        tool_uses.extend(parsed)
    if on_text is None:
        print()
    return "".join(parts).strip(), usage, time.perf_counter() - start, first_token, stop


def stream_model(client, model, messages, temperature, max_tokens, system_prompt, *, tool_config=None, tool_uses=None, on_text=None):
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
            observed = False
            def observe_usage(usage, first_token):
                nonlocal observed
                observed = True
                note_response(usage, started=start, first_token=first_token, attempts=attempt)
            resp = client.converse_stream(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=messages,
                inferenceConfig=inference,
                **({"toolConfig": tool_config} if tool_config is not None else {}),
            )
            try:
                text, usage, latency, first_token, stop = _render_stream(resp["stream"], start, tool_uses=tool_uses,
                    on_text=on_text, on_usage=observe_usage)
            except DeskError:
                if not observed:
                    note_failure(attempt)
                raise
            finally:
                close = getattr(resp["stream"], "close", None)
                if close is not None:
                    close()
            if not observed:
                note_response(usage, started=start, first_token=first_token, attempts=attempt)
            return text, usage, latency, first_token, attempt, stop
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in RETRYABLE_CODES:
                note_failure(attempt)
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

    note_failure(MAX_ATTEMPTS)
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


def call_structured_model(client, model, messages, schema, max_tokens, system_prompt,
                          *, schema_name="order_request"):
    """One native-schema response, with at most MAX_ATTEMPTS transport attempts.

    Reuses the existing client, retry codes and backoff policy. No JSON prompt
    fallback: an unsupported SDK/model/schema is an explicit review outcome.
    """
    shape = client.meta.service_model.operation_model("Converse").input_shape
    if "outputConfig" not in shape.members:
        raise StructuredRequestError(
            "Installed Bedrock SDK lacks outputConfig; install requirements.txt.",
            attempts=0, code="UnsupportedSDK", category="capability_error",
        )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            _simulate_failure()
            response = client.converse(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=messages,
                inferenceConfig={"maxTokens": max_tokens},
                outputConfig={"textFormat": {
                    "type": "json_schema",
                    "structure": {"jsonSchema": {
                        "name": schema_name,
                        "description": "Schema-constrained email extraction or source verification",
                        "schema": json.dumps(schema),
                    }},
                }},
            )
            note_response(response.get("usage", {}), started=start, attempts=attempt)
            return {
                "raw_text": "".join(
                    block["text"] for block in response.get("output", {}).get("message", {}).get("content", [])
                    if "text" in block
                ),
                "stop_reason": response.get("stopReason"),
                "usage": response.get("usage", {}),
                "transport_attempts": attempt,
                "latency_s": round(time.perf_counter() - start, 3),
                "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
            }
        except (ClientError, BotoCoreError) as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError") if isinstance(exc, ClientError) else type(exc).__name__
            retryable = code in RETRYABLE_CODES or isinstance(
                exc, (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError)
            )
            if not retryable or attempt == MAX_ATTEMPTS:
                note_failure(attempt)
                category = "capability_error" if code in {"ValidationException", "ParamValidationError"} else "provider_error"
                raise StructuredRequestError(
                    f"Native Bedrock request failed: {_describe(exc)}",
                    attempts=attempt, code=code, category=category,
                ) from exc
            delay = BASE_DELAY_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            print(f"[structured request {attempt}/{MAX_ATTEMPTS} failed: {code}; retrying in {delay:.1f}s]", file=sys.stderr)
            time.sleep(delay)
