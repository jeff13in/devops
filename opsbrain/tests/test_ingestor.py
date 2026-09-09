"""Unit tests for filesystem document ingestion preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rag.ingestor import PgVectorIngestor, build_chunks, chunk_text


class ChunkingTests(unittest.TestCase):
    def test_chunk_text_preserves_the_configured_overlap(self) -> None:
        chunks = chunk_text("abcdefghijklmnop", chunk_size=10, chunk_overlap=2)

        self.assertEqual(chunks, ["abcdefghij", "ijklmnop"])

    def test_build_chunks_uses_a_stable_relative_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runbook = root / "nested" / "cpu.md"
            runbook.parent.mkdir()
            runbook.write_text("Scale the service when CPU is sustained above 85%.")

            chunks = build_chunks(root)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].source, "nested/cpu.md")
        self.assertEqual(chunks[0].metadata["path"], "nested/cpu.md")

    def test_reingestion_replaces_existing_source_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "cpu.md").write_text("Scale the service when CPU is high.")
            embedding_client = MagicMock()
            embedding_client.embed_documents.return_value = [[0.1, 0.2]]
            cursor = MagicMock()
            cursor.__enter__.return_value = cursor
            connection = MagicMock()
            connection.__enter__.return_value = connection
            connection.cursor.return_value = cursor

            ingestor = PgVectorIngestor()
            with patch.object(ingestor, "_ensure_dependencies"):
                with patch(
                    "rag.ingestor.GoogleGenerativeAIEmbeddings",
                    return_value=embedding_client,
                ):
                    with patch("rag.ingestor.psycopg.connect", return_value=connection):
                        first_result = ingestor.ingest(root)
                        second_result = ingestor.ingest(root)

        self.assertEqual(first_result.chunks_stored, 1)
        self.assertEqual(second_result.chunks_stored, 1)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(cursor.executemany.call_count, 2)


if __name__ == "__main__":
    unittest.main()
