"""Message handler for processing Telegram messages."""
import logging
import asyncio
from typing import Optional, List, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from src.config import Config
from src.core.llm import LLMClient, get_system_prompt_with_document_selection
from src.core.db import ConversationDatabase
from src.core.conversation import build_conversation_context
from src.core.features import FeatureRegistry
from src.core.vector_db import RetrievedChunk
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.tools.document_lookup_tool import DocumentLookupTool
from src.handlers.typing_indicator import send_typing_action_periodically
from src.models.message_data import MessageData
from src.exceptions import LLMError
from src.constants import TelegramLimits
from src.utils.logging import (
    debug_log_rag_retrieval,
    debug_log_llm_context,
    debug_log_llm_response,
)

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages and generates responses."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: ConversationDatabase,
        config: Config,
        retrieval_service: Optional[RetrievalService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        feature_registry: Optional[FeatureRegistry] = None,
    ):
        """Initialize message handler.

        Args:
            llm_client: OpenAI LLM client
            db: Conversation database
            config: Bot configuration
            retrieval_service: Optional retrieval service for RAG (if None, no retrieval)
            embedding_service: Optional embedding service for document lookup tool
            feature_registry: Optional feature registry for tracking optional features
        """
        self.llm_client = llm_client
        self.db = db
        self.config = config
        self.retrieval_service = retrieval_service
        self.embedding_service = embedding_service
        self.feature_registry = feature_registry or FeatureRegistry()

        # Initialize document lookup tool if both services available
        self.document_lookup_tool: Optional[DocumentLookupTool] = None
        if (
            self.config.enable_document_selection
            and self.retrieval_service
            and self.embedding_service
        ):
            self.document_lookup_tool = DocumentLookupTool(
                config=config,
                embedding_service=embedding_service,
                retrieval_service=retrieval_service,
            )
            logger.info("Document lookup tool initialized for message handler")

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
            logger.info(
                f"Incoming user message: user_id={message_data.user_id}, "
                f"chat_id={message_data.chat_id}, message_id={message_data.message_id}, "
                f"text_length={len(message_data.text)} chars"
            )
        except Exception as e:
            logger.error(f"Failed to extract message data: {e}", exc_info=True)
            return

        # Load conversation history if replying to previous message
        conversation_context = self._load_conversation_context(message_data)

        # Retrieve relevant documents via RAG if enabled
        # This triggers embedding generation for semantic search
        retrieved_chunks = self._retrieve_documents(message_data.text)
        retrieved_context = self.retrieval_service.format_context(retrieved_chunks) if retrieved_chunks else ""

        # Log the embedding-based retrieval status
        if retrieved_chunks:
            logger.info(
                f"Embeddings used for RAG: {len(retrieved_chunks)} chunks retrieved, "
                f"will augment LLM context with semantic search results"
            )
        else:
            logger.info(
                f"No chunks retrieved via embedding-based search, "
                f"will use only conversation history (if any) for LLM context"
            )

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
        # Check feature availability explicitly
        if not self.feature_registry.is_available("rag_retrieval"):
            state = self.feature_registry.get_feature_state("rag_retrieval")
            if state:
                logger.debug(
                    f"RAG retrieval unavailable: {state.reason}. Status: {state.status.value}"
                )
            else:
                logger.debug("RAG retrieval not registered in feature registry")
            return []

        if not self.retrieval_service or not self.retrieval_service.should_use_retrieval():
            logger.debug("Retrieval service not available or disabled")
            return []

        logger.info(f"Starting document retrieval for query: '{query[:100]}...'")
        try:
            # Retrieve documents (embedding happens internally in retrieve_context)
            retrieved_chunks = self.retrieval_service.retrieve_context(query)

            if retrieved_chunks:
                logger.info(
                    f"Successfully retrieved {len(retrieved_chunks)} chunks for embedding-based search. "
                    f"Retrieval config: top_k={self.config.top_k_retrievals}, "
                    f"threshold={self.config.similarity_threshold}"
                )
                self._log_retrieval_details(retrieved_chunks)

                # Log embedding-specific details for dev/prod debugging
                logger.info(
                    f"Embedding-based retrieval summary: "
                    f"query_length={len(query)} chars, "
                    f"chunks_returned={len(retrieved_chunks)}, "
                    f"similarity_scores={[f'{chunk.score:.4f}' for chunk in retrieved_chunks]}"
                )
            else:
                logger.info(
                    f"No relevant documents found for query (embedding search completed but no results above threshold). "
                    f"Query: '{query[:100]}...', "
                    f"Threshold: {self.config.similarity_threshold}, "
                    f"Top K: {self.config.top_k_retrievals}"
                )

            return retrieved_chunks

        except Exception as e:
            logger.warning(f"Document retrieval failed (continuing without context): {e}", exc_info=True)
            return []

    def _log_retrieval_details(self, retrieved_chunks: List[RetrievedChunk]) -> None:
        """Log details about retrieved chunks for debugging.

        Args:
            retrieved_chunks: List of retrieved document chunks
        """
        debug_log_rag_retrieval(logger, retrieved_chunks)

    def _get_available_documents(self) -> List[str]:
        """Get list of available indexed documents for the LLM.

        Returns:
            List of document names, empty if none available

        Examples:
            >>> docs = handler._get_available_documents()
            >>> len(docs) > 0
            True
        """
        if not self.retrieval_service:
            return []

        try:
            docs = self.retrieval_service.get_indexed_documents()
            logger.debug(f"Retrieved {len(docs)} indexed documents for tool")
            return docs
        except Exception as e:
            logger.error(f"Failed to get available documents: {e}")
            return []

    def _prepare_document_context(self, document_names: List[str]) -> str:
        """Prepare formatted document list for LLM prompt.

        Args:
            document_names: List of indexed document names

        Returns:
            Formatted document list string, empty if no documents

        Examples:
            >>> context = handler._prepare_document_context(["Doc1", "Doc2"])
            >>> "1. Doc1" in context
            True
        """
        if not document_names or not self.retrieval_service:
            return ""

        try:
            return self.retrieval_service.format_document_list(document_names)
        except Exception as e:
            logger.error(f"Failed to format document list: {e}")
            return ""

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
        # Prepare system prompt and tools for LLM
        system_prompt = None
        tools = None

        # If document selection is enabled, use enhanced prompt and tools
        if self.document_lookup_tool:
            available_docs = self._get_available_documents()
            if available_docs:
                logger.info(
                    f"Documents supplied to model for intelligent selection: {len(available_docs)} total. "
                    f"Available documents: {', '.join(available_docs)}"
                )

                # Prepare document list for prompt
                document_context = self._prepare_document_context(available_docs)

                # Use enhanced system prompt with document selection instructions
                system_prompt = get_system_prompt_with_document_selection(
                    document_list=document_context,
                    max_lookups=self.config.max_document_lookups,
                    max_chunks=self.config.lookup_max_chunks,
                    similarity_threshold=self.config.similarity_threshold,
                )

                # Add tool schema for OpenAI function calling
                tools = [self.document_lookup_tool.get_tool_schema()]
                logger.info("Document selection tool wired into LLM request")

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
        debug_log_llm_context(
            logger,
            user_text,
            retrieved_context if retrieved_context else None,
            len(retrieved_chunks),
            len(conversation_context) if conversation_context else 0,
        )

        # Run LLM call in executor to keep event loop non-blocking
        loop = asyncio.get_event_loop()
        bot_response = await loop.run_in_executor(
            None,
            self.llm_client.generate_response,
            user_text,
            augmented_context,
            system_prompt,
            tools,
        )
        debug_log_llm_response(logger, len(bot_response))

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
