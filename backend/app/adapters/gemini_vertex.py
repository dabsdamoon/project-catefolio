from __future__ import annotations

import json
import os
from typing import Any

import vertexai
from dotenv import load_dotenv
from vertexai.generative_models import GenerativeModel

from app.prompt.entity_prompts import build_entity_relationship_prompt, build_rules_prompt


class GeminiVertexAdapter:
    def __init__(self, model_name: str) -> None:
        self.model = GenerativeModel(model_name)

    def infer_rules(self, transactions: list[dict[str, Any]]) -> list[dict[str, str]]:
        sample = self._build_sample(transactions)
        prompt = build_rules_prompt(sample)
        response = self.model.generate_content(prompt)
        text = getattr(response, "text", "") or ""
        return self._parse_rules(text)

    def infer_graph(
        self, transaction: dict[str, Any], root_context: str | None = None
    ) -> tuple[dict[str, Any], str]:
        prompt = build_entity_relationship_prompt(transaction, root_context=root_context)
        response = self.model.generate_content(prompt)
        text = getattr(response, "text", "") or ""
        return self._parse_graph(text), text

    @staticmethod
    def _build_sample(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sample = []
        for tx in transactions[:60]:
            raw = tx.get("raw", {})
            sample.append(
                {
                    "description": tx.get("description", ""),
                    "amount": tx.get("amount", 0),
                    "note": raw.get("note", ""),
                    "display": raw.get("display", ""),
                    "memo": raw.get("memo", ""),
                }
            )
        return sample

    @staticmethod
    def _parse_rules(text: str) -> list[dict[str, str]]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        rules: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            rules.append(
                {
                    "pattern": str(item.get("pattern", "")).strip(),
                    "match_field": str(item.get("match_field", "description")).strip(),
                    "entity": str(item.get("entity", "")).strip(),
                    "category": str(item.get("category", "")).strip(),
                }
            )
        return rules

    @staticmethod
    def _parse_graph(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"entities": [], "relationships": []}
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])
        if not isinstance(entities, list) or not isinstance(relationships, list):
            return {"entities": [], "relationships": []}
        return {"entities": entities, "relationships": relationships}


if __name__ == "__main__":
    load_dotenv()
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite-001")
    if not project:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT or VERTEX_PROJECT before running this test.")

    vertexai.init(project=project, location=location)
    adapter = GeminiVertexAdapter(model_name)
    result = adapter.model.generate_content("Reply with 'vertex ok' if you can read this.")
    print(getattr(result, "text", ""))
