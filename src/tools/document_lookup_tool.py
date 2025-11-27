"""
Document lookup tool for LLM-based document selection.

This module provides a tool that allows the LLM to select and search specific documents
from the knowledge base. The tool is designed for use with OpenAI's function calling API.

The LLM can use this tool to:
- Select relevant documents to search
- Specify custom search queries
- Control retrieval parameters (top_k, similarity threshold)
- Make multiple lookup calls to different documents

Example:
    >>> tool = DocumentLookupTool(config, embedding_service, retrieval_service)
    >>> schema = tool.get_tool_schema()
    >>> results = tool.execute_lookup(
    ...     document_names=["Laws of Game 2024-25"],
    ...     query="offside rule",
    ...     top_k=3,
    ...     min_similarity=0.7
    ... )
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.config import Config
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    documents_searched: List[str]
    query: str
    results: List[RetrievedChunk]
    error_message: Optional[str] = None


class DocumentLookupTool:
    """Tool for LLM-based document lookup and selection."""

    def __init__(
        self,
        config: Config,
        embedding_service: EmbeddingService,
        retrieval_service: RetrievalService,
        available_documents: Optional[List[str]] = None
    ):
        """
        Initialize the document lookup tool.

        Args:
            config: Configuration object with tool settings
            embedding_service: Service for generating query embeddings
            retrieval_service: Service for retrieving relevant chunks
            available_documents: List of available document names (optional, for validation)

        Examples:
            >>> tool = DocumentLookupTool(config, embedding_service, retrieval_service)
        """
        self.config = config
        self.embedding_service = embedding_service
        self.retrieval_service = retrieval_service
        self.available_documents = available_documents or []

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Get the OpenAI function calling schema for this tool.

        Returns:
            Dictionary defining the tool schema for function calling API

        Examples:
            >>> schema = tool.get_tool_schema()
            >>> schema['name']
            'lookup_documents'
            >>> 'document_names' in schema['parameters']['properties']
            True
        """
        return {
            "type": "function",
            "function": {
                "name": "lookup_documents",
                "description": (
                    "Search relevant document sections for information about football rules, "
                    "laws of the game, and related regulations. Select the documents you want to "
                    "search based on your question, then specify what you're looking for."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Names of specific documents to search. These should match names "
                                "from the available documents list. Examples: "
                                "'Laws of Game 2024-25', 'VAR Guidelines 2024', 'FAQ'"
                            ),
                            "minItems": 1,
                        },
                        "query": {
                            "type": "string",
                            "description": (
                                "Your search query. Be specific about what information you're looking for "
                                "in the selected documents. Examples: 'offside rule', 'handball definition', "
                                "'VAR review procedures'"
                            ),
                            "minLength": 1,
                        },
                        "top_k": {
                            "type": "integer",
                            "description": (
                                f"Number of relevant sections to return from the search. "
                                f"Default: 3, Maximum: {self.config.lookup_max_chunks}"
                            ),
                            "minimum": 1,
                            "maximum": self.config.lookup_max_chunks,
                            "default": 3,
                        },
                        "min_similarity": {
                            "type": "number",
                            "description": (
                                f"Minimum relevance score (0.0-1.0) for returned results. "
                                f"Higher values = stricter filtering. Default: {self.config.similarity_threshold}"
                            ),
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": self.config.similarity_threshold,
                        },
                    },
                    "required": ["document_names", "query"],
                },
            },
        }

    def execute_lookup(
        self,
        document_names: List[str],
        query: str,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
    ) -> ToolResult:
        """
        Execute a document lookup operation.

        Searches the specified documents for relevant chunks matching the query.
        Validates all parameters and handles errors gracefully.

        Args:
            document_names: List of document names to search
            query: Search query describing what to find
            top_k: Number of results to return (1 to lookup_max_chunks)
            min_similarity: Minimum similarity threshold (0.0 to 1.0)

        Returns:
            ToolResult object containing:
            - success: Whether the lookup succeeded
            - documents_searched: List of documents actually searched
            - query: The search query used
            - results: List of RetrievedChunk objects
            - error_message: Error description if unsuccessful

        Examples:
            >>> result = tool.execute_lookup(
            ...     document_names=["Laws of Game 2024-25"],
            ...     query="What is offside?",
            ...     top_k=3
            ... )
            >>> if result.success:
            ...     print(f"Found {len(result.results)} relevant sections")
            >>> else:
            ...     print(f"Error: {result.error_message}")
        """
        logger.info(
            f"Executing document lookup: documents={document_names}, query='{query[:100]}...', "
            f"top_k={top_k}, min_similarity={min_similarity}"
        )

        # Use config defaults if not specified
        top_k = top_k or 3
        min_similarity = min_similarity or self.config.similarity_threshold

        # Validate parameters
        validation_error = self._validate_parameters(
            document_names, query, top_k, min_similarity
        )
        if validation_error:
            logger.warning(f"Parameter validation failed: {validation_error}")
            return ToolResult(
                success=False,
                documents_searched=document_names,
                query=query,
                results=[],
                error_message=validation_error,
            )

        try:
            # Retrieve chunks from the specified documents
            results = self.retrieval_service.retrieve_from_documents(
                query=query,
                document_names=document_names,
                top_k=top_k,
                threshold=min_similarity,
            )

            # Log the tool call details for monitoring
            logger.info(
                f"Model tool call - lookup_documents: "
                f"documents=[{', '.join(document_names)}], "
                f"query='{query}', "
                f"top_k={top_k}, "
                f"min_similarity={min_similarity}"
            )

            # Log chunk scores if available
            if results:
                try:
                    chunk_scores = [f'{chunk.score:.4f}' for chunk in results]
                    logger.info(
                        f"Document lookup successful: retrieved {len(results)} chunks from {len(document_names)} documents. "
                        f"Chunk scores: {chunk_scores}"
                    )
                except (AttributeError, TypeError):
                    # Fallback if chunks don't have score attribute
                    logger.info(
                        f"Document lookup successful: retrieved {len(results)} chunks from {len(document_names)} documents"
                    )
            else:
                logger.info(
                    f"Document lookup completed: no chunks retrieved from {len(document_names)} documents"
                )

            return ToolResult(
                success=True,
                documents_searched=document_names,
                query=query,
                results=results,
                error_message=None,
            )

        except Exception as e:
            error_msg = f"Lookup failed: {str(e)}"
            logger.error(
                f"Model tool call failed - lookup_documents: "
                f"documents=[{', '.join(document_names)}], "
                f"query='{query}', "
                f"error={error_msg}",
                exc_info=True
            )
            return ToolResult(
                success=False,
                documents_searched=document_names,
                query=query,
                results=[],
                error_message=error_msg,
            )

    def _validate_parameters(
        self,
        document_names: List[str],
        query: str,
        top_k: int,
        min_similarity: float,
    ) -> Optional[str]:
        """
        Validate tool parameters.

        Args:
            document_names: List of document names
            query: Search query
            top_k: Number of results
            min_similarity: Minimum similarity threshold

        Returns:
            Error message if validation fails, None if successful

        Examples:
            >>> error = tool._validate_parameters([], "query", 3, 0.7)
            >>> error
            'document_names cannot be empty'
        """
        # Validate document_names
        if not document_names:
            return "document_names cannot be empty"

        if not isinstance(document_names, list):
            return "document_names must be a list"

        if len(document_names) > 10:
            return "document_names cannot contain more than 10 documents"

        # Validate query
        if not query or not query.strip():
            return "query cannot be empty"

        if len(query) > 500:
            return "query is too long (max 500 characters)"

        # Validate top_k
        if not isinstance(top_k, int):
            return "top_k must be an integer"

        if top_k < 1:
            return "top_k must be at least 1"

        if top_k > self.config.lookup_max_chunks:
            return f"top_k cannot exceed {self.config.lookup_max_chunks}"

        # Validate min_similarity
        if not isinstance(min_similarity, (int, float)):
            return "min_similarity must be a number"

        if min_similarity < 0.0 or min_similarity > 1.0:
            return "min_similarity must be between 0.0 and 1.0"

        return None

    def format_result_for_llm(self, result: ToolResult) -> str:
        """
        Format tool result for inclusion in LLM context.

        Args:
            result: ToolResult from execute_lookup

        Returns:
            Formatted string for LLM consumption

        Examples:
            >>> result = tool.execute_lookup(...)
            >>> formatted = tool.format_result_for_llm(result)
            >>> len(formatted) > 0
            True
        """
        if not result.success:
            return f"Error during document lookup: {result.error_message}"

        if not result.results:
            return (
                f"No relevant sections found in {', '.join(result.documents_searched)} "
                f"for query: '{result.query}'"
            )

        lines = []
        lines.append(f"Found {len(result.results)} relevant sections in {', '.join(result.documents_searched)}:\n")

        for i, chunk in enumerate(result.results, 1):
            lines.append(f"Section {i}:")
            if chunk.metadata:
                meta = chunk.metadata
                if meta.get("section"):
                    lines.append(f"  Section: {meta.get('section')}")
                if meta.get("subsection"):
                    lines.append(f"  Subsection: {meta.get('subsection')}")
            lines.append(f"  Content: {chunk.text}\n")

        return "\n".join(lines)
