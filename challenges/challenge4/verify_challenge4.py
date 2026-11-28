"""Opt-in actual local retrieval baseline and bounded live Desk demonstrations.

    .venv/Scripts/python.exe challenges/challenge4/verify_challenge4.py [--live]
Requires an ingested default policy index; --live permits four ask calls and
two /ask turns using the existing answer provider. Never changes policy files.
"""

import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import desk
from naive_rag.local_embeddings import DEFAULT_RAG_DB_DIR, configured_embeddings, project_path
from naive_rag.retrieval import retrieve_chunks

# Assistant-defined expected sources, checked against the policy text.
# These are a small diagnostic set, not human-certified ground truth.
CASES = [
    ("For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee?", ["returns-2025-10.md"]),
    ("How do January and October 2025 return policies differ in window and restocking fee?", ["returns-2025-01.md", "returns-2025-10.md"]),
    ("What bulk discount applies to a line of 250 selling units of one SKU?", ["bulk-pricing.md"]),
    ("Which standard carriers, transit times and below-threshold shipping rates are listed?", ["shipping.md"]),
    ("Who can raise a credit limit and what does Net 30 mean?", ["credit-terms.md"]),
    ("How long is the limited warranty for stock tools and what manufacturing defects does it cover?", ["warranty.md"]),
    ("How soon must visible transit damage or a short shipment be reported?", ["damaged-goods.md"]),
    ("Can opened hazardous chemicals be returned or shipped by USPS?", ["hazardous-goods.md"]),
    ("Can a delivered order be cancelled and is there a cancellation fee before dispatch?", ["order-cancellation.md"]),
    ("Who must approve a refund over $500 and does a one-dollar refund need approval?", ["price-adjustments-and-refunds.md"]),
]


class MeasuredOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushed_length = 0

    def flush(self):
        self.flushed_length = len(self.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / ".desk" / "challenge4-verification" / stamp
    output.mkdir(parents=True)
    report = dict(started_ist=datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                  db_dir=str(project_path(os.environ.get("DESK_RAG_DB_DIR", DEFAULT_RAG_DB_DIR))),
                  expected_source_provenance="assistant-defined from policy text; not human-certified",
                  baseline=[], live=[], answer_provider_requests_authorized=args.live)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "data/policies").glob("*.md")}
    os.environ["DESK_EMBED_OFFLINE"] = "1"
    os.environ["DESK_MAX_TOKENS"] = "2000"
    embedder = configured_embeddings(offline=True)
    def save():
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for question, expected in CASES:
        chunks = retrieve_chunks(question, embedder=embedder)
        found = {chunk.source_file for chunk in chunks}
        report["baseline"].append(dict(question=question, expected_sources=expected,
            retrieved=[dict(id=chunk.chunk_id, score=chunk.score) for chunk in chunks],
            hit_at_4=bool(found & set(expected)), expected_source_coverage=len(found & set(expected)) / len(expected)))
    report["hit_at_4"] = sum(row["hit_at_4"] for row in report["baseline"]) / len(CASES)
    report["embedding"] = embedder.fingerprint
    save()
    print(f"Local retrieval hit@4: {sum(row['hit_at_4'] for row in report['baseline'])}/{len(CASES)} (assistant-defined labels)", flush=True)
    if args.live:
        examples = [
            ("out-of-scope", "What is the favorite color of the CEO of Meridian Supply Co.?"),
            ("exact-sku", "What are the specifications and stock availability of SKU MS-VLV-0200?"),
            ("table", "What bulk discount applies to 250 selling units of one SKU?"),
            ("conflict", "How do the January and October 2025 returns policies differ in return window and restocking fee?"),
        ]
        for name, question in examples:
            stdout, stderr = MeasuredOutput(), io.StringIO()
            argv = ["ask", question, "--debug"]
            print(f"Live Desk check: {name}", flush=True)
            measurement = dict(deltas=[])
            original_stream = desk.stream_model
            def measured_stream(*arguments, **options):
                began = time.perf_counter()
                callback = options["on_text"]
                def emit(value):
                    callback(value)
                    measurement["deltas"].append(dict(elapsed_s=time.perf_counter() - began,
                        characters=len(value), stdout_flushed=stdout.flushed_length == len(stdout.getvalue()),
                        visible_after_callback=stdout.getvalue().endswith(value)))
                options["on_text"] = emit
                try:
                    return original_stream(*arguments, **options)
                finally:
                    measurement["provider_stream_returned_s"] = time.perf_counter() - began
            desk.stream_model = measured_stream
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code, result = desk._dispatch_cli(argv)
            finally:
                desk.stream_model = original_stream
            measurement["visible_before_completion"] = bool(measurement["deltas"]) and all(
                event["stdout_flushed"] and event["visible_after_callback"] and
                event["elapsed_s"] < measurement["provider_stream_returned_s"] for event in measurement["deltas"])
            transcript = stdout.getvalue() + stderr.getvalue()
            (output / f"{name}.txt").write_text(transcript, encoding="utf-8")
            report["live"].append(dict(name=name, argv=argv, exit_code=code, result=result, transcript=transcript,
                                      streaming=measurement))
            save()
            if code != 0:
                report["provider_blocker"] = transcript
                print("Live check failed; remaining provider calls stopped. See report.", flush=True)
                break
        else:
            session_name = "challenge4-" + stamp
            commands = ["/ask " + CASES[0][0] + " --debug", "/ask what about for bulk? --debug",
                        "/save " + session_name, "/exit"]
            print("Live Desk chat: return policy then raw vague follow-up", flush=True)
            process = subprocess.run([sys.executable, str(ROOT / "src/desk.py"), "chat"],
                input="\n".join(commands) + "\n", capture_output=True, text=True, encoding="utf-8",
                cwd=ROOT, timeout=180)
            transcript = process.stdout + process.stderr
            (output / "chat.txt").write_text(transcript, encoding="utf-8")
            session_file = ROOT / "save" / (session_name + ".json")
            report["chat"] = dict(commands=commands, exit_code=process.returncode,
                transcript=transcript, session_path=str(session_file),
                session=json.loads(session_file.read_text(encoding="utf-8")) if session_file.exists() else None)
    report["policies_unchanged"] = hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                            for path in (ROOT / "data/policies").glob("*.md")}
    assert report["policies_unchanged"]
    report["finished_ist"] = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
    save()
    print(f"Evidence: {output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
