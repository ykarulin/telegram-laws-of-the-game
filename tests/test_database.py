"""Tests for conversation database functionality."""
import pytest
import os
from datetime import datetime
from src.core.db import ConversationDatabase, Message

# Use test database URL from environment or default
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://telegram_bot:telegram_bot_password@localhost/telegram_bot_test"
)

# Fixed test values
TEST_CHAT_ID = 12345
TEST_USER_ID = 100
TEST_BOT_ID = "gpt-5-mini"


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db = ConversationDatabase(TEST_DATABASE_URL)
    yield db

    # Cleanup - delete all messages after test
    db.delete_all_for_testing()


class TestMessageStorage:
    """Tests for basic message storage functionality."""

    def test_save_and_retrieve_user_message(self, temp_db):
        """Test saving and retrieving a user message."""
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What is offside?",
        )

        msg = temp_db.get_message(1, TEST_CHAT_ID)
        assert msg is not None
        assert msg.message_id == 1
        assert msg.chat_id == TEST_CHAT_ID
        assert msg.sender_type == "user"
        assert msg.sender_id == str(TEST_USER_ID)
        assert msg.text == "What is offside?"
        assert msg.reply_to_message_id is None
        assert msg.timestamp is not None

    def test_save_and_retrieve_bot_message(self, temp_db):
        """Test saving and retrieving a bot message."""
        temp_db.save_message(
            message_id=10,
            chat_id=TEST_CHAT_ID,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Offside is when a player is ahead of the ball...",
        )

        msg = temp_db.get_message(10, TEST_CHAT_ID)
        assert msg is not None
        assert msg.sender_type == "bot"
        assert msg.sender_id == TEST_BOT_ID

    def test_save_message_with_reply_to(self, temp_db):
        """Test saving messages with reply chain."""
        # User message 1
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What is offside?",
        )

        # Bot response 2
        temp_db.save_message(
            message_id=2,
            chat_id=TEST_CHAT_ID,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Offside is when...",
            reply_to_message_id=1,
        )

        # User followup 3 (replies to bot message 2)
        temp_db.save_message(
            message_id=3,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="Can you explain more?",
            reply_to_message_id=2,
        )

        msg = temp_db.get_message(3, TEST_CHAT_ID)
        assert msg.reply_to_message_id == 2

    def test_get_nonexistent_message(self, temp_db):
        """Test retrieving a message that doesn't exist."""
        msg = temp_db.get_message(999, TEST_CHAT_ID)
        assert msg is None

    def test_save_duplicate_message(self, temp_db):
        """Test that saving duplicate messages doesn't crash."""
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="Question 1",
        )

        # Second save should not raise, but should log a warning
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="Question 2",
        )

        # First message should still be there
        msg = temp_db.get_message(1, TEST_CHAT_ID)
        assert msg.text == "Question 1"

    def test_messages_isolated_by_chat(self, temp_db):
        """Test that messages are properly isolated by chat_id."""
        chat1 = 111
        chat2 = 222

        # Message in chat 1
        temp_db.save_message(
            message_id=1,
            chat_id=chat1,
            sender_type="user",
            sender_id=100,
            text="Chat 1 message",
        )

        # Same message ID in chat 2 (should be allowed)
        temp_db.save_message(
            message_id=1,
            chat_id=chat2,
            sender_type="user",
            sender_id=200,
            text="Chat 2 message",
        )

        msg1 = temp_db.get_message(1, chat1)
        msg2 = temp_db.get_message(1, chat2)

        assert msg1.text == "Chat 1 message"
        assert msg2.text == "Chat 2 message"


