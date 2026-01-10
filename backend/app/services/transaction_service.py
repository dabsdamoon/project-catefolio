from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException, UploadFile

from app.repositories.local_repo import LocalRepository
from app.services.inference_service import InferenceService


class TransactionService:
    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository
        self.inference = InferenceService()

    def process_upload(self, files: list[UploadFile]) -> dict[str, Any]:
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 files per upload.")

        transactions: list[dict[str, Any]] = []
        for file in files:
            df = self._read_dataframe(file)
            transactions.extend(self._prepare_transactions(df))
            file.file.seek(0)
            self.repository.save_upload(file.filename, file.file.read())

        job_id = str(uuid4())
        user_entities = self.repository.list_entities()
        user_rules = self._rules_from_entities(user_entities)
        rules = self.inference.build_rules(transactions, user_rules=user_rules)
        transactions = self.inference.apply_rules(transactions, rules)
        summary = self._build_summary(transactions)
        charts = self._build_charts(transactions)
        payload = {
            "status": "processed",
            "files": [file.filename for file in files],
            "created_at": self._utc_now_iso(),
            "summary": summary,
            "transactions": transactions,
            "charts": charts,
            "rules": rules,
            "narrative": self._build_narrative(summary),
        }
        self.repository.save_job(job_id, payload)
        payload["job_id"] = job_id
        return payload

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.repository.load_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
            raise HTTPException(status_code=400, detail=f"{file.filename} is empty.")
        stream = BytesIO(raw)
        filename = file.filename.lower()
        if filename.endswith(".csv"):
            df = pd.read_csv(stream)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(stream)
            if self._needs_header_extract([str(col) for col in df.columns]):
                stream.seek(0)
                df = pd.read_excel(stream, header=None)
                df = self._extract_header_frame(df)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")
        return df

    def _prepare_transactions(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        if df.shape[0] > 10000:
            raise HTTPException(status_code=400, detail="File exceeds 10,000 rows.")

        mapping = self._normalize_columns([str(col) for col in df.columns])
        renamed = df.rename(columns=mapping)

        if "amount" not in renamed.columns and not {"debit", "credit"}.issubset(renamed.columns):
            raise HTTPException(
                status_code=400,
                detail="Missing required columns: amount or debit/credit.",
            )

        transactions: list[dict[str, Any]] = []
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
                continue

            date_value = row["date"]
            date_parsed = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(date_parsed):
                continue
            date_str = date_parsed.date().isoformat()

            description = str(row.get("description", "")).strip()
            category = str(row.get("category", "")).strip() or ("Income" if amount > 0 else "Expense")
            entity_value = row.get("entity", "")
            entity = ""
            if pd.isna(entity_value):
                entity = ""
            else:
                entity = str(entity_value).strip()
            entity = entity or "Unassigned"
            raw = {
                "note": "" if pd.isna(row.get("note", "")) else str(row.get("note", "")).strip(),
                "display": ""
                if pd.isna(row.get("display", ""))
                else str(row.get("display", "")).strip(),
                "memo": "" if pd.isna(row.get("memo", "")) else str(row.get("memo", "")).strip(),
            }

            transactions.append(
                {
                    "date": date_str,
                    "description": description,
                    "amount": amount,
                    "category": category,
                    "entity": entity,
                    "raw": raw,
                }
            )
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

    @staticmethod
    def _rules_from_entities(entities: list[dict[str, str]]) -> list[dict[str, str]]:
        rules: list[dict[str, str]] = []
        for entity in entities:
            name = entity.get("name", "").strip()
            aliases = entity.get("aliases", [])
            for term in [name, *aliases]:
                term = str(term).strip()
                if not term:
                    continue
                rules.append(
                    {
                        "pattern": term,
                        "match_field": "description",
                        "entity": name,
                        "category": "",
                    }
                )
        return rules
