"""
Retrieval Service for semantic search and context formatting.

Handles:
- Converting user queries to embeddings
- Searching Qdrant for relevant document chunks
- Formatting retrieved chunks for LLM context
- Handling fallback when retrieval fails
"""

import logging
from typing import List, Dict, Any, Optional

from src.services.embedding_service import EmbeddingService
from src.core.vector_db import VectorDatabase, RetrievedChunk
from src.config import Config

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve and format context from vector database."""

    def __init__(self, config: Config, embedding_service: EmbeddingService):
        """
        Initialize retrieval service.

        Args:
            config: Configuration object with Qdrant settings
            embedding_service: EmbeddingService for query embedding
        """
        self.config = config
        self.embedding_service = embedding_service
        self.vector_db = VectorDatabase(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=config.qdrant_api_key,
        )

    def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant document chunks for a query.

        Converts query to embedding, searches Qdrant, returns top-K results
        above similarity threshold.

        With dynamic threshold enabled, filters to chunks within a percentage
        of the best score, but never below static threshold.

        Args:
            query: User question or search query
            top_k: Number of results (default from config)
            threshold: Minimum similarity score (default from config)

        Returns:
            List of RetrievedChunk objects, empty if no results

        Examples:
            >>> chunks = service.retrieve_context("What is VAR?")
            >>> len(chunks)
            3
            >>> chunks[0].score
            0.87
        """
        if not query or len(query.strip()) == 0:
            logger.warning("Empty query provided to retrieve_context")
            return []

        # Use config defaults if not specified
        top_k = top_k or self.config.top_k_retrievals
        threshold = threshold or self.config.similarity_threshold

        try:
            # Convert query to embedding
            query_embedding = self.embedding_service.embed_text(query)

            if query_embedding is None:
                logger.error("Failed to embed query")
                return []

            # Log query embedding for debugging dev/prod differences
            logger.info(
                f"Query embedding generated for: '{query[:100]}...' "
                f"(embedding_dims={len(query_embedding)}, "
                f"first_5={query_embedding[:5]}, "
                f"last_5={query_embedding[-5:]}, "
                f"min={min(query_embedding):.4f}, "
                f"max={max(query_embedding):.4f}, "
                f"mean={sum(query_embedding) / len(query_embedding):.4f})"
            )

            # Search Qdrant with higher limit to allow post-filtering with dynamic threshold
            results = self.vector_db.search(
                collection_name=self.config.qdrant_collection_name,
                query_vector=query_embedding,
                limit=top_k,
                min_score=threshold,
            )

            # Apply dynamic threshold filtering if configured
            if self.config.rag_dynamic_threshold_margin is not None and results:
                results = self._apply_dynamic_threshold(results, threshold)

            # Log retrieval results with embedding similarity details
            if results:
                logger.info(
                    f"Retrieved {len(results)} chunks for query "
                    f"(threshold={threshold}, top_k={top_k}, "
                    f"dynamic_margin={self.config.rag_dynamic_threshold_margin}, "
                    f"scores=[{', '.join(f'{r.score:.4f}' for r in results)}])"
                )
                for i, result in enumerate(results, 1):
                    logger.debug(
                        f"  Result {i}: score={result.score:.4f}, "
                        f"doc={result.metadata.get('document_name', 'unknown')}, "
                        f"section={result.metadata.get('section', 'unknown')}, "
                        f"text_preview={result.text[:80]}..."
                    )
            else:
                logger.info(
                    f"No chunks retrieved for query (threshold={threshold}, top_k={top_k})"
                )

            return results

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    def _apply_dynamic_threshold(
        self,
        chunks: List[RetrievedChunk],
        static_threshold: float,
    ) -> List[RetrievedChunk]:
        """
        Apply dynamic threshold filtering to retrieved chunks.

        Filters chunks to those within a percentage of the best score,
        but never below the static threshold. Caps results at 3 chunks.

        Args:
            chunks: Retrieved chunks from Qdrant
            static_threshold: Static similarity threshold

        Returns:
            Filtered list of chunks (max 3)

        Examples:
            >>> chunks = [
            ...     RetrievedChunk(score=0.95, ...),
            ...     RetrievedChunk(score=0.85, ...),
            ...     RetrievedChunk(score=0.70, ...),
            ... ]
            >>> filtered = service._apply_dynamic_threshold(chunks, 0.7)
            >>> len(filtered) <= 3
            True
        """
        if not chunks:
            return []

        best_score = chunks[0].score
        dynamic_threshold = best_score * (1 - self.config.rag_dynamic_threshold_margin)
        effective_threshold = max(dynamic_threshold, static_threshold)

        logger.debug(
            f"Dynamic threshold calculation: "
            f"best_score={best_score:.4f}, "
            f"margin={self.config.rag_dynamic_threshold_margin}, "
            f"dynamic_threshold={dynamic_threshold:.4f}, "
            f"static_threshold={static_threshold:.4f}, "
            f"effective_threshold={effective_threshold:.4f}"
        )

        filtered = [chunk for chunk in chunks if chunk.score >= effective_threshold]
        result = filtered[:3]  # Cap at 3 chunks

        logger.debug(
            f"Dynamic threshold filtered {len(chunks)} chunks to {len(result)} "
            f"(effective_threshold={effective_threshold:.4f})"
        )

        return result

    def format_context(
        self,
        chunks: List[RetrievedChunk],
        include_metadata: bool = True,
        include_scores: bool = False,
    ) -> str:
        """
        Format retrieved chunks as LLM context string.

        Creates a readable string with retrieved document excerpts
        and optional metadata for injection into LLM prompts.

        Args:
            chunks: List of RetrievedChunk objects
            include_metadata: Include section/source info (default: True)
            include_scores: Include similarity scores (default: False)

        Returns:
            Formatted string for use in LLM context

        Examples:
            >>> chunks = [
            ...     RetrievedChunk(text="VAR is...", score=0.9, metadata={...}),
            ...     RetrievedChunk(text="The use of VAR...", score=0.87, metadata={...})
            ... ]
            >>> context = service.format_context(chunks)
            >>> "VAR is" in context
            True
        """
        if not chunks:
            return ""

        lines = []
        lines.append("=== Retrieved Context from Football Documents ===\n")

        for i, chunk in enumerate(chunks, 1):
            lines.append(f"\n[Document {i}]")

            # Add metadata if available and requested
            if include_metadata and chunk.metadata:
                meta = chunk.metadata
                if meta.get("document_name"):
                    lines.append(f"Source: {meta.get('document_name')}")
                if meta.get("section"):
                    lines.append(f"Section: {meta.get('section')}")
                if meta.get("subsection"):
                    lines.append(f"Subsection: {meta.get('subsection')}")
                if meta.get("version"):
                    lines.append(f"Version: {meta.get('version')}")

            # Add similarity score if requested
            if include_scores:
                lines.append(f"Relevance: {chunk.score:.1%}")

            # Add chunk text
            lines.append(f"\n{chunk.text}")

        lines.append("\n\n=== End of Retrieved Context ===")

        return "\n".join(lines)

    def format_inline_citation(self, chunk: RetrievedChunk) -> str:
        """
        Format chunk as inline citation for response.

        Used to cite sources in bot responses (respects Telegram message limits).

        Args:
            chunk: RetrievedChunk to format

        Returns:
            Citation string (e.g., "[Source: Laws of the Game, Law 1]")

        Examples:
            >>> chunk = RetrievedChunk(metadata={"document_name": "Laws 2024", "section": "Law 1"})
            >>> citation = service.format_inline_citation(chunk)
            >>> citation
            '[Source: Laws 2024, Law 1]'
        """
        if not chunk.metadata:
            return "[Source: Unknown]"

        meta = chunk.metadata
        parts = []

        if meta.get("document_name"):
            parts.append(meta.get("document_name"))
        if meta.get("section"):
            parts.append(meta.get("section"))
        if meta.get("subsection"):
            parts.append(meta.get("subsection"))

        if parts:
            return f"[Source: {', '.join(parts)}]"
        return "[Source: Document]"

    def retrieve_and_format(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        include_scores: bool = False,
    ) -> str:
        """
        Convenience method: retrieve and format context in one call.

        Args:
            query: User question
            top_k: Number of results (default from config)
            threshold: Minimum score (default from config)
            include_scores: Include relevance scores in output

        Returns:
            Formatted context string, or empty string if no results

        Examples:
            >>> context = service.retrieve_and_format("What is VAR?")
            >>> len(context) > 0
            True
        """
        chunks = self.retrieve_context(query, top_k, threshold)

        if not chunks:
            logger.warning(f"No relevant documents found for query: {query}")
            return ""

        return self.format_context(chunks, include_scores=include_scores)

    def should_use_retrieval(self) -> bool:
        """
        Check if retrieval is available and enabled.

        Returns:
            True if Qdrant is accessible and collection exists

        Examples:
            >>> if service.should_use_retrieval():
            ...     context = service.retrieve_and_format(query)
        """
        try:
            # Quick health check
            if not self.vector_db.health_check():
                logger.warning("Qdrant server not responding")
                return False

            # Check if collection exists
            if not self.vector_db.collection_exists(
                self.config.qdrant_collection_name
            ):
                logger.warning(f"Collection '{self.config.qdrant_collection_name}' not found")
                return False

            return True

        except Exception as e:
            logger.warning(f"Retrieval availability check failed: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the indexed collection.

        Returns:
            Dictionary with collection info (point count, memory usage, etc.)

        Examples:
            >>> stats = service.get_collection_stats()
            >>> stats['points_count']
            1532
        """
        try:
            from qdrant_client.http import models

            client = self.vector_db.client
            collection_info = client.get_collection(
                self.config.qdrant_collection_name
            )

            return {
                "name": self.config.qdrant_collection_name,
                "points_count": collection_info.points_count,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status,
                "config": {
                    "vector_size": (
                        collection_info.config.params.vectors.size
                        if hasattr(collection_info.config.params, "vectors")
                        else None
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}

    def retrieve_from_documents(
        self,
        query: str,
        document_names: List[str],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant chunks from specific documents only.

        This method is called by the document lookup tool to search
        within a subset of documents selected by the LLM.

        Args:
            query: Search query
            document_names: List of specific document names to search
            top_k: Number of results (default from config)
            threshold: Minimum similarity threshold (default from config)

        Returns:
            List of RetrievedChunk objects from the selected documents

        Examples:
            >>> chunks = service.retrieve_from_documents(
            ...     query="offside rule",
            ...     document_names=["Laws of Game 2024-25"],
            ...     top_k=3
            ... )
            >>> len(chunks)
            2
        """
        if not query or len(query.strip()) == 0:
            logger.warning("Empty query provided to retrieve_from_documents")
            return []

        if not document_names:
            logger.warning("Empty document_names provided to retrieve_from_documents")
            return []

        # Use config defaults if not specified
        top_k = top_k or self.config.top_k_retrievals
        threshold = threshold or self.config.similarity_threshold

        try:
            # Get document IDs from names
            from src.services.document_service import DocumentService
            doc_service = DocumentService(self.config, None)  # Would need session in real implementation
            doc_ids = doc_service.get_document_ids_by_names(document_names)

            if not doc_ids:
                logger.warning(
                    f"No indexed documents found matching: {', '.join(document_names)}"
                )
                return []

            # Embed the query
            query_embedding = self.embedding_service.embed_text(query)
            if query_embedding is None:
                logger.error("Failed to embed query for document-specific search")
                return []

            # Search Qdrant for chunks from these documents
            # Note: Qdrant doesn't natively support filtering by metadata field values,
            # so we retrieve top results and then filter by document name in metadata
            results = self.vector_db.search(
                collection_name=self.config.qdrant_collection_name,
                query_vector=query_embedding,
                limit=top_k * 2,  # Over-fetch to account for filtering
                min_score=threshold,
            )

            # Filter results to only include chunks from specified documents
            filtered_results = [
                chunk
                for chunk in results
                if chunk.metadata
                and chunk.metadata.get("document_name") in document_names
            ]

            # Apply dynamic threshold if configured
            if self.config.rag_dynamic_threshold_margin is not None and filtered_results:
                filtered_results = self._apply_dynamic_threshold(
                    filtered_results, threshold
                )

            # Respect top_k limit
            filtered_results = filtered_results[:top_k]

            logger.info(
                f"Retrieved {len(filtered_results)} chunks from {len(document_ids)} documents "
                f"for query: '{query[:100]}...'"
            )

            return filtered_results

        except Exception as e:
            logger.error(f"Document-specific retrieval failed: {e}", exc_info=True)
            return []

    def format_document_list(
        self,
        document_names: List[str],
        include_numbering: bool = True,
    ) -> str:
        """
        Format document list for LLM consumption.

        Provides the LLM with a readable list of available documents
        to guide its document selection for the lookup tool.

        Args:
            document_names: List of document names to format
            include_numbering: Whether to include numbered list (default: True)

        Returns:
            Formatted document list string, or empty string if no documents

        Examples:
            >>> formatted = service.format_document_list(
            ...     ["Laws of Game 2024-25", "VAR Guidelines 2024"]
            ... )
            >>> print(formatted)
            1. Laws of Game 2024-25
            2. VAR Guidelines 2024
        """
        if not document_names:
            return ""

        if include_numbering:
            lines = [
                f"{i}. {name}"
                for i, name in enumerate(document_names, 1)
            ]
        else:
            lines = [f"- {name}" for name in document_names]

        return "\n".join(lines)

    def get_indexed_documents(self) -> List[str]:
        """
        Get list of all indexed document names.

        Convenience method that retrieves indexed documents from DocumentService.
        Used to populate the document list for the LLM.

        Returns:
            List of document names, empty if none

        Examples:
            >>> docs = service.get_indexed_documents()
            >>> docs
            ['Laws of Game 2024-25', 'VAR Guidelines 2024']
        """
        try:
            from src.services.document_service import DocumentService
            doc_service = DocumentService(self.config, None)  # Would need session in real implementation
            return doc_service.get_indexed_document_names()
        except Exception as e:
            logger.error(f"Failed to get indexed documents: {e}")
            return []
