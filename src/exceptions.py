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
