"""Opt-in regression test against real PostgreSQL + pgvector, without API calls."""

import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql


@unittest.skipUnless(os.getenv("RAG_TEST_DATABASE_URL"), "requires RAG_TEST_DATABASE_URL")
class DatabaseSetupTests(unittest.TestCase):
    def test_fresh_schema_supports_default_embeddings_and_cosine_search(self):
        # Every object and row is rolled back, including when initialization fails.
        connection = psycopg.connect(os.environ["RAG_TEST_DATABASE_URL"])
        try:
            with connection.cursor() as cursor:
                schema = sql.Identifier("opu40_" + uuid4().hex)
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(schema))
                init_sql = Path(__file__).resolve().parents[1] / "database" / "init.sql"
                cursor.execute(init_sql.read_text(encoding="utf-8"))
                # Initialization must also be safe to rerun.
                cursor.execute(init_sql.read_text(encoding="utf-8"))
                vector = "[1," + ",".join(["0"] * 3071) + "]"
                cursor.execute(
                    "INSERT INTO document_chunks (source, content, embedding) "
                    "VALUES ('cpu.md', 'Check CPU usage.', %s::vector)",
                    (vector,),
                )
                cursor.execute(
                    "SELECT source, vector_dims(embedding), "
                    "1 - (embedding <=> %s::vector) FROM document_chunks "
                    "ORDER BY embedding <=> %s::vector LIMIT 1",
                    (vector, vector),
                )
                self.assertEqual(cursor.fetchone(), ("cpu.md", 3072, 1.0))
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
