"""Admin service for managing monitoring preferences and sending notifications to admins."""
import logging
import re
from typing import Optional, List
from telegram import Bot
from src.core.db import ConversationDatabase, MonitoringLevel

logger = logging.getLogger(__name__)


class AdminService:
    """Service for admin notifications and preference management."""

    def __init__(self, db: ConversationDatabase, bot: Bot, admin_user_ids: Optional[List[int]]):
        """Initialize AdminService.

        Args:
            db: ConversationDatabase instance
            bot: Telegram Bot instance for sending messages
            admin_user_ids: List of admin user IDs from configuration
        """
        self.db = db
        self.bot = bot
        self.admin_user_ids = admin_user_ids or []

    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin.

        Args:
            user_id: Telegram user ID to check

        Returns:
            True if user is an admin, False otherwise
        """
        return user_id in self.admin_user_ids

    def get_monitoring_level(self, user_id: int) -> Optional[str]:
        """Get monitoring level for an admin user.

        Args:
            user_id: Telegram user ID (admin)

        Returns:
            Monitoring level (error, info, debug) or None
        """
        if not self.is_admin(user_id):
            return None

        return self.db.get_admin_monitoring_level(user_id)

    def set_monitoring_level(self, user_id: int, level: str) -> bool:
        """Set monitoring level for an admin user.

        Args:
            user_id: Telegram user ID (admin)
            level: Monitoring level (error, info, debug)

        Returns:
            True if successful, False otherwise
        """
        if not self.is_admin(user_id):
            return False

        try:
            # Create preference if it doesn't exist
            self.db.get_or_create_admin_preference(user_id)
            # Update the level
            self.db.update_admin_monitoring_level(user_id, level)
            return True
        except (ValueError, Exception) as e:
            logger.error(f"Error setting monitoring level for {user_id}: {e}")
            return False

    @staticmethod
    def redact_sensitive_data(text: str) -> str:
        """Redact API keys and tokens from text.

        Args:
            text: Text that may contain sensitive data

        Returns:
            Text with sensitive data redacted
        """
        # Redact API keys (e.g., sk-..., api_key=..., etc.)
        text = re.sub(r'(api[_-]?key|sk-\w+|token[_-]?\w+)[\s=:]*[\w\-]+', r'\1=***REDACTED***', text, flags=re.IGNORECASE)
        # Redact URLs with credentials (e.g., postgresql://user:password@host)
        text = re.sub(r'(://[\w\-]+:)[\w\-]+(@)', r'\1***REDACTED***\2', text)
        return text

    async def send_error_notification(self, admin_id: int, error_message: str, user_id: int, error_stage: str = "unknown") -> bool:
        """Send error notification to admin.

        Args:
            admin_id: Telegram user ID of admin
            error_message: Error message to send
            user_id: Telegram user ID of user who caused the error
            error_stage: Stage where error occurred (e.g., 'llm_generation', 'retrieval', 'database', etc.)

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            level = self.get_monitoring_level(admin_id)
            if not level:
                return False

            # ERROR level and above gets error messages
            if level not in [MonitoringLevel.ERROR.value, MonitoringLevel.INFO.value, MonitoringLevel.DEBUG.value]:
                return False

            message = f"⚠️ **Error**\n\nUser ID: `{user_id}`\nStage: `{error_stage}`\nError: {self.redact_sensitive_data(error_message)}"
            await self.bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
            logger.debug(f"Sent error notification to admin {admin_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending error notification to admin {admin_id}: {e}")
            return False

    async def send_info_notification(self, admin_id: int, user_id: int, response_text: str) -> bool:
        """Send info notification (bot replied to user) to admin.

        Args:
            admin_id: Telegram user ID of admin
            user_id: Telegram user ID of user who received the response
            response_text: Bot's response text

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            level = self.get_monitoring_level(admin_id)
            if not level:
                return False

            # INFO level and above gets info messages
            if level not in [MonitoringLevel.INFO.value, MonitoringLevel.DEBUG.value]:
                return False

            message = f"ℹ️ **Response Sent**\n\nUser ID: `{user_id}`\nResponse: {self.redact_sensitive_data(response_text[:200])}"
            await self.bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
            logger.debug(f"Sent info notification to admin {admin_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending info notification to admin {admin_id}: {e}")
            return False

    async def send_debug_notification(self, admin_id: int, notification_type: str, data: dict) -> bool:
        """Send debug notification to admin.

        Args:
            admin_id: Telegram user ID of admin
            notification_type: Type of debug notification (incoming_message, tool_call, bot_reply)
            data: Data dictionary with notification details

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            level = self.get_monitoring_level(admin_id)
            if level != MonitoringLevel.DEBUG.value:
                return False

            if notification_type == "incoming_message":
                message = f"🔵 **Incoming Message**\n\nUser ID: `{data.get('user_id')}`\nMessage: {self.redact_sensitive_data(data.get('text', '')[:150])}"
            elif notification_type == "tool_call":
                params = self.redact_sensitive_data(str(data.get('parameters', {})))
                message = f"🔧 **Tool Call**\n\nTool: `{data.get('tool_name')}`\nParameters: {params[:150]}"
            elif notification_type == "bot_reply":
                message = f"💬 **Bot Reply**\n\nUser ID: `{data.get('user_id')}`\nReply: {self.redact_sensitive_data(data.get('text', '')[:150])}"
            else:
                return False

            await self.bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
            logger.debug(f"Sent debug notification ({notification_type}) to admin {admin_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending debug notification to admin {admin_id}: {e}")
            return False

    async def send_admin_help(self, admin_id: int) -> bool:
        """Send help message to admin.

        Args:
            admin_id: Telegram user ID of admin

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            help_text = """🤖 **Admin Commands**

Available commands:

/monitor **debug** - Show all activities (incoming messages, tool calls, bot responses)
/monitor **info** - Show user responses and errors only
/monitor **error** - Show errors only (default level)
/monitor **status** - Check your current monitoring level

**Monitoring Levels Explained:**
• **error** - Only errors
• **info** - Errors + bot responses
• **debug** - Everything (errors, messages, tool calls, responses)
"""
            await self.bot.send_message(chat_id=admin_id, text=help_text, parse_mode="Markdown")
            logger.debug(f"Sent help message to admin {admin_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending help to admin {admin_id}: {e}")
            return False
