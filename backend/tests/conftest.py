"""Pytest fixtures and configuration."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

# Set environment variables before importing app modules
os.environ["LLM_PROVIDER"] = "vertex"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash-lite-001"


@pytest.fixture
def sample_transactions() -> list[dict[str, Any]]:
    """Sample transaction data for testing."""
    return [
        {
            "date": "2024-01-15",
            "description": "Amazon Purchase",
            "amount": -99.99,
            "category": "Shopping",
            "entity": "Amazon",
            "raw": {"note": "", "display": "", "memo": ""},
        },
        {
            "date": "2024-01-16",
            "description": "Salary Deposit",
            "amount": 5000.00,
            "category": "Income",
            "entity": "Employer",
            "raw": {"note": "Monthly salary", "display": "", "memo": ""},
        },
        {
            "date": "2024-01-17",
            "description": "Starbucks Coffee",
            "amount": -5.50,
            "category": "Food & Dining",
            "entity": "Starbucks",
            "raw": {"note": "", "display": "", "memo": "Latte"},
        },
        {
            "date": "2024-01-18",
            "description": "Electric Bill",
            "amount": -150.00,
            "category": "Utilities",
            "entity": "Power Company",
            "raw": {"note": "", "display": "", "memo": ""},
        },
    ]


@pytest.fixture
def sample_rules() -> list[dict[str, str]]:
    """Sample rule data for testing."""
    return [
        {
            "pattern": "Amazon",
            "match_field": "description",
            "entity": "Amazon",
            "category": "Shopping",
        },
        {
            "pattern": "Starbucks",
            "match_field": "description",
            "entity": "Starbucks",
            "category": "Food & Dining",
        },
    ]


@pytest.fixture
def sample_csv_content() -> bytes:
    """Sample CSV file content."""
    csv_data = """date,description,amount,category
2024-01-15,Amazon Purchase,-99.99,Shopping
2024-01-16,Salary Deposit,5000.00,Income
2024-01-17,Starbucks Coffee,-5.50,Food & Dining
"""
    return csv_data.encode("utf-8")


@pytest.fixture
def sample_csv_file(sample_csv_content: bytes) -> UploadFile:
    """Sample CSV upload file."""
    file = BytesIO(sample_csv_content)
    return UploadFile(filename="test_transactions.csv", file=file)


@pytest.fixture
def sample_korean_csv_content() -> bytes:
    """Sample Korean bank statement CSV content."""
    csv_data = """거래일시,보낸분/받는분,출금액(원),입금액(원),적요,메모
2024-01-15,홍길동,50000,0,이체,월세
2024-01-16,주식회사ABC,0,3000000,급여,1월급여
2024-01-17,스타벅스,5500,0,카드결제,커피
"""
    return csv_data.encode("utf-8")


@pytest.fixture
def sample_korean_csv_file(sample_korean_csv_content: bytes) -> UploadFile:
    """Sample Korean CSV upload file."""
    file = BytesIO(sample_korean_csv_content)
    return UploadFile(filename="korean_transactions.csv", file=file)


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        (data_dir / "jobs").mkdir()
        (data_dir / "entities").mkdir()
        (data_dir / "uploads").mkdir()
        yield data_dir


@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """Mock LLM response for entity graph."""
    return {
        "entities": [
            {"id": "1", "name": "Amazon", "type": "Company", "evidence": "Amazon Purchase"},
        ],
        "relationships": [
            {"source": "user", "target": "1", "label": "purchased_from", "evidence": "Amazon Purchase"},
        ],
    }


@pytest.fixture
def mock_category_response() -> list[dict[str, Any]]:
    """Mock LLM response for category inference."""
    return [
        {"index": 0, "categories": ["Shopping", "E-commerce"]},
        {"index": 1, "categories": ["Income", "Salary"]},
        {"index": 2, "categories": ["Food & Dining", "Coffee"]},
    ]


@pytest.fixture
def mock_rules_response() -> list[dict[str, str]]:
    """Mock LLM response for rules inference."""
    return [
        {"pattern": "Amazon", "match_field": "description", "entity": "Amazon", "category": "Shopping"},
        {"pattern": "Starbucks", "match_field": "description", "entity": "Starbucks", "category": "Food & Dining"},
    ]


@pytest.fixture
def mock_gemini_adapter():
    """Mock the GeminiVertexAdapter for testing without LLM calls."""
    with patch("app.adapters.gemini_vertex.GenerativeModel") as mock_model:
        mock_instance = MagicMock()
        mock_model.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_inference_service(mock_rules_response, mock_category_response):
    """Mock InferenceService for testing without LLM calls."""
    with patch("app.services.transaction_service.InferenceService") as mock_service:
        instance = MagicMock()
        instance.build_rules.return_value = mock_rules_response
        instance.infer_categories.return_value = (mock_category_response, ["raw_text"])
        instance.apply_rules.side_effect = lambda txns, rules: txns
        mock_service.return_value = instance
        yield instance


@pytest.fixture
def test_client(mock_inference_service, temp_data_dir) -> Generator[TestClient, None, None]:
    """Create a test client with mocked dependencies."""
    with patch("app.repositories.local_repo.LocalRepository") as mock_repo:
        mock_repo_instance = MagicMock()
        mock_repo_instance.list_entities.return_value = []
        mock_repo_instance.load_job.return_value = None
        mock_repo.return_value = mock_repo_instance

        from app.main import app

        with TestClient(app) as client:
            yield client
