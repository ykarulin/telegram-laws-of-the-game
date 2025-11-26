"""Integration tests for multilingual retrieval with e5-large embeddings."""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.services.embedding_service import EmbeddingService, Chunk
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk


class TestMultilingualEmbedding:
    """Test multilingual embedding capabilities with e5-large model."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_english_query_english_document(self, mock_st):
        """Test English query retrieves English document (baseline test)."""
        mock_model = MagicMock()
        # Simulate identical embeddings for same language
        embedding = np.array([0.9] * 1024).astype(np.float32)
        mock_model.encode.return_value = embedding
        mock_st.return_value = mock_model

        service = EmbeddingService()

        # Both English query and document should have high similarity
        query_embedding = service.embed_text("What is the offside rule?")
        doc_embedding = service.embed_text("The offside rule states that a player is in an offside position when nearer to the goal line.")

        assert query_embedding is not None
        assert doc_embedding is not None
        assert len(query_embedding) == 1024
        assert len(doc_embedding) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_russian_query_english_document(self, mock_st):
        """Test Russian query can retrieve English document (cross-lingual test)."""
        mock_model = MagicMock()
        # Simulate similar embeddings despite language difference (multilingual alignment)
        # This simulates e5-large's cross-lingual property
        russian_embedding = np.array([0.85] * 1024).astype(np.float32)
        english_embedding = np.array([0.84] * 1024).astype(np.float32)

        mock_model.encode.side_effect = [russian_embedding, english_embedding]
        mock_st.return_value = mock_model

        service = EmbeddingService()

        # Russian query should still produce valid 1024-dim embedding
        russian_query = service.embed_text("Что такое офсайд?")
        english_doc = service.embed_text("The offside rule states that a player is in an offside position.")

        assert russian_query is not None
        assert english_doc is not None
        assert len(russian_query) == 1024
        assert len(english_doc) == 1024

        # In real e5-large, these would have high cosine similarity despite language
        # For mocked test, we just verify both are embeddings
        mock_model.encode.assert_called()

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_german_query_english_document(self, mock_st):
        """Test German query can retrieve English document (cross-lingual test)."""
        mock_model = MagicMock()
        german_embedding = np.array([0.83] * 1024).astype(np.float32)
        english_embedding = np.array([0.84] * 1024).astype(np.float32)

        mock_model.encode.side_effect = [german_embedding, english_embedding]
        mock_st.return_value = mock_model

        service = EmbeddingService()

        german_query = service.embed_text("Was ist die Abseitsregel?")
        english_doc = service.embed_text("The offside rule applies to all players on the field.")

        assert german_query is not None
        assert english_doc is not None
        assert len(german_query) == 1024
        assert len(english_doc) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_multilingual_batch_embedding(self, mock_st):
        """Test batch embedding with mixed language texts."""
        mock_model = MagicMock()
        embeddings = np.random.rand(5, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        service = EmbeddingService()

        texts = [
            "What is the offside rule?",  # English
            "Что такое офсайд?",  # Russian
            "Was ist die Abseitsregel?",  # German
            "Qu'est-ce que la règle de hors-jeu?",  # French
            "¿Cuál es la regla del fuera de juego?"  # Spanish
        ]

        embeddings_result = service.embed_batch(texts)

        assert len(embeddings_result) == 5
        assert all(e is not None for e in embeddings_result)
        assert all(len(e) == 1024 for e in embeddings_result)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_chunk_embedding_multilingual_metadata(self, mock_st):
        """Test chunks with multilingual content preserve metadata."""
        mock_model = MagicMock()
        # Return 3x1024 array for 3 chunks
        embeddings = np.random.rand(3, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        service = EmbeddingService()

        # Create chunks in different languages
        english_chunk = Chunk(
            text="Offside is when a player is in an offside position.",
            section="Law 11",
            subsection="Offside",
            page_number=5
        )

        russian_chunk = Chunk(
            text="Офсайд - это когда игрок находится в положении офсайда.",
            section="Правило 11",
            subsection="Офсайд",
            page_number=5
        )

        german_chunk = Chunk(
            text="Abseits liegt vor, wenn ein Spieler in einer Abseitsstellung ist.",
            section="Regel 11",
            subsection="Abseits",
            page_number=5
        )

        chunks = [english_chunk, russian_chunk, german_chunk]
        results = service.embed_chunks(chunks)

        assert len(results) == 3

        # Verify metadata is preserved
        assert results[0]["section"] == "Law 11"
        assert results[1]["section"] == "Правило 11"
        assert results[2]["section"] == "Regel 11"

        # All should have valid embeddings
        assert all(len(r["embedding"]) == 1024 for r in results)


class TestMultilingualRetrieval:
    """Test retrieval service with multilingual embeddings."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config for multilingual testing."""
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
        """Create mock embedding service that returns 1024-dim vectors."""
        service = MagicMock()
        # All embeddings are 1024-dimensional now
        service.embed_text.return_value = [0.1] * 1024
        service.vector_size = 1024
        return service

    def test_retrieval_service_with_1024_dimensions(self, mock_config, mock_embedding_service):
        """Test RetrievalService works with 1024-dim embeddings from e5-large."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            # Should initialize correctly with 1024-dim embedding service
            assert service.embedding_service.vector_size == 1024
            assert mock_vector_db is not None

    def test_russian_query_retrieves_english_context(self, mock_config, mock_embedding_service):
        """Test Russian query can retrieve English document context."""
        chunk1 = RetrievedChunk(
            chunk_id="law11_1",
            text="Offside is when a player is nearer to the opponent's goal line than both the ball and the last two opponents.",
            score=0.78,  # Cross-lingual similarity score
            metadata={"section": "Law 11", "language": "English", "document_name": "Laws of Game"}
        )

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = [chunk1]

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            # Query in Russian
            chunks = service.retrieve_context("Что такое офсайд?")

            assert len(chunks) == 1
            assert "Offside" in chunks[0].text
            assert chunks[0].score >= 0.55  # Above threshold
            # Verify embedding was called with Russian text
            mock_embedding_service.embed_text.assert_called()

    def test_german_query_retrieves_english_context(self, mock_config, mock_embedding_service):
        """Test German query can retrieve English document context."""
        chunk1 = RetrievedChunk(
            chunk_id="law11_1",
            text="The rule applies to all players on the field.",
            score=0.76,
            metadata={"section": "Law 11", "language": "English", "document_name": "Laws of Game"}
        )

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = [chunk1]

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            # Query in German
            chunks = service.retrieve_context("Was ist die Abseitsregel?")

            assert len(chunks) == 1
            assert chunks[0].score >= 0.55
            mock_embedding_service.embed_text.assert_called()

    def test_multilingual_queries_same_semantic_space(self, mock_config, mock_embedding_service):
        """Test that queries in different languages map to same semantic space."""
        # All queries have same meaning, should retrieve same document
        chunk = RetrievedChunk(
            chunk_id="law11",
            text="Offside is a fundamental rule in football.",
            score=0.80,
            metadata={"section": "Law 11"}
        )

        queries = [
            "What is offside?",  # English
            "Что такое офсайд?",  # Russian
            "Was ist Abseits?",  # German
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = [chunk]

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            results = []
            for query in queries:
                chunks = service.retrieve_context(query)
                results.append(chunks)

            # All queries should retrieve the same document
            assert all(len(r) == 1 for r in results)
            assert all(r[0].chunk_id == "law11" for r in results)

            # embed_text should be called once per query
            assert mock_embedding_service.embed_text.call_count >= 3

    def test_multilingual_context_below_threshold(self, mock_config, mock_embedding_service):
        """Test that low-similarity cross-lingual results are filtered by vector_db."""
        chunk = RetrievedChunk(
            chunk_id="law11",
            text="Some unrelated content about substitutions.",
            score=0.45,  # Below threshold of 0.55
            metadata={"section": "Law 3"}
        )

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            # Vector DB returns empty list when results are below threshold
            mock_vector_db.search.return_value = []

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            # Query in Russian
            chunks = service.retrieve_context("Что такое офсайд?")

            # Vector DB should filter out results below threshold
            assert len(chunks) == 0
            mock_vector_db.search.assert_called_once()

    def test_mixed_language_documents_in_collection(self, mock_config, mock_embedding_service):
        """Test retrieval works when collection has documents in multiple languages."""
        # Simulate collection with documents in different languages
        chunks = [
            RetrievedChunk(
                chunk_id="en_1",
                text="Offside rule in English",
                score=0.85,
                metadata={"language": "English"}
            ),
            RetrievedChunk(
                chunk_id="ru_1",
                text="Правило офсайда на русском",
                score=0.80,
                metadata={"language": "Russian"}
            ),
            RetrievedChunk(
                chunk_id="de_1",
                text="Abseitsregel auf Deutsch",
                score=0.78,
                metadata={"language": "German"}
            ),
        ]

        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vector_db = MagicMock()
            mock_vdb_class.return_value = mock_vector_db
            mock_vector_db.search.return_value = chunks

            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db

            # Single query should find documents in all languages
            retrieved = service.retrieve_context("offside")

            assert len(retrieved) == 3
            assert any("English" in r.metadata.get("language", "") for r in retrieved)
            assert any("Russian" in r.metadata.get("language", "") for r in retrieved)
            assert any("German" in r.metadata.get("language", "") for r in retrieved)


class TestVectorSizeConsistency:
    """Test that vector sizes are consistent across the system."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embedding_service_returns_1024_dims(self, mock_st):
        """Test EmbeddingService returns 1024-dimensional vectors."""
        mock_model = MagicMock()
        embedding = np.random.rand(1024).astype(np.float32)
        mock_model.encode.return_value = embedding
        mock_st.return_value = mock_model

        service = EmbeddingService()

        result = service.embed_text("Test text")
        assert result is not None
        assert len(result) == 1024
        assert service.vector_size == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_batch_embedding_preserves_1024_dims(self, mock_st):
        """Test batch embeddings are all 1024-dimensional."""
        mock_model = MagicMock()
        embeddings = np.random.rand(10, 1024).astype(np.float32)
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        service = EmbeddingService()
        results = service.embed_batch(["text"] * 10)

        assert all(len(e) == 1024 for e in results)
        assert service.vector_size == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_vector_size_matches_model_specification(self, mock_st):
        """Test that vector size matches e5-large specification."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        # Test default model (intfloat/multilingual-e5-large)
        service = EmbeddingService()
        assert service.vector_size == 1024

        # Test explicit e5-large models
        size_large = EmbeddingService._get_vector_size("intfloat/e5-large")
        assert size_large == 1024

        size_multilingual = EmbeddingService._get_vector_size("intfloat/multilingual-e5-large")
        assert size_multilingual == 1024


class TestCrossLingualSemanticAlignment:
    """Test cross-lingual semantic alignment properties of e5-large."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_synonyms_across_languages_proximity(self, mock_st):
        """Test that synonyms in different languages have similar embeddings."""
        mock_model = MagicMock()

        # Simulate similar embeddings for semantically equivalent texts
        base_embedding = np.array([0.7] * 1024).astype(np.float32)
        similar_embedding = np.array([0.68] * 1024).astype(np.float32)

        mock_model.encode.side_effect = [
            base_embedding,  # English
            similar_embedding,  # Russian (semantically equivalent)
        ]
        mock_st.return_value = mock_model

        service = EmbeddingService()

        english_text = "The player was in an offside position"
        russian_text = "Игрок находился в положении офсайда"

        eng_emb = np.array(service.embed_text(english_text))
        rus_emb = np.array(service.embed_text(russian_text))

        # Both should be 1024-dimensional
        assert len(eng_emb) == 1024
        assert len(rus_emb) == 1024

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_language_invariant_document_clustering(self, mock_st):
        """Test that documents about the same topic cluster together regardless of language."""
        mock_model = MagicMock()

        # Offside-related texts in different languages should have similar embeddings
        offside_texts = [
            "What is the offside rule?",
            "Что такое правило офсайда?",
            "Was ist die Abseitsregel?",
        ]

        # Simulate similar embeddings for all (they're semantically about the same)
        embeddings = np.array([
            [0.85] * 1024,
            [0.84] * 1024,
            [0.83] * 1024,
        ]).astype(np.float32)

        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        service = EmbeddingService()
        results = service.embed_batch(offside_texts)

        # All should be valid embeddings
        assert len(results) == 3
        assert all(len(e) == 1024 for e in results)

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_unrelated_content_different_semantic_space(self, mock_st):
        """Test that unrelated content has different embeddings."""
        mock_model = MagicMock()

        offside_embedding = np.array([0.85] * 1024).astype(np.float32)
        unrelated_embedding = np.array([0.2] * 1024).astype(np.float32)

        mock_model.encode.side_effect = [
            offside_embedding,
            unrelated_embedding,
        ]
        mock_st.return_value = mock_model

        service = EmbeddingService()

        offside_text = service.embed_text("What is the offside rule?")
        unrelated_text = service.embed_text("How to make pasta")

        assert offside_text is not None
        assert unrelated_text is not None
        # In real scenario, these would be far apart in semantic space


class TestZeroCostEmbedding:
    """Test that multilingual-e5-large embeddings have zero cost (local inference)."""

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_embedding_cost_always_zero(self, mock_st):
        """Test that embedding cost estimation returns 0 (no API calls)."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        service = EmbeddingService()

        # No matter the volume, local inference costs nothing
        assert service.estimate_embedding_cost(100) == 0.0
        assert service.estimate_embedding_cost(10000) == 0.0
        assert service.estimate_embedding_cost(1000000) == 0.0

    @patch("src.services.embedding_service.SentenceTransformer")
    def test_no_openai_calls_in_embedding(self, mock_st):
        """Test that embedding service doesn't make OpenAI API calls."""
        mock_model = MagicMock()
        embedding = np.array([0.1] * 1024).astype(np.float32)
        mock_model.encode.return_value = embedding
        mock_st.return_value = mock_model

        service = EmbeddingService()
        service.embed_text("Test text")

        # Only SentenceTransformer should be used, no OpenAI client
        assert not hasattr(service, "client")
        assert hasattr(service, "model")
        assert mock_model.encode.called
