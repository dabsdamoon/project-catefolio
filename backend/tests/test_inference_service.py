"""Unit tests for InferenceService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import LLMError, LLMParseError
from app.services.inference_service import InferenceService


class TestInferGraph:
    """Tests for entity graph inference."""

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_returns_graph_and_raw_text(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_graph.return_value = (
            {"entities": [{"id": "1", "name": "Test"}], "relationships": []},
            "raw response",
        )
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        result, raw = service.infer_graph({"description": "Test"})
        assert len(result["entities"]) == 1
        assert raw == "raw response"

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_handles_parse_error_gracefully(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_graph.side_effect = LLMParseError("Parse error", raw_response="bad json")
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        result, raw = service.infer_graph({"description": "Test"})
        assert result == {"entities": [], "relationships": []}


class TestInferCategories:
    """Tests for batch category inference."""

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_processes_batches(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_categories_batch.return_value = (
            [{"index": 0, "categories": ["Cat1"]}],
            "raw",
        )
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        transactions = [{"description": f"Tx{i}", "amount": i} for i in range(150)]
        results, raw_texts = service.infer_categories(transactions, ["Cat1"], batch_size=100)

        # Should have called twice (150 / 100 = 2 batches)
        assert mock_adapter.infer_categories_batch.call_count == 2

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_handles_batch_errors(self, mock_adapter_class):
        mock_adapter = MagicMock()
        # First batch succeeds, second fails
        mock_adapter.infer_categories_batch.side_effect = [
            ([{"index": 0, "categories": ["Cat1"]}], "raw1"),
            LLMParseError("Parse error", raw_response="bad"),
        ]
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        transactions = [{"description": f"Tx{i}", "amount": i} for i in range(150)]
        results, raw_texts = service.infer_categories(transactions, ["Cat1"], batch_size=100)

        # Should have results from first batch only
        assert len(results) == 1
        assert len(raw_texts) == 2  # Both batches recorded

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_correct_index_offsets(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_categories_batch.return_value = (
            [{"index": 0, "categories": ["Cat1"]}],
            "raw",
        )
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        transactions = [{"description": f"Tx{i}", "amount": i} for i in range(5)]
        service.infer_categories(transactions, ["Cat1"], batch_size=2)

        # Check that batch payloads have correct indices
        calls = mock_adapter.infer_categories_batch.call_args_list
        first_batch_payload = calls[0][0][0]
        assert first_batch_payload[0]["index"] == 0
        assert first_batch_payload[1]["index"] == 1

        second_batch_payload = calls[1][0][0]
        assert second_batch_payload[0]["index"] == 2
        assert second_batch_payload[1]["index"] == 3
