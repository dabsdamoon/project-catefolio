"""Custom exceptions for the Catefolio application."""

from __future__ import annotations


class CatefolioError(Exception):
    """Base exception for all Catefolio errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class FileProcessingError(CatefolioError):
    """Raised when file processing fails."""

    pass


class LLMError(CatefolioError):
    """Base exception for LLM-related errors."""

    pass


class LLMConnectionError(LLMError):
    """Raised when connection to LLM provider fails."""

    pass


class LLMParseError(LLMError):
    """Raised when parsing LLM response fails."""

    def __init__(self, message: str, raw_response: str = "", details: dict | None = None) -> None:
        super().__init__(message, details)
        self.raw_response = raw_response


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit is exceeded."""

    pass


class ValidationError(CatefolioError):
    """Raised when input validation fails."""

    pass


class JobNotFoundError(CatefolioError):
    """Raised when a job is not found."""

    pass


class EntityNotFoundError(CatefolioError):
    """Raised when an entity is not found."""

    pass
