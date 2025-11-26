"""Async utilities for typing indicator and background tasks."""
import asyncio
import logging
from typing import Callable, Any, Optional
from telegram import Update
from telegram.constants import ChatAction

logger = logging.getLogger(__name__)


async def send_typing_action_periodically(
    update: Update,
    interval: int = 5
) -> None:
    """Periodically send typing indicator to show bot is processing.

    Args:
        update: Telegram update object with chat information
        interval: Seconds between each typing indicator (default: 5)
    """
    while True:
        try:
            await update.effective_chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Failed to send typing action: {e}")
            break


async def send_typing_with_async_fn(
    update: Update,
    async_fn: Callable,
    interval: int = 5
) -> Any:
    """Execute async function with periodic typing indicator in background.

    Creates a background task that periodically sends typing indicators while
    the main async function executes. This makes the bot appear responsive.

    Args:
        update: Telegram update object with chat information
        async_fn: Async function to execute
        interval: Seconds between typing indicators (default: 5)

    Returns:
        Result of the async function

    Example:
        response = await send_typing_with_async_fn(
            update,
            llm_client.generate_response(text, context),
            interval=5
        )
    """
    # Start typing indicator task
    typing_task = asyncio.create_task(send_typing_action_periodically(update, interval))

    try:
        # Execute the main async function
        result = await async_fn
        return result
    finally:
        # Cancel typing task
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
