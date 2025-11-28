"""PostgreSQL database layer using SQLAlchemy and asyncpg."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
from contextlib import contextmanager
from enum import Enum

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, select, desc, and_, JSON
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError

logger = logging.getLogger(__name__)

Base = declarative_base()


def utc_now() -> datetime:
    """Get current time in UTC timezone.

    Returns:
        datetime object with UTC timezone information
    """
    return datetime.now(timezone.utc)


class MessageModel(Base):
    """SQLAlchemy model for messages table (one message per record)."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, nullable=False, index=True)  # Telegram message ID
    chat_id = Column(Integer, nullable=False, index=True)  # Telegram chat ID (supports multi-user/multi-chat)
    sender_type = Column(String(10), nullable=False)  # 'user' or 'bot'
    sender_id = Column(String(255), nullable=False, index=True)  # user_id (if user) or bot model name (if bot)
    text = Column(Text, nullable=False)
    reply_to_message_id = Column(Integer, nullable=True, index=True)  # References any previous message (user or bot)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"MessageModel(id={self.id}, message_id={self.message_id}, chat_id={self.chat_id}, "
            f"sender={self.sender_type}, reply_to={self.reply_to_message_id})"
        )


class DocumentModel(Base):
    """SQLAlchemy model for documents table (tracks uploaded documents and their indexing status)."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    document_type = Column(String(50), nullable=False, index=True)
    version = Column(String(50), nullable=True)
    content = Column(Text, nullable=True)
    source_url = Column(String(512), nullable=True)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    document_metadata = Column(JSON, nullable=True)
    qdrant_status = Column(String(20), nullable=False, default='pending', index=True)
    qdrant_collection_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    relative_path = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"DocumentModel(id={self.id}, name={self.name}, type={self.document_type}, "
            f"status={self.qdrant_status}, version={self.version})"
        )


class MonitoringLevel(Enum):
    """Monitoring levels for admin notifications."""
    ERROR = "error"
    INFO = "info"
    DEBUG = "debug"


class AdminPreferenceModel(Base):
    """SQLAlchemy model for admin preferences table (tracks monitoring level per admin)."""
    __tablename__ = "admin_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)  # Telegram user ID
    monitoring_level = Column(String(10), nullable=False, default='error')  # error, info, debug
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"AdminPreferenceModel(user_id={self.user_id}, monitoring_level={self.monitoring_level})"


@dataclass
class Message:
    """Data class representing a single message."""
    message_id: int
    chat_id: int
    sender_type: str  # 'user' or 'bot'
    sender_id: str  # user_id as string (if user) or bot model name (if bot)
    text: str
    reply_to_message_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    db_id: Optional[int] = None  # Internal database ID

    @classmethod
    def from_model(cls, model: MessageModel) -> "Message":
        """Create Message from SQLAlchemy model."""
        return cls(
            message_id=model.message_id,
            chat_id=model.chat_id,
            sender_type=model.sender_type,
            sender_id=model.sender_id,
            text=model.text,
            reply_to_message_id=model.reply_to_message_id,
            timestamp=model.timestamp,
            db_id=model.id,
        )

    def is_bot_message(self) -> bool:
        """Check if this message was sent by the bot.

        Returns:
            True if sender_type is 'bot', False otherwise
        """
        return self.sender_type == "bot"

    def is_user_message(self) -> bool:
        """Check if this message was sent by a user.

        Returns:
            True if sender_type is 'user', False otherwise
        """
        return self.sender_type == "user"

    def to_dict(self) -> dict:
        """Convert message to dictionary representation.

        Returns:
            Dictionary with all message fields
        """
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "text": self.text,
            "reply_to_message_id": self.reply_to_message_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "db_id": self.db_id,
        }


class ConversationDatabase:
    """PostgreSQL database manager using SQLAlchemy."""

    def __init__(self, database_url: str):
        """Initialize database connection.

        Args:
            database_url: PostgreSQL connection string
                Format: postgresql://user:password@host/database
        """
        self.database_url = database_url
        # Convert standard postgresql:// URLs to use psycopg3 driver explicitly
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

        # Create engine with connection pooling, no async
        # Using psycopg3 (pure Python driver) for Python 3.13 compatibility
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            isolation_level="AUTOCOMMIT",  # Required for table creation
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized: {database_url.split('@')[1] if '@' in database_url else database_url}")

    @contextmanager
    def get_session(self):
        """Context manager for safe session handling with automatic cleanup.

        Yields:
            SQLAlchemy Session object

        Example:
            with db.get_session() as session:
                user = session.query(MessageModel).first()
                session.add(new_message)
        """
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def __enter__(self):
        """Support for 'with' statement on database object."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting 'with' block."""
        self.close()

    def _validate_message_id(self, message_id: int) -> None:
        """Validate message_id parameter.

        Args:
            message_id: Telegram message ID to validate

        Raises:
            ValueError: If message_id is invalid (must be > 0)
        """
        if not isinstance(message_id, int):
            raise ValueError(f"message_id must be an integer, got {type(message_id).__name__}")
        if message_id <= 0:
            raise ValueError(f"message_id must be positive, got {message_id}")

    def _validate_chat_id(self, chat_id: int) -> None:
        """Validate chat_id parameter.

        Args:
            chat_id: Telegram chat ID to validate

        Raises:
            ValueError: If chat_id is invalid (must be non-zero)
        """
        if not isinstance(chat_id, int):
            raise ValueError(f"chat_id must be an integer, got {type(chat_id).__name__}")
        if chat_id == 0:
            raise ValueError("chat_id cannot be zero")

    def _validate_text(self, text: str) -> None:
        """Validate text parameter.

        Args:
            text: Message text to validate

        Raises:
            ValueError: If text is invalid (must be non-empty string)
        """
        if not isinstance(text, str):
            raise ValueError(f"text must be a string, got {type(text).__name__}")
        if not text or not text.strip():
            raise ValueError("text cannot be empty or whitespace-only")

    def save_message(
        self,
        message_id: int,
        chat_id: int,
        sender_type: str,
        sender_id: int,
        text: str,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        """Save a single message to the database.

        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            sender_type: 'user' or 'bot'
            sender_id: User ID (if user) or bot ID (if bot)
            text: Message text
            reply_to_message_id: Telegram message ID this message replies to

        Raises:
            ValueError: If any parameter fails validation
        """
        # Validate inputs
        self._validate_message_id(message_id)
        self._validate_chat_id(chat_id)
        self._validate_text(text)

        logger.debug(f"Attempting to save {sender_type} message {message_id} in chat {chat_id}")
        try:
            with self.get_session() as session:
                # Check if message already exists (by message_id + chat_id)
                existing = session.query(MessageModel).filter(
                    MessageModel.message_id == message_id,
                    MessageModel.chat_id == chat_id
                ).first()

                if existing:
                    logger.warning(f"Message {message_id} in chat {chat_id} already exists in database")
                    return

                # Create and save new message
                message = MessageModel(
                    message_id=message_id,
                    chat_id=chat_id,
                    sender_type=sender_type,
                    sender_id=sender_id,
                    text=text,
                    reply_to_message_id=reply_to_message_id,
                )
                session.add(message)
                logger.info(
                    f"Saved {sender_type} message {message_id} in chat {chat_id} "
                    f"(sender={sender_id}, reply_to={reply_to_message_id}, text_len={len(text)})"
                )
        except IntegrityError as e:
            logger.warning(f"Integrity constraint violation saving message {message_id}: {e}")
            # Message might already exist or constraint violation - this is often benign
        except OperationalError as e:
            logger.error(f"Database operational error saving message {message_id}: {e}", exc_info=True)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error saving message {message_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving message {message_id}: {e}", exc_info=True)
            raise

    def get_message(self, message_id: int, chat_id: int) -> Optional[Message]:
        """Retrieve a single message by ID.

        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID

        Returns:
            Message if found, None otherwise

        Raises:
            ValueError: If any parameter fails validation
        """
        # Validate inputs
        self._validate_message_id(message_id)
        self._validate_chat_id(chat_id)

        try:
            with self.get_session() as session:
                model = session.query(MessageModel).filter(
                    MessageModel.message_id == message_id,
                    MessageModel.chat_id == chat_id
                ).first()

                if model:
                    return Message.from_model(model)
                return None
        except OperationalError as e:
            logger.error(f"Database operational error retrieving message {message_id}: {e}", exc_info=True)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving message {message_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving message {message_id}: {e}", exc_info=True)
            raise

    def get_conversation_chain(self, message_id: int, chat_id: int, user_id: int) -> List[Message]:
        """Build conversation chain by tracing reply_to_message_id backwards.

        Starts from a given message and traces back through the reply chain,
        including both user and bot messages.

        Args:
            message_id: Starting message ID (typically the message being replied to)
            chat_id: Telegram chat ID (to disambiguate across chats)
            user_id: User ID (for context - helps with filtering)

        Returns:
            List of messages in conversation, ordered chronologically

        Raises:
            ValueError: If any parameter fails validation
        """
        # Validate inputs
        self._validate_message_id(message_id)
        self._validate_chat_id(chat_id)
        if not isinstance(user_id, int):
            raise ValueError(f"user_id must be an integer, got {type(user_id).__name__}")

        try:
            with self.get_session() as session:
                chain = []
                logger.debug(f"Starting conversation chain trace from message_id={message_id} in chat {chat_id}")

                current_id = message_id
                iteration = 0

                # Trace backwards through the conversation chain
                while current_id is not None:
                    iteration += 1
                    logger.debug(f"Chain iteration {iteration}: fetching message_id={current_id}")

                    message_model = session.query(MessageModel).filter(
                        MessageModel.message_id == current_id,
                        MessageModel.chat_id == chat_id
                    ).first()

                    if not message_model:
                        logger.debug(f"Message {current_id} in chat {chat_id} not found in database, stopping chain")
                        break

                    # Stop chain if we've crossed into a different user's messages
                    if message_model.sender_type == 'user' and message_model.sender_id != str(user_id):
                        logger.debug(f"Message {current_id} belongs to different user, stopping chain")
                        break

                    message = Message.from_model(message_model)
                    chain.insert(0, message)
                    logger.debug(f"Added {message_model.sender_type} message {current_id} to chain (reply_to={message.reply_to_message_id})")
                    current_id = message.reply_to_message_id

                logger.debug(f"Conversation chain complete: {len(chain)} messages total")
                return chain
        except OperationalError as e:
            logger.error(f"Database operational error building conversation chain: {e}", exc_info=True)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error building conversation chain: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error building conversation chain: {e}", exc_info=True)
            raise

    def get_latest_messages(
        self, chat_id: int, limit: int = 10
    ) -> List[Message]:
        """Get the most recent messages in a chat.

        Args:
            chat_id: Telegram chat ID
            limit: Maximum number of messages to return

        Returns:
            List of messages, ordered by timestamp (newest first)

        Raises:
            ValueError: If any parameter fails validation
        """
        # Validate inputs
        self._validate_chat_id(chat_id)
        if not isinstance(limit, int) or limit < 1:
            raise ValueError(f"limit must be a positive integer, got {limit}")

        try:
            with self.get_session() as session:
                models = session.query(MessageModel).filter(
                    MessageModel.chat_id == chat_id
                ).order_by(
                    desc(MessageModel.timestamp)
                ).limit(limit).all()

                return [Message.from_model(m) for m in models]
        except OperationalError as e:
            logger.error(f"Database operational error retrieving latest messages: {e}", exc_info=True)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving latest messages: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving latest messages: {e}", exc_info=True)
            raise

    def delete_all_for_testing(self) -> None:
        """Delete all messages (for testing only).

        WARNING: This will permanently delete all conversation data.
        """
        try:
            with self.get_session() as session:
                session.query(MessageModel).delete()
                logger.warning("All messages deleted (testing only)")
        except OperationalError as e:
            logger.error(f"Database operational error deleting messages: {e}", exc_info=True)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting messages: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting messages: {e}", exc_info=True)
            raise

    def get_or_create_admin_preference(self, user_id: int, default_level: str = "error") -> AdminPreferenceModel:
        """Get or create admin preference for a user.

        Args:
            user_id: Telegram user ID
            default_level: Default monitoring level if creating new preference

        Returns:
            AdminPreferenceModel instance
        """
        try:
            with self.get_session() as session:
                pref = session.query(AdminPreferenceModel).filter(
                    AdminPreferenceModel.user_id == user_id
                ).first()

                if pref:
                    return pref

                # Create new preference with default level
                new_pref = AdminPreferenceModel(
                    user_id=user_id,
                    monitoring_level=default_level
                )
                session.add(new_pref)
                logger.info(f"Created admin preference for user {user_id} with level {default_level}")
                return new_pref
        except SQLAlchemyError as e:
            logger.error(f"Database error getting or creating admin preference for {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting or creating admin preference for {user_id}: {e}", exc_info=True)
            raise

    def update_admin_monitoring_level(self, user_id: int, level: str) -> AdminPreferenceModel:
        """Update admin monitoring level.

        Args:
            user_id: Telegram user ID
            level: New monitoring level (error, info, debug)

        Returns:
            Updated AdminPreferenceModel instance
        """
        if level not in [l.value for l in MonitoringLevel]:
            raise ValueError(f"Invalid monitoring level: {level}. Must be one of: {[l.value for l in MonitoringLevel]}")

        try:
            with self.get_session() as session:
                pref = session.query(AdminPreferenceModel).filter(
                    AdminPreferenceModel.user_id == user_id
                ).first()

                if not pref:
                    raise ValueError(f"No admin preference found for user {user_id}")

                pref.monitoring_level = level
                logger.info(f"Updated monitoring level for admin {user_id} to {level}")
                return pref
        except SQLAlchemyError as e:
            logger.error(f"Database error updating admin monitoring level for {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating admin monitoring level for {user_id}: {e}", exc_info=True)
            raise

    def get_admin_monitoring_level(self, user_id: int) -> Optional[str]:
        """Get admin monitoring level.

        Args:
            user_id: Telegram user ID

        Returns:
            Monitoring level (error, info, debug) or None if not set
        """
        try:
            with self.get_session() as session:
                pref = session.query(AdminPreferenceModel).filter(
                    AdminPreferenceModel.user_id == user_id
                ).first()

                if pref:
                    return pref.monitoring_level
                return None
        except SQLAlchemyError as e:
            logger.error(f"Database error getting admin monitoring level for {user_id}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting admin monitoring level for {user_id}: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """Close database connections."""
        self.engine.dispose()
        logger.info("Database connections closed")
