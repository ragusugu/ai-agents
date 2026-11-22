"""Desk, Challenge 1: one question in, one answer out.

Usage:
    python desk.py ask "your question" [--model ID] [--temperature T]

Provider: Amazon Bedrock via the raw boto3 SDK (Converse API). No agent framework.

Environment variables:
    DESK_MODEL       Bedrock model or inference-profile ID (default: us.moonshotai.kimi-k3.1)
    AWS_REGION       Region (default: us-east-1). AWS credentials come from the standard
                     AWS chain (env vars or ~/.aws), never from code.
    DESK_PRICE_IN    USD per 1M input tokens  (optional, enables the cost estimate)
    DESK_PRICE_OUT   USD per 1M output tokens (optional)
    DESK_MAX_TOKENS  Output cap, reasoning models spend tokens thinking (default: 4000)
    DESK_SIMULATE    "429" or "timeout": fail every attempt on purpose, to test retries
"""

import argparse
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


def load_dotenv(path=None):
    """Load variables from a .env file into os.environ if not already present."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
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


def call_model(client, model, question, temperature, max_tokens):
    """One Converse call with retry. Returns (text, usage, latency_s, attempts)."""
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
                messages=[{"role": "user", "content": [{"text": question}]}],
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


def estimate_cost(usage):
    p_in = os.environ.get("DESK_PRICE_IN")
    p_out = os.environ.get("DESK_PRICE_OUT")
    if not (p_in and p_out):
        return "n/a (set DESK_PRICE_IN / DESK_PRICE_OUT, USD per 1M tokens)"
    cost = (usage["inputTokens"] * float(p_in) + usage["outputTokens"] * float(p_out)) / 1_000_000
    return f"${cost:.6f}"


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


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="desk", description="Desk: Meridian Supply Co. assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="send one question to the model")
    ask.add_argument("question")
    ask.add_argument("--model", help="override DESK_MODEL")
    ask.add_argument("--temperature", type=float, help="sampling temperature (e.g. 0 or 1)")
    ask.set_defaults(func=cmd_ask)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except DeskError as exc:
        print(f"desk: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
