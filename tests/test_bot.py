"""Tests for bot message handling."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User as TelegramUser, Chat
from telegram.ext import ContextTypes
from src.handlers.message_handler import MessageHandler
from src.config import Config, Environment
from src.exceptions import LLMError


@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = MagicMock(spec=Config)
    config.environment = Environment.TESTING
    config.openai_model = "gpt-4-turbo"
    return config


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_response = MagicMock(return_value="This is a test response.")
    return client


@pytest.fixture
def mock_database():
    """Create a mock database."""
    db = MagicMock()
    db.save_message = MagicMock()
    db.get_conversation_chain = MagicMock(return_value=[])
    return db


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    user = TelegramUser(id=123, is_bot=False, first_name="Test")
    chat = MagicMock(spec=Chat)
    chat.id = 123  # Set chat ID
    chat.send_action = AsyncMock()

    message = MagicMock(spec=Message)
    message.text = "What's the offside rule?"
    message.message_id = 1
    message.chat_id = 123  # Set message chat ID
    message.from_user = user
    message.reply_to_message = None
    message.reply_text = AsyncMock()
    message.chat = chat

    update = MagicMock(spec=Update)
    update.message = message
    update.effective_chat = chat
    update.effective_user = user
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram Context object."""
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    return context


@pytest.fixture
def message_handler(mock_llm_client, mock_database, mock_config):
    """Create a message handler with mocked dependencies."""
    return MessageHandler(mock_llm_client, mock_database, mock_config)


@pytest.mark.asyncio
async def test_handle_message_generates_llm_response(message_handler, mock_update, mock_context):
    """Test that bot generates LLM response."""
    # Execute
    await message_handler.handle(mock_update, mock_context)

    # Assert - generate_response is called with user message and conversation_context (None in this case)
    message_handler.llm_client.generate_response.assert_called_once()
    args = message_handler.llm_client.generate_response.call_args
    assert args[0][0] == "What's the offside rule?"
    assert args[0][1] is None  # No conversation context for standalone message

    # Verify database saved both user and bot messages (called twice)
    assert message_handler.db.save_message.call_count == 2

    # Verify reply was sent
    mock_update.message.reply_text.assert_called_once()
    assert "test response" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_message_sends_typing_indicator(message_handler, mock_update, mock_context):
    """Test that handler sends typing indicator periodically."""
    import time

    # Mock the generate_response to take some time (run in executor, so synchronous)
    def slow_generate(message, conversation_context=None, system_prompt=None, tools=None):
        time.sleep(0.15)  # Sleep for 150ms - long enough for at least 1 typing indicator
        return "This is a test response."

    message_handler.llm_client.generate_response = slow_generate

    # Execute
    await message_handler.handle(mock_update, mock_context)

    # Assert - typing indicator should be sent at least once
    # With 150ms sleep and 5s interval, at least the initial send_action should happen
    assert mock_update.effective_chat.send_action.call_count >= 1
    # Verify all calls were with "typing"
    for call in mock_update.effective_chat.send_action.call_args_list:
        assert call[0][0] == "typing"


@pytest.mark.asyncio
async def test_handle_message_handles_llm_error(message_handler, mock_update, mock_context):
    """Test handler gracefully handles LLM errors."""
    # Make generate_response fail
    message_handler.llm_client.generate_response = MagicMock(
        side_effect=LLMError("API Error")
    )

    # Execute
    await message_handler.handle(mock_update, mock_context)

    # Assert - should send error message
    reply_calls = mock_update.message.reply_text.call_args_list
    assert len(reply_calls) == 1
    assert "error" in reply_calls[0][0][0].lower()


@pytest.mark.asyncio
async def test_handle_message_builds_conversation_context(message_handler, mock_update, mock_context):
    """Test that handler builds conversation context when replying to a message."""
    from src.core.db import Message as DBMessage

    # Setup - message replying to another
    mock_update.message.reply_to_message = MagicMock()
    mock_update.message.reply_to_message.message_id = 5

    # Setup - conversation chain (user message + bot response)
    chain = [
        DBMessage(
            message_id=5,
            chat_id=123,
            sender_type="user",
            sender_id="123",
            text="Previous question",
            reply_to_message_id=None
        ),
        DBMessage(
            message_id=6,
            chat_id=123,
            sender_type="bot",
            sender_id="gpt-4-turbo",
            text="Previous answer",
            reply_to_message_id=5
        ),
    ]
    message_handler.db.get_conversation_chain = MagicMock(return_value=chain)

    # Execute
    await message_handler.handle(mock_update, mock_context)

    # Assert - get_conversation_chain was called with correct arguments (message_id, chat_id, user_id)
    message_handler.db.get_conversation_chain.assert_called_once_with(5, 123, 123)

    # Assert - generate_response was called with conversation context
    call_args = message_handler.llm_client.generate_response.call_args
    assert call_args is not None
    # Second argument should be conversation context (not None)
    assert call_args[0][1] is not None
    assert isinstance(call_args[0][1], list)
    assert len(call_args[0][1]) == 2  # user message + assistant response


@pytest.mark.asyncio
async def test_handle_message_with_no_text(message_handler, mock_update, mock_context):
    """Test handler gracefully handles messages without text."""
    mock_update.message.text = None

    # Execute
    await message_handler.handle(mock_update, mock_context)

    # Assert - nothing should be called
    message_handler.llm_client.generate_response.assert_not_called()
    message_handler.db.save_message.assert_not_called()
    mock_update.message.reply_text.assert_not_called()
