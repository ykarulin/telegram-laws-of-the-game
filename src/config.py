"""Configuration management for different environments."""
import os
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
from src.exceptions import ConfigError


class Environment(Enum):
    """Available environments."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


@dataclass
class Config:
    """Base configuration class."""
    environment: Environment
    telegram_bot_token: str
    log_level: str
    debug: bool
    openai_api_key: str
    openai_model: str
    openai_max_tokens: int
    openai_temperature: float
    database_url: str
    # Admin Configuration
    admin_user_ids: list[int] = None
    # Telegram Webhook Configuration (optional)
    telegram_webhook_url: str = None
    telegram_webhook_port: int = 8443
    telegram_webhook_secret_token: str = None
    # Qdrant Vector Database
    qdrant_host: str = None
    qdrant_port: int = None
    qdrant_api_key: str = None
    qdrant_collection_name: str = None
    # Embedding Configuration
    embedding_model: str = None
    embedding_batch_size: int = None
    top_k_retrievals: int = None
    similarity_threshold: float = None
    rag_dynamic_threshold_margin: Optional[float] = None
    # Document Lookup Tool Configuration
    max_document_lookups: int = None
    lookup_max_chunks: int = None
    require_tool_use: bool = False
    enable_document_selection: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        if not 0.0 <= self.openai_temperature <= 2.0:
            raise ConfigError(
                f"openai_temperature must be between 0.0 and 2.0, got {self.openai_temperature}"
            )

        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ConfigError(
                f"similarity_threshold must be between 0.0 and 1.0, got {self.similarity_threshold}"
            )

        if not 1 <= self.embedding_batch_size <= 2048:
            raise ConfigError(
                f"embedding_batch_size must be between 1 and 2048, got {self.embedding_batch_size}"
            )

        if self.top_k_retrievals < 1:
            raise ConfigError(
                f"top_k_retrievals must be at least 1, got {self.top_k_retrievals}"
            )

        if self.rag_dynamic_threshold_margin is not None:
            if not 0.0 <= self.rag_dynamic_threshold_margin <= 1.0:
                raise ConfigError(
                    f"rag_dynamic_threshold_margin must be between 0.0 and 1.0, got {self.rag_dynamic_threshold_margin}"
                )

        # Validate document lookup tool configuration
        if self.max_document_lookups is not None:
            if self.max_document_lookups < 1:
                raise ConfigError(
                    f"max_document_lookups must be at least 1, got {self.max_document_lookups}"
                )

        if self.lookup_max_chunks is not None:
            if self.lookup_max_chunks < 1:
                raise ConfigError(
                    f"lookup_max_chunks must be at least 1, got {self.lookup_max_chunks}"
                )

        if self.qdrant_port <= 0 or self.qdrant_port > 65535:
            raise ConfigError(
                f"qdrant_port must be between 1 and 65535, got {self.qdrant_port}"
            )

        if self.openai_max_tokens < 1:
            raise ConfigError(
                f"openai_max_tokens must be at least 1, got {self.openai_max_tokens}"
            )

        # Validate webhook port if webhook URL is set
        if self.telegram_webhook_url:
            if self.telegram_webhook_port <= 0 or self.telegram_webhook_port > 65535:
                raise ConfigError(
                    f"telegram_webhook_port must be between 1 and 65535, got {self.telegram_webhook_port}"
                )

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        env_name = os.getenv("ENVIRONMENT", "development").lower()

        try:
            environment = Environment[env_name.upper()]
        except KeyError:
            raise ConfigError(f"Unknown environment: {env_name}. Must be one of: {[e.value for e in Environment]}")

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN environment variable is required")

        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ConfigError("OPENAI_API_KEY environment variable is required")

        # Database URL is required
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ConfigError("DATABASE_URL environment variable is required")

        # Qdrant configuration
        qdrant_host = os.getenv("QDRANT_HOST")
        if not qdrant_host:
            raise ConfigError("QDRANT_HOST environment variable is required")

        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        qdrant_collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        if not qdrant_collection_name:
            raise ConfigError("QDRANT_COLLECTION_NAME environment variable is required")

        # Webhook configuration (optional)
        webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
        webhook_port = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443")) if webhook_url else 8443
        webhook_secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN")

        # Parse admin user IDs from comma-separated environment variable
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_user_ids = None
        if admin_ids_str:
            try:
                admin_user_ids = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]
            except ValueError:
                raise ConfigError(f"ADMIN_USER_IDS must be comma-separated integers, got: {admin_ids_str}")

        return cls(
            environment=environment,
            telegram_bot_token=token,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            debug=environment != Environment.PRODUCTION,
            openai_api_key=openai_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4-turbo"),
            openai_max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
            openai_temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
            database_url=database_url,
            admin_user_ids=admin_user_ids,
            telegram_webhook_url=webhook_url,
            telegram_webhook_port=webhook_port,
            telegram_webhook_secret_token=webhook_secret_token,
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            qdrant_collection_name=qdrant_collection_name,
            embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large"),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "100")),
            top_k_retrievals=int(os.getenv("TOP_K_RETRIEVALS", "5")),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.7")),
            rag_dynamic_threshold_margin=float(os.getenv("RAG_DYNAMIC_THRESHOLD_MARGIN")) if os.getenv("RAG_DYNAMIC_THRESHOLD_MARGIN") else None,
            max_document_lookups=int(os.getenv("MAX_DOCUMENT_LOOKUPS", "5")),
            lookup_max_chunks=int(os.getenv("LOOKUP_MAX_CHUNKS", "5")),
            require_tool_use=os.getenv("REQUIRE_TOOL_USE", "false").lower() == "true",
            enable_document_selection=os.getenv("ENABLE_DOCUMENT_SELECTION", "true").lower() == "true",
        )


def load_config(env_file: str = None) -> Config:
    """Load configuration from .env file and environment variables."""
    if env_file:
        load_dotenv(env_file)
    else:
        # Load from environment-specific .env file first
        env_name = os.getenv("ENVIRONMENT", "development").lower()
        env_specific_file = f".env.{env_name}"

        if os.path.exists(env_specific_file):
            load_dotenv(env_specific_file)
        else:
            # Fallback to generic .env
            load_dotenv(".env")

    return Config.from_env()
