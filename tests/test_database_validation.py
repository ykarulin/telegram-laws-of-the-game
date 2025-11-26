"""Tests for ConversationDatabase input validation methods."""
import pytest
import os
from src.core.db import ConversationDatabase

# Use test database URL from environment or default
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://telegram_bot:telegram_bot_password@localhost/telegram_bot_test"
)


@pytest.fixture
def db():
    """Create a database instance for testing."""
    return ConversationDatabase(TEST_DATABASE_URL)


class TestMessageIdValidation:
    """Test _validate_message_id method."""

    def test_valid_message_id(self, db):
        """Valid positive integer should not raise."""
        db._validate_message_id(1)
        db._validate_message_id(999999)
        db._validate_message_id(2147483647)  # Max 32-bit int

    def test_invalid_message_id_zero(self, db):
        """Zero should raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            db._validate_message_id(0)

    def test_invalid_message_id_negative(self, db):
        """Negative integers should raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            db._validate_message_id(-1)
        with pytest.raises(ValueError, match="must be positive"):
            db._validate_message_id(-999)

    def test_invalid_message_id_not_integer(self, db):
        """Non-integer types should raise ValueError."""
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_message_id("123")
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_message_id(123.45)
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_message_id(None)


class TestChatIdValidation:
    """Test _validate_chat_id method."""

    def test_valid_chat_id_positive(self, db):
        """Positive integers should be valid."""
        db._validate_chat_id(1)
        db._validate_chat_id(999999)
        db._validate_chat_id(2147483647)

    def test_valid_chat_id_negative(self, db):
        """Negative integers should be valid (Telegram supports group chat IDs as negative)."""
        db._validate_chat_id(-1)
        db._validate_chat_id(-999)
        db._validate_chat_id(-2147483648)

    def test_invalid_chat_id_zero(self, db):
        """Zero should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be zero"):
            db._validate_chat_id(0)

    def test_invalid_chat_id_not_integer(self, db):
        """Non-integer types should raise ValueError."""
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_chat_id("123")
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_chat_id(123.45)
        with pytest.raises(ValueError, match="must be an integer"):
            db._validate_chat_id(None)


class TestTextValidation:
    """Test _validate_text method."""

    def test_valid_text(self, db):
        """Non-empty strings should be valid."""
        db._validate_text("Hello")
        db._validate_text("a")
        db._validate_text("This is a longer message with special chars !@#$%")

    def test_invalid_text_empty(self, db):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            db._validate_text("")

    def test_invalid_text_whitespace_only(self, db):
        """Whitespace-only strings should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
            db._validate_text("   ")
        with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
            db._validate_text("\t")
        with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
            db._validate_text("\n")

    def test_invalid_text_not_string(self, db):
        """Non-string types should raise ValueError."""
        with pytest.raises(ValueError, match="must be a string"):
            db._validate_text(123)
        with pytest.raises(ValueError, match="must be a string"):
            db._validate_text(None)
        with pytest.raises(ValueError, match="must be a string"):
            db._validate_text(["text"])


class TestValidationIntegration:
    """Test validation in context of save_message method."""

    def test_save_message_with_invalid_message_id(self, db):
        """save_message should reject invalid message_id."""
        with pytest.raises(ValueError, match="must be positive"):
            db.save_message(
                message_id=0,
                chat_id=123,
                sender_type="user",
                sender_id=456,
                text="Hello"
            )

    def test_save_message_with_invalid_chat_id(self, db):
        """save_message should reject invalid chat_id."""
        with pytest.raises(ValueError, match="cannot be zero"):
            db.save_message(
                message_id=1,
                chat_id=0,
                sender_type="user",
                sender_id=456,
                text="Hello"
            )

    def test_save_message_with_invalid_text(self, db):
        """save_message should reject empty text."""
        with pytest.raises(ValueError, match="cannot be empty"):
            db.save_message(
                message_id=1,
                chat_id=123,
                sender_type="user",
                sender_id=456,
                text=""
            )

    def test_get_message_with_invalid_ids(self, db):
        """get_message should reject invalid IDs."""
        with pytest.raises(ValueError):
            db.get_message(message_id=-1, chat_id=123)

        with pytest.raises(ValueError):
            db.get_message(message_id=1, chat_id=0)

    def test_get_conversation_chain_with_invalid_user_id(self, db):
        """get_conversation_chain should reject invalid user_id type."""
        with pytest.raises(ValueError, match="must be an integer"):
            db.get_conversation_chain(
                message_id=1,
                chat_id=123,
                user_id="not_an_int"
            )

    def test_get_latest_messages_with_invalid_limit(self, db):
        """get_latest_messages should reject invalid limit."""
        with pytest.raises(ValueError, match="must be a positive integer"):
            db.get_latest_messages(chat_id=123, limit=0)

        with pytest.raises(ValueError, match="must be a positive integer"):
            db.get_latest_messages(chat_id=123, limit=-1)

        with pytest.raises(ValueError, match="must be a positive integer"):
            db.get_latest_messages(chat_id=123, limit="10")