class TestConversationChains:
    """Tests for conversation chain building."""

    def test_single_message_chain(self, temp_db):
        """Test chain for a standalone message (no reply_to)."""
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What is offside?",
        )

        chain = temp_db.get_conversation_chain(1, TEST_CHAT_ID, TEST_USER_ID)
        assert len(chain) == 1
        assert chain[0].message_id == 1

    def test_linear_conversation_chain(self, temp_db):
        """Test building a linear conversation chain: User -> Bot -> User."""
        # Message 1: User asks
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What is offside?",
        )

        # Message 2: Bot responds (reply to 1)
        temp_db.save_message(
            message_id=2,
            chat_id=TEST_CHAT_ID,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Offside is...",
            reply_to_message_id=1,
        )

        # Message 3: User follows up (reply to 2)
        temp_db.save_message(
            message_id=3,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="Can you explain more?",
            reply_to_message_id=2,
        )

        # Get chain from message 3 (should be 1, 2, 3)
        chain = temp_db.get_conversation_chain(3, TEST_CHAT_ID, TEST_USER_ID)
        assert len(chain) == 3
        assert chain[0].message_id == 1
        assert chain[1].message_id == 2
        assert chain[2].message_id == 3
        assert chain[0].sender_type == "user"
        assert chain[1].sender_type == "bot"
        assert chain[2].sender_type == "user"

    def test_branched_conversation_chain(self, temp_db):
        """Test building chain when user creates a different branch.

        Structure:
        - Message 1: User asks
        - Message 2: Bot responds (reply to 1)
        - Message 3: User follows up (reply to 2)
        - Message 4: User asks differently (reply to 2) - different branch

        When user sends message 4, chain should be 1, 2, 4 (not 3)
        """
        # Message 1: User asks
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What is offside?",
        )

        # Message 2: Bot responds
        temp_db.save_message(
            message_id=2,
            chat_id=TEST_CHAT_ID,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Offside is...",
            reply_to_message_id=1,
        )

        # Message 3: User follows up on message 2
        temp_db.save_message(
            message_id=3,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What about passive offside?",
            reply_to_message_id=2,
        )

        # Message 4: Bot response to message 3
        temp_db.save_message(
            message_id=4,
            chat_id=TEST_CHAT_ID,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Passive offside is...",
            reply_to_message_id=3,
        )

        # Message 5: User asks different question, replies to message 2 (branch point)
        temp_db.save_message(
            message_id=5,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="What about VAR?",
            reply_to_message_id=2,
        )

        # Get chain from message 5 (should be 1, 2, 5 - not 3, 4)
        chain = temp_db.get_conversation_chain(5, TEST_CHAT_ID, TEST_USER_ID)
        assert len(chain) == 3
        assert chain[0].message_id == 1
        assert chain[1].message_id == 2
        assert chain[2].message_id == 5

    def test_broken_chain_stops_at_missing_message(self, temp_db):
        """Test that chain building stops when a referenced message is missing."""
        # Only save message 3, not message 2
        temp_db.save_message(
            message_id=3,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=TEST_USER_ID,
            text="Some question",
            reply_to_message_id=2,  # References non-existent message 2
        )

        # Get chain from 3 - should only get 3 since 2 doesn't exist
        chain = temp_db.get_conversation_chain(3, TEST_CHAT_ID, TEST_USER_ID)
        assert len(chain) == 1
        assert chain[0].message_id == 3

    def test_chain_stops_at_different_user(self, temp_db):
        """Test that chain building stops at messages from different users."""
        # Message from user 100
        temp_db.save_message(
            message_id=1,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=100,
            text="User 100 question",
        )

        # Message from user 200 replying to user 100's message
        temp_db.save_message(
            message_id=2,
            chat_id=TEST_CHAT_ID,
            sender_type="user",
            sender_id=200,
            text="User 200 question",
            reply_to_message_id=1,
        )

        # Get chain from user 200's message
        chain = temp_db.get_conversation_chain(2, TEST_CHAT_ID, 200)
        # Should only get message 2 (stops at user boundary on first iteration)
        assert len(chain) == 1
        assert chain[0].message_id == 2


