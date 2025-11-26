"""Integration tests for token-based document chunking.

Tests the complete flow of:
1. Loading an embedding model (with real tokenizer)
2. Tokenizing document text
3. Creating token-aware chunks
4. Verifying chunk quality and properties
"""

import pytest
from src.services.embedding_service import EmbeddingService, Chunk


class TestTokenBasedChunkingIntegration:
    """Integration tests for token-based chunking with real models."""

    @pytest.fixture
    def embedding_service(self):
        """Create an embedding service with real model and tokenizer."""
        return EmbeddingService()

    def test_tokenizer_is_loaded(self, embedding_service):
        """Test that tokenizer is properly loaded from the embedding model."""
        assert embedding_service.tokenizer is not None
        assert hasattr(embedding_service.tokenizer, 'encode')
        assert hasattr(embedding_service.tokenizer, 'decode')

    def test_tokenization_consistency(self, embedding_service):
        """Test that encode -> decode is consistent."""
        text = "The Laws of the Game determine the winner of a match."
        tokens = embedding_service.tokenizer.encode(text)
        decoded_text = embedding_service.tokenizer.decode(
            tokens,
            skip_special_tokens=True
        ).strip()

        # Decoded text should be similar to original (may differ due to tokenization)
        assert len(decoded_text) > 0
        assert "Laws" in decoded_text or "laws" in decoded_text.lower()

    def test_chunk_document_short_text(self, embedding_service):
        """Test chunking a short document (single chunk)."""
        text = "Law 1: The Field of Play"
        chunks = embedding_service.chunk_document(
            text,
            chunk_size=500,
            overlap=100
        )

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_chunk_document_medium_text(self, embedding_service):
        """Test chunking a medium-length document."""
        # Create a text that's likely to produce more than 500 tokens
        text = """
        Law 1: The Field of Play
        The field of play shall be rectangular. The length of the touchline shall be
        greater than the length of the goal-line. The minimum length of the goal-line
        is 50 yards; the maximum is 100 yards. The minimum length of the touchline is
        100 yards; the maximum is 130 yards. The field of play is divided into two halves
        by the halfway-line. The center-spot is indicated at the midpoint of the halfway-line.
        """ * 6  # Increased repetition to ensure > 500 tokens

        chunks = embedding_service.chunk_document(
            text,
            chunk_size=500,
            overlap=100
        )

        # Verify that tokens were counted
        token_count = len(embedding_service.tokenizer.encode(text))
        # Should produce multiple chunks since text is > 500 tokens
        if token_count > 500:
            assert len(chunks) >= 2
        else:
            # If text is still < 500 tokens, it's OK to have 1 chunk
            assert len(chunks) >= 1

        # All chunks should have consistent metadata
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert len(chunk.text) > 0
            assert 0 <= chunk.chunk_index < chunk.total_chunks

        # Verify chunk order
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_document_preserves_section_metadata(self, embedding_service):
        """Test that section and subsection metadata is preserved through chunking."""
        text = """
        Rule 1.1: The basic rule
        This is the content of rule 1.1 explaining the basic principle.
        """ * 5

        chunks = embedding_service.chunk_document(
            text,
            chunk_size=300,
            overlap=50,
            section="Laws of the Game",
            subsection="Rule 1: Basic Rules",
            page_number=10
        )

        assert len(chunks) > 0

        # All chunks should have the same metadata
        for chunk in chunks:
            assert chunk.section == "Laws of the Game"
            assert chunk.subsection == "Rule 1: Basic Rules"
            assert chunk.page_number == 10

    def test_chunk_document_token_boundaries(self, embedding_service):
        """Test that chunks respect token boundaries (no broken tokens)."""
        text = """
        When determining the outcome of a match in which extra time is played,
        the team which scores the greater number of goals shall be the winner.
        """ * 3

        chunks = embedding_service.chunk_document(
            text,
            chunk_size=200,
            overlap=50
        )

        # Each chunk should be decodable from tokens without errors
        for chunk in chunks:
            assert chunk.text is not None
            assert len(chunk.text) > 0
            # Text should not have partial words or weird characters from mid-token cuts
            assert not chunk.text.startswith("▁")  # BPE token marker

    def test_chunk_overlap_provides_context(self, embedding_service):
        """Test that overlap between chunks preserves context."""
        text = """
        The goalkeeper is the only player allowed to handle the ball
        within the penalty area. If a goalkeeper handles the ball outside
        the penalty area, they are treated as an outfield player.
        """ * 5

        chunks_with_overlap = embedding_service.chunk_document(
            text,
            chunk_size=300,
            overlap=100
        )

        chunks_no_overlap = embedding_service.chunk_document(
            text,
            chunk_size=300,
            overlap=0
        )

        # With overlap, adjacent chunks should share content
        if len(chunks_with_overlap) > 1:
            # Check that first chunk's end overlaps with second chunk's start
            chunk1_end = chunks_with_overlap[0].text.split()[-30:]
            chunk2_start = chunks_with_overlap[1].text.split()[:30]

            # Convert to text for comparison
            chunk1_end_text = " ".join(chunk1_end).lower()
            chunk2_start_text = " ".join(chunk2_start).lower()

            # There should be some word overlap due to token overlap
            overlap_count = len(set(chunk1_end_text.split()) & set(chunk2_start_text.split()))
            # With 100 token overlap, we expect at least some word overlap
            assert overlap_count > 0

    def test_chunk_document_multilingual(self, embedding_service):
        """Test chunking with multilingual text (model supports multilingual-e5-large)."""
        # English
        en_text = "The field of play is rectangular. " * 30
        en_chunks = embedding_service.chunk_document(en_text, chunk_size=500)

        # Russian
        ru_text = "Поле игры имеет прямоугольную форму. " * 30
        ru_chunks = embedding_service.chunk_document(ru_text, chunk_size=500)

        assert len(en_chunks) > 0
        assert len(ru_chunks) > 0

        # Different languages should produce different token counts
        en_tokens = embedding_service.tokenizer.encode(en_text)
        ru_tokens = embedding_service.tokenizer.encode(ru_text)

        # Both should have reasonable token counts
        assert len(en_tokens) > 100
        assert len(ru_tokens) > 100

    def test_chunk_handles_special_characters(self, embedding_service):
        """Test that chunking handles special characters and formatting."""
        text = """
        Rule 1.1: Field dimensions
        - Length: 100-130 yards (90-120 meters)
        - Width: 50-100 yards (45-90 meters)
        - Goal area: 18 × 44 yards
        - Penalty area: 18 × 44 yards
        """ * 3

        chunks = embedding_service.chunk_document(text, chunk_size=300)

        assert len(chunks) > 0

        # Chunks should preserve structure
        reconstructed = " ".join(chunk.text for chunk in chunks)
        assert "Length:" in reconstructed
        assert "Width:" in reconstructed
        assert "Goal area:" in reconstructed

    def test_chunk_document_empty_chunks_filtered(self, embedding_service):
        """Test that empty chunks are filtered out."""
        text = "Content. " * 100

        chunks = embedding_service.chunk_document(
            text,
            chunk_size=200,
            overlap=50
        )

        # All chunks should have non-empty text
        for chunk in chunks:
            assert chunk.text.strip() != ""
            assert len(chunk.text) > 0

    def test_chunk_indices_correct(self, embedding_service):
        """Test that chunk indices are correctly assigned."""
        text = "The quick brown fox jumps over the lazy dog. " * 50

        chunks = embedding_service.chunk_document(
            text,
            chunk_size=200,
            overlap=50
        )

        assert len(chunks) > 1

        # Check sequential chunk indices
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)

    def test_large_document_chunking(self, embedding_service):
        """Test chunking of a large document."""
        # Create a large text (simulating a real UEFA document)
        large_text = """
        LAW 1: THE FIELD OF PLAY

        The field of play shall be rectangular. The length of the touchline shall be
        greater than the length of the goal-line. The minimum length of the goal-line
        is 50 yards; the maximum is 100 yards. The minimum length of the touchline is
        100 yards; the maximum is 130 yards.

        LAW 2: THE BALL

        The ball shall have a circumference of not more than 70 centimetres and not less
        than 68 centimetres. The ball shall have a weight of not more than 450 grammes
        and not less than 410 grammes. The ball shall be spherical.

        LAW 3: THE PLAYERS

        A match is played by two teams, each consisting of not more than eleven players,
        one of whom is the goalkeeper. A match may not start or continue if either team
        has fewer than seven players.
        """ * 20

        chunks = embedding_service.chunk_document(
            text=large_text,
            chunk_size=500,
            overlap=100,
            section="Laws of the Game",
            subsection="Official Rules",
            page_number=1
        )

        assert len(chunks) > 5

        # Verify structure
        total_text_len = sum(len(chunk.text) for chunk in chunks)
        assert total_text_len > len(large_text) / 2  # Account for overlaps and trimming

        # All chunks should be properly indexed
        chunk_indices = [chunk.chunk_index for chunk in chunks]
        assert chunk_indices == list(range(len(chunks)))

    def test_chunk_reconstruction(self, embedding_service):
        """Test that chunks can be used to reconstruct meaningful content."""
        original_text = """
        When a player is in an offside position and directly involved in active play
        or interferes with an opponent, the player is in a breach of the Law. A player
        in an offside position is only penalised if, at the moment the ball is played
        by a teammate, the player is in an offside position.
        """ * 4

        chunks = embedding_service.chunk_document(
            original_text,
            chunk_size=300,
            overlap=100
        )

        # Reconstruct by joining chunks with some deduplication of overlap
        reconstructed = chunks[0].text

        for i in range(1, len(chunks)):
            # Simple reconstruction: just append (overlap will be duplicated)
            reconstructed += " " + chunks[i].text

        # Reconstructed text should contain key concepts from original
        assert "offside" in reconstructed.lower()
        assert "player" in reconstructed.lower()
