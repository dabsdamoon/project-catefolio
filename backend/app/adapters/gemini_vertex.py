from __future__ import annotations

import json
import os
from typing import Any

import vertexai
from dotenv import load_dotenv
from google.api_core import exceptions as google_exceptions
from vertexai.generative_models import GenerativeModel

from app.core.exceptions import LLMConnectionError, LLMParseError, LLMRateLimitError
from app.core.logging import get_logger
from app.prompt.entity_prompts import (
    build_category_prompt,
    build_entity_relationship_prompt,
)

logger = get_logger("catefolio.adapters.gemini")


class GeminiVertexAdapter:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            self.model = GenerativeModel(model_name)
            logger.info(f"Initialized GeminiVertexAdapter with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize GenerativeModel: {e}")
            raise LLMConnectionError(
                f"Failed to initialize LLM model: {model_name}",
                details={"model": model_name, "error": str(e)},
            ) from e

    def infer_graph(
        self, transaction: dict[str, Any], root_context: str | None = None
    ) -> tuple[dict[str, Any], str]:
        prompt = build_entity_relationship_prompt(transaction, root_context=root_context)
        logger.debug(f"Inferring entity graph for transaction: {transaction.get('description', '')[:50]}")

        text = self._call_model(prompt, operation="infer_graph")
        result = self._parse_graph(text)
        logger.info(
            f"Extracted {len(result.get('entities', []))} entities, "
            f"{len(result.get('relationships', []))} relationships"
        )
        return result, text

    def infer_categories_batch(
        self, transactions: list[dict[str, Any]], categories: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str]:
        """Infer categories for a batch of transactions.

        Args:
            transactions: List of transaction dictionaries
            categories: List of category dicts with 'name' and 'keywords' fields
        """
        prompt = build_category_prompt(transactions, categories)
        logger.debug(f"Inferring categories for batch of {len(transactions)} transactions")

        with open("/Users/dabsdamoon/projects/project-catefolio/tmp/prompt.txt", "w") as f:
            f.write(prompt)

        text = self._call_model(prompt, operation="infer_categories_batch")
        results = self._parse_categories(text)
        logger.info(f"Categorized {len(results)} transactions in batch")
        return results, text

    def _call_model(self, prompt: str, operation: str = "generate") -> str:
        """Call the LLM model with error handling."""
        try:
            response = self.model.generate_content(prompt)
            text = getattr(response, "text", "") or ""
            if not text:
                logger.warning(f"Empty response from LLM for operation: {operation}")
            return text
        except google_exceptions.ResourceExhausted as e:
            logger.error(f"LLM rate limit exceeded: {e}")
            raise LLMRateLimitError(
                "Rate limit exceeded. Please try again later.",
                details={"operation": operation, "error": str(e)},
            ) from e
        except google_exceptions.ServiceUnavailable as e:
            logger.error(f"LLM service unavailable: {e}")
            raise LLMConnectionError(
                "LLM service is temporarily unavailable.",
                details={"operation": operation, "error": str(e)},
            ) from e
        except google_exceptions.InvalidArgument as e:
            logger.error(f"Invalid argument to LLM: {e}")
            raise LLMConnectionError(
                "Invalid request to LLM service.",
                details={"operation": operation, "error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"Unexpected LLM error during {operation}: {e}", exc_info=True)
            raise LLMConnectionError(
                f"Failed to communicate with LLM: {e}",
                details={"operation": operation, "error": str(e)},
            ) from e

    def _parse_graph(self, text: str) -> dict[str, Any]:
        cleaned = self._strip_code_fence(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse graph JSON: {e}. Raw response: {text[:200]}")
            raise LLMParseError(
                "Failed to parse entity graph from LLM response",
                raw_response=text,
                details={"error": str(e)},
            ) from e

        entities = data.get("entities", [])
        relationships = data.get("relationships", [])
        if not isinstance(entities, list) or not isinstance(relationships, list):
            logger.warning("Invalid graph structure: entities or relationships not a list")
            return {"entities": [], "relationships": []}
        return {"entities": entities, "relationships": relationships}

    def _parse_categories(self, text: str) -> list[dict[str, Any]]:
        cleaned = self._strip_code_fence(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse categories JSON: {e}. Raw response: {text[:200]}")
            raise LLMParseError(
                "Failed to parse categories from LLM response",
                raw_response=text,
                details={"error": str(e)},
            ) from e

        if not isinstance(data, list):
            logger.warning(f"Expected list for categories, got {type(data).__name__}")
            return []

        results: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            categories = item.get("categories", [])
            if isinstance(categories, str):
                categories = [categories]
            if not isinstance(categories, list):
                categories = []
            categories = [str(cat).strip() for cat in categories if str(cat).strip()]
            results.append({"index": int(item.get("index", -1)), "categories": categories})
        return results

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        return cleaned.strip()


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
