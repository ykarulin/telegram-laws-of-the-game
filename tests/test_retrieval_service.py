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
        config.rag_dynamic_threshold_margin = None
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


class TestDynamicThreshold:
    """Test dynamic threshold filtering functionality."""

    @pytest.fixture
    def mock_config_with_dynamic(self):
        """Create a mock config with dynamic threshold enabled."""
        config = MagicMock()
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.top_k_retrievals = 3
        config.similarity_threshold = 0.7
        config.rag_dynamic_threshold_margin = 0.15  # 15% margin
        return config

    @pytest.fixture
    def mock_config_without_dynamic(self):
        """Create a mock config with dynamic threshold disabled."""
        config = MagicMock()
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.top_k_retrievals = 3
        config.similarity_threshold = 0.7
        config.rag_dynamic_threshold_margin = None
        return config

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = MagicMock()
        service.embed_text.return_value = [0.1] * 512
        return service

    def test_dynamic_threshold_filters_chunks(self, mock_config_with_dynamic, mock_embedding_service):
        """Test that dynamic threshold filters chunks correctly."""
        # Chunks: 0.95, 0.85, 0.75, 0.65, 0.55
        # Best score: 0.95, margin: 0.15
        # Dynamic threshold: 0.95 * (1 - 0.15) = 0.95 * 0.85 = 0.8075
        # Should include: 0.95, 0.85 (but not 0.75, 0.65, 0.55)
        chunks = [
            RetrievedChunk("1", "Text 1", 0.95, {}),
            RetrievedChunk("2", "Text 2", 0.85, {}),
            RetrievedChunk("3", "Text 3", 0.75, {}),
            RetrievedChunk("4", "Text 4", 0.65, {}),
            RetrievedChunk("5", "Text 5", 0.55, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("What is VAR?")

            # Should have filtered to 2 chunks (0.95 and 0.85)
            assert len(result) == 2
            assert result[0].score == 0.95
            assert result[1].score == 0.85

    def test_dynamic_threshold_respects_static_minimum(self, mock_config_with_dynamic, mock_embedding_service):
        """Test that dynamic threshold never goes below static threshold."""
        # Chunks: 0.75, 0.65, 0.55
        # Best score: 0.75, margin: 0.15
        # Dynamic threshold: 0.75 * (1 - 0.15) = 0.75 * 0.85 = 0.6375
        # But static threshold is 0.7, so effective threshold = max(0.6375, 0.7) = 0.7
        # Should include: 0.75 (but not 0.65, 0.55)
        chunks = [
            RetrievedChunk("1", "Text 1", 0.75, {}),
            RetrievedChunk("2", "Text 2", 0.65, {}),
            RetrievedChunk("3", "Text 3", 0.55, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Should have only 1 chunk (0.75)
            assert len(result) == 1
            assert result[0].score == 0.75

    def test_dynamic_threshold_caps_at_3_chunks(self, mock_config_with_dynamic, mock_embedding_service):
        """Test that dynamic threshold results are capped at 3 chunks."""
        # Chunks: 0.95, 0.90, 0.87, 0.85, 0.83
        # Best score: 0.95, margin: 0.15
        # Dynamic threshold: 0.95 * (1 - 0.15) = 0.8075
        # All chunks above 0.8075 would be: 0.95, 0.90, 0.87, 0.85, 0.83
        # But should be capped at 3
        chunks = [
            RetrievedChunk("1", "Text 1", 0.95, {}),
            RetrievedChunk("2", "Text 2", 0.90, {}),
            RetrievedChunk("3", "Text 3", 0.87, {}),
            RetrievedChunk("4", "Text 4", 0.85, {}),
            RetrievedChunk("5", "Text 5", 0.83, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Should be capped at 3
            assert len(result) == 3
            assert result[0].score == 0.95
            assert result[1].score == 0.90
            assert result[2].score == 0.87

    def test_dynamic_threshold_disabled_returns_all_chunks(self, mock_config_without_dynamic, mock_embedding_service):
        """Test that without dynamic threshold, all valid chunks are returned."""
        # Without dynamic threshold, should respect original top_k and static threshold
        chunks = [
            RetrievedChunk("1", "Text 1", 0.95, {}),
            RetrievedChunk("2", "Text 2", 0.85, {}),
            RetrievedChunk("3", "Text 3", 0.75, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_without_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Should return all 3 (no dynamic filtering)
            assert len(result) == 3

    def test_apply_dynamic_threshold_direct_call(self, mock_config_with_dynamic, mock_embedding_service):
        """Test _apply_dynamic_threshold method directly."""
        chunks = [
            RetrievedChunk("1", "Text 1", 0.95, {}),
            RetrievedChunk("2", "Text 2", 0.85, {}),
            RetrievedChunk("3", "Text 3", 0.75, {}),
            RetrievedChunk("4", "Text 4", 0.65, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            result = service._apply_dynamic_threshold(chunks, 0.7)

            # Expected: dynamic_threshold = 0.95 * (1 - 0.15) = 0.8075
            # Effective = max(0.8075, 0.7) = 0.8075
            # Should include: 0.95, 0.85
            assert len(result) == 2
            assert result[0].score == 0.95
            assert result[1].score == 0.85

    def test_apply_dynamic_threshold_empty_chunks(self, mock_config_with_dynamic, mock_embedding_service):
        """Test _apply_dynamic_threshold with empty chunk list."""
        with patch("src.services.retrieval_service.VectorDatabase"):
            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            result = service._apply_dynamic_threshold([], 0.7)

            assert result == []

    def test_dynamic_threshold_single_chunk(self, mock_config_with_dynamic, mock_embedding_service):
        """Test dynamic threshold with only one chunk."""
        chunks = [RetrievedChunk("1", "Text 1", 0.95, {})]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Single chunk should be included
            assert len(result) == 1
            assert result[0].score == 0.95

    def test_dynamic_threshold_preserves_order(self, mock_config_with_dynamic, mock_embedding_service):
        """Test that dynamic threshold preserves chunk order."""
        chunks = [
            RetrievedChunk("1", "Text 1", 0.95, {}),
            RetrievedChunk("2", "Text 2", 0.88, {}),
            RetrievedChunk("3", "Text 3", 0.85, {}),
            RetrievedChunk("4", "Text 4", 0.75, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Check order is preserved (descending by score)
            assert result[0].score >= result[1].score
            if len(result) > 2:
                assert result[1].score >= result[2].score

    def test_dynamic_threshold_margin_calculation(self, mock_config_with_dynamic, mock_embedding_service):
        """Test the mathematical correctness of dynamic threshold calculation."""
        # Margin of 0.20 (20%)
        mock_config_with_dynamic.rag_dynamic_threshold_margin = 0.20

        chunks = [
            RetrievedChunk("1", "Text 1", 0.90, {}),
            RetrievedChunk("2", "Text 2", 0.80, {}),
            RetrievedChunk("3", "Text 3", 0.70, {}),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config_with_dynamic, mock_embedding_service)
            service.vector_db = mock_vector_db

            result = service.retrieve_context("Query")

            # Best score: 0.90, margin: 0.20
            # Dynamic threshold: 0.90 * (1 - 0.20) = 0.90 * 0.80 = 0.72
            # Effective = max(0.72, 0.7) = 0.72
            # Should include: 0.90, 0.80 (0.70 is below 0.72)
            assert len(result) == 2
            assert all(chunk.score >= 0.72 for chunk in result)
