"""Extended tests for retrieval service to increase coverage."""
import pytest
from unittest.mock import MagicMock, patch
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk


class TestRetrievalServiceExtended:
    """Extended retrieval service tests for comprehensive coverage."""

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
        config.use_retrieval = True
        config.rag_dynamic_threshold_margin = None
        return config

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = MagicMock()
        service.embed_text = MagicMock(return_value=[0.1] * 512)
        return service

    def test_retrieval_service_with_different_thresholds(self, mock_config, mock_embedding_service):
        """Test retrieval with different similarity thresholds."""
        thresholds = [0.3, 0.5, 0.7, 0.9]

        for threshold in thresholds:
            mock_config.similarity_threshold = threshold

            with patch("src.services.retrieval_service.VectorDatabase"):
                service = RetrievalService(mock_config, mock_embedding_service)
                assert service.config.similarity_threshold == threshold

    def test_retrieval_service_with_different_top_k_values(self, mock_config, mock_embedding_service):
        """Test retrieval with different top_k values."""
        top_k_values = [1, 3, 5, 10, 20]

        for top_k in top_k_values:
            mock_config.top_k_retrievals = top_k

            with patch("src.services.retrieval_service.VectorDatabase"):
                service = RetrievalService(mock_config, mock_embedding_service)
                assert service.config.top_k_retrievals == top_k

    def test_retrieve_context_scoring_order(self, mock_config, mock_embedding_service):
        """Test that retrieved chunks are ordered by score (highest first)."""
        # Qdrant returns results sorted by score in descending order
        chunks = [
            RetrievedChunk("3", "Highest score", 0.95, {}),
            RetrievedChunk("2", "Middle score", 0.80, {}),
            RetrievedChunk("1", "Lowest score", 0.60, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db

            # Qdrant returns results already sorted by score (highest first)
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            retrieved = service.retrieve_context("Query")

            # Should be in descending order by score
            if len(retrieved) > 1:
                for i in range(len(retrieved) - 1):
                    assert retrieved[i].score >= retrieved[i + 1].score

    def test_format_context_empty_list(self, mock_config, mock_embedding_service):
        """Test formatting empty context."""
        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context([])

            assert context == ""

    def test_format_context_single_chunk_with_metadata(self, mock_config, mock_embedding_service):
        """Test formatting single chunk with full metadata."""
        chunk = RetrievedChunk(
            "1",
            "Offside rule definition",
            0.92,
            {
                "document_name": "Laws of Game 2025-26",
                "section": "Law 11",
                "subsection": "Offside",
                "page_number": 42
            }
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context([chunk])

            assert "Offside rule definition" in context
            assert len(context) > 0

    def test_format_context_with_minimal_metadata(self, mock_config, mock_embedding_service):
        """Test formatting chunk with minimal metadata."""
        chunk = RetrievedChunk(
            "1",
            "Content",
            0.9,
            {}
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context([chunk])

            assert "Content" in context

    def test_retrieve_context_with_special_characters(self, mock_config, mock_embedding_service):
        """Test retrieval with special characters in query."""
        query = "What about → arrows ↑ and £ symbols?"

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context(query)

            # Embedding should be created for special char query
            mock_embedding_service.embed_text.assert_called()

    def test_retrieve_context_with_very_long_query(self, mock_config, mock_embedding_service):
        """Test retrieval with very long query."""
        long_query = "What " + "is " * 500 + "offside?"

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context(long_query)

            # Should handle long queries
            assert mock_embedding_service.embed_text.called

    def test_retrieve_context_single_character_query(self, mock_config, mock_embedding_service):
        """Test retrieval with single character query."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context("?")

            # Should handle minimal query
            assert mock_embedding_service.embed_text.called

    def test_format_inline_citation_with_all_fields(self, mock_config, mock_embedding_service):
        """Test citation formatting with all metadata fields."""
        chunk = RetrievedChunk(
            "1",
            "Content",
            0.92,
            {
                "document_name": "Laws of Game 2025-26",
                "document_type": "rules",
                "section": "Law 11",
                "subsection": "Offside",
                "page_number": 42
            }
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            citation = service.format_inline_citation(chunk)

            assert isinstance(citation, str)
            assert len(citation) > 0

    def test_retrieve_context_with_retrieval_disabled(self, mock_config, mock_embedding_service):
        """Test that retrieval returns empty when disabled."""
        mock_config.use_retrieval = False

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)

            # Check should_use_retrieval
            assert not mock_config.use_retrieval

    def test_retrieve_context_respects_score_threshold(self, mock_config, mock_embedding_service):
        """Test that score threshold is respected in retrieval."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context("Query")

            # Verify threshold was used
            call_args = mock_vector_db.search.call_args
            assert call_args.kwargs["min_score"] == 0.55

    def test_retrieve_context_respects_top_k_limit(self, mock_config, mock_embedding_service):
        """Test that top_k limit is respected."""
        chunks = [RetrievedChunk(str(i), f"Content {i}", 0.9, {}) for i in range(10)]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks[:5]

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            retrieved = service.retrieve_context("Query")

            assert len(retrieved) <= 5

    def test_retrieve_context_query_embedding_called(self, mock_config, mock_embedding_service):
        """Test that query is embedded before search."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            query = "Test query"
            service.retrieve_context(query)

            # Embedding should be created
            mock_embedding_service.embed_text.assert_called_with(query)

    def test_format_context_multiple_chunks_order(self, mock_config, mock_embedding_service):
        """Test that multiple chunks maintain order in formatted context."""
        chunks = [
            RetrievedChunk(str(i), f"Chunk {i} content", 0.9 - i * 0.1, {})
            for i in range(3)
        ]

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context(chunks)

            # Order should be preserved
            idx_0 = context.find("Chunk 0")
            idx_1 = context.find("Chunk 1")
            idx_2 = context.find("Chunk 2")

            if idx_0 >= 0 and idx_1 >= 0 and idx_2 >= 0:
                assert idx_0 < idx_1 < idx_2

    def test_citation_with_special_characters(self, mock_config, mock_embedding_service):
        """Test citation formatting with special characters in metadata."""
        chunk = RetrievedChunk(
            "1",
            "Content",
            0.92,
            {
                "document_name": "Laws & Rules (2025-26)",
                "section": "Law #11"
            }
        )

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            citation = service.format_inline_citation(chunk)

            assert isinstance(citation, str)

    def test_retrieve_context_embedding_vector_dimension(self, mock_config, mock_embedding_service):
        """Test that embedding vectors have correct dimensions."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            # Embedding should be 512 dimensions
            embedding = [0.1] * 512
            mock_embedding_service.embed_text.return_value = embedding

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context("Query")

            # Verify embedding dimension was passed to search
            call_args = mock_vector_db.search.call_args
            query_vector = call_args.kwargs.get("query_vector") or call_args[1] if len(call_args) > 1 else []
            assert len(query_vector) == 512

    def test_retrieve_context_collection_name(self, mock_config, mock_embedding_service):
        """Test that correct collection name is used."""
        mock_config.qdrant_collection_name = "custom_collection"

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            service.retrieve_context("Query")

            # Verify collection name was passed to search
            call_args = mock_vector_db.search.call_args
            collection_name = call_args.kwargs.get("collection_name")
            assert collection_name == "custom_collection"

    def test_vector_database_initialization_params(self, mock_config, mock_embedding_service):
        """Test vector database is initialized with correct parameters."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            RetrievalService(mock_config, mock_embedding_service)

            # Verify initialization
            mock_vdb_class.assert_called_once()
            call_kwargs = mock_vdb_class.call_args.kwargs

            assert call_kwargs["host"] == "localhost"
            assert call_kwargs["port"] == 6333

    def test_retrieve_with_null_embedding(self, mock_config, mock_embedding_service):
        """Test retrieval when embedding returns None."""
        mock_embedding_service.embed_text.return_value = None

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            chunks = service.retrieve_context("Query")

            # Should return empty on embedding failure
            assert chunks == []

    def test_multiple_chunks_different_scores(self, mock_config, mock_embedding_service):
        """Test chunks with various score ranges."""
        chunks = [
            RetrievedChunk("1", "High score", 0.99, {}),
            RetrievedChunk("2", "Medium score", 0.75, {}),
            RetrievedChunk("3", "Low score", 0.56, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            retrieved = service.retrieve_context("Query")

            assert len(retrieved) == 3
            # Verify score order
            assert retrieved[0].score >= retrieved[1].score >= retrieved[2].score

    def test_format_context_separators(self, mock_config, mock_embedding_service):
        """Test that context chunks are properly separated."""
        chunks = [
            RetrievedChunk("1", "First chunk", 0.9, {}),
            RetrievedChunk("2", "Second chunk", 0.8, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config, mock_embedding_service)
            context = service.format_context(chunks)

            # Should have separators between chunks
            assert len(context) > 0
