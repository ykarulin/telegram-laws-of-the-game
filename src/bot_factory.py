"""Bot application factory for creating and configuring the Telegram bot."""
import logging
from telegram.ext import Application, MessageHandler as TelegramMessageHandler, CommandHandler, filters
from src.config import Config
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.core.features import FeatureRegistry, FeatureStatus
from src.handlers.message_handler import MessageHandler
from src.handlers.admin_handler import AdminHandler
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.services.admin_service import AdminService

logger = logging.getLogger(__name__)


def create_application(config: Config) -> Application:
    """Create and configure the Telegram bot application.

    Args:
        config: Bot configuration

    Returns:
        Configured Application instance ready to run
    """
    # Initialize feature registry
    feature_registry = FeatureRegistry()

    # Initialize services
    llm_client = LLMClient(
        api_key=config.openai_api_key,
        model=config.openai_model,
        max_tokens=config.openai_max_tokens,
        temperature=config.openai_temperature,
    )
    db = ConversationDatabase(config.database_url)

    # Initialize RAG services (embedding + retrieval)
    retrieval_service = None
    embedding_service = None

    try:
        embedding_service = EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model
        )
        db_session = db.SessionLocal()
        retrieval_service = RetrievalService(
            config, embedding_service, db_session, feature_registry
        )

        # Verify Qdrant is actually accessible
        if retrieval_service.should_use_retrieval():
            feature_registry.register_feature(
                "rag_retrieval",
                FeatureStatus.ENABLED,
                reason="Qdrant and embedding service initialized successfully",
            )
            logger.info("RAG services initialized (embedding + retrieval)")
        else:
            feature_registry.register_feature(
                "rag_retrieval",
                FeatureStatus.UNAVAILABLE,
                reason="Qdrant health check failed or collection missing",
            )
            logger.warning("RAG services initialized but Qdrant unavailable")
            retrieval_service = None
            embedding_service = None
    except Exception as e:
        feature_registry.register_feature(
            "rag_retrieval",
            FeatureStatus.UNAVAILABLE,
            reason=f"Initialization failed: {str(e)}",
        )
        logger.warning(f"Failed to initialize RAG services: {e}. Bot will run without document retrieval.")
        retrieval_service = None
        embedding_service = None

    # Track document selection tool availability
    if config.enable_document_selection:
        if retrieval_service and embedding_service:
            feature_registry.register_feature(
                "document_selection",
                FeatureStatus.ENABLED,
                reason="Tool enabled via configuration with all dependencies available",
            )
        else:
            feature_registry.register_feature(
                "document_selection",
                FeatureStatus.UNAVAILABLE,
                reason="Missing dependencies (retrieval_service or embedding_service)",
            )
    else:
        feature_registry.register_feature(
            "document_selection",
            FeatureStatus.DISABLED,
            reason="Disabled via configuration (enable_document_selection=False)",
        )

    # Log feature availability summary
    feature_registry.log_summary()

    # Create application first to get bot instance
    application = Application.builder().token(config.telegram_bot_token).build()

    # Initialize AdminService
    admin_service = AdminService(db, application.bot, config.admin_user_ids)
    admin_handler_instance = AdminHandler(admin_service)

    message_handler_instance = MessageHandler(
        llm_client, db, config, retrieval_service, embedding_service, feature_registry, admin_service
    )

    # Register admin command handlers (for DMs only)
    application.add_handler(CommandHandler("monitor", admin_handler_instance.handle_monitor_command))
    application.add_handler(CommandHandler("help", admin_handler_instance.handle_help_command))

    # Register message handler for text messages (excluding commands)
    application.add_handler(
        TelegramMessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler_instance.handle
        )
    )

    # Store admin_service in application context for use by message handler
    application.admin_service = admin_service

    logger.info(f"Bot created: {config.environment.value} environment")
    return application
