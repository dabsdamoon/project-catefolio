from __future__ import annotations

import json
from typing import Any


ENTITY_RELATIONSHIP_PROMPT = """
You are extracting entity nodes and relationships for GraphRAG.
Return JSON only with keys: entities, relationships.
Each entity: {{id, name, type, evidence}}.
Each relationship: {{source, target, label, evidence}}.
Use only fields in the transaction payload as evidence.
Root organization context: {context}
Transaction:
{transaction}
"""

CATEGORY_PROMPT = """
You are assigning up to three categories to each transaction.
Choose from the provided categories list only.
Use the keyword hints to match transactions more accurately.
If a transaction description contains any of the keywords for a category,
that category should be strongly considered.
Return JSON only as an array of objects: {{index, categories}}.
The categories field must be a list with 1 to 3 items.
If no category fits, return categories as ["Uncategorized"].

Categories with keyword hints:
{category_hints}

Valid category names:
{category_list}

Transactions:
{transactions}
"""

def build_entity_relationship_prompt(
    transaction: dict[str, Any],
    root_context: str | None = None,
) -> str:
    context = root_context or "Organization context not provided."
    payload = json.dumps(transaction, ensure_ascii=False)
    return ENTITY_RELATIONSHIP_PROMPT.format(
        context=context,
        transaction=payload,
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
    transactions_payload = json.dumps(transactions, ensure_ascii=False)

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

    return CATEGORY_PROMPT.format(
        category_hints=category_hints,
        category_list=category_list,
        transactions=transactions_payload,
    )
