"""Unit tests for GeminiVertexAdapter."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import LLMConnectionError, LLMParseError, LLMRateLimitError


class TestStripCodeFence:
    """Tests for code fence stripping."""

    def test_removes_json_code_fence(self):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        text = '```json\n[{"key": "value"}]\n```'
        result = GeminiVertexAdapter._strip_code_fence(text)
        assert result == '[{"key": "value"}]'

    def test_removes_plain_code_fence(self):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        text = "```\n[1, 2, 3]\n```"
        result = GeminiVertexAdapter._strip_code_fence(text)
        assert result == "[1, 2, 3]"

    def test_handles_no_code_fence(self):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        text = '{"key": "value"}'
        result = GeminiVertexAdapter._strip_code_fence(text)
        assert result == '{"key": "value"}'

    def test_handles_whitespace(self):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        text = "  ```json\n[1, 2]\n```  "
        result = GeminiVertexAdapter._strip_code_fence(text)
        assert result == "[1, 2]"


class TestParseGraph:
    """Tests for entity graph parsing."""

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_parses_valid_graph(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        text = json.dumps(
            {
                "entities": [{"id": "1", "name": "Test", "type": "Company"}],
                "relationships": [{"source": "user", "target": "1", "label": "bought_from"}],
            }
        )
        result = adapter._parse_graph(text)
        assert len(result["entities"]) == 1
        assert len(result["relationships"]) == 1

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_raises_on_invalid_json(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        with pytest.raises(LLMParseError):
            adapter._parse_graph("not json")

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_missing_fields(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        result = adapter._parse_graph("{}")
        assert result["entities"] == []
        assert result["relationships"] == []

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_returns_empty_for_invalid_structure(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        result = adapter._parse_graph('{"entities": "not a list", "relationships": []}')
        assert result == {"entities": [], "relationships": []}


class TestParseCategories:
    """Tests for category parsing."""

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_parses_valid_categories(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        text = json.dumps(
            [
                {"index": 0, "categories": ["Shopping", "E-commerce"]},
                {"index": 1, "categories": ["Food"]},
            ]
        )
        result = adapter._parse_categories(text)
        assert len(result) == 2
        assert result[0]["index"] == 0
        assert result[0]["categories"] == ["Shopping", "E-commerce"]

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_raises_on_invalid_json(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        with pytest.raises(LLMParseError):
            adapter._parse_categories("not json")

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_string_category(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        text = json.dumps([{"index": 0, "categories": "SingleCategory"}])
        result = adapter._parse_categories(text)
        assert result[0]["categories"] == ["SingleCategory"]

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_filters_empty_categories(self, mock_model):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        adapter = GeminiVertexAdapter("test-model")
        text = json.dumps([{"index": 0, "categories": ["Valid", "", "  ", "Also Valid"]}])
        result = adapter._parse_categories(text)
        assert result[0]["categories"] == ["Valid", "Also Valid"]


class TestCallModel:
    """Tests for LLM model calls."""

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_successful_call(self, mock_model_class):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "response text"
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model

        adapter = GeminiVertexAdapter("test-model")
        result = adapter._call_model("test prompt")
        assert result == "response text"

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_empty_response(self, mock_model_class):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = None
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model

        adapter = GeminiVertexAdapter("test-model")
        result = adapter._call_model("test prompt")
        assert result == ""

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_rate_limit(self, mock_model_class):
        from google.api_core import exceptions as real_exceptions

        from app.adapters.gemini_vertex import GeminiVertexAdapter

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = real_exceptions.ResourceExhausted("Rate limit")
        mock_model_class.return_value = mock_model

        adapter = GeminiVertexAdapter("test-model")
        with pytest.raises(LLMRateLimitError):
            adapter._call_model("test prompt")

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_service_unavailable(self, mock_model_class):
        from google.api_core import exceptions as real_exceptions

        from app.adapters.gemini_vertex import GeminiVertexAdapter

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = real_exceptions.ServiceUnavailable("Down")
        mock_model_class.return_value = mock_model

        adapter = GeminiVertexAdapter("test-model")
        with pytest.raises(LLMConnectionError):
            adapter._call_model("test prompt")

    @patch("app.adapters.gemini_vertex.GenerativeModel")
    def test_handles_generic_exception(self, mock_model_class):
        from app.adapters.gemini_vertex import GeminiVertexAdapter

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("Unknown error")
        mock_model_class.return_value = mock_model

        adapter = GeminiVertexAdapter("test-model")
        with pytest.raises(LLMConnectionError):
            adapter._call_model("test prompt")
