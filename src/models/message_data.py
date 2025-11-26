"""Data models for message handling."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class MessageData:
    """Extracted and validated message data from Telegram update."""

    user_id: int
    """Telegram user ID."""

    chat_id: int
    """Telegram chat ID (group, private, etc)."""

    message_id: int
    """Telegram message ID (unique within chat)."""

    text: str
    """Message text content."""

    reply_to_message_id: Optional[int] = None
    """Message ID this message replies to (for conversation chains)."""

    @classmethod
    def from_telegram_message(cls, update_message) -> "MessageData":
        """Create MessageData from Telegram Update.message object.

        Args:
            update_message: The message object from telegram.Update

        Returns:
            MessageData instance with extracted values
        """
        return cls(
            user_id=update_message.from_user.id,
            chat_id=update_message.chat_id,
            message_id=update_message.message_id,
            text=update_message.text,
            reply_to_message_id=(
                update_message.reply_to_message.message_id
                if update_message.reply_to_message
                else None
            ),
        )

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"MessageData(user={self.user_id}, chat={self.chat_id}, "
            f"msg={self.message_id}, reply_to={self.reply_to_message_id})"
        )
