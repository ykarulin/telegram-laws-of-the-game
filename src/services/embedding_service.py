"""
Embedding Service for document chunking and vector generation.

Handles:
- Document chunking with overlap
- Text embedding using OpenAI API
- Batch processing for efficiency
- Error handling and retries
"""

import logging
from typing import List, Dict, Any, Optional
import time
from dataclasses import dataclass

import openai
from openai import OpenAI
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


class EmbeddingService:
    """Generate embeddings for document chunks using OpenAI API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """
        Initialize embedding service.

        Args:
            api_key: OpenAI API key
            model: Embedding model name (default: text-embedding-3-small)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.vector_size = self._get_vector_size(model)

    @staticmethod
    def _get_vector_size(model: str) -> int:
        """Get vector dimension size for model."""
        if "3-small" in model:
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
        Split document into overlapping chunks.

        Uses character-based chunking with overlap to preserve context
        across chunk boundaries.

        Args:
            text: Document text to chunk
            chunk_size: Target chunk size in characters (default: 500)
            overlap: Overlap between consecutive chunks in characters (default: 100)
            section: Document section name (for metadata)
            subsection: Document subsection name (for metadata)
            page_number: Page number (for metadata)

        Returns:
            List of Chunk objects

        Examples:
            >>> chunks = service.chunk_document("Long text...", chunk_size=500)
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

        # If text is smaller than chunk size, return single chunk
        if len(text) <= chunk_size:
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

        # Create overlapping chunks
        start = 0
        chunk_index = 0

        while start < len(text):
            # Get chunk end position
            end = min(start + chunk_size, len(text))

            # If not at end of text, try to break at sentence boundary
            if end < len(text):
                # Look backward for a sentence boundary (. ! ?)
                last_sentence = max(
                    text.rfind(".", start, end),
                    text.rfind("!", start, end),
                    text.rfind("?", start, end),
                )
                if last_sentence > start + chunk_size // 2:
                    end = last_sentence + 1

            # Extract chunk
            chunk_text = text[start:end].strip()

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

            # Move to next chunk (with overlap)
            start = end - overlap if end < len(text) else len(text)

        # Update total_chunks count
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        logger.info(
            f"Chunked document into {len(chunks)} chunks "
            f"(size={chunk_size}, overlap={overlap})"
        )

        return chunks

    def embed_text(self, text: str, retries: int = 3) -> Optional[List[float]]:
        """
        Generate embedding for a single text string.

        Args:
            text: Text to embed
            retries: Number of retries on failure (default: 3)

        Returns:
            List of floats representing the embedding, or None on failure

        Examples:
            >>> embedding = service.embed_text("What is VAR?")
            >>> len(embedding)
            512
            >>> isinstance(embedding[0], float)
            True
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided to embed_text")
            return None

        for attempt in range(retries):
            try:
                response = self.client.embeddings.create(
                    input=text, model=self.model, dimensions=self.vector_size
                )
                embedding = response.data[0].embedding
                logger.debug(f"Embedded text ({len(text)} chars) → {len(embedding)} dims")
                return embedding

            except openai.RateLimitError:
                wait_time = (2 ** attempt) + 1  # Exponential backoff
                logger.warning(
                    f"Rate limit hit, waiting {wait_time}s before retry "
                    f"({attempt + 1}/{retries})"
                )
                time.sleep(wait_time)

            except openai.APIError as e:
                logger.error(f"OpenAI API error: {e}")
                if attempt == retries - 1:
                    return None
                time.sleep(1)

        logger.error(f"Failed to embed text after {retries} attempts")
        return None

    def embed_batch(
        self, texts: List[str], batch_size: int = 100, retries: int = 3
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Batches API calls for efficiency. Handles rate limiting with
        exponential backoff.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (default: 100, max: 2048)
            retries: Number of retries per batch (default: 3)

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
        embeddings: List[Optional[List[float]]] = []

        # Process in batches
        for batch_start in range(0, len(texts), batch_size):
            batch_end = min(batch_start + batch_size, len(texts))
            batch_texts = texts[batch_start:batch_end]

            logger.info(
                f"Embedding batch {batch_start // batch_size + 1} "
                f"({len(batch_texts)} texts)..."
            )

            # Try with exponential backoff
            for attempt in range(retries):
                try:
                    response = self.client.embeddings.create(
                        input=batch_texts, model=self.model, dimensions=self.vector_size
                    )

                    # Extract embeddings in order
                    batch_embeddings = sorted(
                        response.data, key=lambda x: x.index
                    )
                    embeddings.extend(
                        [e.embedding for e in batch_embeddings]
                    )

                    logger.info(f"Successfully embedded {len(batch_texts)} texts")
                    break

                except openai.RateLimitError:
                    wait_time = (2 ** attempt) + 1
                    logger.warning(
                        f"Rate limit, waiting {wait_time}s ({attempt + 1}/{retries})"
                    )
                    time.sleep(wait_time)

                except openai.APIError as e:
                    logger.error(f"API error on batch: {e}")
                    if attempt == retries - 1:
                        embeddings.extend([None] * len(batch_texts))
                    else:
                        time.sleep(1)

        return embeddings

    def embed_chunks(
        self,
        chunks: List[Chunk],
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Embed a list of chunks and return with metadata.

        Args:
            chunks: List of Chunk objects to embed
            batch_size: Batch size for API calls (default: 100)

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
        Estimate cost of embedding texts.

        Pricing (as of 2024):
        - text-embedding-3-small: $0.02 per 1M tokens
        - text-embedding-3-large: $0.13 per 1M tokens

        Args:
            num_texts: Number of texts to embed
            avg_length: Average length in characters

        Returns:
            Estimated cost in USD
        """
        tokens_per_text = self.estimate_tokens("x" * avg_length)
        total_tokens = num_texts * tokens_per_text

        if "3-small" in self.model:
            cost_per_token = 0.02 / 1_000_000
        elif "3-large" in self.model:
            cost_per_token = 0.13 / 1_000_000
        else:
            cost_per_token = 0.0001 / 1_000_000

        return total_tokens * cost_per_token