class TestLatestMessages:
    """Tests for retrieving recent messages."""

    def test_get_latest_messages_empty(self, temp_db):
        """Test getting latest messages when none exist."""
        msgs = temp_db.get_latest_messages(TEST_CHAT_ID)
        assert msgs == []

    def test_get_latest_messages_limit(self, temp_db):
        """Test getting latest messages with limit."""
        import time

        # Save 5 messages with delays to ensure different timestamps
        for i in range(1, 6):
            temp_db.save_message(
                message_id=i,
                chat_id=TEST_CHAT_ID,
                sender_type="user",
                sender_id=TEST_USER_ID,
                text=f"Question {i}",
            )
            time.sleep(0.05)

        # Get only 3 latest
        msgs = temp_db.get_latest_messages(TEST_CHAT_ID, limit=3)
        assert len(msgs) == 3
        # Should be in reverse order (newest first)
        assert msgs[0].message_id == 5
        assert msgs[1].message_id == 4
        assert msgs[2].message_id == 3

    def test_get_latest_messages_only_for_chat(self, temp_db):
        """Test that get_latest_messages only returns messages for specific chat."""
        chat1 = 111
        chat2 = 222

        # Messages in chat 1
        temp_db.save_message(
            message_id=1,
            chat_id=chat1,
            sender_type="user",
            sender_id=100,
            text="Chat 1 msg",
        )

        # Messages in chat 2
        temp_db.save_message(
            message_id=2,
            chat_id=chat2,
            sender_type="user",
            sender_id=200,
            text="Chat 2 msg 1",
        )
        temp_db.save_message(
            message_id=3,
            chat_id=chat2,
            sender_type="user",
            sender_id=200,
            text="Chat 2 msg 2",
        )

        msgs_chat1 = temp_db.get_latest_messages(chat1)
        msgs_chat2 = temp_db.get_latest_messages(chat2)

        assert len(msgs_chat1) == 1
        assert msgs_chat1[0].chat_id == chat1

        assert len(msgs_chat2) == 2
        assert all(msg.chat_id == chat2 for msg in msgs_chat2)


class TestDatabaseIntegration:
    """Integration tests with realistic conversation scenarios."""

    def test_realistic_conversation_flow(self, temp_db):
        """Test a realistic multi-turn conversation with alternating user/bot messages."""
        chat_id = 999
        user_id = 555

        # Turn 1: User asks about offside
        temp_db.save_message(
            message_id=1,
            chat_id=chat_id,
            sender_type="user",
            sender_id=user_id,
            text="What is the offside rule?",
        )

        # Bot responds
        temp_db.save_message(
            message_id=2,
            chat_id=chat_id,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="The offside rule prevents players from being ahead of the ball...",
            reply_to_message_id=1,
        )

        # Turn 2: User asks for clarification
        temp_db.save_message(
            message_id=3,
            chat_id=chat_id,
            sender_type="user",
            sender_id=user_id,
            text="Can you give an example?",
            reply_to_message_id=2,
        )

        # Bot responds with example
        temp_db.save_message(
            message_id=4,
            chat_id=chat_id,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="Sure! If a player is receiving the ball and there are fewer than two opponents...",
            reply_to_message_id=3,
        )

        # Verify chain
        chain = temp_db.get_conversation_chain(4, chat_id, user_id)
        assert len(chain) == 4
        assert chain[0].sender_type == "user"
        assert chain[1].sender_type == "bot"
        assert chain[2].sender_type == "user"
        assert chain[3].sender_type == "bot"

    def test_multiple_users_isolated_conversations(self, temp_db):
        """Test that conversations between different users are properly isolated."""
        chat_id = 777

        # User 1 conversation
        temp_db.save_message(
            message_id=100,
            chat_id=chat_id,
            sender_type="user",
            sender_id=1,
            text="User 1 Q1",
        )
        temp_db.save_message(
            message_id=101,
            chat_id=chat_id,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="User 1 A1",
            reply_to_message_id=100,
        )
        temp_db.save_message(
            message_id=102,
            chat_id=chat_id,
            sender_type="user",
            sender_id=1,
            text="User 1 Q2",
            reply_to_message_id=101,
        )

        # User 2 conversation in same chat
        temp_db.save_message(
            message_id=200,
            chat_id=chat_id,
            sender_type="user",
            sender_id=2,
            text="User 2 Q1",
        )
        temp_db.save_message(
            message_id=201,
            chat_id=chat_id,
            sender_type="bot",
            sender_id=TEST_BOT_ID,
            text="User 2 A1",
            reply_to_message_id=200,
        )

        # Verify isolation
        chain1 = temp_db.get_conversation_chain(102, chat_id, 1)
        assert len(chain1) == 3
        assert all(msg.message_id in [100, 101, 102] for msg in chain1)

        chain2 = temp_db.get_conversation_chain(201, chat_id, 2)
        assert len(chain2) == 2
        assert all(msg.message_id in [200, 201] for msg in chain2)


