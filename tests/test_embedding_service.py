"""Tests for embedding service with multilingual-e5-large."""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.services.embedding_service import EmbeddingService, Chunk


class TestEmbeddingServiceInitialization:
    """Test EmbeddingService initialization."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_initialization_default_model(self, mock_st):
        """Test EmbeddingService initialization with default model."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()

        assert service.model == mock_model
        assert service.vector_size == 1024
        mock_st.assert_called_once_with("intfloat/multilingual-e5-large")

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_initialization_custom_model(self, mock_st):
        """Test EmbeddingService initialization with custom model."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService(model="multilingual-e5-large")

        assert service.model == mock_model
        assert service.vector_size == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_initialization_api_key_ignored(self, mock_st):
        """Test that api_key parameter is ignored."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        # Should not raise error even with api_key
        service = EmbeddingService(api_key="test-key", model="multilingual-e5-large")

        assert service.model == mock_model


class TestVectorSize:
    """Test vector size detection for different models."""

    def test_get_vector_size_e5_large(self):
        """Test vector size for multilingual-e5-large."""
        size = EmbeddingService._get_vector_size("multilingual-e5-large")
        assert size == 1024

    def test_get_vector_size_e5_large_variant(self):
        """Test vector size for e5-large variant."""
        size = EmbeddingService._get_vector_size("intfloat/e5-large")
        assert size == 1024

    def test_get_vector_size_small_legacy(self):
        """Test vector size for legacy text-embedding-3-small."""
        size = EmbeddingService._get_vector_size("text-embedding-3-small")
        assert size == 512

    def test_get_vector_size_large_legacy(self):
        """Test vector size for legacy text-embedding-3-large."""
        size = EmbeddingService._get_vector_size("text-embedding-3-large")
        assert size == 3072

    def test_get_vector_size_default(self):
        """Test default vector size for unknown models."""
        size = EmbeddingService._get_vector_size("unknown-model")
        assert size == 1536


