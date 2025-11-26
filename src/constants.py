"""Application-wide constants and configuration values."""


class TelegramLimits:
    """Telegram Bot API limits and constraints."""
    MAX_MESSAGE_LENGTH = 4096
    MESSAGE_LENGTH_BUFFER = 50  # Buffer for truncation


class EmbeddingConfig:
    """Embedding service defaults and limits."""
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 100
    VECTOR_DIMENSIONS_SMALL = 512  # text-embedding-3-small
    VECTOR_DIMENSIONS_LARGE = 3072  # text-embedding-3-large
    VECTOR_DIMENSIONS_DEFAULT = 1536  # Older models default
    API_BATCH_SIZE_LIMIT = 2048  # OpenAI API max batch size


class OpenAIConfig:
    """OpenAI API configuration defaults."""
    DEFAULT_TEMPERATURE = 0.7
    MIN_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 2.0
    DEFAULT_MODEL = "gpt-4-turbo"
    EMBEDDING_MODEL = "text-embedding-3-small"
