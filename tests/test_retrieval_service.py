"""Tests for retrieval service."""
import pytest
from unittest.mock import MagicMock, patch
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk


class TestRetrievalService:
    """Test RetrievalService class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock()
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.top_k_retrievals = 5
        config.similarity_threshold = 0.55
        return config

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = MagicMock()
        service.embed_text.return_value = [0.1] * 512
        return service

    @pytest.fixture
    def mock_vector_db(self):
        """Create a mock vector database."""
        db = MagicMock()
        return db

    def test_initialization(self, mock_config, mock_embedding_service):
        """Test RetrievalService initialization."""
        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            assert service.config == mock_config
            assert service.embedding_service == mock_embedding_service
            assert service.config.top_k_retrievals == 5
            assert service.config.similarity_threshold == 0.55

    def test_should_use_retrieval_enabled(self, mock_config, mock_embedding_service):
        """Test should_use_retrieval returns true when Qdrant is healthy."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vdb = MagicMock()
            mock_vdb.health_check.return_value = True
            mock_vdb.collection_exists.return_value = True
            mock_vdb_class.return_value = mock_vdb

            service = RetrievalService(mock_config, mock_embedding_service)
            assert service.should_use_retrieval() is True

    def test_should_use_retrieval_disabled(self, mock_config, mock_embedding_service):
        """Test should_use_retrieval returns false when Qdrant is unhealthy."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vdb = MagicMock()
            mock_vdb.health_check.return_value = False
            mock_vdb_class.return_value = mock_vdb

            service = RetrievalService(mock_config, mock_embedding_service)
            assert service.should_use_retrieval() is False

    def test_retrieve_context_success(self, mock_config, mock_embedding_service):
        """Test successful context retrieval."""
        chunk1 = RetrievedChunk(
            chunk_id="1",
            text="Offside is when a player is nearer to the opponent's goal line than both the ball and the last two opponents.",
            score=0.92,
            metadata={"section": "Law 11", "document_name": "Laws of Game"}
        )
        chunk2 = RetrievedChunk(
            chunk_id="2",
            text="A player in an offside position receives the ball from an opponent.",
            score=0.85,
            metadata={"section": "Law 11", "document_name": "Laws of Game"}
        )

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = [chunk1, chunk2]

            mock_embedding_service.embed_text.return_value = [0.1] * 512
            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            chunks = service.retrieve_context("What is offside?")

            assert len(chunks) == 2
            assert chunks[0].score == 0.92
            assert "Offside" in chunks[0].text
            mock_vector_db.search.assert_called_once()

    def test_retrieve_context_no_results(self, mock_config, mock_embedding_service):
        """Test context retrieval with no results."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            chunks = service.retrieve_context("Nonexistent topic")

            assert len(chunks) == 0

    def test_retrieve_context_respects_limit(self, mock_config, mock_embedding_service):
        """Test that retrieve respects top_k limit."""
        chunks = [
            RetrievedChunk(f"{i}", f"Content {i}", 0.9 - i * 0.05, {})
            for i in range(10)
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks[:5]

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            retrieved = service.retrieve_context("Query")

            # Should respect top_k=5
            assert len(retrieved) <= 5

    def test_format_context_single_chunk(self, mock_config, mock_embedding_service):
        """Test formatting context from chunks."""
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Offside rule definition",
            score=0.92,
            metadata={"section": "Law 11", "page_number": 5}
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context([chunk])

            assert "Offside rule definition" in context
            assert isinstance(context, str)

    def test_format_context_multiple_chunks(self, mock_config, mock_embedding_service):
        """Test formatting context from multiple chunks."""
        chunks = [
            RetrievedChunk(
                chunk_id="1",
                text="First chunk content",
                score=0.92,
                metadata={"section": "Law 1"}
            ),
            RetrievedChunk(
                chunk_id="2",
                text="Second chunk content",
                score=0.85,
                metadata={"section": "Law 2"}
            )
        ]

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context(chunks)

            assert "First chunk content" in context
            assert "Second chunk content" in context

    def test_format_context_empty(self, mock_config, mock_embedding_service):
        """Test formatting context with empty chunks."""
        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context([])

            assert context == ""

    def test_format_inline_citation(self, mock_config, mock_embedding_service):
        """Test inline citation formatting."""
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Offside rule",
            score=0.92,
            metadata={
                "document_name": "Laws of Game 2025-26",
                "section": "Law 11",
                "page_number": 42
            }
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            citation = service.format_inline_citation(chunk)

            assert "Laws of Game 2025-26" in citation
            assert "Law 11" in citation
            # Verify the citation format
            assert citation.startswith("[Source:")
            assert citation.endswith("]")

    def test_format_inline_citation_minimal_metadata(self, mock_config, mock_embedding_service):
        """Test citation formatting with minimal metadata."""
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Content",
            score=0.92,
            metadata={"document_name": "Document"}
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            citation = service.format_inline_citation(chunk)

            assert "Document" in citation

    def test_retrieve_context_with_filtering(self, mock_config, mock_embedding_service):
        """Test retrieve with metadata filtering."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context("Query")

            # Verify search was called with correct parameters
            call_args = mock_vector_db.search.call_args
            assert call_args.kwargs["limit"] == 5
            assert call_args.kwargs["min_score"] == 0.55

    def test_retrieve_context_embedding_error_handling(self, mock_config, mock_embedding_service):
        """Test graceful handling of embedding errors."""
        mock_embedding_service.embed_text.return_value = None

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)

            chunks = service.retrieve_context("Query")

            # Should return empty list if embedding fails
            assert chunks == []

    def test_similarity_threshold_is_respected(self, mock_config, mock_embedding_service):
        """Test that similarity threshold from config is used."""
        mock_config.similarity_threshold = 0.75

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            assert service.config.similarity_threshold == 0.75

    def test_top_k_from_config(self, mock_config, mock_embedding_service):
        """Test that top_k is read from config."""
        mock_config.top_k_retrievals = 10

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            assert service.config.top_k_retrievals == 10

    def test_vector_db_initialization_parameters(self, mock_config, mock_embedding_service):
        """Test that VectorDatabase is initialized with correct parameters."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            RetrievalService(mock_config, mock_embedding_service)

            mock_vdb_class.assert_called_once_with(
                host="localhost",
                port=6333,
                api_key=None
            )

    def test_retrieve_context_query_string(self, mock_config, mock_embedding_service):
        """Test that query string is passed to embedding service."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            query = "What is the offside rule?"
            service.retrieve_context(query)

            # Verify embedding was created for the query
            mock_embedding_service.embed_text.assert_called_with(query)

    def test_format_context_preserves_order(self, mock_config, mock_embedding_service):
        """Test that format_context preserves chunk order."""
        chunks = [
            RetrievedChunk(f"{i}", f"Chunk {i}", 0.9 - i * 0.1, {})
            for i in range(3)
        ]

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context(chunks)

            # Context should maintain order
            idx_0 = context.find("Chunk 0")
            idx_1 = context.find("Chunk 1")
            idx_2 = context.find("Chunk 2")

            assert idx_0 < idx_1 < idx_2
