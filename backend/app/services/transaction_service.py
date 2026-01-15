from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException, UploadFile

from app.core.exceptions import FileProcessingError, JobNotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.utils import transaction_signature
from app.repositories.firestore_repo import FirestoreRepository
from app.services.inference_service import InferenceService

logger = get_logger("catefolio.services.transaction")


class TransactionService:
    MAX_FILES_PER_UPLOAD = 10
    MAX_ROWS_PER_FILE = 10000

    def __init__(self, repository: FirestoreRepository) -> None:
        self.repository = repository
        self.inference = InferenceService()
        self.categories = self._load_categories()
        logger.info(f"TransactionService initialized with {len(self.categories)} categories")

    def check_duplicates(
        self,
        files: list[UploadFile],
        user_id: str,
    ) -> dict[str, Any] | None:
        """Check if uploaded files would create duplicate transactions.

        Args:
            files: List of uploaded files to check
            user_id: Owner's user ID

        Returns:
            Existing job info if duplicate found, None otherwise
        """
        transactions: list[dict[str, Any]] = []
        for file in files:
            try:
                df = self._read_dataframe(file)
                file_transactions = self._prepare_transactions(df)
                transactions.extend(file_transactions)
                file.file.seek(0)  # Reset for later use
            except Exception:
                continue

        if not transactions:
            return None

        content_signature = self._compute_content_signature(transactions)
        existing = self.repository.find_job_by_signature(content_signature, user_id)

        if existing:
            return {
                "job_id": existing["id"],
                "created_at": existing.get("created_at"),
                "transaction_count": existing.get("transaction_count", 0),
                "categorized": existing.get("categorized", False),
                "content_signature": content_signature,
            }
        return None

    def process_upload(
        self,
        files: list[UploadFile],
        categorize: bool = False,
        user_id: str | None = None,
        team_id: str | None = None,
        overwrite_job_id: str | None = None,
    ) -> dict[str, Any]:
        """Process uploaded transaction files with deduplication.

        Args:
            files: List of uploaded files to process
            categorize: Whether to run AI categorization (default: False)
            user_id: Owner's user ID for multi-tenant isolation
            team_id: User's team ID for team-based category lookup
            overwrite_job_id: If provided, delete this job before creating new one
        """
        if len(files) > self.MAX_FILES_PER_UPLOAD:
            logger.warning(f"Upload rejected: {len(files)} files exceeds limit of {self.MAX_FILES_PER_UPLOAD}")
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {self.MAX_FILES_PER_UPLOAD} files per upload.",
            )

        # Delete existing job if overwriting
        if overwrite_job_id and user_id:
            logger.info(f"Overwriting existing job: {overwrite_job_id}")
            self.repository.delete_job(overwrite_job_id, user_id=user_id)

        # Get existing transaction signatures for deduplication
        existing_signatures: set[str] = set()
        if user_id:
            existing_signatures = self.repository.get_all_transaction_signatures(user_id)
            logger.info(f"Loaded {len(existing_signatures)} existing transaction signatures for deduplication")

        logger.info(f"Processing upload: {len(files)} files, categorize={categorize}")
        all_raw_transactions: list[dict[str, Any]] = []  # For computing content_signature (before dedup)
        transactions: list[dict[str, Any]] = []  # Deduplicated transactions to save
        duplicates_skipped = 0

        for file in files:
            try:
                df = self._read_dataframe(file)
                file_transactions = self._prepare_transactions(df)
                all_raw_transactions.extend(file_transactions)  # Keep raw for signature

                # Deduplicate against existing transactions
                new_transactions = []
                for txn in file_transactions:
                    sig = transaction_signature(txn)
                    if sig not in existing_signatures:
                        new_transactions.append(txn)
                        existing_signatures.add(sig)  # Add to set to catch duplicates within this upload
                    else:
                        duplicates_skipped += 1

                transactions.extend(new_transactions)
                file.file.seek(0)
                self.repository.save_upload(file.filename, file.file.read(), user_id=user_id)
                logger.info(f"Processed file '{file.filename}': {len(new_transactions)} new transactions ({len(file_transactions) - len(new_transactions)} duplicates skipped)")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing file '{file.filename}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process file '{file.filename}': {str(e)}",
                )

        if duplicates_skipped > 0:
            logger.info(f"Total duplicates skipped: {duplicates_skipped}")

        # Compute content signature from RAW transactions (before dedup) so it matches check_duplicates
        content_signature = self._compute_content_signature(all_raw_transactions)

        job_id = str(uuid4())
        logger.info(f"Created job {job_id} with {len(transactions)} total transactions")

        # Load categories from Firestore (team-specific, user-specific, or default)
        # Priority: team_id > user_id > default
        categories = self._get_categories_for_user(user_id, team_id)

        # Step 1: Always apply keyword-based categorization (free, no LLM cost)
        keyword_matched: set[int] = set()
        if categories:
            keyword_matched = self._apply_keyword_categories(transactions, categories)
            if keyword_matched:
                logger.info(f"Keyword matching: {len(keyword_matched)}/{len(transactions)} transactions matched")

        # Step 2: Only send unmatched transactions to LLM if AI categorization is enabled
        if categorize and categories:
            unmatched_transactions = [
                (idx, tx) for idx, tx in enumerate(transactions)
                if idx not in keyword_matched
            ]

            if unmatched_transactions:
                logger.info(f"AI categorization enabled for {len(unmatched_transactions)} unmatched transactions")
                # Create a list for LLM with original indices preserved
                unmatched_list = [tx for _, tx in unmatched_transactions]
                idx_mapping = [idx for idx, _ in unmatched_transactions]

                category_results, _ = self.inference.infer_categories(unmatched_list, categories)

                # Remap results back to original indices
                remapped_results = [
                    {"index": idx_mapping[r["index"]], "categories": r["categories"]}
                    for r in category_results
                    if 0 <= r.get("index", -1) < len(idx_mapping)
                ]
                self._apply_category_results(transactions, remapped_results, categories)
                logger.info(f"LLM categorization: {len(category_results)} results for {len(unmatched_list)} transactions")
            else:
                logger.info("All transactions matched by keywords - skipping LLM")
        elif not categorize:
            logger.info("AI categorization disabled - keyword matching only")

        summary = self._build_summary(transactions)
        charts = self._build_charts(transactions)

        payload = {
            "status": "processed",
            "files": [file.filename for file in files],
            "created_at": self._utc_now_iso(),
            "summary": summary,
            "transactions": transactions,
            "charts": charts,
            "categories": [cat["name"] for cat in categories] if categories else [],
            "categorized": categorize and bool(categories),
            "narrative": self._build_narrative(summary),
            "content_signature": content_signature,
            "duplicates_skipped": duplicates_skipped,
        }
        # save_job pops transactions from payload, so keep a reference
        transactions_copy = transactions
        self.repository.save_job(job_id, payload, user_id=user_id)
        # Restore transactions after save (save_job pops it for sub-collection storage)
        payload["transactions"] = transactions_copy
        payload["job_id"] = job_id

        logger.info(
            f"Job {job_id} complete: {len(transactions)} transactions, "
            f"income=${summary['total_income']:,.2f}, expenses=${summary['total_expenses']:,.2f}"
        )
        return payload

    def get_job(self, job_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Get a job by ID.

        Args:
            job_id: Job's unique identifier
            user_id: If provided, verify ownership

        Returns:
            Job data

        Raises:
            HTTPException: If job not found or unauthorized
        """
        logger.debug(f"Retrieving job: {job_id}")
        job = self.repository.load_job(job_id, user_id=user_id)
        if not job:
            logger.warning(f"Job not found or unauthorized: {job_id}")
            raise HTTPException(status_code=404, detail="Job not found.")
        return job

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _compute_content_signature(transactions: list[dict[str, Any]]) -> str:
        """Compute a signature for transaction content to detect duplicates."""
        # Sort transactions to ensure consistent ordering
        sorted_txns = sorted(
            transactions,
            key=lambda t: (t.get("date", ""), t.get("description", ""), t.get("amount", 0))
        )
        # Create signature from all transaction signatures
        signatures = [transaction_signature(t) for t in sorted_txns]
        combined = "|".join(signatures)
        return hashlib.md5(combined.encode()).hexdigest()

    @staticmethod
    def _normalize_columns(columns: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for column in columns:
            key = column.strip().lower()
            if key in {"date", "transaction date", "posted date"}:
                mapping[column] = "date"
            elif key in {"description", "memo", "details", "merchant", "payee"}:
                mapping[column] = "description"
            elif key in {"amount", "amt", "value"}:
                mapping[column] = "amount"
            elif key in {"category", "categories"}:
                mapping[column] = "category"
            elif key in {"entity", "business/personal", "business or personal", "tag"}:
                mapping[column] = "entity"
            elif key in {"거래일시", "거래일자"}:
                mapping[column] = "date"
            elif key in {"보낸분/받는분", "거래처"}:
                mapping[column] = "description"
            elif key in {"출금액(원)", "출금액"}:
                mapping[column] = "debit"
            elif key in {"입금액(원)", "입금액"}:
                mapping[column] = "credit"
            elif key in {"구분"}:
                mapping[column] = "entity"
            elif key in {"적요"}:
                mapping[column] = "note"
            elif key in {"내 통장 표시"}:
                mapping[column] = "display"
            elif key in {"메모"}:
                mapping[column] = "memo"
        return mapping

    @staticmethod
    def _extract_header_frame(df: pd.DataFrame) -> pd.DataFrame:
        header_index = None
        for idx, row in df.iterrows():
            row_text = " ".join(str(value) for value in row.tolist())
            if "거래일시" in row_text and "출금액" in row_text and "입금액" in row_text:
                header_index = idx
                break
        if header_index is None:
            return df
        data = df.iloc[header_index + 1 :].copy()
        data.columns = df.iloc[header_index].tolist()
        return data.reset_index(drop=True)

    @staticmethod
    def _needs_header_extract(columns: list[str]) -> bool:
        lowered = [str(col).lower() for col in columns]
        if any("unnamed" in col for col in lowered):
            return True
        if any("계좌번호" in col for col in columns):
            return True
        return False

    def _read_dataframe(self, file: UploadFile) -> pd.DataFrame:
        raw = file.file.read()
        if not raw:
            logger.warning(f"Empty file uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail=f"{file.filename} is empty.")

        stream = BytesIO(raw)
        filename = file.filename.lower()

        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(stream)
            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(stream)
                if self._needs_header_extract([str(col) for col in df.columns]):
                    stream.seek(0)
                    df = pd.read_excel(stream, header=None)
                    df = self._extract_header_frame(df)
            else:
                logger.warning(f"Unsupported file type: {file.filename}")
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to read file '{file.filename}': {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read file '{file.filename}': {str(e)}",
            )

        logger.debug(f"Read dataframe from '{file.filename}': {df.shape[0]} rows, {df.shape[1]} columns")
        return df

    def _prepare_transactions(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        if df.shape[0] > self.MAX_ROWS_PER_FILE:
            logger.warning(f"File exceeds {self.MAX_ROWS_PER_FILE} rows: {df.shape[0]}")
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds {self.MAX_ROWS_PER_FILE:,} rows.",
            )

        mapping = self._normalize_columns([str(col) for col in df.columns])
        renamed = df.rename(columns=mapping)

        if "amount" not in renamed.columns and not {"debit", "credit"}.issubset(renamed.columns):
            raise HTTPException(
                status_code=400,
                detail="Missing required columns: amount or debit/credit.",
            )

        transactions: list[dict[str, Any]] = []
        skipped_count = 0

        for _, row in renamed.iterrows():
            amount = None
            if "amount" in renamed.columns:
                try:
                    amount = float(row["amount"])
                except (TypeError, ValueError):
                    amount = None
            elif "debit" in renamed.columns and "credit" in renamed.columns:
                debit = row.get("debit", 0) or 0
                credit = row.get("credit", 0) or 0
                try:
                    debit = float(debit)
                    credit = float(credit)
                    amount = credit if credit > 0 else -debit
                except (TypeError, ValueError):
                    amount = None

            if amount is None:
                skipped_count += 1
                continue

            date_value = row.get("date")
            if date_value is None:
                skipped_count += 1
                continue

            date_parsed = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(date_parsed):
                skipped_count += 1
                continue
            date_str = date_parsed.date().isoformat()

            description = str(row.get("description", "")).strip()
            # Category should be Uncategorized by default - AI will predict actual category
            category = str(row.get("category", "")).strip() or "Uncategorized"
            # Track transaction type (income/expense) separately from category
            transaction_type = "income" if amount > 0 else "expense"
            entity_value = row.get("entity", "")
            entity = ""
            if pd.isna(entity_value):
                entity = ""
            else:
                entity = str(entity_value).strip()
            entity = entity or "Unassigned"
            raw = {
                "note": "" if pd.isna(row.get("note", "")) else str(row.get("note", "")).strip(),
                "display": "" if pd.isna(row.get("display", "")) else str(row.get("display", "")).strip(),
                "memo": "" if pd.isna(row.get("memo", "")) else str(row.get("memo", "")).strip(),
            }

            transactions.append(
                {
                    "date": date_str,
                    "description": description,
                    "amount": amount,
                    "category": category,
                    "transaction_type": transaction_type,
                    "entity": entity,
                    "raw": raw,
                }
            )

        if skipped_count > 0:
            logger.debug(f"Skipped {skipped_count} rows with invalid data")

        return transactions

    @staticmethod
    def _build_summary(transactions: list[dict[str, Any]]) -> dict[str, Any]:
        income = sum(t["amount"] for t in transactions if t["amount"] > 0)
        expenses = sum(abs(t["amount"]) for t in transactions if t["amount"] < 0)
        entity_counts: dict[str, int] = {}
        for transaction in transactions:
            entity = str(transaction.get("entity") or "Unassigned").strip() or "Unassigned"
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
        return {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_savings": round(income - expenses, 2),
            "entity_counts": entity_counts,
        }

    @staticmethod
    def _build_charts(transactions: list[dict[str, Any]]) -> dict[str, Any]:
        df = pd.DataFrame(transactions)
        if df.empty:
            return {
                "daily_trend": {"labels": [], "income": [], "expenses": []},
                "expense_breakdown": {"labels": [], "values": []},
                "business_vs_personal": {"labels": ["Business", "Personal"], "values": [0, 0]},
            }

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        grouped = df.groupby(df["date"].dt.strftime("%m/%d"))
        income = grouped.apply(lambda x: x.loc[x["amount"] > 0, "amount"].sum())
        expenses = grouped.apply(lambda x: abs(x.loc[x["amount"] < 0, "amount"].sum()))

        expense_df = df[df["amount"] < 0]
        breakdown = expense_df.groupby("category")["amount"].sum().abs().sort_values(ascending=False).head(6)

        entity_counts = df["entity"].fillna("Unassigned").astype(str).str.strip()
        entity_counts = entity_counts.replace({"nan": "Unassigned", "NaN": "Unassigned", "": "Unassigned"})
        entity_summary = entity_counts.value_counts()

        return {
            "daily_trend": {
                "labels": income.index.tolist(),
                "income": income.round(2).tolist(),
                "expenses": expenses.round(2).tolist(),
            },
            "expense_breakdown": {
                "labels": breakdown.index.tolist(),
                "values": breakdown.round(2).tolist(),
            },
            "entity_breakdown": {
                "labels": entity_summary.index.tolist(),
                "values": entity_summary.values.tolist(),
            },
        }

    @staticmethod
    def _build_narrative(summary: dict[str, Any]) -> str:
        return (
            "Your uploaded files have been consolidated. "
            f"Total income is ${summary['total_income']:,}, "
            f"total expenses are ${summary['total_expenses']:,}, "
            f"and net savings are ${summary['net_savings']:,}. "
            "Review the category breakdown to spot the largest cost drivers."
        )

    def _apply_keyword_categories(
        self,
        transactions: list[dict[str, Any]],
        categories: list[dict[str, Any]],
    ) -> set[int]:
        """Apply categories based on keyword matching.

        First matching category becomes the primary category.
        Additional matching categories are stored in the 'entity' field
        as a comma-separated list for reference.

        Args:
            transactions: List of transaction dicts to categorize
            categories: List of category dicts with 'name' and 'keywords' fields

        Returns:
            Set of transaction indices that were matched by keywords
        """
        matched_indices: set[int] = set()

        for idx, tx in enumerate(transactions):
            # Build searchable text from transaction
            search_text = " ".join([
                tx.get("description", ""),
                tx.get("raw", {}).get("note", ""),
                tx.get("raw", {}).get("display", ""),
                tx.get("raw", {}).get("memo", ""),
            ]).lower()

            # Collect ALL matching categories
            matched_categories: list[str] = []
            for category in categories:
                keywords = category.get("keywords", [])
                for keyword in keywords:
                    if keyword.lower() in search_text:
                        matched_categories.append(category["name"])
                        break  # Found match for this category, move to next

            if matched_categories:
                # First match becomes primary category
                tx["category"] = matched_categories[0]
                matched_indices.add(idx)

                # Additional matches stored in entity field
                if len(matched_categories) > 1:
                    tx["entity"] = ", ".join(matched_categories[1:])

        return matched_indices

    def _apply_category_results(
        self,
        transactions: list[dict[str, Any]],
        results: list[dict[str, Any]],
        categories: list[dict[str, Any]],
    ) -> None:
        """Apply AI-predicted category to transactions.

        Sets only the primary category (first prediction from AI).
        Entity field is reserved for GraphRAG feature.
        Validates that returned categories are in the allowed list.

        Args:
            transactions: List of transaction dicts to update
            results: AI categorization results with 'index' and 'categories'
            categories: Valid category list to validate against
        """
        valid_category_names = {cat["name"] for cat in categories}

        for result in results:
            index = result.get("index", -1)
            predicted_categories = result.get("categories", [])
            if isinstance(predicted_categories, str):
                predicted_categories = [predicted_categories]
            if 0 <= index < len(transactions) and predicted_categories:
                # Validate category against allowed list
                category = predicted_categories[0]
                if category in valid_category_names:
                    transactions[index]["category"] = category
                else:
                    logger.warning(f"LLM returned invalid category '{category}', keeping default")

    @staticmethod
    def _load_categories() -> list[dict[str, Any]]:
        """Load categories with keywords from JSON file.

        Returns:
            List of category dicts with 'name' and 'keywords' fields
        """
        base_dir = Path(__file__).resolve().parents[3]
        default_path = base_dir / "test_expense_categories" / "expense_category.json"
        path = Path(os.getenv("CATEGORY_PATH", str(default_path)))

        if not path.exists():
            logger.debug(f"Category file not found: {path}")
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse category file: {e}")
            return []

        categories: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, dict):
                    name = str(value.get("name", "")).strip()
                    keywords = value.get("keywords", [])
                    if not isinstance(keywords, list):
                        keywords = []
                    if name:
                        categories.append({"name": name, "keywords": keywords})
                else:
                    name = str(value).strip()
                    if name:
                        categories.append({"name": name, "keywords": []})
        elif isinstance(data, list):
            for value in data:
                if isinstance(value, dict):
                    name = str(value.get("name", "")).strip()
                    keywords = value.get("keywords", [])
                    if not isinstance(keywords, list):
                        keywords = []
                    if name:
                        categories.append({"name": name, "keywords": keywords})
                else:
                    name = str(value).strip()
                    if name:
                        categories.append({"name": name, "keywords": []})

        logger.debug(f"Loaded {len(categories)} categories from {path}")
        return categories

    def _get_categories_for_user(
        self,
        user_id: str | None,
        team_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Load categories from Firestore for the user/team.

        Firestore stores categories in dict format with category IDs as keys:
            {"CAT_001": {"name": "Category Name", "keywords": ["kw1", "kw2"]}, ...}

        This method converts to list format expected by categorization methods:
            [{"name": "Category Name", "keywords": ["kw1", "kw2"]}, ...]

        Lookup priority: team_id > user_id > default
        Falls back to static JSON categories if Firestore has no data.

        Args:
            user_id: User's unique identifier (optional)
            team_id: Team's unique identifier (optional, takes priority)

        Returns:
            List of category dicts with 'name' and 'keywords' fields
        """
        # Priority: team_id > user_id > default
        lookup_id = team_id or user_id
        data = self.repository.get_categories(user_id=lookup_id)
        logger.debug(f"Category lookup: team_id={team_id}, user_id={user_id}, lookup_id={lookup_id}")

        if not data:
            logger.debug(f"No categories in Firestore for user {user_id}, using static JSON")
            return self.categories  # Fall back to static JSON

        # Convert dict format to list format
        categories: list[dict[str, Any]] = []
        for key, value in data.items():
            if isinstance(value, dict):
                name = str(value.get("name", "")).strip()
                keywords = value.get("keywords", [])
                if not isinstance(keywords, list):
                    keywords = []
                if name:
                    categories.append({"name": name, "keywords": keywords})

        if categories:
            keyword_count = sum(len(cat.get("keywords", [])) for cat in categories)
            logger.info(f"Loaded {len(categories)} categories from Firestore with {keyword_count} total keywords")
        else:
            logger.debug(f"Firestore categories empty for user {user_id}, using static JSON")
            return self.categories

        return categories
