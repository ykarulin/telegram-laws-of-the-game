"""
Embedding Service for document chunking and vector generation.

Handles:
- Document chunking with overlap
- Text embedding using multilingual-e5-large model
- Batch processing for efficiency
- Support for multiple languages without language detection
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer
from src.constants import EmbeddingConfig

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a document chunk with metadata."""
    text: str
    section: str = ""
    subsection: str = ""
    page_number: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary representation.

        Returns:
            Dictionary with all chunk fields
        """
        return {
            "text": self.text,
            "section": self.section,
            "subsection": self.subsection,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
        }

    def get_location(self) -> str:
        """Get human-readable location information.

        Returns:
            String describing the location in the document (e.g., "Section > Subsection, Page 5")
        """
        parts = []
        if self.section:
            parts.append(self.section)
        if self.subsection:
            parts.append(self.subsection)

        location = " > ".join(parts) if parts else "Unknown section"

        if self.page_number is not None:
            location += f", Page {self.page_number}"

        return location

    def is_first_chunk(self) -> bool:
        """Check if this is the first chunk of the document.

        Returns:
            True if this is chunk 0, False otherwise
        """
        return self.chunk_index == 0

    def is_last_chunk(self) -> bool:
        """Check if this is the last chunk of the document.

        Returns:
            True if this is the final chunk, False otherwise
        """
        return self.chunk_index == self.total_chunks - 1


class EmbeddingService:
    """Generate embeddings for document chunks using multilingual-e5-large model."""

    def __init__(self, api_key: str = None, model: str = "intfloat/multilingual-e5-large"):
        """
        Initialize embedding service with self-hosted multilingual model.

        Args:
            api_key: Ignored (kept for backward compatibility)
            model: Model name (default: multilingual-e5-large)

        Note:
            The api_key parameter is kept for backward compatibility with bot_factory.py
            but is not used for local embedding inference.
        """
        try:
            # Load model from Hugging Face (cached after first download)
            logger.info(f"Loading embedding model: {model}")
            self.model = SentenceTransformer(model)
            self.tokenizer = self.model.tokenizer
            self.vector_size = self._get_vector_size(model)
            logger.info(f"Loaded {model} with {self.vector_size} dimensions")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    @staticmethod
    def _get_vector_size(model: str) -> int:
        """Get vector dimension size for model."""
        if "e5-large" in model or "multilingual-e5-large" in model:
            return EmbeddingConfig.VECTOR_DIMENSIONS_E5_LARGE
        elif "3-small" in model:
            return EmbeddingConfig.VECTOR_DIMENSIONS_SMALL
        elif "3-large" in model:
            return EmbeddingConfig.VECTOR_DIMENSIONS_LARGE
        else:
            return EmbeddingConfig.VECTOR_DIMENSIONS_DEFAULT

    def chunk_document(
        self,
        text: str,
        chunk_size: int = EmbeddingConfig.DEFAULT_CHUNK_SIZE,
        overlap: int = EmbeddingConfig.DEFAULT_CHUNK_OVERLAP,
        section: str = "",
        subsection: str = "",
        page_number: Optional[int] = None,
    ) -> List[Chunk]:
        """
        Split document into overlapping chunks based on tokens.

        Uses token-based chunking with overlap to preserve context across chunk
        boundaries. Tokens are from the embedding model's tokenizer for consistency
        with how text is actually encoded into vectors.

        Args:
            text: Document text to chunk
            chunk_size: Target chunk size in tokens (default: 500)
            overlap: Overlap between consecutive chunks in tokens (default: 100)
            section: Document section name (for metadata)
            subsection: Document subsection name (for metadata)
            page_number: Page number (for metadata)

        Returns:
            List of Chunk objects

        Examples:
            >>> chunks = service.chunk_document("Long text...", chunk_size=500, overlap=100)
            >>> len(chunks)
            3
            >>> chunks[0].text[:50]
            'Long text...'
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided to chunk_document")
            return []

        chunks = []
        text = text.strip()

        try:
            # Tokenize the entire text
            token_ids = self.tokenizer.encode(text)

            if not token_ids:
                logger.warning("Text produced no tokens after tokenization")
                return []

            # If text is smaller than chunk size (in tokens), return single chunk
            if len(token_ids) <= chunk_size:
                return [
                    Chunk(
                        text=text,
                        section=section,
                        subsection=subsection,
                        page_number=page_number,
                        chunk_index=0,
                        total_chunks=1,
                    )
                ]

            # Create overlapping chunks based on token boundaries
            start_token = 0
            chunk_index = 0

            while start_token < len(token_ids):
                # Get chunk end position (in tokens)
                end_token = min(start_token + chunk_size, len(token_ids))

                # Decode tokens back to text
                chunk_token_ids = token_ids[start_token:end_token]
                chunk_text = self.tokenizer.decode(
                    chunk_token_ids,
                    skip_special_tokens=True
                ).strip()

                if chunk_text:  # Only add non-empty chunks
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            section=section,
                            subsection=subsection,
                            page_number=page_number,
                            chunk_index=chunk_index,
                            total_chunks=0,  # Will update after loop
                        )
                    )
                    chunk_index += 1

                # Move to next chunk (with overlap in tokens)
                start_token = end_token - overlap if end_token < len(token_ids) else len(token_ids)

            # Update total_chunks count
            for chunk in chunks:
                chunk.total_chunks = len(chunks)

            logger.info(
                f"Chunked document into {len(chunks)} chunks "
                f"(size={chunk_size} tokens, overlap={overlap} tokens, "
                f"total_tokens={len(token_ids)})"
            )

            return chunks

        except Exception as e:
            logger.error(f"Failed to chunk document: {e}")
            raise

    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text string.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding, or None on failure

        Examples:
            >>> embedding = service.embed_text("What is VAR?")
            >>> len(embedding)
            1024
            >>> isinstance(embedding[0], float)
            True
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided to embed_text")
            return None

        try:
            # Local inference - multilingual-e5-large automatically handles any language
            embedding = self.model.encode(text, convert_to_tensor=False)
            logger.debug(f"Embedded text ({len(text)} chars) → {len(embedding)} dims")
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to embed text: {e}")
            return None

    def embed_batch(
        self, texts: List[str], batch_size: int = 100
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Efficient batch processing with SentenceTransformer.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch (default: 100)

        Returns:
            List of embeddings (one per input text, None if failed)

        Examples:
            >>> texts = ["What is VAR?", "What is offside?"]
            >>> embeddings = service.embed_batch(texts)
            >>> len(embeddings)
            2
            >>> all(e is not None for e in embeddings)
            True
        """
        if not texts:
            logger.warning("Empty text list provided to embed_batch")
            return []

        try:
            logger.info(f"Embedding batch of {len(texts)} texts...")

            # Use SentenceTransformer's batch processing
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                convert_to_tensor=False,
                show_progress_bar=len(texts) > 100
            )

            # Convert numpy array to list of lists
            embeddings_list = [embedding.tolist() for embedding in embeddings]
            logger.info(f"Successfully embedded {len(embeddings_list)} texts")

            return embeddings_list

        except Exception as e:
            logger.error(f"Failed to embed batch: {e}")
            return [None] * len(texts)

    def embed_chunks(
        self,
        chunks: List[Chunk],
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Embed a list of chunks and return with metadata.

        Args:
            chunks: List of Chunk objects to embed
            batch_size: Batch size for embedding (default: 100)

        Returns:
            List of dicts with chunk text, embedding, and metadata

        Examples:
            >>> chunks = [Chunk(text="Text 1"), Chunk(text="Text 2")]
            >>> results = service.embed_chunks(chunks)
            >>> len(results)
            2
            >>> 'embedding' in results[0]
            True
        """
        if not chunks:
            logger.warning("No chunks provided to embed_chunks")
            return []

        # Extract texts
        texts = [chunk.text for chunk in chunks]

        # Embed in batches
        embeddings = self.embed_batch(texts, batch_size=batch_size)

        # Combine with metadata
        results = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            if embedding is not None:
                results.append(
                    {
                        "text": chunk.text,
                        "embedding": embedding,
                        "section": chunk.section,
                        "subsection": chunk.subsection,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": chunk.total_chunks,
                    }
                )
            else:
                logger.warning(f"Failed to embed chunk {i}")

        logger.info(f"Successfully embedded {len(results)} out of {len(chunks)} chunks")
        return results

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation).

        Uses rule of thumb: ~1 token per 4 characters.

        Args:
            text: Text to estimate tokens for

        Returns:
            Approximate token count
        """
        return len(text) // 4

    def estimate_embedding_cost(self, num_texts: int, avg_length: int = 500) -> float:
        """
        Estimate cost of embedding texts (always 0 for local inference).

        Args:
            num_texts: Number of texts to embed
            avg_length: Average length in characters

        Returns:
            Always returns 0 (local inference is free)
        """
        return 0.0
