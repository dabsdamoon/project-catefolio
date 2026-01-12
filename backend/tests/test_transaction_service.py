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


class TestRulesFromEntities:
    """Tests for entity-to-rules conversion."""

    def test_basic_entity_conversion(self):
        entities = [
            {"name": "Amazon", "aliases": ["AMZN", "Amazon.com"]},
            {"name": "Starbucks", "aliases": []},
        ]
        rules = TransactionService._rules_from_entities(entities)
        assert len(rules) == 4  # Amazon + 2 aliases + Starbucks
        assert any(r["pattern"] == "Amazon" for r in rules)
        assert any(r["pattern"] == "AMZN" for r in rules)

    def test_empty_entities(self):
        rules = TransactionService._rules_from_entities([])
        assert rules == []

    def test_empty_name_skipped(self):
        entities = [{"name": "", "aliases": ["test"]}]
        rules = TransactionService._rules_from_entities(entities)
        assert len(rules) == 1  # Only the alias


class TestApplyCategoryResults:
    """Tests for applying category results."""

    def test_apply_categories(self):
        transactions = [
            {"category": "Expense", "entity": "Unknown"},
            {"category": "Expense", "entity": "Unknown"},
        ]
        results = [
            {"index": 0, "categories": ["Shopping", "E-commerce"]},
            {"index": 1, "categories": ["Food"]},
        ]
        TransactionService._apply_category_results(transactions, results)
        assert transactions[0]["category"] == "Shopping"
        assert transactions[0]["categories"] == ["Shopping", "E-commerce"]
        assert transactions[1]["category"] == "Food"

    def test_invalid_index_ignored(self):
        transactions = [{"category": "Expense"}]
        results = [{"index": 99, "categories": ["Shopping"]}]
        TransactionService._apply_category_results(transactions, results)
        assert transactions[0]["category"] == "Expense"  # Unchanged

    def test_empty_categories_ignored(self):
        transactions = [{"category": "Expense"}]
        results = [{"index": 0, "categories": []}]
        TransactionService._apply_category_results(transactions, results)
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
