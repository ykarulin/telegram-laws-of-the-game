"""Message handler for processing Telegram messages."""
import logging
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from src.config import Config
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.core.conversation import build_conversation_context
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.handlers.typing_indicator import send_typing_action_periodically
from src.exceptions import LLMError

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages and generates responses."""

    # Telegram message character limit
    TELEGRAM_MAX_MESSAGE_LENGTH = 4096

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
        """Handle incoming message and send response.

        Args:
            update: Telegram update containing the message
            context: Telegram bot context
        """
        if not update.message or not update.message.text:
            logger.warning("Received update without message or text")
            return

        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        user_text = update.message.text
        reply_to_message_id = update.message.reply_to_message.message_id \
            if update.message.reply_to_message else None

        logger.debug(
            f"User {user_id} in chat {chat_id}: {user_text[:50]}... "
            f"(reply_to={reply_to_message_id})"
        )

        # Build conversation context if replying to previous message
        conversation_context: Optional[list] = None
        if reply_to_message_id:
            logger.debug(f"Loading conversation chain for reply_to_message_id={reply_to_message_id}")
            try:
                chain = self.db.get_conversation_chain(reply_to_message_id, chat_id, user_id)
                logger.debug(f"Loaded conversation chain: {len(chain) if chain else 0} messages")
                if chain:
                    conversation_context = build_conversation_context(chain)
                    logger.debug(f"Built conversation context with {len(conversation_context)} context items from {len(chain)} messages")
                else:
                    logger.debug(f"No messages found in conversation chain for reply_to_message_id={reply_to_message_id}")
            except Exception as e:
                logger.error(f"Error loading conversation chain: {e}", exc_info=True)

        # Retrieve relevant documents if retrieval service available and enabled
        retrieved_context = ""
        retrieved_chunks = []
        if self.retrieval_service and self.retrieval_service.should_use_retrieval():
            logger.debug(f"Retrieving documents for query: {user_text[:50]}...")
            try:
                retrieved_chunks = self.retrieval_service.retrieve_context(user_text)
                if retrieved_chunks:
                    retrieved_context = self.retrieval_service.format_context(retrieved_chunks)
                    logger.info(f"Retrieved {len(retrieved_chunks)} chunks for document context")

                    # Log details about each retrieved chunk for debugging
                    logger.debug(f"📚 RAG RETRIEVAL DETAILS:")
                    for idx, chunk in enumerate(retrieved_chunks, 1):
                        logger.debug(f"  [{idx}] Score: {chunk.score:.3f}")
                        logger.debug(f"      Document: {chunk.metadata.get('document_name', 'N/A') if chunk.metadata else 'N/A'}")
                        logger.debug(f"      Type: {chunk.metadata.get('document_type', 'N/A') if chunk.metadata else 'N/A'}")
                        logger.debug(f"      Section: {chunk.metadata.get('section', 'N/A') if chunk.metadata else 'N/A'}")
                        logger.debug(f"      Preview: {chunk.text[:80]}...")

                    logger.debug(f"📝 AUGMENTED PROMPT CONTEXT:")
                    logger.debug(f"Context length: {len(retrieved_context)} chars")
                    logger.debug(f"Context preview:\n{retrieved_context[:300]}...")
                else:
                    logger.debug("No relevant documents found for query")
            except Exception as e:
                logger.warning(f"Document retrieval failed (continuing without context): {e}")
                retrieved_context = ""
                retrieved_chunks = []
        else:
            logger.debug("Retrieval service not available or disabled")

        # Generate response with typing indicator
        typing_task = asyncio.create_task(send_typing_action_periodically(update, interval=5))

        try:
            # Prepare augmented conversation context with retrieved documents
            augmented_context = None
            if conversation_context or retrieved_context:
                augmented_context = []
                if retrieved_context:
                    # Retrieved context is a string, wrap it in a system message
                    augmented_context.append({
                        "role": "system",
                        "content": f"DOCUMENT CONTEXT:\n{retrieved_context}"
                    })
                if conversation_context:
                    augmented_context.extend(conversation_context)
                logger.debug(f"Augmented context with {len(augmented_context)} items")

                # Log what's being sent to LLM
                logger.debug(f"📤 SENDING TO LLM:")
                logger.debug(f"User query: {user_text}")
                if retrieved_context:
                    logger.debug(f"RAG context added: {len(retrieved_context)} chars from {len(retrieved_chunks)} chunks")
                if conversation_context:
                    logger.debug(f"Conversation context: {len(conversation_context)} items")

            # Run LLM call in executor to keep it non-blocking
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
                logger.debug(f"Appended citations to response (now {len(bot_response)} chars)")

            # Send response
            response_message = await update.message.reply_text(bot_response)
            bot_message_id = response_message.message_id

            # Save user message to database
            self.db.save_message(
                message_id=message_id,
                chat_id=chat_id,
                sender_type="user",
                sender_id=str(user_id),
                text=user_text,
                reply_to_message_id=reply_to_message_id,
            )

            # Save bot response message to database
            self.db.save_message(
                message_id=bot_message_id,
                chat_id=chat_id,
                sender_type="bot",
                sender_id=self.config.openai_model,  # Use model name as bot identifier
                text=bot_response,
                reply_to_message_id=message_id,
            )

            logger.info(f"Saved messages: user {message_id}, bot {bot_message_id}")
            logger.debug(f"User message {message_id} in chain with bot response {bot_message_id}")

        except LLMError as e:
            error_msg = str(e)
            logger.error(f"LLM error for user {user_id}: {error_msg}")
            await update.message.reply_text(f"Sorry, I encountered an error: {error_msg}")

        finally:
            # Cancel typing indicator
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    def _append_citations(self, response: str, retrieved_chunks: list) -> str:
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
        if total_length <= self.TELEGRAM_MAX_MESSAGE_LENGTH:
            return response + citations_text

        # If over limit, truncate response to make room for citations
        # Leave buffer for citations and ensure we don't cut in middle of sentence
        available_length = self.TELEGRAM_MAX_MESSAGE_LENGTH - len(citations_text) - 50

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
