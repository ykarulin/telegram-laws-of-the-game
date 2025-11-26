import os
import pytest
from src.config import Config, Environment, load_config
from src.exceptions import ConfigError


class TestEnvironmentEnum:
    """Test Environment enum."""

    def test_all_environments_defined(self):
        """Test that all environments are defined."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.TESTING.value == "testing"
        assert Environment.PRODUCTION.value == "production"


class TestConfigFromEnv:
    """Test Config.from_env() class method."""

    def test_config_from_env_development(self, monkeypatch):
        """Test loading development config."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dev_token_123")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        config = Config.from_env()

        assert config.environment == Environment.DEVELOPMENT
        assert config.telegram_bot_token == "dev_token_123"
        assert config.openai_api_key == "sk-test123"
        assert config.log_level == "DEBUG"
        assert config.debug is True

    def test_config_from_env_production(self, monkeypatch):
        """Test loading production config."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "prod_token_456")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-prod123")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@prod/db")
        monkeypatch.setenv("QDRANT_HOST", "qdrant.prod")
        monkeypatch.setenv("QDRANT_PORT", "6333")
        monkeypatch.setenv("LOG_LEVEL", "INFO")

        config = Config.from_env()

        assert config.environment == Environment.PRODUCTION
        assert config.telegram_bot_token == "prod_token_456"
        assert config.openai_api_key == "sk-prod123"
        assert config.log_level == "INFO"
        assert config.debug is False

    def test_config_from_env_testing(self, monkeypatch):
        """Test loading testing config."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token_789")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test789")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/test_db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")

        config = Config.from_env()

        assert config.environment == Environment.TESTING
        assert config.telegram_bot_token == "test_token_789"
        assert config.openai_api_key == "sk-test789"
        assert config.debug is True

    def test_config_missing_token(self, monkeypatch):
        """Test that missing token raises error."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
            Config.from_env()

    def test_config_unknown_environment(self, monkeypatch):
        """Test that unknown environment raises error."""
        monkeypatch.setenv("ENVIRONMENT", "unknown")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

        with pytest.raises(ConfigError, match="Unknown environment"):
            Config.from_env()

    def test_config_defaults(self, monkeypatch):
        """Test default values."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        config = Config.from_env()

        assert config.log_level == "INFO"

    def test_config_case_insensitive_environment(self, monkeypatch):
        """Test that environment is case insensitive."""
        monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@prod/db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")

        config = Config.from_env()

        assert config.environment == Environment.PRODUCTION

    def test_config_missing_openai_api_key(self, monkeypatch):
        """Test that missing OpenAI API key raises error."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
            Config.from_env()

    def test_config_openai_defaults(self, monkeypatch):
        """Test default OpenAI configuration."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("QDRANT_HOST", "localhost")
        monkeypatch.setenv("QDRANT_PORT", "6333")
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_MAX_TOKENS", raising=False)

        config = Config.from_env()

        assert config.openai_model == "gpt-4-turbo"
        assert config.openai_max_tokens == 4096
