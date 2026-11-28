"""Local ingest contracts: real Chroma/tokenizer, injected embedding/provider I/O."""

import contextlib
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tokenizers import Tokenizer, models, pre_tokenizers, processors
import desk
import presentation as ui
from naive_rag import ingest as rag
from naive_rag.local_embeddings import LocalEmbeddings, project_path, validate_vectors
from model import DeskError
from naive_rag.rag_chunker import PolicySource, chunk_policy, load_policies
from skill_tools import workflow_argv
from naive_rag.vector_store import PolicyStore, ingest_lock


def tokenizer():
    vocab = {word: index for index, word in enumerate(
        ["[UNK]", "[CLS]", "[SEP]", "return", "policy", "bulk", "stock", "days", "thirty", "new", "|", "#"])}
    result = Tokenizer(models.WordPiece(vocab=vocab, unk_token="[UNK]"))
    result.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    result.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]",
        special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    return result


class FakeEmbeddings:
    """Deterministic vectors exercise storage only, not retrieval quality."""
    dimension, max_tokens, model_name = 4, 512, "test-local"

    def __init__(self):
        self.tokenizer = tokenizer()
        self.fingerprint = dict(provider="test-only", model="fixture", dimension=4, artifact="v1")
        self.calls = []

    def prepare(self):
        pass

    def embed_documents(self, texts):
        self.calls.extend(texts)
        return [[value + 1 for value in hashlib.sha256(text.encode()).digest()[:4]] for text in texts]


