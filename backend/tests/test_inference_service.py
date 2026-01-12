"""Unit tests for InferenceService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import LLMError, LLMParseError
from app.services.inference_service import InferenceService


class TestDeduplicateRules:
    """Tests for rule deduplication."""

    def test_removes_duplicates(self):
        rules = [
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"},
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"},
            {"pattern": "Starbucks", "match_field": "description", "entity": "Starbucks", "category": "Food"},
        ]
        deduped = InferenceService._deduplicate_rules(rules)
        assert len(deduped) == 2

    def test_keeps_different_rules(self):
        rules = [
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"},
            {"pattern": "Amazon", "match_field": "note", "entity": "Amazon", "category": "Shopping"},
        ]
        deduped = InferenceService._deduplicate_rules(rules)
        assert len(deduped) == 2

    def test_empty_rules(self):
        deduped = InferenceService._deduplicate_rules([])
        assert deduped == []

    def test_preserves_order(self):
        rules = [
            {"pattern": "First", "match_field": "description", "entity": "A", "category": ""},
            {"pattern": "Second", "match_field": "description", "entity": "B", "category": ""},
        ]
        deduped = InferenceService._deduplicate_rules(rules)
        assert deduped[0]["pattern"] == "First"
        assert deduped[1]["pattern"] == "Second"


class TestApplyRules:
    """Tests for rule application."""

    def test_applies_matching_rule(self):
        transactions = [
            {
                "description": "Amazon Purchase",
                "amount": -100,
                "raw": {"note": "", "display": "", "memo": ""},
            }
        ]
        rules = [
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"}
        ]
        result = InferenceService.apply_rules(transactions, rules)
        assert result[0]["entity"] == "Amazon"
        assert result[0]["category"] == "Shopping"

    def test_no_matching_rule_uses_default(self):
        transactions = [
            {
                "description": "Random Store",
                "amount": -100,
                "raw": {"note": "", "display": "", "memo": ""},
            }
        ]
        rules = [
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"}
        ]
        result = InferenceService.apply_rules(transactions, rules)
        assert result[0]["entity"] == "Debit"  # Default for negative amount

    def test_positive_amount_default_credit(self):
        transactions = [
            {
                "description": "Unknown Deposit",
                "amount": 100,
                "raw": {"note": "", "display": "", "memo": ""},
            }
        ]
        result = InferenceService.apply_rules(transactions, [])
        assert result[0]["entity"] == "Credit"

    def test_matches_different_fields(self):
        transactions = [
            {
                "description": "Regular Transaction",
                "amount": -50,
                "raw": {"note": "Amazon", "display": "", "memo": ""},
            }
        ]
        rules = [
            {"pattern": "Amazon", "match_field": "note", "entity": "Amazon", "category": "Shopping"}
        ]
        result = InferenceService.apply_rules(transactions, rules)
        assert result[0]["entity"] == "Amazon"

    def test_empty_pattern_not_matched(self):
        transactions = [
            {
                "description": "Test",
                "amount": -50,
                "raw": {"note": "", "display": "", "memo": ""},
            }
        ]
        rules = [
            {"pattern": "", "match_field": "description", "entity": "Empty", "category": ""}
        ]
        result = InferenceService.apply_rules(transactions, rules)
        assert result[0]["entity"] == "Debit"  # Fell through to default

    def test_first_matching_rule_wins(self):
        transactions = [
            {
                "description": "Amazon Starbucks",
                "amount": -50,
                "raw": {"note": "", "display": "", "memo": ""},
            }
        ]
        rules = [
            {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"},
            {"pattern": "Starbucks", "match_field": "description", "entity": "Starbucks", "category": "Food"},
        ]
        result = InferenceService.apply_rules(transactions, rules)
        assert result[0]["entity"] == "Amazon"
        assert result[0]["category"] == "Shopping"


class TestBuildRules:
    """Tests for rule building with LLM."""

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_combines_user_and_llm_rules(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_rules.return_value = [
            {"pattern": "LLM", "match_field": "description", "entity": "LLM", "category": "Tech"}
        ]
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        user_rules = [
            {"pattern": "User", "match_field": "description", "entity": "User", "category": "Custom"}
        ]
        result = service.build_rules([], user_rules=user_rules)
        assert len(result) == 2
        assert any(r["pattern"] == "User" for r in result)
        assert any(r["pattern"] == "LLM" for r in result)

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_handles_llm_parse_error(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_rules.side_effect = LLMParseError("Parse error", raw_response="bad json")
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        user_rules = [
            {"pattern": "User", "match_field": "description", "entity": "User", "category": "Custom"}
        ]
        result = service.build_rules([], user_rules=user_rules)
        assert len(result) == 1  # Only user rules

    @patch("app.services.inference_service.GeminiVertexAdapter")
    def test_propagates_llm_connection_error(self, mock_adapter_class):
        mock_adapter = MagicMock()
        mock_adapter.infer_rules.side_effect = LLMError("Connection failed")
        mock_adapter_class.return_value = mock_adapter

        service = InferenceService()
        with pytest.raises(LLMError):
            service.build_rules([])


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