class TestLargeTelegramIDs:
    """Regression tests for handling large Telegram IDs (64-bit integers)."""

    def test_save_and_retrieve_large_chat_id(self, temp_db):
        """Test that large chat IDs (exceeding 32-bit limit) are handled correctly.

        Telegram chat IDs can be 64-bit signed integers. This test verifies
        that the database correctly stores and retrieves chat IDs that exceed
        the 32-bit signed integer limit (2,147,483,647).

        Regression test for: https://github.com/issue/large-chat-id-overflow
        """
        # Chat ID: 5872238465 (exceeds 32-bit limit)
        large_chat_id = 5872238465
        message_id = 150
        user_id = 12345

        # Save message with large chat ID
        temp_db.save_message(
            message_id=message_id,
            chat_id=large_chat_id,
            sender_type="user",
            sender_id=user_id,
            text="Test message with large chat ID",
        )

        # Retrieve and verify
        msg = temp_db.get_message(message_id, large_chat_id)
        assert msg is not None
        assert msg.message_id == message_id
        assert msg.chat_id == large_chat_id
        assert msg.sender_id == str(user_id)
        assert msg.text == "Test message with large chat ID"

    def test_large_message_id(self, temp_db):
        """Test that large message IDs (64-bit) are handled correctly."""
        chat_id = 12345
        # Large message ID (within BIGINT range: -9223372036854775808 to 9223372036854775807)
        large_message_id = 4999999999999999  # Large but within range
        user_id = 100

        temp_db.save_message(
            message_id=large_message_id,
            chat_id=chat_id,
            sender_type="user",
            sender_id=user_id,
            text="Message with large ID",
        )

        msg = temp_db.get_message(large_message_id, chat_id)
        assert msg is not None
        assert msg.message_id == large_message_id

    def test_large_reply_to_message_id(self, temp_db):
        """Test that large reply_to_message_id values are handled correctly."""
        chat_id = 5872238465  # Large chat ID
        user_id = 100

        # First message with large message ID
        large_message_id = 2999999999
        temp_db.save_message(
            message_id=large_message_id,
            chat_id=chat_id,
            sender_type="user",
            sender_id=user_id,
            text="Original message",
        )

        # Reply with another large message ID
        reply_message_id = 3000000000
        temp_db.save_message(
            message_id=reply_message_id,
            chat_id=chat_id,
            sender_type="bot",
            sender_id="gpt-5-mini",
            text="Bot response",
            reply_to_message_id=large_message_id,
        )

        msg = temp_db.get_message(reply_message_id, chat_id)
        assert msg.reply_to_message_id == large_message_id

    def test_conversation_chain_with_large_ids(self, temp_db):
        """Test conversation chain building with large Telegram IDs."""
        large_chat_id = 5872238465
        user_id = 100

        # Build a conversation chain with large IDs
        msg1_id = 2999999999
        temp_db.save_message(
            message_id=msg1_id,
            chat_id=large_chat_id,
            sender_type="user",
            sender_id=user_id,
            text="User question",
        )

        msg2_id = 3000000000
        temp_db.save_message(
            message_id=msg2_id,
            chat_id=large_chat_id,
            sender_type="bot",
            sender_id="gpt-5-mini",
            text="Bot answer",
            reply_to_message_id=msg1_id,
        )

        msg3_id = 3000000001
        temp_db.save_message(
            message_id=msg3_id,
            chat_id=large_chat_id,
            sender_type="user",
            sender_id=user_id,
            text="Follow-up",
            reply_to_message_id=msg2_id,
        )

        # Get chain from last message
        chain = temp_db.get_conversation_chain(msg3_id, large_chat_id, user_id)
        assert len(chain) == 3
        assert chain[0].message_id == msg1_id
        assert chain[1].message_id == msg2_id
        assert chain[2].message_id == msg3_id
