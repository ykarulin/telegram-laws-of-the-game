"""Configuration management for different environments."""
import os
from enum import Enum
from dataclasses import dataclass
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
    # Qdrant Vector Database
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: str
    qdrant_collection_name: str
    # Embedding Configuration
    embedding_model: str
    embedding_batch_size: int
    top_k_retrievals: int
    similarity_threshold: float

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
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            qdrant_collection_name=qdrant_collection_name,
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "100")),
            top_k_retrievals=int(os.getenv("TOP_K_RETRIEVALS", "5")),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.7")),
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
