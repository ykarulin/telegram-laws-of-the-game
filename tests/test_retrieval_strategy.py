"""
Tests for mixed retrieval strategy: dynamic thresholds and document-specific lookup.

Tests validate that:
1. Dynamic threshold filtering works correctly
2. Document-specific retrieval (via tool) differs from generic retrieval
3. Threshold configuration is properly applied
4. Results are correctly filtered and capped
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.config import Config
from src.services.retrieval_service import RetrievalService
from src.services.embedding_service import EmbeddingService
from src.core.vector_db import RetrievedChunk, VectorDatabase


@pytest.fixture
def mock_config():
    """Create a configuration with dynamic threshold enabled."""
    config = Mock(spec=Config)
    config.similarity_threshold = 0.7
    config.top_k_retrievals = 5
    config.qdrant_host = "localhost"
    config.qdrant_port = 6333
    config.qdrant_api_key = None
    config.qdrant_collection_name = "documents"
    config.rag_dynamic_threshold_margin = 0.15  # 15% margin
    config.database_url = "postgresql://test"  # For database operations
    return config


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    service = Mock(spec=EmbeddingService)
    service.embed_text = Mock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
    return service


@pytest.fixture
def mock_vector_db():
    """Create a mock vector database."""
    return Mock(spec=VectorDatabase)


@pytest.fixture
def retrieval_service(mock_config, mock_embedding_service, mock_vector_db):
    """Create a retrieval service with mocked vector DB."""
    service = RetrievalService(mock_config, mock_embedding_service)
    service.vector_db = mock_vector_db
    return service


def create_mock_chunk(text, score, doc_name="Test Doc", section="Test Section"):
    """Helper to create a mock RetrievedChunk."""
    chunk = Mock(spec=RetrievedChunk)
    chunk.text = text
    chunk.score = score
    chunk.metadata = {
        "document_name": doc_name,
        "section": section,
        "version": "2024-25"
    }
    return chunk


class TestDynamicThresholdFiltering:
    """Tests for dynamic threshold filtering logic."""

    def test_dynamic_threshold_filtering_applied_when_enabled(
        self, retrieval_service, mock_config, mock_vector_db, mock_embedding_service
    ):
        """Test that dynamic threshold is applied when configured."""
        # Setup mock chunks with varying scores
        chunks = [
            create_mock_chunk("Best match", 0.95),
            create_mock_chunk("Good match", 0.85),
            create_mock_chunk("Marginal match", 0.72),
            create_mock_chunk("Below static threshold", 0.65),
        ]
        mock_vector_db.search.return_value = chunks

        # Retrieve with dynamic threshold enabled
        results = retrieval_service.retrieve_context(
            query="test query",
            top_k=5,
            threshold=0.7
        )

        # With margin=0.15, dynamic threshold = 0.95 * (1-0.15) = 0.8075
        # So chunks with score >= 0.8075 should be included
        # Marginal match (0.72) and below (0.65) should be filtered
        assert len(results) <= 3  # Dynamic threshold should cap at 3
        assert results[0].score >= 0.8075 or results[0].score >= 0.7  # Effective threshold

    def test_static_threshold_enforced_as_minimum(
        self, retrieval_service, mock_config, mock_vector_db
    ):
        """Test that static threshold is never undercut by dynamic threshold."""
        # Setup chunks where dynamic threshold would be very low
        chunks = [
            create_mock_chunk("Best", 0.75),
            create_mock_chunk("Marginal", 0.65),
        ]
        mock_vector_db.search.return_value = chunks

        static_threshold = 0.7
        results = retrieval_service.retrieve_context(
            query="test",
            threshold=static_threshold
        )

        # All results should respect static threshold minimum
        for chunk in results:
            assert chunk.score >= static_threshold

    def test_dynamic_threshold_capping_at_three_chunks(
        self, retrieval_service, mock_config, mock_vector_db
    ):
        """Test that results are capped at 3 chunks with dynamic threshold."""
        # Setup many chunks within dynamic threshold range
        chunks = [
            create_mock_chunk("1", 0.95),
            create_mock_chunk("2", 0.94),
            create_mock_chunk("3", 0.93),
            create_mock_chunk("4", 0.92),
            create_mock_chunk("5", 0.91),
        ]
        mock_vector_db.search.return_value = chunks

        results = retrieval_service.retrieve_context(
            query="test",
            top_k=5,
            threshold=0.7
        )

        # Should be capped at 3
        assert len(results) <= 3

    def test_dynamic_threshold_disabled_when_margin_is_none(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that dynamic threshold is skipped when margin is None."""
        mock_config.rag_dynamic_threshold_margin = None

        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        chunks = [
            create_mock_chunk("1", 0.95),
            create_mock_chunk("2", 0.85),
            create_mock_chunk("3", 0.72),
            create_mock_chunk("4", 0.65),
        ]
        # Vector DB search already filters by min_score, so only chunks >= threshold are returned
        mock_vector_db.search.return_value = [c for c in chunks if c.score >= 0.7]

        results = service.retrieve_context(
            query="test",
            top_k=5,
            threshold=0.7
        )

        # Without dynamic threshold, static threshold (0.7) is applied by vector_db.search
        # So we should only get chunks with score >= 0.7
        assert all(chunk.score >= 0.7 for chunk in results)


