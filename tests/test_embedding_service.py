"""Tests for embedding service."""
import pytest
from unittest.mock import MagicMock, patch
from src.services.embedding_service import EmbeddingService, Chunk


class TestEmbeddingService:
    """Test EmbeddingService class."""

    def test_initialization(self):
        """Test EmbeddingService initialization."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService(
                api_key="test-key",
                model="text-embedding-3-small"
            )
            assert service.model == "text-embedding-3-small"
            assert service.vector_size == 512

    def test_get_vector_size_small(self):
        """Test vector size for text-embedding-3-small."""
        size = EmbeddingService._get_vector_size("text-embedding-3-small")
        assert size == 512

    def test_get_vector_size_large(self):
        """Test vector size for text-embedding-3-large."""
        size = EmbeddingService._get_vector_size("text-embedding-3-large")
        assert size == 3072

    def test_get_vector_size_default(self):
        """Test default vector size for unknown models."""
        size = EmbeddingService._get_vector_size("text-embedding-2")
        assert size == 1536

    def test_chunk_document_small_text(self):
        """Test chunking of text smaller than chunk size."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            text = "This is a small text."
            chunks = service.chunk_document(text, chunk_size=500)

            assert len(chunks) == 1
            assert chunks[0].text == text
            assert chunks[0].chunk_index == 0
            assert chunks[0].total_chunks == 1

    def test_chunk_document_with_overlap(self):
        """Test chunking with overlap."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            text = "a" * 1000  # 1000 character string
            chunks = service.chunk_document(
                text,
                chunk_size=300,
                overlap=100
            )

            assert len(chunks) > 1
            # Check overlap - end of first chunk should overlap with start of second
            assert chunks[0].text[-100:] in chunks[1].text

    def test_chunk_document_with_section_metadata(self):
        """Test that chunk metadata is preserved."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            text = "Rule 1: Content here. Rule 2: More content here."
            chunks = service.chunk_document(
                text,
                section="Laws",
                subsection="Basic Rules",
                page_number=5
            )

            for chunk in chunks:
                assert chunk.section == "Laws"
                assert chunk.subsection == "Basic Rules"
                assert chunk.page_number == 5

    def test_chunk_document_empty_text(self):
        """Test chunking of empty text."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            chunks = service.chunk_document("")
            assert len(chunks) == 0

    def test_chunk_document_sentence_boundary(self):
        """Test that chunks break at sentence boundaries."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            text = "This is sentence one. This is sentence two. " * 10
            chunks = service.chunk_document(
                text,
                chunk_size=200
            )

            # All chunks should end with a period (sentence boundary)
            for chunk in chunks[:-1]:  # Skip last one which might not end with period
                assert chunk.text.rstrip().endswith((".", "!", "?"))

    def test_embed_text_success(self):
        """Test successful text embedding."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1] * 512

        with patch("src.services.embedding_service.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response

            service = EmbeddingService("test-key")
            service.client = mock_client

            embedding = service.embed_text("What is offside?")

            assert len(embedding) == 512
            mock_client.embeddings.create.assert_called_once()

    def test_embed_text_empty(self):
        """Test embedding of empty text."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            embedding = service.embed_text("")
            assert embedding is None

    def test_embed_text_with_retry(self):
        """Test embedding with retry on rate limit."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1] * 512

        with patch("src.services.embedding_service.OpenAI") as mock_openai:
            with patch("src.services.embedding_service.time.sleep"):
                with patch("src.services.embedding_service.openai") as mock_openai_module:
                    # Set up RateLimitError
                    mock_openai_module.RateLimitError = Exception
                    mock_openai_module.APIError = Exception

                    mock_openai.return_value = mock_client
                    # Fail once with RateLimitError, then succeed
                    mock_client.embeddings.create.side_effect = [
                        Exception("Rate limited"),
                        mock_response
                    ]

                    service = EmbeddingService("test-key")
                    service.client = mock_client

                    embedding = service.embed_text("Test text", retries=2)

                    assert embedding is not None
                    assert len(embedding) == 512
                    assert mock_client.embeddings.create.call_count == 2

    def test_embed_batch_success(self):
        """Test successful batch embedding."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(index=0, embedding=[0.1] * 512),
            MagicMock(index=1, embedding=[0.2] * 512)
        ]

        with patch("src.services.embedding_service.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response

            service = EmbeddingService("test-key")
            service.client = mock_client

            texts = ["Text 1", "Text 2"]
            embeddings = service.embed_batch(texts, batch_size=2)

            assert len(embeddings) == 2
            assert all(e is not None for e in embeddings)

    def test_embed_chunks_with_metadata(self):
        """Test embedding chunks with metadata preservation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(index=0, embedding=[0.1] * 512)
        ]

        with patch("src.services.embedding_service.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response

            service = EmbeddingService("test-key")
            service.client = mock_client

            chunk = Chunk(
                text="Test chunk",
                section="Law 1",
                subsection="Offside",
                page_number=5,
                chunk_index=0,
                total_chunks=1
            )

            results = service.embed_chunks([chunk])

            assert len(results) == 1
            assert results[0]["text"] == "Test chunk"
            assert results[0]["section"] == "Law 1"
            assert results[0]["subsection"] == "Offside"
            assert results[0]["page_number"] == 5
            assert len(results[0]["embedding"]) == 512

    def test_estimate_tokens(self):
        """Test token estimation."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            # Roughly 1 token per 4 characters
            tokens = service.estimate_tokens("a" * 400)
            assert tokens == 100

    def test_estimate_embedding_cost_small_model(self):
        """Test embedding cost estimation for small model."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key", model="text-embedding-3-small")
            # text-embedding-3-small: $0.02 per 1M tokens
            cost = service.estimate_embedding_cost(num_texts=1000, avg_length=500)
            # ~125 texts per token (500 chars / 4), so 125 tokens per text
            # 1000 texts * 125 tokens = 125,000 tokens
            # 125,000 / 1,000,000 * $0.02 = $0.0025
            assert cost > 0
            assert cost < 0.01  # Should be very cheap

    def test_estimate_embedding_cost_large_model(self):
        """Test embedding cost estimation for large model."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key", model="text-embedding-3-large")
            # text-embedding-3-large: $0.13 per 1M tokens
            cost = service.estimate_embedding_cost(num_texts=1000, avg_length=500)
            assert cost > 0
            assert cost < 0.1  # Should be more expensive than small

    def test_chunk_updates_total_chunks(self):
        """Test that total_chunks is updated for all chunks."""
        with patch("src.services.embedding_service.OpenAI"):
            service = EmbeddingService("test-key")
            text = "a" * 1000
            chunks = service.chunk_document(text, chunk_size=300)

            num_chunks = len(chunks)
            for chunk in chunks:
                assert chunk.total_chunks == num_chunks
