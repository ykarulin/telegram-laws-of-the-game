"""PostgreSQL database layer using SQLAlchemy and asyncpg."""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, select, desc, and_
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

logger = logging.getLogger(__name__)

Base = declarative_base()


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
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"MessageModel(id={self.id}, message_id={self.message_id}, chat_id={self.chat_id}, "
            f"sender={self.sender_type}, reply_to={self.reply_to_message_id})"
        )


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
        """
        logger.debug(f"Attempting to save {sender_type} message {message_id} in chat {chat_id}")
        session: Session = self.SessionLocal()
        try:
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
            session.commit()
            logger.info(
                f"✓ Saved {sender_type} message {message_id} in chat {chat_id} "
                f"(sender={sender_id}, reply_to={reply_to_message_id}, text_len={len(text)})"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving message {message_id}: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def get_message(self, message_id: int, chat_id: int) -> Optional[Message]:
        """Retrieve a single message by ID.

        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID

        Returns:
            Message if found, None otherwise
        """
        session: Session = self.SessionLocal()
        try:
            model = session.query(MessageModel).filter(
                MessageModel.message_id == message_id,
                MessageModel.chat_id == chat_id
            ).first()

            if model:
                return Message.from_model(model)
            return None
        except Exception as e:
            logger.error(f"Error retrieving message: {e}")
            raise
        finally:
            session.close()

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
        """
        chain = []
        session: Session = self.SessionLocal()

        try:
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
        except Exception as e:
            logger.error(f"Error building conversation chain: {e}", exc_info=True)
            raise
        finally:
            session.close()

        logger.debug(f"Conversation chain complete: {len(chain)} messages total")
        return chain

    def get_latest_messages(
        self, chat_id: int, limit: int = 10
    ) -> List[Message]:
        """Get the most recent messages in a chat.

        Args:
            chat_id: Telegram chat ID
            limit: Maximum number of messages to return

        Returns:
            List of messages, ordered by timestamp (newest first)
        """
        session: Session = self.SessionLocal()
        try:
            models = session.query(MessageModel).filter(
                MessageModel.chat_id == chat_id
            ).order_by(
                desc(MessageModel.timestamp)
            ).limit(limit).all()

            return [Message.from_model(m) for m in models]
        except Exception as e:
            logger.error(f"Error retrieving latest messages: {e}")
            raise
        finally:
            session.close()

    def delete_all_for_testing(self) -> None:
        """Delete all messages (for testing only).

        WARNING: This will permanently delete all conversation data.
        """
        session: Session = self.SessionLocal()
        try:
            session.query(MessageModel).delete()
            session.commit()
            logger.warning("All messages deleted (testing only)")
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting messages: {e}")
            raise
        finally:
            session.close()

    def close(self) -> None:
        """Close database connections."""
        self.engine.dispose()
        logger.info("Database connections closed")
