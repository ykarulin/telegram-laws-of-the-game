"""Logging utilities for development and production environments.

Separates development-only decorative logs (with emojis) from production logs.
Development logs are only output when logger level is DEBUG.
"""
import logging
from typing import Optional, List


def debug_log_rag_retrieval(
    logger: logging.Logger,
    retrieved_chunks: List,
) -> None:
    """Log details about retrieved chunks for debugging (dev-only).

    Only outputs when logger level is DEBUG. Includes decorative emojis and formatting.

    Args:
        logger: Logger instance to use
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


def debug_log_llm_context(
    logger: logging.Logger,
    user_text: str,
    retrieved_context: Optional[str] = None,
    retrieved_chunks_count: int = 0,
    conversation_context_count: int = 0,
) -> None:
    """Log what context is being sent to LLM (dev-only).

    Only outputs when logger level is DEBUG. Includes decorative emoji.

    Args:
        logger: Logger instance to use
        user_text: The user's input message
        retrieved_context: Formatted document context (if any)
        retrieved_chunks_count: Number of retrieved chunks
        conversation_context_count: Number of conversation context items
    """
    if logger.level > logging.DEBUG:
        return

    logger.debug("📤 SENDING TO LLM:")
    logger.debug(f"User query: {user_text}")
    if retrieved_context:
        logger.debug(f"RAG context: {len(retrieved_context)} chars from {retrieved_chunks_count} chunks")
    if conversation_context_count > 0:
        logger.debug(f"Conversation context: {conversation_context_count} items")


def debug_log_llm_response(
    logger: logging.Logger,
    response_length: int,
) -> None:
    """Log LLM response details (dev-only).

    Only outputs when logger level is DEBUG. Includes decorative emoji.

    Args:
        logger: Logger instance to use
        response_length: Length of the LLM response in characters
    """
    if logger.level > logging.DEBUG:
        return

    logger.debug(f"📥 LLM RESPONSE: {response_length} chars")
