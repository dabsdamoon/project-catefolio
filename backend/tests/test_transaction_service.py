"""Unit tests for TransactionService."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from app.services.transaction_service import TransactionService


class TestNormalizeColumns:
    """Tests for column normalization."""

    def test_english_date_columns(self):
        columns = ["Date", "Transaction Date", "Posted Date"]
        mapping = TransactionService._normalize_columns(columns)
        assert mapping["Date"] == "date"
        assert mapping["Transaction Date"] == "date"
        assert mapping["Posted Date"] == "date"

    def test_english_description_columns(self):
        columns = ["Description", "Memo", "Details", "Merchant", "Payee"]
        mapping = TransactionService._normalize_columns(columns)
        assert all(mapping[col] == "description" for col in columns)

    def test_english_amount_columns(self):
        columns = ["Amount", "AMT", "Value"]
        mapping = TransactionService._normalize_columns(columns)
        assert all(mapping[col] == "amount" for col in columns)

    def test_korean_columns(self):
        columns = ["거래일시", "보낸분/받는분", "출금액(원)", "입금액(원)", "적요", "메모"]
        mapping = TransactionService._normalize_columns(columns)
        assert mapping["거래일시"] == "date"
        assert mapping["보낸분/받는분"] == "description"
        assert mapping["출금액(원)"] == "debit"
        assert mapping["입금액(원)"] == "credit"
        assert mapping["적요"] == "note"
        assert mapping["메모"] == "memo"

    def test_case_insensitive(self):
        columns = ["DATE", "description", "AMOUNT"]
        mapping = TransactionService._normalize_columns(columns)
        assert mapping["DATE"] == "date"
        assert mapping["description"] == "description"
        assert mapping["AMOUNT"] == "amount"

    def test_unknown_columns_not_mapped(self):
        columns = ["random_column", "unknown"]
        mapping = TransactionService._normalize_columns(columns)
        assert len(mapping) == 0


class TestBuildSummary:
    """Tests for summary building."""

    def test_basic_summary(self, sample_transactions):
        summary = TransactionService._build_summary(sample_transactions)
        assert summary["total_income"] == 5000.00
        assert summary["total_expenses"] == 255.49  # 99.99 + 5.50 + 150.00
        assert summary["net_savings"] == 4744.51

    def test_empty_transactions(self):
        summary = TransactionService._build_summary([])
        assert summary["total_income"] == 0
        assert summary["total_expenses"] == 0
        assert summary["net_savings"] == 0
        assert summary["entity_counts"] == {}

    def test_entity_counts(self, sample_transactions):
        summary = TransactionService._build_summary(sample_transactions)
        assert "Amazon" in summary["entity_counts"]
        assert "Employer" in summary["entity_counts"]
        assert summary["entity_counts"]["Amazon"] == 1

    def test_unassigned_entity(self):
        transactions = [
            {"amount": 100, "entity": None},
            {"amount": -50, "entity": ""},
        ]
        summary = TransactionService._build_summary(transactions)
        assert summary["entity_counts"]["Unassigned"] == 2


class TestBuildCharts:
    """Tests for chart data building."""

    def test_empty_transactions(self):
        charts = TransactionService._build_charts([])
        assert charts["daily_trend"]["labels"] == []
        assert charts["expense_breakdown"]["labels"] == []

    def test_daily_trend(self, sample_transactions):
        charts = TransactionService._build_charts(sample_transactions)
        assert len(charts["daily_trend"]["labels"]) > 0
        assert len(charts["daily_trend"]["income"]) > 0
        assert len(charts["daily_trend"]["expenses"]) > 0

    def test_expense_breakdown(self, sample_transactions):
        charts = TransactionService._build_charts(sample_transactions)
        assert "labels" in charts["expense_breakdown"]
        assert "values" in charts["expense_breakdown"]

    def test_entity_breakdown(self, sample_transactions):
        charts = TransactionService._build_charts(sample_transactions)
        assert "labels" in charts["entity_breakdown"]
        assert "values" in charts["entity_breakdown"]


class TestBuildNarrative:
    """Tests for narrative generation."""

    def test_narrative_format(self):
        summary = {
            "total_income": 5000.00,
            "total_expenses": 1000.00,
            "net_savings": 4000.00,
        }
        narrative = TransactionService._build_narrative(summary)
        assert "5,000" in narrative
        assert "1,000" in narrative
        assert "4,000" in narrative


class TestApplyCategoryResults:
    """Tests for applying category results."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock service with categories for testing."""
        mock_repo = MagicMock()
        mock_categories = [
            {"name": "Shopping", "keywords": []},
            {"name": "Food", "keywords": []},
            {"name": "Expense", "keywords": []},
        ]
        with patch("app.services.transaction_service.InferenceService"), \
             patch.object(TransactionService, "_load_categories", return_value=mock_categories):
            service = TransactionService(mock_repo)
        return service

    def test_apply_categories(self, mock_service):
        transactions = [
            {"category": "Expense", "entity": "Unknown"},
            {"category": "Expense", "entity": "Unknown"},
        ]
        results = [
            {"index": 0, "categories": ["Shopping", "E-commerce"]},
            {"index": 1, "categories": ["Food"]},
        ]
        mock_service._apply_category_results(transactions, results, mock_service.categories)
        # Only the first category is applied (no categories array stored)
        assert transactions[0]["category"] == "Shopping"
        assert transactions[1]["category"] == "Food"

    def test_invalid_index_ignored(self, mock_service):
        transactions = [{"category": "Expense"}]
        results = [{"index": 99, "categories": ["Shopping"]}]
        mock_service._apply_category_results(transactions, results, mock_service.categories)
        assert transactions[0]["category"] == "Expense"  # Unchanged

    def test_empty_categories_ignored(self, mock_service):
        transactions = [{"category": "Expense"}]
        results = [{"index": 0, "categories": []}]
        mock_service._apply_category_results(transactions, results, mock_service.categories)
        assert transactions[0]["category"] == "Expense"  # Unchanged


