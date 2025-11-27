#!/usr/bin/env python3
"""Football Rules Expert Bot - Main entry point."""
import logging
import sys
from src.config import load_config, ConfigError
from src.bot_factory import create_application
from src.exceptions import BotError

# Setup logging first (before anything else)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level='INFO'
)
logger = logging.getLogger(__name__)

# Suppress noisy debug logs from external libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.WARNING)
logging.getLogger("pdfminer.psparser").setLevel(logging.WARNING)
logging.getLogger("pdfminer.pdfpage").setLevel(logging.WARNING)
logging.getLogger("pdfminer.cmapdb").setLevel(logging.WARNING)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.WARNING)
logging.getLogger("pdfminer.pdfdocument").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def main() -> None:
    """Start the bot."""
    try:
        # Load configuration
        config = load_config()
        # Set log level on root logger so all loggers respect it
        logging.getLogger().setLevel(config.log_level)
        logger.setLevel(config.log_level)

        logger.info(f"Starting bot in {config.environment.value} environment...")
        logger.debug(f"Debug mode: {config.debug}")
        logger.info(f"Using model: {config.openai_model}")

        # Test database connectivity
        from src.core.db import ConversationDatabase
        logger.info("Testing database connectivity...")
        db = ConversationDatabase(config.database_url)
        logger.info("✓ Database connection successful")

        # Create and run application
        application = create_application(config)

        # Choose between webhook and polling based on configuration
        if config.telegram_webhook_url:
            logger.info(f"Starting bot with webhook at {config.telegram_webhook_url}:{config.telegram_webhook_port}...")
            application.run_webhook(
                listen="0.0.0.0",
                port=config.telegram_webhook_port,
                url_path=config.telegram_webhook_url,
                webhook_url=f"{config.telegram_webhook_url}",
                secret_token=config.telegram_webhook_secret_token,
            )
        else:
            logger.info("Starting bot with polling...")
            application.run_polling()

    except ConfigError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)
    except BotError as e:
        logger.error(f"Bot Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
