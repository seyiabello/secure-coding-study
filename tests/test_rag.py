"""
tests/test_rag.py
-----------------
Unit tests for rag/retriever.py — Advanced RAG pipeline.

Tests cover each pipeline stage in isolation using mocked OpenAI and
ChromaDB calls. No real API calls are made during these tests.

Run:
    python -m pytest tests/test_rag.py -v
    python -m unittest tests.test_rag -v
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

from rag.retriever import (
    AVAILABLE_DOMAINS,
    N_FINAL_RESULTS,
    format_for_prompt,
    rerank,
    rewrite_query,
    search,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(cwe_id: str, domain: str = "injection", distance: float = 0.1) -> dict:
    return {
        "id":       f"{cwe_id}_main",
        "text":     f"Description of {cwe_id}. SQL injection vulnerability...",
        "metadata": {
            "cwe_id":     cwe_id,
            "short_name": f"Test {cwe_id}",
            "rank":       1,
            "severity":   "High",
            "domain":     domain,
            "chunk_type": "main",
        },
        "distance": distance,
    }


def _make_openai_response(content_dict: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(content_dict)
    return mock_resp


def _make_collection(chunks: list[dict]) -> MagicMock:
    mock_col = MagicMock()
    mock_col.count.return_value = len(chunks)
    mock_col.query.return_value = {
        "documents": [[c["text"]     for c in chunks]],
        "metadatas": [[c["metadata"] for c in chunks]],
        "distances": [[c["distance"] for c in chunks]],
        "ids":       [[c["id"]       for c in chunks]],
    }
    return mock_col


# ---------------------------------------------------------------------------
# TestRewriteQuery
# ---------------------------------------------------------------------------

class TestRewriteQuery(unittest.TestCase):

    @patch("rag.retriever.openai_client")
    def test_returns_search_query_and_domains(self, mock_client):
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "search_query":     "SQL injection authentication credential",
            "relevant_domains": ["injection", "access_control"],
        })

        query, domains = rewrite_query("Write a login function")

        self.assertEqual(query, "SQL injection authentication credential")
        self.assertIn("injection",      domains)
        self.assertIn("access_control", domains)

    @patch("rag.retriever.openai_client")
    def test_filters_invalid_domains(self, mock_client):
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "search_query":     "authentication security",
            "relevant_domains": ["injection", "not_a_real_domain", "access_control"],
        })

        _, domains = rewrite_query("Write a login function")

        self.assertNotIn("not_a_real_domain", domains)
        self.assertIn("injection",      domains)
        self.assertIn("access_control", domains)

    @patch("rag.retriever.openai_client")
    def test_falls_back_to_all_domains_when_none_valid(self, mock_client):
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "search_query":     "something",
            "relevant_domains": ["made_up", "nonsense"],
        })

        _, domains = rewrite_query("Write a function")

        self.assertEqual(domains, AVAILABLE_DOMAINS)

    @patch("rag.retriever.openai_client")
    def test_falls_back_to_task_when_no_search_query(self, mock_client):
        task = "Write a file upload handler"
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "relevant_domains": ["injection"],
        })

        query, _ = rewrite_query(task)

        self.assertEqual(query, task)

    @patch("rag.retriever.openai_client")
    def test_calls_openai_once(self, mock_client):
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "search_query": "query", "relevant_domains": ["injection"],
        })

        rewrite_query("task")

        mock_client.chat.completions.create.assert_called_once()


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------

class TestSearch(unittest.TestCase):

    def test_returns_correct_structure(self):
        chunks = [_make_chunk("CWE-89"), _make_chunk("CWE-20")]
        collection = _make_collection(chunks)

        results = search(collection, "sql injection", ["injection"])

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIn("id",       r)
            self.assertIn("text",     r)
            self.assertIn("metadata", r)
            self.assertIn("distance", r)

    def test_applies_domain_filter(self):
        collection = _make_collection([_make_chunk("CWE-89")])

        search(collection, "sql injection", ["injection", "memory"])

        call_kwargs = collection.query.call_args.kwargs
        self.assertEqual(
            call_kwargs["where"],
            {"domain": {"$in": ["injection", "memory"]}},
        )

    def test_returns_empty_list_for_empty_collection(self):
        mock_col = MagicMock()
        mock_col.count.return_value = 0
        mock_col.query.return_value = {
            "documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]],
        }

        results = search(mock_col, "sql injection", ["injection"])

        self.assertEqual(results, [])

    def test_metadata_preserved(self):
        chunk = _make_chunk("CWE-89")
        collection = _make_collection([chunk])

        results = search(collection, "query", ["injection"])

        self.assertEqual(results[0]["metadata"]["cwe_id"], "CWE-89")
        self.assertEqual(results[0]["id"], "CWE-89_main")


# ---------------------------------------------------------------------------
# TestRerank
# ---------------------------------------------------------------------------

class TestRerank(unittest.TestCase):

    @patch("rag.retriever.openai_client")
    def test_returns_all_when_candidates_lte_n_final(self, mock_client):
        # 2 candidates, n_final=3 → return all without calling GPT-4o
        chunks = [_make_chunk("CWE-89"), _make_chunk("CWE-20")]

        results = rerank("task", chunks, n_final=3)

        mock_client.chat.completions.create.assert_not_called()
        self.assertEqual(results, chunks)

    @patch("rag.retriever.openai_client")
    def test_selects_top_n_by_llm(self, mock_client):
        chunks = [_make_chunk(f"CWE-{cwe}") for cwe in [89, 20, 22, 79, 200]]
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "top_indices": [2, 0, 3],
        })

        results = rerank("task", chunks, n_final=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["metadata"]["cwe_id"], "CWE-22")
        self.assertEqual(results[1]["metadata"]["cwe_id"], "CWE-89")
        self.assertEqual(results[2]["metadata"]["cwe_id"], "CWE-79")

    @patch("rag.retriever.openai_client")
    def test_handles_out_of_range_indices(self, mock_client):
        chunks = [_make_chunk(f"CWE-{cwe}") for cwe in [89, 20, 22, 79, 200]]
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "top_indices": [99, 0],  # 99 is out of range
        })

        results = rerank("task", chunks, n_final=3)

        # Should still return 3 results, padded after the 1 valid index (0)
        self.assertEqual(len(results), 3)
        cwe_ids = [r["metadata"]["cwe_id"] for r in results]
        self.assertIn("CWE-89", cwe_ids)

    @patch("rag.retriever.openai_client")
    def test_deduplicates_by_cwe_id(self, mock_client):
        chunks = [
            _make_chunk("CWE-89", distance=0.1),
            _make_chunk("CWE-89", distance=0.2),  # duplicate CWE
            _make_chunk("CWE-20", distance=0.3),
            _make_chunk("CWE-22", distance=0.4),
        ]
        chunks[1]["id"] = "CWE-89_detail"
        mock_client.chat.completions.create.return_value = _make_openai_response({
            "top_indices": [0, 1, 2],  # both CWE-89 variants selected
        })

        results = rerank("task", chunks, n_final=3)

        cwe_ids = [r["metadata"]["cwe_id"] for r in results]
        self.assertEqual(cwe_ids.count("CWE-89"), 1)

    @patch("rag.retriever.openai_client")
    def test_exact_n_final_candidates_skips_llm(self, mock_client):
        chunks = [_make_chunk("CWE-89"), _make_chunk("CWE-20"), _make_chunk("CWE-22")]

        results = rerank("task", chunks, n_final=3)

        mock_client.chat.completions.create.assert_not_called()
        self.assertEqual(len(results), 3)


# ---------------------------------------------------------------------------
# TestFormatForPrompt
# ---------------------------------------------------------------------------

class TestFormatForPrompt(unittest.TestCase):

    def test_empty_results_returns_fallback_message(self):
        result = format_for_prompt([])
        self.assertEqual(result, "No relevant CWE entries found.")

    def test_formats_single_result(self):
        chunks = [_make_chunk("CWE-89")]
        result = format_for_prompt(chunks)

        self.assertIn("CWE-89",     result)
        self.assertIn("Test CWE-89", result)
        self.assertIn("[1]",         result)

    def test_formats_multiple_results_in_order(self):
        chunks = [_make_chunk("CWE-89"), _make_chunk("CWE-20"), _make_chunk("CWE-22")]
        result = format_for_prompt(chunks)

        self.assertIn("[1]", result)
        self.assertIn("[2]", result)
        self.assertIn("[3]", result)
        pos1 = result.index("CWE-89")
        pos2 = result.index("CWE-20")
        pos3 = result.index("CWE-22")
        self.assertLess(pos1, pos2)
        self.assertLess(pos2, pos3)

    def test_contains_metadata_fields(self):
        chunks = [_make_chunk("CWE-89")]
        result = format_for_prompt(chunks)

        self.assertIn("High",      result)       # severity
        self.assertIn("injection", result)       # domain
        self.assertIn("1/25",      result)       # rank/25

    def test_chunk_text_included(self):
        chunks = [_make_chunk("CWE-89")]
        result = format_for_prompt(chunks)
        self.assertIn("SQL injection vulnerability", result)


# ---------------------------------------------------------------------------
# TestRetrieve  (integration — all external calls mocked)
# ---------------------------------------------------------------------------

class TestRetrieve(unittest.TestCase):

    @patch("rag.retriever.rerank")
    @patch("rag.retriever.search")
    @patch("rag.retriever.get_collection")
    @patch("rag.retriever.rewrite_query")
    def test_full_pipeline_calls_all_stages(
        self, mock_rewrite, mock_get_col, mock_search, mock_rerank
    ):
        from rag.retriever import retrieve

        task = "Write a secure login function"
        mock_rewrite.return_value = ("sql injection auth", ["injection"])
        mock_collection = MagicMock()
        mock_get_col.return_value = mock_collection
        candidates = [_make_chunk("CWE-89"), _make_chunk("CWE-20")]
        mock_search.return_value = candidates
        final_chunks = [_make_chunk("CWE-89")]
        mock_rerank.return_value = final_chunks

        results = retrieve(task)

        mock_rewrite.assert_called_once_with(task)
        mock_get_col.assert_called_once()
        mock_search.assert_called_once_with(mock_collection, "sql injection auth", ["injection"])
        mock_rerank.assert_called_once_with(task, candidates, N_FINAL_RESULTS)
        self.assertEqual(results, final_chunks)

    @patch("rag.retriever.rerank")
    @patch("rag.retriever.search")
    @patch("rag.retriever.get_collection")
    @patch("rag.retriever.rewrite_query")
    def test_retrieve_returns_top_n_chunks(
        self, mock_rewrite, mock_get_col, mock_search, mock_rerank
    ):
        from rag.retriever import retrieve

        mock_rewrite.return_value = ("query", ["injection"])
        mock_get_col.return_value = MagicMock()
        mock_search.return_value = [_make_chunk(f"CWE-{i}") for i in range(10)]
        expected = [_make_chunk("CWE-89"), _make_chunk("CWE-20"), _make_chunk("CWE-22")]
        mock_rerank.return_value = expected

        results = retrieve("task", n_final=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results, expected)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