class TestChunking:
    """Test document chunking functionality."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_document_small_text(self, mock_st):
        """Test chunking of text smaller than chunk size."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        text = "This is a small text."
        chunks = service.chunk_document(text, chunk_size=500)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_document_with_overlap(self, mock_st):
        """Test chunking with overlap."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        text = "a" * 1000  # 1000 character string
        chunks = service.chunk_document(
            text,
            chunk_size=300,
            overlap=100
        )

        assert len(chunks) > 1
        # Check overlap - end of first chunk should overlap with start of second
        assert chunks[0].text[-100:] in chunks[1].text

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_document_with_section_metadata(self, mock_st):
        """Test that chunk metadata is preserved."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
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

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_document_empty_text(self, mock_st):
        """Test chunking of empty text."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        chunks = service.chunk_document("")
        assert len(chunks) == 0

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_document_sentence_boundary(self, mock_st):
        """Test that chunks break at sentence boundaries."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        text = "This is sentence one. This is sentence two. " * 10
        chunks = service.chunk_document(
            text,
            chunk_size=200
        )

        # All chunks should end with a period (sentence boundary)
        for chunk in chunks[:-1]:  # Skip last one which might not end with period
            assert chunk.text.rstrip().endswith((".", "!", "?"))

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_updates_total_chunks(self, mock_st):
        """Test that total_chunks is updated for all chunks."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        text = "a" * 1000
        chunks = service.chunk_document(text, chunk_size=300)

        num_chunks = len(chunks)
        for chunk in chunks:
            assert chunk.total_chunks == num_chunks


class TestSingleTextEmbedding:
    """Test single text embedding."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_english(self, mock_st):
        """Test embedding of English text."""
        mock_model = MagicMock()
        embedding_array = np.array([0.1, 0.2, 0.3] + [0.0] * 1021)
        mock_model.encode.return_value = embedding_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("What is offside?")

        assert embedding is not None
        assert len(embedding) == 1024
        assert isinstance(embedding, list)
        assert all(isinstance(x, float) for x in embedding)
        mock_model.encode.assert_called_once_with("What is offside?", convert_to_tensor=False)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_russian(self, mock_st):
        """Test embedding of Russian text."""
        mock_model = MagicMock()
        embedding_array = np.array([0.1, 0.2, 0.3] + [0.0] * 1021)
        mock_model.encode.return_value = embedding_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("Что такое офсайд?")

        assert embedding is not None
        assert len(embedding) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_german(self, mock_st):
        """Test embedding of German text."""
        mock_model = MagicMock()
        embedding_array = np.array([0.1, 0.2, 0.3] + [0.0] * 1021)
        mock_model.encode.return_value = embedding_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("Was ist Abseits?")

        assert embedding is not None
        assert len(embedding) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_empty(self, mock_st):
        """Test embedding of empty text returns None."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("")
        assert embedding is None

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_whitespace_only(self, mock_st):
        """Test embedding of whitespace-only text returns None."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("   ")
        assert embedding is None

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_text_error_handling(self, mock_st):
        """Test error handling in embed_text."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = Exception("Model error")
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embedding = service.embed_text("Test text")

        assert embedding is None


class TestBatchEmbedding:
    """Test batch embedding functionality."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_batch_success(self, mock_st):
        """Test successful batch embedding."""
        mock_model = MagicMock()
        # Return 3x1024 array for 3 texts
        embeddings_array = np.random.rand(3, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = service.embed_batch(texts, batch_size=2)

        assert len(embeddings) == 3
        assert all(e is not None for e in embeddings)
        assert all(len(e) == 1024 for e in embeddings)
        assert all(isinstance(e, list) for e in embeddings)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_batch_mixed_languages(self, mock_st):
        """Test batch embedding with mixed languages."""
        mock_model = MagicMock()
        embeddings_array = np.random.rand(3, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        texts = [
            "What is VAR?",
            "Что такое ВАР?",
            "Was ist VAR?"
        ]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(e is not None for e in embeddings)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_batch_empty(self, mock_st):
        """Test batch embedding with empty list."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        embeddings = service.embed_batch([])

        assert embeddings == []

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_batch_error_handling(self, mock_st):
        """Test error handling in embed_batch."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = Exception("Batch error")
        mock_st.return_value = mock_model

        service = EmbeddingService()
        texts = ["Text 1", "Text 2"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 2
        assert all(e is None for e in embeddings)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_batch_consistency(self, mock_st):
        """Test that batch encoding uses correct parameters."""
        mock_model = MagicMock()
        embeddings_array = np.random.rand(2, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        texts = ["Text 1", "Text 2"]
        embeddings = service.embed_batch(texts, batch_size=50)

        # Verify the model was called with correct parameters
        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert call_args[0][0] == texts
        assert call_args[1]["batch_size"] == 50
        assert call_args[1]["convert_to_tensor"] is False


class TestChunkEmbedding:
    """Test embedding of document chunks."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_chunks_with_metadata(self, mock_st):
        """Test embedding chunks with metadata preservation."""
        mock_model = MagicMock()
        embedding_array = np.random.rand(1, 1024).astype(np.float32)
        mock_model.encode.return_value = embedding_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
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
        assert len(results[0]["embedding"]) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_chunks_multiple(self, mock_st):
        """Test embedding multiple chunks."""
        mock_model = MagicMock()
        embeddings_array = np.random.rand(3, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings_array
        mock_st.return_value = mock_model

        service = EmbeddingService()
        chunks = [
            Chunk(text=f"Chunk {i}", section="Test") for i in range(3)
        ]

        results = service.embed_chunks(chunks)

        assert len(results) == 3
        assert all("embedding" in r for r in results)
        assert all(len(r["embedding"]) == 1024 for r in results)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embed_chunks_empty(self, mock_st):
        """Test embedding empty chunk list."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        results = service.embed_chunks([])

        assert results == []


class TestCostEstimation:
    """Test cost estimation."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_estimate_embedding_cost_always_zero(self, mock_st):
        """Test that embedding cost is always zero (local inference)."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()

        # Should always return 0 for local inference
        assert service.estimate_embedding_cost(100, 500) == 0.0
        assert service.estimate_embedding_cost(1000, 1000) == 0.0
        assert service.estimate_embedding_cost(10000, 100) == 0.0

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_estimate_tokens(self, mock_st):
        """Test token estimation."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()
        # Roughly 1 token per 4 characters
        tokens = service.estimate_tokens("a" * 400)
        assert tokens == 100