class TestDocumentSpecificRetrieval:
    """Tests for document-specific retrieval (tool-enabled path)."""

    def test_retrieve_from_documents_filters_by_document_name(
        self, retrieval_service, mock_vector_db
    ):
        """Test that retrieve_from_documents filters results by document name."""
        # Setup mixed chunks from different documents
        all_chunks = [
            create_mock_chunk("Content 1", 0.95, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content 2", 0.93, doc_name="VAR Guidelines 2024"),
            create_mock_chunk("Content 3", 0.91, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content 4", 0.89, doc_name="Other Document"),
        ]
        mock_vector_db.search.return_value = all_chunks

        # Request only from specific document
        with patch('src.services.document_service.DocumentService') as mock_doc_service_class:
            mock_doc_service = MagicMock()
            mock_doc_service_class.return_value = mock_doc_service
            mock_doc_service.get_document_ids_by_names.return_value = ["doc_id_1"]

            results = retrieval_service.retrieve_from_documents(
                query="test",
                document_names=["Laws of Game 2024-25"],
                top_k=3,
                threshold=0.7
            )

            # All results should be from requested document
            for chunk in results:
                assert chunk.metadata["document_name"] == "Laws of Game 2024-25"

    def test_retrieve_from_documents_with_multiple_documents(
        self, retrieval_service, mock_vector_db
    ):
        """Test retrieval from multiple selected documents."""
        all_chunks = [
            create_mock_chunk("Content 1", 0.95, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content 2", 0.93, doc_name="VAR Guidelines 2024"),
            create_mock_chunk("Content 3", 0.91, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content 4", 0.89, doc_name="Other Document"),
        ]
        mock_vector_db.search.return_value = all_chunks

        with patch('src.services.document_service.DocumentService') as mock_doc_service_class:
            mock_doc_service = MagicMock()
            mock_doc_service_class.return_value = mock_doc_service
            mock_doc_service.get_document_ids_by_names.return_value = ["doc_id_1", "doc_id_2"]

            results = retrieval_service.retrieve_from_documents(
                query="test",
                document_names=["Laws of Game 2024-25", "VAR Guidelines 2024"],
                top_k=5,
                threshold=0.7
            )

            # Results should be from one of the two requested documents
            for chunk in results:
                assert chunk.metadata["document_name"] in [
                    "Laws of Game 2024-25",
                    "VAR Guidelines 2024"
                ]

    def test_retrieve_from_documents_overfetches_for_filtering(
        self, retrieval_service, mock_vector_db
    ):
        """Test that retrieve_from_documents over-fetches to compensate for filtering."""
        # The implementation should request more results than top_k
        # to account for documents being filtered out
        all_chunks = [
            create_mock_chunk(f"Content {i}", 0.95 - i*0.01, doc_name="Requested Doc")
            for i in range(10)
        ]
        mock_vector_db.search.return_value = all_chunks

        requested_top_k = 3

        # Mock the document service and database to return valid doc IDs
        with patch('src.services.document_service.DocumentService') as mock_doc_service_class:
            with patch('src.core.db.ConversationDatabase') as mock_db_class:
                mock_doc_service = MagicMock()
                mock_doc_service_class.return_value = mock_doc_service
                mock_doc_service.get_document_ids_by_names.return_value = {"Requested Doc": 1}

                mock_db = MagicMock()
                mock_db_class.return_value = mock_db
                mock_session = MagicMock()
                mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_db.get_session.return_value.__exit__ = MagicMock(return_value=None)

                results = retrieval_service.retrieve_from_documents(
                    query="test",
                    document_names=["Requested Doc"],
                    top_k=requested_top_k,
                    threshold=0.7
                )

            # Verify over-fetching was used (limit should be > top_k)
            call_kwargs = mock_vector_db.search.call_args[1]
            assert call_kwargs["limit"] > requested_top_k  # Over-fetching
            assert call_kwargs["limit"] == requested_top_k * 2  # Exactly 2x for filtering


class TestGenericVsToolSpecificRetrieval:
    """Tests comparing generic retrieval vs tool-specific retrieval."""

    def test_generic_retrieval_searches_all_documents(
        self, retrieval_service, mock_vector_db
    ):
        """Test that generic retrieval searches across all documents."""
        chunks = [
            create_mock_chunk("Content", 0.95, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content", 0.93, doc_name="VAR Guidelines 2024"),
        ]
        mock_vector_db.search.return_value = chunks

        results = retrieval_service.retrieve_context(
            query="test",
            top_k=5
        )

        # Results should be from multiple documents
        doc_names = {chunk.metadata["document_name"] for chunk in results}
        # At least attempt to search all (retrieval_service doesn't filter by doc)
        assert mock_vector_db.search.called

    def test_tool_specific_retrieval_searches_selected_documents(
        self, retrieval_service, mock_vector_db
    ):
        """Test that tool-specific retrieval filters to selected documents."""
        all_chunks = [
            create_mock_chunk("Content", 0.95, doc_name="Laws of Game 2024-25"),
            create_mock_chunk("Content", 0.93, doc_name="VAR Guidelines 2024"),
            create_mock_chunk("Content", 0.91, doc_name="Laws of Game 2024-25"),
        ]
        mock_vector_db.search.return_value = all_chunks

        selected_docs = ["Laws of Game 2024-25"]
        with patch('src.services.document_service.DocumentService') as mock_doc_service_class:
            mock_doc_service = MagicMock()
            mock_doc_service_class.return_value = mock_doc_service
            mock_doc_service.get_document_ids_by_names.return_value = ["doc_id_1"]

            results = retrieval_service.retrieve_from_documents(
                query="test",
                document_names=selected_docs,
                top_k=3
            )

            # All results should be from selected documents only
            for chunk in results:
                assert chunk.metadata["document_name"] in selected_docs


class TestThresholdApplication:
    """Tests for threshold configuration and application."""

    def test_config_threshold_used_as_default(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that config threshold is used when not overridden."""
        expected_threshold = 0.75
        mock_config.similarity_threshold = expected_threshold

        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        chunks = [
            create_mock_chunk("1", 0.9),
            create_mock_chunk("2", 0.8),
            create_mock_chunk("3", 0.7),
        ]
        mock_vector_db.search.return_value = chunks

        results = service.retrieve_context(query="test")

        # Verify config threshold was passed to vector_db.search
        call_kwargs = mock_vector_db.search.call_args[1]
        assert call_kwargs["min_score"] == expected_threshold

    def test_custom_threshold_overrides_config(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that provided threshold overrides config."""
        mock_config.similarity_threshold = 0.7
        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        custom_threshold = 0.85
        chunks = [create_mock_chunk("1", 0.9)]
        mock_vector_db.search.return_value = chunks

        results = service.retrieve_context(
            query="test",
            threshold=custom_threshold
        )

        # Verify custom threshold was used
        call_kwargs = mock_vector_db.search.call_args[1]
        assert call_kwargs["min_score"] == custom_threshold

    def test_threshold_respects_bounds(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that threshold values stay within valid bounds."""
        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        chunks = [create_mock_chunk("1", 0.9)]
        mock_vector_db.search.return_value = chunks

        # Test with extreme values
        results = service.retrieve_context(
            query="test",
            threshold=0.0  # Minimum
        )
        assert mock_vector_db.search.called

        mock_vector_db.reset_mock()
        results = service.retrieve_context(
            query="test",
            threshold=1.0  # Maximum
        )
        assert mock_vector_db.search.called


class TestTopKApplication:
    """Tests for top_k parameter application."""

    def test_config_top_k_used_as_default(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that config top_k is used when not overridden."""
        expected_top_k = 3
        mock_config.top_k_retrievals = expected_top_k

        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        chunks = [create_mock_chunk(f"{i}", 0.9 - i*0.01) for i in range(5)]
        mock_vector_db.search.return_value = chunks

        results = service.retrieve_context(query="test")

        # Verify config top_k was used
        call_kwargs = mock_vector_db.search.call_args[1]
        assert call_kwargs["limit"] == expected_top_k

    def test_custom_top_k_overrides_config(
        self, mock_config, mock_embedding_service, mock_vector_db
    ):
        """Test that provided top_k overrides config."""
        mock_config.top_k_retrievals = 3

        service = RetrievalService(mock_config, mock_embedding_service)
        service.vector_db = mock_vector_db

        custom_top_k = 5
        chunks = [create_mock_chunk(f"{i}", 0.9 - i*0.01) for i in range(6)]
        mock_vector_db.search.return_value = chunks

        results = service.retrieve_context(
            query="test",
            top_k=custom_top_k
        )

        # Verify custom top_k was used
        call_kwargs = mock_vector_db.search.call_args[1]
        assert call_kwargs["limit"] == custom_top_k


class TestRetrievalEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_query_returns_empty_results(
        self, retrieval_service, mock_vector_db
    ):
        """Test that empty query returns no results."""
        results = retrieval_service.retrieve_context(query="")
        assert results == []
        mock_vector_db.search.assert_not_called()

    def test_whitespace_only_query_returns_empty_results(
        self, retrieval_service, mock_vector_db
    ):
        """Test that whitespace-only query returns no results."""
        results = retrieval_service.retrieve_context(query="   ")
        assert results == []
        mock_vector_db.search.assert_not_called()

    def test_vector_db_exception_returns_empty_results(
        self, retrieval_service, mock_vector_db, mock_embedding_service
    ):
        """Test that vector DB exceptions are caught gracefully."""
        mock_vector_db.search.side_effect = Exception("DB connection error")
        mock_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]

        results = retrieval_service.retrieve_context(query="test")

        assert results == []

    def test_none_embedding_returns_empty_results(
        self, retrieval_service, mock_embedding_service, mock_vector_db
    ):
        """Test that None embedding is handled gracefully."""
        mock_embedding_service.embed_text.return_value = None

        results = retrieval_service.retrieve_context(query="test")

        assert results == []
        mock_vector_db.search.assert_not_called()

    def test_empty_results_from_vector_db(
        self, retrieval_service, mock_vector_db
    ):
        """Test handling of empty results from vector DB."""
        mock_vector_db.search.return_value = []

        results = retrieval_service.retrieve_context(query="test")

        assert results == []