class TestPrepareTransactions:
    """Tests for transaction preparation from dataframes."""

    @patch("app.services.transaction_service.InferenceService")
    def test_prepare_with_amount_column(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15", "2024-01-16"],
                "description": ["Purchase", "Deposit"],
                "amount": [-100.00, 500.00],
            }
        )
        transactions = service._prepare_transactions(df)
        assert len(transactions) == 2
        assert transactions[0]["amount"] == -100.00
        assert transactions[1]["amount"] == 500.00

    @patch("app.services.transaction_service.InferenceService")
    def test_prepare_with_debit_credit_columns(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15", "2024-01-16"],
                "description": ["Withdrawal", "Deposit"],
                "debit": [100.00, 0],
                "credit": [0, 500.00],
            }
        )
        transactions = service._prepare_transactions(df)
        assert len(transactions) == 2
        assert transactions[0]["amount"] == -100.00
        assert transactions[1]["amount"] == 500.00

    @patch("app.services.transaction_service.InferenceService")
    def test_missing_required_columns_raises(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15"],
                "description": ["Test"],
            }
        )
        with pytest.raises(HTTPException) as exc_info:
            service._prepare_transactions(df)
        assert exc_info.value.status_code == 400
        assert "amount" in exc_info.value.detail.lower()

    @patch("app.services.transaction_service.InferenceService")
    def test_exceeds_row_limit_raises(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15"] * 10001,
                "description": ["Test"] * 10001,
                "amount": [100] * 10001,
            }
        )
        with pytest.raises(HTTPException) as exc_info:
            service._prepare_transactions(df)
        assert exc_info.value.status_code == 400
        assert "10,000" in exc_info.value.detail

    @patch("app.services.transaction_service.InferenceService")
    def test_invalid_amount_skipped(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15", "2024-01-16"],
                "description": ["Valid", "Invalid"],
                "amount": [100.00, "not_a_number"],
            }
        )
        transactions = service._prepare_transactions(df)
        assert len(transactions) == 1
        assert transactions[0]["description"] == "Valid"

    @patch("app.services.transaction_service.InferenceService")
    def test_invalid_date_skipped(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.list_entities.return_value = []

        service = TransactionService(mock_repo)
        df = pd.DataFrame(
            {
                "date": ["2024-01-15", "invalid_date"],
                "description": ["Valid", "Invalid"],
                "amount": [100.00, 200.00],
            }
        )
        transactions = service._prepare_transactions(df)
        assert len(transactions) == 1


class TestGetJob:
    """Tests for job retrieval."""

    @patch("app.services.transaction_service.InferenceService")
    def test_job_not_found_raises(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = None

        service = TransactionService(mock_repo)
        with pytest.raises(HTTPException) as exc_info:
            service.get_job("nonexistent-id")
        assert exc_info.value.status_code == 404

    @patch("app.services.transaction_service.InferenceService")
    def test_job_found(self, mock_inference):
        mock_inference.return_value = MagicMock()
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = {"status": "processed", "transactions": []}

        service = TransactionService(mock_repo)
        job = service.get_job("valid-id")
        assert job["status"] == "processed"


class TestKeywordCategorization:
    """Tests for keyword-based categorization."""

    @pytest.fixture
    def service_with_keywords(self):
        """Create a service with categories that have keywords."""
        mock_repo = MagicMock()
        mock_categories = [
            {"name": "Insurance", "keywords": ["BUPA", "Cigna", "Tricare"]},
            {"name": "Medical", "keywords": ["Hospital", "Clinic", "Pharmacy"]},
            {"name": "Utilities", "keywords": ["Electric", "Water", "Gas"]},
            {"name": "Uncategorized", "keywords": []},
        ]
        with patch("app.services.transaction_service.InferenceService"), \
             patch.object(TransactionService, "_load_categories", return_value=mock_categories):
            service = TransactionService(mock_repo)
        return service

    def test_keyword_match_in_description(self, service_with_keywords):
        """Keywords in description are matched."""
        transactions = [
            {"description": "BUPA Premium Payment", "category": "Uncategorized", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert 0 in matched
        assert transactions[0]["category"] == "Insurance"

    def test_keyword_match_case_insensitive(self, service_with_keywords):
        """Keyword matching is case-insensitive."""
        transactions = [
            {"description": "bupa premium", "category": "Uncategorized", "raw": {}},
            {"description": "CIGNA Health", "category": "Uncategorized", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert len(matched) == 2
        assert transactions[0]["category"] == "Insurance"
        assert transactions[1]["category"] == "Insurance"

    def test_keyword_match_in_raw_fields(self, service_with_keywords):
        """Keywords in raw.note, raw.display, raw.memo are also matched."""
        transactions = [
            {"description": "Payment", "category": "Uncategorized", "raw": {"note": "BUPA insurance"}},
            {"description": "Transfer", "category": "Uncategorized", "raw": {"display": "Hospital visit"}},
            {"description": "Expense", "category": "Uncategorized", "raw": {"memo": "Electric bill"}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert len(matched) == 3
        assert transactions[0]["category"] == "Insurance"
        assert transactions[1]["category"] == "Medical"
        assert transactions[2]["category"] == "Utilities"

    def test_no_keyword_match_returns_empty(self, service_with_keywords):
        """Transactions without keyword matches are not in the returned set."""
        transactions = [
            {"description": "Random Purchase", "category": "Uncategorized", "raw": {}},
            {"description": "Coffee Shop", "category": "Uncategorized", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert len(matched) == 0
        assert transactions[0]["category"] == "Uncategorized"
        assert transactions[1]["category"] == "Uncategorized"

    def test_multiple_category_matches_stores_extras_in_entity(self, service_with_keywords):
        """When multiple categories match, extras are stored in entity field."""
        # Add a category that will also match
        categories = service_with_keywords.categories + [
            {"name": "Healthcare", "keywords": ["Hospital", "BUPA"]}
        ]
        transactions = [
            {"description": "BUPA Hospital Payment", "category": "Uncategorized", "entity": "", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, categories)
        assert 0 in matched
        # First match (Insurance) becomes category, second (Medical) goes to entity
        assert transactions[0]["category"] == "Insurance"
        # Medical and Healthcare also matched
        assert "Medical" in transactions[0]["entity"] or "Healthcare" in transactions[0]["entity"]

    def test_first_category_wins(self, service_with_keywords):
        """First matching category (in list order) becomes the primary category."""
        transactions = [
            {"description": "BUPA Cigna Tricare", "category": "Uncategorized", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert transactions[0]["category"] == "Insurance"

    def test_empty_keywords_list_no_match(self, service_with_keywords):
        """Categories with empty keywords list don't match."""
        transactions = [
            {"description": "Uncategorized transaction", "category": "Uncategorized", "raw": {}},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert len(matched) == 0

    def test_missing_raw_field_handled(self, service_with_keywords):
        """Transactions without raw field are handled gracefully."""
        transactions = [
            {"description": "BUPA Payment", "category": "Uncategorized"},
        ]
        matched = service_with_keywords._apply_keyword_categories(transactions, service_with_keywords.categories)
        assert 0 in matched
        assert transactions[0]["category"] == "Insurance"