class IngestTests(unittest.TestCase):
    def setUp(self):
        test_root = ROOT / ".desk" / "test-runs"
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="desk-ingest-", dir=test_root, ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.source = self.root / "policy folder"
        self.source.mkdir()
        self.db = self.root / "db"
        self.embedder = FakeEmbeddings()
        self.write("a.md", "return stock policy " * 20)
        self.write("b.md", "bulk policy thirty days")

    def tearDown(self):
        if self.db.exists():
            # Only this test's isolated Chroma system, never the user's DB.
            PolicyStore(self.db).client._system.stop()
        self.temp.cleanup()

    def write(self, name, text):
        path = self.source / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_ingest(self, source=None, **kwargs):
        options = dict(db_dir=self.db, chunk_size=12, overlap=2, embedder=self.embedder)
        options.update(kwargs)
        return rag.ingest_policies(source or self.source, **options)

    def store(self):
        return PolicyStore(self.db)

    def rows(self):
        return self.store().client.get_collection("desk_policies", embedding_function=None).get(
            include=["documents", "metadatas", "embeddings"])

    def test_idempotence_original_text_metadata_and_restart(self):
        result = self.run_ingest()
        first = self.rows()
        self.assertEqual(result["files_total"], 2)
        self.assertEqual(result["embedded_chunks"], len(first["ids"]))
        self.assertEqual(len(first["ids"]), len(set(first["ids"])))
        for document, meta in zip(first["documents"], first["metadatas"]):
            self.assertIn(document, (self.source / meta["source_file"]).read_text(encoding="utf-8"))
            self.assertEqual(meta["source_path"], str(self.source / meta["source_file"]))
            self.assertEqual(len(first["embeddings"][0]), 4)
        self.embedder.calls.clear()
        second = self.run_ingest()
        self.assertEqual((second["files_unchanged"], second["embedded_chunks"]), (2, 0))
        self.assertEqual(self.embedder.calls, [])
        self.assertEqual(set(self.rows()["ids"]), set(first["ids"]))

    def test_single_file_shrink_preserves_other_records(self):
        self.run_ingest()
        before = {item: doc for item, doc in zip(self.rows()["ids"], self.rows()["documents"])}
        file = self.write("a.md", "new policy")
        result = self.run_ingest(file)
        after = dict(zip(self.rows()["ids"], self.rows()["documents"]))
        self.assertEqual(after["b.md#1"], before["b.md#1"])
        self.assertEqual(set(after), {"a.md#1", "b.md#1"})
        self.assertEqual(result["indexed_files_total"], 2)
        self.assertGreater(result["chunks_removed"], 0)

    def test_deleted_and_empty_files_then_final_file_deletion(self):
        self.run_ingest()
        self.write("a.md", "")
        (self.source / "b.md").unlink()
        result = self.run_ingest()
        self.assertEqual((result["chunks_total"], result["files_removed"]), (0, 1))
        (self.source / "a.md").unlink()
        result = self.run_ingest()
        self.assertEqual((result["files_total"], result["files_removed"]), (0, 1))
        self.assertEqual(self.rows()["ids"], [])

    def test_folder_scope_preserves_other_folder_and_collision_fails(self):
        self.run_ingest()
        other = self.root / "other"
        other.mkdir()
        extra = other / "extra.md"
        extra.write_text("bulk days", encoding="utf-8")
        self.run_ingest(other)
        (self.source / "a.md").unlink()
        (self.source / "b.md").unlink()
        self.run_ingest()
        self.assertEqual(self.rows()["ids"], ["extra.md#1"])
        self.write("extra.md", "new policy")
        with self.assertRaisesRegex(DeskError, "collision"):
            self.run_ingest()
        self.assertEqual(self.rows()["ids"], ["extra.md#1"])

    def test_missing_path_or_invalid_utf8_never_prunes(self):
        self.run_ingest()
        before = self.rows()["ids"]
        for source in (self.root / "missing", self.root / "policy.pdf"):
            if source.suffix:
                source.write_bytes(b"pdf")
            with self.assertRaises(DeskError):
                self.run_ingest(source)
        (self.source / "bad.md").write_bytes(b"\xff")
        with self.assertRaisesRegex(DeskError, "UTF-8"):
            self.run_ingest()
        self.assertEqual(self.rows()["ids"], before)

    def test_config_and_artifact_guard_reset_keeps_other_collection(self):
        self.run_ingest()
        self.store().client.create_collection("unrelated", embedding_function=None)
        with self.assertRaisesRegex(DeskError, "configuration"):
            self.run_ingest(chunk_size=11)
        self.embedder.fingerprint["artifact"] = "v2"
        with self.assertRaisesRegex(DeskError, "configuration"):
            self.run_ingest()
        self.run_ingest(reset=True)
        self.assertIn("unrelated", [collection.name for collection in self.store().client.list_collections()])

    def test_missing_or_corrupt_record_is_reembedded(self):
        self.run_ingest()
        collection = self.store().client.get_collection("desk_policies", embedding_function=None)
        collection.delete(ids=["a.md#1"])
        self.embedder.calls.clear()
        result = self.run_ingest()
        self.assertEqual(result["files_updated"], 1)
        self.assertIn("a.md#1", self.rows()["ids"])
        collection.update(ids=["b.md#1"], documents=["corrupt"], embeddings=[[1., 0., 0., 0.]])
        self.assertEqual(self.run_ingest()["files_updated"], 1)

    def test_embedding_failure_does_not_change_index(self):
        self.run_ingest()
        before = self.rows()["ids"]
        self.write("a.md", "new policy")
        with patch.object(self.embedder, "embed_documents", return_value=[[float("nan")] * 4]):
            with self.assertRaisesRegex(DeskError, "Invalid local embedding"):
                self.run_ingest()
        self.assertEqual(self.rows()["ids"], before)
        self.assertFalse(self.store().pending_path.exists())

    def test_partial_publish_blocks_reuse_and_reset_recovers(self):
        self.run_ingest()
        self.write("a.md", "new policy")
        collection_type = type(self.store().client.get_collection("desk_policies", embedding_function=None))
        with patch.object(collection_type, "upsert", side_effect=RuntimeError("simulated write failure")):
            with self.assertRaisesRegex(DeskError, "partial index"):
                self.run_ingest()
        with self.assertRaisesRegex(DeskError, "interrupted"):
            self.run_ingest()
        self.run_ingest(reset=True)
        self.assertFalse(self.store().pending_path.exists())

    def test_concurrent_ingest_lock_and_invalid_chunks(self):
        with ingest_lock(self.db), self.assertRaisesRegex(DeskError, "Another desk ingest"):
            self.run_ingest()
        for size, overlap in [(511, 50), (0, 0), (12, 12), (12, -1)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(DeskError):
                self.run_ingest(chunk_size=size, overlap=overlap)


class ChunkAndAdapterTests(unittest.TestCase):
    def test_windows_are_source_substrings_with_expected_overlap(self):
        text = "# policy\n\n" + "return bulk stock days " * 15 + "\n| SKU MS-VLV-0200 | தமிழ் |"
        source = PolicySource("policy.md", "sourcehash", text)
        chunks = chunk_policy(source, tokenizer(), 12, 2)
        self.assertGreater(len(chunks), 2)
        for index, chunk in enumerate(chunks, 1):
            self.assertEqual(chunk.chunk_id, f"policy.md#{index}")
            self.assertIn(chunk.text, text)
            self.assertLessEqual(chunk.token_count, 12)
        self.assertEqual(chunks, chunk_policy(source, tokenizer(), 12, 2))
        for first, second in zip(chunks, chunks[1:]):
            first_ids = tokenizer().encode(first.text, add_special_tokens=False).ids
            second_ids = tokenizer().encode(second.text, add_special_tokens=False).ids
            self.assertEqual(first_ids[-2:], second_ids[:2])

    def test_vector_validation_rejects_bad_shape_values_and_normalizes(self):
        for vectors in ([], [[1, 2]], [[0] * 4], [[float("inf")] * 4], [[float("nan")] * 4]):
            with self.subTest(vectors=vectors), self.assertRaises(DeskError):
                validate_vectors(vectors, 1, 4)
        self.assertEqual(validate_vectors([[2, 0, 0, 0]], 1, 4), [[1., 0., 0., 0.]])

    def test_unsupported_model_is_clear_and_lazy(self):
        with self.assertRaisesRegex(DeskError, "Unsupported"):
            LocalEmbeddings(model="remote-titan")
        self.assertIsNone(LocalEmbeddings()._runtime)


class InterfaceTests(unittest.TestCase):
    def state(self):
        return dict(model="unchanged-api-model", messages=[], total_in=0, total_out=0)

    def test_menu_source_prompt_and_quoted_windows_paths(self):
        from chat_commands import command_catalog
        self.assertEqual(len(command_catalog(desk.build_parser())), 8)
        state = self.state()
        with patch.object(desk, "make_client") as client, contextlib.redirect_stdout(io.StringIO()):
            desk.handle_command("/ingest", state)
            self.assertTrue(state["ingest_source_pending"])
            with patch.object(desk, "_dispatch_cli", return_value=(0, dict(command="ingest", text="actual summary"))) as run:
                desk.handle_command(r'/ingest "C:\Policy Folder\returns.md" --offline', state)
            self.assertEqual(run.call_args.args[0], ["ingest", r"C:\Policy Folder\returns.md", "--offline"])
            client.assert_not_called()
        self.assertEqual(state["messages"][-1]["content"][0]["text"], "actual summary")

    def test_cli_does_not_require_answer_model_or_call_provider(self):
        result = dict(files_total=1, indexed_files_total=1, files_updated=1, files_unchanged=0,
            files_removed=0, chunks_total=1, embedded_chunks=1, chunks_removed=0, latency_s=.1,
            source="selected.md", db_dir="isolated", embed_model="local")
        with patch.dict(os.environ, {}, clear=True), patch("naive_rag.ingest.ingest_policies", return_value=result) as run, \
             patch.object(desk, "make_client") as client, contextlib.redirect_stdout(io.StringIO()):
            code, response = desk._dispatch_cli(["ingest", "--source", "selected.md", "--offline"])
        self.assertEqual(code, 0)
        self.assertEqual(response["ingest"], result)
        self.assertEqual(run.call_args.args[0], "selected.md")
        self.assertEqual(project_path(run.call_args.kwargs["db_dir"]), ROOT / "src" / "naive_rag" / "rag_db")
        client.assert_not_called()

    def test_typed_natural_language_tool_uses_shared_workflow_no_answer_call(self):
        tool = dict(name="ingest_policies", input=dict(source=r"C:\Policy Folder\policy.md"))
        self.assertEqual(workflow_argv(tool), ["ingest", tool["input"]["source"]])
        state = self.state()
        with patch.object(desk, "_dispatch_cli", return_value=(0, dict(command="ingest", text="real summary"))) as run, \
             patch.object(desk, "make_client") as client, contextlib.redirect_stdout(io.StringIO()):
            desk._run_chat_skill([tool], "update this policy in the vector DB", state)
        self.assertEqual(run.call_args.args[0], ["ingest", tool["input"]["source"]])
        client.assert_not_called()
        self.assertEqual(state["messages"][-1]["content"][0]["text"], "real summary")
        for invalid in ({}, dict(source=""), dict(source="policy.md", reset=True)):
            with self.assertRaises(DeskError):
                workflow_argv(dict(name="ingest_policies", input=invalid))

    def test_guided_chat_stays_local(self):
        replies = iter(["/ingest", '"C:\\Policy Folder\\policy.md"', "/exit"])
        with patch("chat_commands.chat_reader", return_value=lambda prompt: next(replies)), \
             patch.object(desk, "make_client") as client, \
             patch.object(desk, "_dispatch_cli", return_value=(0, dict(command="ingest", text="indexed"))) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            desk.cmd_chat(desk.build_parser().parse_args(["chat", "--model", "unchanged"]))
        self.assertEqual(run.call_args.args[0], ["ingest", "C:\\Policy Folder\\policy.md"])
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
