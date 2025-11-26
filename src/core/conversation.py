"""Conversation context building utilities."""
from typing import List, Dict, Any
from src.core.db import Message


def build_conversation_context(messages: List[Message]) -> List[Dict[str, str]]:
    """Convert Message objects to LLM format.

    Takes a list of Message objects from the database and converts them to the
    format expected by the OpenAI API. Messages can be from either user or bot.

    Args:
        messages: List of Message objects representing a conversation chain,
                 ordered chronologically (oldest first)

    Returns:
        List of message dictionaries with 'role' and 'content' fields in the format:
        [
            {"role": "user", "content": "user message"},
            {"role": "assistant", "content": "bot message"},
            ...
        ]
    """
    context = []
    for msg in messages:
        # Determine role based on sender type
        role = "user" if msg.sender_type == "user" else "assistant"
        context.append({"role": role, "content": msg.text})
    return context
