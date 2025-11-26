"""Tests for vector database functionality."""
import pytest
from unittest.mock import MagicMock, patch
from src.core.vector_db import VectorDatabase, RetrievedChunk


class TestVectorDatabase:
    """Test VectorDatabase class."""

    def test_initialization(self):
        """Test VectorDatabase initialization."""
        with patch("src.core.vector_db.QdrantClient"):
            db = VectorDatabase(host="localhost", port=6333)
            assert db.host == "localhost"
            assert db.port == 6333

    def test_initialization_with_api_key(self):
        """Test VectorDatabase initialization with API key."""
        with patch("src.core.vector_db.QdrantClient"):
            db = VectorDatabase(
                host="qdrant.example.com",
                port=6333,
                api_key="test-key"
            )
            assert db.api_key == "test-key"

    def test_health_check_success(self):
        """Test successful health check."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock()

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            result = db.health_check()

            assert result is True
            mock_client.get_collections.assert_called_once()

    def test_health_check_failure(self):
        """Test health check failure."""
        mock_client = MagicMock()
        mock_client.get_collections.side_effect = Exception("Connection error")

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            result = db.health_check()

            assert result is False

    def test_search_success(self):
        """Test successful vector search."""
        mock_client = MagicMock()
        mock_point1 = MagicMock()
        mock_point1.id = "1"
        mock_point1.score = 0.95
        mock_point1.payload = {
            "text": "Offside rule explanation",
            "section": "Law 11",
            "document_name": "Laws of Game"
        }

        mock_point2 = MagicMock()
        mock_point2.id = "2"
        mock_point2.score = 0.87
        mock_point2.payload = {
            "text": "Offside in penalty area",
            "section": "Law 11",
            "document_name": "Laws of Game"
        }

        mock_response = MagicMock()
        mock_response.points = [mock_point1, mock_point2]
        mock_client.query_points.return_value = mock_response

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            query_vector = [0.1] * 512
            results = db.search("football_documents", query_vector, limit=5, min_score=0.5)

            assert len(results) == 2
            assert results[0].chunk_id == "1"
            assert results[0].score == 0.95
            assert results[0].text == "Offside rule explanation"
            assert results[0].metadata["section"] == "Law 11"

    def test_search_with_metadata_filter(self):
        """Test search with metadata filter."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            from qdrant_client.models import Filter
            test_filter = Filter()
            db.search(
                "football_documents",
                [0.1] * 512,
                metadata_filter=test_filter
            )

            # Verify filter was passed to query_points
            call_args = mock_client.query_points.call_args
            assert "query_filter" in call_args.kwargs

    def test_search_no_results(self):
        """Test search with no results."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            results = db.search("football_documents", [0.1] * 512)

            assert len(results) == 0

    def test_search_below_score_threshold(self):
        """Test that results below score threshold are excluded."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []  # Qdrant filters by score_threshold parameter
        mock_client.query_points.return_value = mock_response

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            results = db.search(
                "football_documents",
                [0.1] * 512,
                min_score=0.75
            )

            # Verify score threshold was passed
            call_args = mock_client.query_points.call_args
            assert call_args.kwargs["score_threshold"] == 0.75

    def test_upsert_points_success(self):
        """Test successful upserting of points."""
        mock_client = MagicMock()

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            vectors_data = [
                {
                    "id": "1",
                    "vector": [0.1] * 512,
                    "payload": {"text": "Test content", "section": "Law 1"}
                }
            ]

            db.upsert_points("football_documents", vectors_data)

            mock_client.upsert.assert_called_once()


    def test_delete_points_success(self):
        """Test successful deletion of points."""
        mock_client = MagicMock()

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            db.delete_points("football_documents", point_ids=["1", "2"])

            mock_client.delete.assert_called_once()


    def test_collection_exists_true(self):
        """Test checking if collection exists (true case)."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_collection.return_value = mock_collection

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            exists = db.collection_exists("football_documents")

            assert exists is True
            mock_client.get_collection.assert_called_once_with("football_documents")

    def test_collection_exists_false(self):
        """Test checking if collection exists (false case)."""
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Collection not found")

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            exists = db.collection_exists("football_documents")

            assert exists is False

    def test_get_collection_info(self):
        """Test getting collection info."""
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 607
        mock_info.vectors_count = 607
        mock_info.status = "green"
        mock_info.config.params.vectors.size = 512
        mock_info.indexed_vectors_count = 607
        mock_client.get_collection.return_value = mock_info

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            info = db.get_collection_info("football_documents")

            assert isinstance(info, dict)
            assert info["point_count"] == 607
            assert info["vector_size"] == 512

    def test_search_respects_limit_parameter(self):
        """Test that search respects the limit parameter."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        with patch("src.core.vector_db.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value = mock_client

            db = VectorDatabase("localhost", 6333)
            db.client = mock_client

            db.search("football_documents", [0.1] * 512, limit=10)

            call_args = mock_client.query_points.call_args
            assert call_args.kwargs["limit"] == 10

    def test_retrieved_chunk_dataclass(self):
        """Test RetrievedChunk dataclass."""
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Offside rule",
            score=0.95,
            metadata={"section": "Law 11"}
        )

        assert chunk.chunk_id == "1"
        assert chunk.text == "Offside rule"
        assert chunk.score == 0.95
        assert chunk.metadata["section"] == "Law 11"
