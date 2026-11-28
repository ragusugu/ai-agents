"""Opt-in actual CPU-model smoke: cached model + isolated synthetic policies.

Run after caching the selected model:
    .venv/Scripts/python.exe challenges/challenge4/smoke_ingest.py
Leaves evidence under .desk/ingest-smoke; never reads/modifies real policies.
"""

import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from naive_rag.local_embeddings import LocalEmbeddings
from model import DeskError
from naive_rag.ingest import ingest_policies
from naive_rag.vector_store import PolicyStore


def diagnose(db, embedder):
    """Read actual stored vectors and search directly; not desk ask/RAG."""
    collection = PolicyStore(db).client.get_collection("desk_policies", embedding_function=None)
    rows = collection.get(include=["documents", "embeddings", "metadatas"])
    assert rows["ids"]
    for vector in rows["embeddings"]:
        assert len(vector) == 384 and all(math.isfinite(value) for value in vector)
        assert abs(sum(value * value for value in vector) - 1) < 1e-5
    recomputed = embedder.embed_documents([rows["documents"][0]])[0]
    difference = max(abs(a - b) for a, b in zip(recomputed, rows["embeddings"][0]))
    assert difference < 1e-5
    instruction = "Represent this sentence for searching relevant passages: "
    vector = embedder.embed_documents([instruction + "What is the return deadline for unopened stock?"])[0]
    hits = collection.query(query_embeddings=[vector], n_results=min(2, collection.count()),
                            include=["distances", "documents"])
    assert hits["ids"][0][0].startswith("returns.md#")
    return dict(collection="desk_policies", stored_count=len(rows["ids"]), dimension=384,
                finite_normalized_vectors=True, max_recomputed_vector_difference=float(difference),
                lookup_ids=hits["ids"][0], cosine_similarities=[1 - d for d in hits["distances"][0]],
                sqlite_exists=(Path(db) / "chroma.sqlite3").is_file(),
                artifacts=sorted(path.name for path in Path(db).iterdir()))


def main():
    run_dir = ROOT / ".desk" / "ingest-smoke" / uuid.uuid4().hex
    source = run_dir / "policy folder"
    source.mkdir(parents=True)
    returns = source / "returns.md"
    returns.write_text("# Returns\n" + "Unopened stock may be returned within thirty days.\n" * 480, encoding="utf-8")
    bulk = source / "bulk.md"
    bulk.write_text("# Bulk pricing\n| Quantity | Discount |\n| 100 | 5% |\nSKU: MS-VLV-0200\n", encoding="utf-8")
    db = run_dir / "db"
    embedder = LocalEmbeddings(offline=True)
    report = dict(source="isolated synthetic fixture only", run_dir=str(run_dir), answer_api_calls=0, progress=[])
    started = time.perf_counter()
    def ingest(path=source, **options):
        def progress(event):
            report["progress"].append(dict(event, elapsed_s=time.perf_counter() - started))
            print(event["message"], flush=True)
        result = ingest_policies(path, db_dir=db, embedder=embedder, progress=progress, **options)
        print(json.dumps(result), flush=True)
        return result
    report["initial"] = ingest()
    report["repeat"] = ingest()
    report["diagnostic"] = diagnose(db, embedder)
    assert report["initial"]["files_updated"] == 2
    assert report["initial"]["embedded_chunks"] > 8
    assert report["repeat"]["files_unchanged"] == 2
    assert report["repeat"]["embedded_chunks"] == 0
    assert report["initial"]["chunks_total"] == report["repeat"]["chunks_total"]
    cli = subprocess.run([sys.executable, str(ROOT / "src" / "desk.py"), "ingest", str(source),
                          "--db-dir", str(db), "--offline"], capture_output=True, text=True,
                         encoding="utf-8", timeout=120)
    report["fresh_process_cli"] = dict(returncode=cli.returncode, stdout=cli.stdout, stderr=cli.stderr)
    assert cli.returncode == 0, cli.stderr
    assert "embedded 0" in cli.stdout
    returns.write_text("Unopened stock may be returned within thirty days.\n", encoding="utf-8")
    report["file_shrink"] = ingest(returns)
    assert report["file_shrink"]["chunks_total"] == 2
    assert report["file_shrink"]["indexed_files_total"] == 2
    bulk.unlink()
    report["deleted_file"] = ingest()
    assert report["deleted_file"]["files_removed"] == 1
    try:
        ingest(chunk_size=400)
    except DeskError as exc:
        report["config_mismatch"] = str(exc)
    else:
        raise AssertionError("configuration mismatch was not rejected")
    report["reset"] = ingest(chunk_size=400, reset=True)
    report["reset_repeat"] = ingest(chunk_size=400)
    assert report["reset_repeat"]["embedded_chunks"] == 0
    report["embedding"] = embedder.fingerprint
    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            report["peak_process_working_set_mib"] = round(counters.PeakWorkingSetSize / 1024**2, 1)
    path = run_dir / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Actual local embedding/Chroma smoke passed. Evidence: {path}")
    PolicyStore(db).client._system.stop()


if __name__ == "__main__":
    main()
