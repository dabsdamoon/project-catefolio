from __future__ import annotations

from typing import Any

import os

from app.adapters.gemini_vertex import GeminiVertexAdapter


class InferenceService:
    def __init__(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "vertex").lower()
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite-001")
        if provider != "vertex":
            raise ValueError("Only Vertex AI is supported. Set LLM_PROVIDER=vertex.")
        self.adapter = GeminiVertexAdapter(model_name)

    def build_rules(
        self,
        transactions: list[dict[str, Any]],
        user_rules: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        user_rules = user_rules or []
        llm_rules = self.adapter.infer_rules(transactions)
        return self._deduplicate_rules(user_rules + llm_rules)

    def infer_graph(
        self, transaction: dict[str, Any], root_context: str | None = None
    ) -> tuple[dict[str, Any], str]:
        return self.adapter.infer_graph(transaction, root_context=root_context)

    @staticmethod
    def _deduplicate_rules(rules: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str, str, str]] = set()
        deduped: list[dict[str, str]] = []
        for rule in rules:
            key = (
                rule.get("pattern", ""),
                rule.get("match_field", ""),
                rule.get("entity", ""),
                rule.get("category", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(rule)
        return deduped

    @staticmethod
    def apply_rules(
        transactions: list[dict[str, Any]],
        rules: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        for tx in transactions:
            base_entity = "Credit" if tx.get("amount", 0) > 0 else "Debit"
            matched = False
            raw = tx.get("raw", {})
            description = str(tx.get("description", "") or "")
            note = str(raw.get("note", "") or "")
            display = str(raw.get("display", "") or "")
            memo = str(raw.get("memo", "") or "")
            fields = {
                "description": description,
                "note": note,
                "display": display,
                "memo": memo,
            }
            for rule in rules:
                pattern = rule.get("pattern", "")
                match_field = rule.get("match_field", "description")
                haystack = fields.get(match_field, "")
                if pattern and pattern in haystack:
                    if rule.get("category"):
                        tx["category"] = rule["category"]
                    if rule.get("entity"):
                        tx["entity"] = rule["entity"]
                    matched = True
            if not matched:
                tx["entity"] = tx.get("entity") or base_entity
            elif not tx.get("entity"):
                tx["entity"] = base_entity
        return transactions
