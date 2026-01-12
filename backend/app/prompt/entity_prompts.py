from __future__ import annotations

import json
from typing import Any


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
    categories: list[dict[str, Any]],
) -> str:
    """Build prompt for categorizing transactions.

    Args:
        transactions: List of transaction dictionaries
        categories: List of category dicts with 'name' and 'keywords' fields
    """
    payload = json.dumps(transactions, ensure_ascii=False)

    # Build category descriptions with keywords
    category_descriptions = []
    category_names = []
    for cat in categories:
        name = cat.get("name", "")
        keywords = cat.get("keywords", [])
        category_names.append(name)
        if keywords:
            keyword_str = ", ".join(keywords)
            category_descriptions.append(f"- {name}: Look for keywords like [{keyword_str}]")
        else:
            category_descriptions.append(f"- {name}")

    category_list = json.dumps(category_names, ensure_ascii=False)
    category_hints = "\n".join(category_descriptions)

    return (
        "You are assigning up to three categories to each transaction.\n"
        "Choose from the provided categories list only.\n"
        "Use the keyword hints to match transactions more accurately.\n"
        "If a transaction description contains any of the keywords for a category, "
        "that category should be strongly considered.\n"
        "Return JSON only as an array of objects: {index, categories}.\n"
        "The categories field must be a list with 1 to 3 items.\n"
        "If no category fits, return categories as [\"Uncategorized\"].\n\n"
        f"Categories with keyword hints:\n{category_hints}\n\n"
        f"Valid category names:\n{category_list}\n\n"
        f"Transactions:\n{payload}\n"
    )
