"""Custom exceptions for the law-of-the-game bot."""


class BotError(Exception):
    """Base exception for bot errors."""

    pass


class LLMError(BotError):
    """Exception raised for LLM-related errors."""

    pass


class DatabaseError(BotError):
    """Exception raised for database-related errors."""

    pass


class ConfigError(BotError):
    """Exception raised for configuration-related errors."""

    pass


class RetrievalError(BotError):
    """Exception raised for document retrieval-related errors.

    Distinguishes between different types of retrieval failures:
    - Health check failures (Qdrant/database unavailable)
    - Embedding failures (query embedding generation failed)
    - Search failures (vector search failed)
    """

    def __init__(self, message: str, error_type: str = "unknown"):
        """Initialize RetrievalError.

        Args:
            message: Error description
            error_type: Category of failure (health_check, embedding, search, etc.)
        """
        super().__init__(message)
        self.error_type = error_type
