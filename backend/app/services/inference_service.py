from __future__ import annotations

import os
from typing import Any

from app.adapters.gemini_vertex import GeminiVertexAdapter
from app.core.exceptions import LLMError, LLMParseError
from app.core.logging import get_logger

logger = get_logger("catefolio.services.inference")


class InferenceService:
    def __init__(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "vertex").lower()
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite-001")
        if provider != "vertex":
            raise ValueError("Only Vertex AI is supported. Set LLM_PROVIDER=vertex.")
        self.adapter = GeminiVertexAdapter(model_name)
        logger.info(f"InferenceService initialized with provider={provider}, model={model_name}")

    def build_rules(
        self,
        transactions: list[dict[str, Any]],
        user_rules: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        user_rules = user_rules or []
        logger.info(f"Building rules for {len(transactions)} transactions, {len(user_rules)} user rules")

        try:
            llm_rules = self.adapter.infer_rules(transactions)
        except LLMParseError as e:
            logger.warning(f"Failed to parse LLM rules, using user rules only: {e}")
            llm_rules = []
        except LLMError as e:
            logger.error(f"LLM error during rule inference: {e}")
            raise

        combined = self._deduplicate_rules(user_rules + llm_rules)
        logger.info(f"Generated {len(combined)} total rules ({len(llm_rules)} from LLM)")
        return combined

    def infer_graph(
        self, transaction: dict[str, Any], root_context: str | None = None
    ) -> tuple[dict[str, Any], str]:
        logger.debug(f"Inferring graph for transaction: {transaction.get('description', '')[:50]}")
        try:
            return self.adapter.infer_graph(transaction, root_context=root_context)
        except LLMParseError as e:
            logger.warning(f"Failed to parse entity graph: {e}")
            return {"entities": [], "relationships": []}, e.raw_response
        except LLMError as e:
            logger.error(f"LLM error during graph inference: {e}")
            raise

    def infer_categories(
        self,
        transactions: list[dict[str, Any]],
        categories: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Infer categories for transactions.

        Args:
            transactions: List of transaction dictionaries
            categories: List of category dicts with 'name' and 'keywords' fields
            batch_size: Number of transactions per batch
        """
        logger.info(f"Inferring categories for {len(transactions)} transactions in batches of {batch_size}")
        results: list[dict[str, Any]] = []
        raw_texts: list[str] = []
        failed_batches: list[int] = []

        for batch_num, start in enumerate(range(0, len(transactions), batch_size)):
            batch = transactions[start : start + batch_size]
            batch_payload = [
                {
                    "index": idx + start,
                    "description": tx.get("description", ""),
                    "amount": tx.get("amount", 0),
                    "note": tx.get("raw", {}).get("note", ""),
                    "display": tx.get("raw", {}).get("display", ""),
                    "memo": tx.get("raw", {}).get("memo", ""),
                }
                for idx, tx in enumerate(batch)
            ]

            try:
                parsed, raw_text = self.adapter.infer_categories_batch(batch_payload, categories)
                results.extend(parsed)
                raw_texts.append(raw_text)
                logger.debug(f"Batch {batch_num + 1}: categorized {len(parsed)} transactions")
            except LLMParseError as e:
                logger.warning(f"Batch {batch_num + 1} parse error: {e}")
                failed_batches.append(batch_num + 1)
                raw_texts.append(e.raw_response)
            except LLMError as e:
                logger.error(f"Batch {batch_num + 1} LLM error: {e}")
                failed_batches.append(batch_num + 1)
                raw_texts.append("")

        if failed_batches:
            logger.warning(f"Failed batches: {failed_batches}")

        logger.info(f"Category inference complete: {len(results)} categorized, {len(failed_batches)} failed batches")
        return results, raw_texts

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
        logger.debug(f"Applying {len(rules)} rules to {len(transactions)} transactions")
        matched_count = 0

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
                    matched_count += 1
                    break
            if not matched:
                tx["entity"] = tx.get("entity") or base_entity
            elif not tx.get("entity"):
                tx["entity"] = base_entity

        logger.info(f"Applied rules: {matched_count}/{len(transactions)} transactions matched")
        return transactions
