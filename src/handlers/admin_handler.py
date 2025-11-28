"""Admin command handler for managing monitoring preferences."""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.services.admin_service import AdminService
from src.core.db import MonitoringLevel

logger = logging.getLogger(__name__)


class AdminHandler:
    """Handler for admin commands."""

    def __init__(self, admin_service: AdminService):
        """Initialize AdminHandler.

        Args:
            admin_service: AdminService instance
        """
        self.admin_service = admin_service

    async def handle_monitor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /monitor command.

        Usage:
            /monitor debug - Set monitoring level to debug
            /monitor info - Set monitoring level to info
            /monitor error - Set monitoring level to error
            /monitor status - Show current monitoring level
        """
        user_id = update.effective_user.id
        chat = update.effective_chat

        # Only allow in private chats (DM)
        if chat.type != "private":
            await context.bot.send_message(
                chat_id=user_id,
                text="Admin commands are only available in private messages."
            )
            return

        # Check if user is admin
        if not self.admin_service.is_admin(user_id):
            await context.bot.send_message(
                chat_id=user_id,
                text="You are not authorized to use admin commands."
            )
            return

        # Parse command arguments
        args = context.args or []

        if not args:
            await context.bot.send_message(
                chat_id=user_id,
                text="Usage: /monitor [debug|info|error|status]"
            )
            return

        command = args[0].lower()

        if command == "status":
            level = self.admin_service.get_monitoring_level(user_id)
            if level:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Your current monitoring level: **{level}**",
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Your monitoring level is not set. Use `/monitor [debug|info|error]` to set it."
                )
            return

        # Validate level
        valid_levels = [level.value for level in MonitoringLevel]
        if command not in valid_levels:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Invalid monitoring level. Must be one of: {', '.join(valid_levels)}"
            )
            return

        # Set monitoring level
        if self.admin_service.set_monitoring_level(user_id, command):
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Monitoring level set to **{command}**",
                parse_mode="Markdown"
            )
            logger.info(f"Admin {user_id} set monitoring level to {command}")
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="Failed to update monitoring level. Please try again."
            )

    async def handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command for admins."""
        user_id = update.effective_user.id
        chat = update.effective_chat

        # Only allow in private chats (DM)
        if chat.type != "private":
            await context.bot.send_message(
                chat_id=user_id,
                text="Admin commands are only available in private messages."
            )
            return

        # Check if user is admin
        if not self.admin_service.is_admin(user_id):
            await context.bot.send_message(
                chat_id=user_id,
                text="You are not authorized to use admin commands."
            )
            return

        # Send help
        await self.admin_service.send_admin_help(user_id)
