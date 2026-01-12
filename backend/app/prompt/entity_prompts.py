from __future__ import annotations

import json
from typing import Any


def build_rules_prompt(sample: list[dict[str, Any]]) -> str:
    return (
        "You are extracting lightweight mapping rules for transactions.\n"
        "Return JSON only as an array of rules with keys: pattern, match_field, entity, category.\n"
        "Rules must be grounded in provided fields (description, note, display, memo).\n"
        "If uncertain, return an empty array.\n\n"
        f"Transactions sample:\n{json.dumps(sample, ensure_ascii=False)}\n"
    )


def build_entity_relationship_prompt(
    transaction: dict[str, Any],
    root_context: str | None = None,
) -> str:
    context = root_context or "Organization context not provided."
    payload = json.dumps(transaction, ensure_ascii=False)
    return (
        "You are extracting entity nodes and relationships for GraphRAG.\n"
        "Return JSON only with keys: entities, relationships.\n"
        "Each entity: {id, name, type, evidence}.\n"
        "Each relationship: {source, target, label, evidence}.\n"
        "Use only fields in the transaction payload as evidence.\n"
        f"Root organization context: {context}\n\n"
        f"Transaction:\n{payload}\n"
    )


def build_category_prompt(
    transactions: list[dict[str, Any]],
    categories: list[str],
) -> str:
    payload = json.dumps(transactions, ensure_ascii=False)
    category_list = json.dumps(categories, ensure_ascii=False)
    return (
        "You are assigning up to three categories to each transaction.\n"
        "Choose from the provided categories list only.\n"
        "Return JSON only as an array of objects: {index, categories}.\n"
        "The categories field must be a list with 1 to 3 items.\n"
        "If no category fits, return categories as [\"Uncategorized\"].\n\n"
        f"Categories:\n{category_list}\n\n"
        f"Transactions:\n{payload}\n"
    )
