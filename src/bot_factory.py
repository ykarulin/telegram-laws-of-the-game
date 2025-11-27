"""Bot application factory for creating and configuring the Telegram bot."""
import logging
from telegram.ext import Application, MessageHandler as TelegramMessageHandler, filters
from src.config import Config
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.handlers.message_handler import MessageHandler
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


def create_application(config: Config) -> Application:
    """Create and configure the Telegram bot application.

    Args:
        config: Bot configuration

    Returns:
        Configured Application instance ready to run
    """
    # Initialize services
    llm_client = LLMClient(
        api_key=config.openai_api_key,
        model=config.openai_model,
        max_tokens=config.openai_max_tokens,
        temperature=config.openai_temperature,
    )
    db = ConversationDatabase(config.database_url)

    # Initialize RAG services (embedding + retrieval)
    try:
        embedding_service = EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model
        )
        db_session = db.SessionLocal()
        retrieval_service = RetrievalService(config, embedding_service, db_session)
        logger.info("RAG services initialized (embedding + retrieval)")
    except Exception as e:
        logger.warning(f"Failed to initialize RAG services: {e}. Bot will run without document retrieval.")
        retrieval_service = None

    message_handler_instance = MessageHandler(llm_client, db, config, retrieval_service)

    # Create application
    application = Application.builder().token(config.telegram_bot_token).build()

    # Register message handler for text messages (excluding commands)
    application.add_handler(
        TelegramMessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler_instance.handle
        )
    )

    logger.info(f"Bot created: {config.environment.value} environment")
    return application
