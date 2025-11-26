"""Message handler for processing Telegram messages."""
import logging
import asyncio
from typing import Optional, List, Dict
from telegram import Update
from telegram.ext import ContextTypes
from src.config import Config
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.core.conversation import build_conversation_context
from src.core.vector_db import RetrievedChunk
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.handlers.typing_indicator import send_typing_action_periodically
from src.models.message_data import MessageData
from src.exceptions import LLMError
from src.constants import TelegramLimits

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages and generates responses."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: ConversationDatabase,
        config: Config,
        retrieval_service: Optional[RetrievalService] = None
    ):
        """Initialize message handler.

        Args:
            llm_client: OpenAI LLM client
            db: Conversation database
            config: Bot configuration
            retrieval_service: Optional retrieval service for RAG (if None, no retrieval)
        """
        self.llm_client = llm_client
        self.db = db
        self.config = config
        self.retrieval_service = retrieval_service

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming message and orchestrate response generation.

        Processing Flow:
        ┌─────────────────────────────┐
        │   Extract message data      │
        └──────────────┬──────────────┘
                       │
                ┌──────┴──────┐
                │             │
                ↓             ↓
        [Load context]  [Retrieve docs]
        from DB         from Qdrant
                │             │
                └──────┬──────┘
                       │
                       ↓
        ┌─────────────────────────────┐
        │ Generate response via LLM   │
        │ (with typing indicator)     │
        └──────────────┬──────────────┘
                       │
                       ↓
        ┌─────────────────────────────┐
        │ Append citations            │
        │ (if docs retrieved)         │
        └──────────────┬──────────────┘
                       │
                       ↓
        ┌─────────────────────────────┐
        │ Send + persist to database  │
        └─────────────────────────────┘

        Args:
            update: Telegram update containing the message
            context: Telegram bot context
        """
        if not update.message or not update.message.text:
            logger.warning("Received update without message or text")
            return

        # Extract and validate message data
        try:
            message_data = MessageData.from_telegram_message(update.message)
            logger.debug(f"Processing message: {message_data}")
        except Exception as e:
            logger.error(f"Failed to extract message data: {e}", exc_info=True)
            return

        # Load conversation history if replying to previous message
        conversation_context = self._load_conversation_context(message_data)

        # Retrieve relevant documents via RAG if enabled
        retrieved_chunks = self._retrieve_documents(message_data.text)
        retrieved_context = self.retrieval_service.format_context(retrieved_chunks) if retrieved_chunks else ""

        # Generate response with typing indicator
        typing_task = asyncio.create_task(send_typing_action_periodically(update, interval=5))

        try:
            bot_response = await self._generate_response(
                message_data.text,
                conversation_context,
                retrieved_context,
                retrieved_chunks
            )

            # Send and persist messages
            await self._send_and_persist(update, message_data, bot_response, retrieved_chunks)

        except LLMError as e:
            error_msg = str(e)
            logger.error(f"LLM error for user {message_data.user_id}: {error_msg}")
            await update.message.reply_text(f"Sorry, I encountered an error: {error_msg}")

        finally:
            # Cancel typing indicator
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    def _load_conversation_context(self, message_data: MessageData) -> Optional[List[Dict[str, str]]]:
        """Load conversation chain from database if message replies to previous message.

        Args:
            message_data: Extracted message data

        Returns:
            Conversation context list or None if not replying or no chain found
        """
        if not message_data.reply_to_message_id:
            return None

        logger.debug(f"Loading conversation chain for reply_to={message_data.reply_to_message_id}")
        try:
            chain = self.db.get_conversation_chain(
                message_data.reply_to_message_id,
                message_data.chat_id,
                message_data.user_id
            )
            if not chain:
                logger.debug(f"No messages found in conversation chain")
                return None

            conversation_context = build_conversation_context(chain)
            logger.debug(
                f"Built conversation context with {len(conversation_context)} items "
                f"from {len(chain)} messages"
            )
            return conversation_context

        except Exception as e:
            logger.error(f"Error loading conversation chain: {e}", exc_info=True)
            return None

    def _retrieve_documents(self, query: str) -> List[RetrievedChunk]:
        """Retrieve relevant document chunks via semantic search.

        Args:
            query: User query text to search for in documents

        Returns:
            List of retrieved chunks (empty if retrieval disabled or fails)
        """
        if not self.retrieval_service or not self.retrieval_service.should_use_retrieval():
            logger.debug("Retrieval service not available or disabled")
            return []

        logger.debug(f"Retrieving documents for query: {query[:50]}...")
        try:
            retrieved_chunks = self.retrieval_service.retrieve_context(query)

            if retrieved_chunks:
                logger.info(f"Retrieved {len(retrieved_chunks)} chunks")
                self._log_retrieval_details(retrieved_chunks)
            else:
                logger.debug("No relevant documents found for query")

            return retrieved_chunks

        except Exception as e:
            logger.warning(f"Document retrieval failed (continuing without context): {e}")
            return []

    def _log_retrieval_details(self, retrieved_chunks: List[RetrievedChunk]) -> None:
        """Log details about retrieved chunks for debugging.

        Args:
            retrieved_chunks: List of retrieved document chunks
        """
        if logger.level > logging.DEBUG:
            return

        logger.debug("📚 RAG RETRIEVAL DETAILS:")
        for idx, chunk in enumerate(retrieved_chunks, 1):
            logger.debug(f"  [{idx}] Score: {chunk.score:.3f}")
            if chunk.metadata:
                logger.debug(f"      Document: {chunk.metadata.get('document_name', 'N/A')}")
                logger.debug(f"      Type: {chunk.metadata.get('document_type', 'N/A')}")
                logger.debug(f"      Section: {chunk.metadata.get('section', 'N/A')}")
            logger.debug(f"      Preview: {chunk.text[:80]}...")

    async def _generate_response(
        self,
        user_text: str,
        conversation_context: Optional[List[Dict[str, str]]],
        retrieved_context: str,
        retrieved_chunks: List[RetrievedChunk]
    ) -> str:
        """Generate LLM response with augmented context.

        Args:
            user_text: The user's input message
            conversation_context: Previous messages in conversation chain
            retrieved_context: Formatted document context from retrieval
            retrieved_chunks: Raw retrieved chunks for citation

        Returns:
            Generated response text (possibly with citations appended)
        """
        # Prepare augmented context combining conversation history and documents
        augmented_context: Optional[List[Dict[str, str]]] = None
        if conversation_context or retrieved_context:
            augmented_context = []
            if retrieved_context:
                augmented_context.append({
                    "role": "system",
                    "content": f"DOCUMENT CONTEXT:\n{retrieved_context}"
                })
            if conversation_context:
                augmented_context.extend(conversation_context)
            logger.debug(f"Augmented context with {len(augmented_context)} items")

        # Log what's being sent to LLM
        if logger.level <= logging.DEBUG:
            logger.debug("📤 SENDING TO LLM:")
            logger.debug(f"User query: {user_text}")
            if retrieved_context:
                logger.debug(f"RAG context: {len(retrieved_context)} chars from {len(retrieved_chunks)} chunks")
            if conversation_context:
                logger.debug(f"Conversation context: {len(conversation_context)} items")

        # Run LLM call in executor to keep event loop non-blocking
        loop = asyncio.get_event_loop()
        bot_response = await loop.run_in_executor(
            None,
            self.llm_client.generate_response,
            user_text,
            augmented_context
        )
        logger.debug(f"📥 LLM RESPONSE: {len(bot_response)} chars")

        # Append source citations if documents were retrieved
        if retrieved_chunks:
            bot_response = self._append_citations(bot_response, retrieved_chunks)
            logger.debug(f"Appended citations (now {len(bot_response)} chars)")

        return bot_response

    async def _send_and_persist(
        self,
        update: Update,
        message_data: MessageData,
        bot_response: str,
        retrieved_chunks: List[RetrievedChunk]
    ) -> None:
        """Send response via Telegram and persist both messages to database.

        Args:
            update: Telegram update object
            message_data: Extracted message data
            bot_response: Generated response text
            retrieved_chunks: Retrieved chunks (for potential further processing)
        """
        # Send response via Telegram
        response_message = await update.message.reply_text(bot_response)
        bot_message_id = response_message.message_id

        # Persist user message
        self.db.save_message(
            message_id=message_data.message_id,
            chat_id=message_data.chat_id,
            sender_type="user",
            sender_id=str(message_data.user_id),
            text=message_data.text,
            reply_to_message_id=message_data.reply_to_message_id,
        )

        # Persist bot response
        self.db.save_message(
            message_id=bot_message_id,
            chat_id=message_data.chat_id,
            sender_type="bot",
            sender_id=self.config.openai_model,
            text=bot_response,
            reply_to_message_id=message_data.message_id,
        )

        logger.info(
            f"Sent response to user {message_data.user_id}: "
            f"user_msg={message_data.message_id}, bot_msg={bot_message_id}"
        )

    def _append_citations(self, response: str, retrieved_chunks: List[RetrievedChunk]) -> str:
        """
        Append unique source citations to bot response.

        Extracts citations from retrieved chunks and appends them to the response,
        while respecting Telegram's 4096 character message limit.

        Args:
            response: The LLM-generated response text
            retrieved_chunks: List of RetrievedChunk objects used in context

        Returns:
            Response with citations appended, truncated if necessary to fit limit
        """
        if not retrieved_chunks or not self.retrieval_service:
            return response

        # Build unique citations from retrieved chunks
        seen_citations = set()
        citations = []

        for chunk in retrieved_chunks:
            citation = self.retrieval_service.format_inline_citation(chunk)
            # Avoid duplicate citations from same document/section
            if citation not in seen_citations:
                seen_citations.add(citation)
                citations.append(citation)

        if not citations:
            return response

        # Format citations section
        citations_text = "\n\n" + "\n".join(citations)
        total_length = len(response) + len(citations_text)

        # If within limit, append all citations
        if total_length <= TelegramLimits.MAX_MESSAGE_LENGTH:
            return response + citations_text

        # If over limit, truncate response to make room for citations
        # Leave buffer for citations and ensure we don't cut in middle of sentence
        available_length = TelegramLimits.MAX_MESSAGE_LENGTH - len(citations_text) - TelegramLimits.MESSAGE_LENGTH_BUFFER

        if available_length < 100:
            # Even with truncation, can't fit citations reasonably
            logger.warning(
                f"Response too long ({total_length} chars) to append citations, "
                f"sending without citations"
            )
            return response

        # Truncate response at word boundary
        truncated = response[:available_length]
        # Find last period, newline, or word boundary
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        last_boundary = max(last_period, last_newline)

        if last_boundary > available_length - 100:
            truncated = truncated[:last_boundary + 1]
        else:
            # Fall back to last space
            last_space = truncated.rfind(" ")
            if last_space > 0:
                truncated = truncated[:last_space]

        logger.info(
            f"Response truncated from {len(response)} to {len(truncated)} chars "
            f"to fit citations within Telegram limit"
        )

        return truncated + citations_text
