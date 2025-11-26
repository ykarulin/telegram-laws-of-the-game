"""Tests for dataclass utility methods."""
import pytest
from datetime import datetime
from src.core.db import Message
from src.core.vector_db import RetrievedChunk
from src.services.embedding_service import Chunk


class TestMessageUtilities:
    """Test Message dataclass utility methods."""

    def test_is_bot_message_true(self):
        """is_bot_message should return True for bot messages."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="bot",
            sender_id="gpt-4",
            text="Hello"
        )
        assert msg.is_bot_message() is True

    def test_is_bot_message_false(self):
        """is_bot_message should return False for user messages."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello"
        )
        assert msg.is_bot_message() is False

    def test_is_user_message_true(self):
        """is_user_message should return True for user messages."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello"
        )
        assert msg.is_user_message() is True

    def test_is_user_message_false(self):
        """is_user_message should return False for bot messages."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="bot",
            sender_id="gpt-4",
            text="Hello"
        )
        assert msg.is_user_message() is False

    def test_to_dict_basic(self):
        """to_dict should convert message to dictionary."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello world"
        )
        result = msg.to_dict()

        assert isinstance(result, dict)
        assert result["message_id"] == 1
        assert result["chat_id"] == 123
        assert result["sender_type"] == "user"
        assert result["sender_id"] == "456"
        assert result["text"] == "Hello world"

    def test_to_dict_with_timestamp(self):
        """to_dict should format timestamp as ISO format."""
        timestamp = datetime(2025, 11, 26, 15, 30, 45)
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello",
            timestamp=timestamp
        )
        result = msg.to_dict()

        assert result["timestamp"] == "2025-11-26T15:30:45"

    def test_to_dict_without_timestamp(self):
        """to_dict should handle missing timestamp."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello"
        )
        result = msg.to_dict()

        assert result["timestamp"] is None

    def test_to_dict_with_reply_to(self):
        """to_dict should include reply_to_message_id."""
        msg = Message(
            message_id=2,
            chat_id=123,
            sender_type="bot",
            sender_id="gpt-4",
            text="Response",
            reply_to_message_id=1
        )
        result = msg.to_dict()

        assert result["reply_to_message_id"] == 1

    def test_to_dict_with_db_id(self):
        """to_dict should include internal db_id."""
        msg = Message(
            message_id=1,
            chat_id=123,
            sender_type="user",
            sender_id="456",
            text="Hello",
            db_id=999
        )
        result = msg.to_dict()

        assert result["db_id"] == 999


class TestRetrievedChunkUtilities:
    """Test RetrievedChunk dataclass utility methods."""

    def test_get_source_with_document_name(self):
        """get_source should extract document_name from metadata."""
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Some text",
            score=0.95,
            metadata={"document_name": "rules.pdf"}
        )
        assert chunk.get_source() == "rules.pdf"

    def test_get_source_missing(self):
        """get_source should return 'Unknown' when document_name missing."""
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Some text",
            score=0.95,
            metadata={}
        )
        assert chunk.get_source() == "Unknown"

    def test_get_section_with_section(self):
        """get_section should extract section from metadata."""
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Some text",
            score=0.95,
            metadata={"section": "Offside Rule"}
        )
        assert chunk.get_section() == "Offside Rule"

    def test_get_section_missing(self):
        """get_section should return 'Unknown' when section missing."""
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Some text",
            score=0.95,
            metadata={}
        )
        assert chunk.get_section() == "Unknown"

    def test_to_dict_basic(self):
        """to_dict should convert chunk to dictionary."""
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Some text",
            score=0.95,
            metadata={"document_name": "rules.pdf"}
        )
        result = chunk.to_dict()

        assert isinstance(result, dict)
        assert result["chunk_id"] == "c1"
        assert result["text"] == "Some text"
        assert result["score"] == 0.95
        assert result["metadata"] == {"document_name": "rules.pdf"}

    def test_to_dict_preserves_all_fields(self):
        """to_dict should preserve all chunk fields."""
        metadata = {
            "document_name": "rules.pdf",
            "section": "Offside",
            "document_type": "pdf"
        }
        chunk = RetrievedChunk(
            chunk_id="chunk_123",
            text="The ball is in play when...",
            score=0.87,
            metadata=metadata
        )
        result = chunk.to_dict()

        assert result["chunk_id"] == "chunk_123"
        assert result["text"] == "The ball is in play when..."
        assert result["score"] == 0.87
        assert result["metadata"] == metadata


class TestChunkUtilities:
    """Test Chunk dataclass utility methods."""

    def test_to_dict_basic(self):
        """to_dict should convert chunk to dictionary."""
        chunk = Chunk(
            text="Some content",
            section="Introduction",
            chunk_index=0,
            total_chunks=5
        )
        result = chunk.to_dict()

        assert isinstance(result, dict)
        assert result["text"] == "Some content"
        assert result["section"] == "Introduction"
        assert result["subsection"] == ""
        assert result["page_number"] is None
        assert result["chunk_index"] == 0
        assert result["total_chunks"] == 5

    def test_to_dict_with_all_fields(self):
        """to_dict should include all optional fields."""
        chunk = Chunk(
            text="Some content",
            section="Chapter 2",
            subsection="2.3 Rules",
            page_number=45,
            chunk_index=2,
            total_chunks=10
        )
        result = chunk.to_dict()

        assert result["text"] == "Some content"
        assert result["section"] == "Chapter 2"
        assert result["subsection"] == "2.3 Rules"
        assert result["page_number"] == 45
        assert result["chunk_index"] == 2
        assert result["total_chunks"] == 10

    def test_get_location_with_section_only(self):
        """get_location should show section when subsection is empty."""
        chunk = Chunk(
            text="Content",
            section="Rules",
            subsection="",
            page_number=10
        )
        assert chunk.get_location() == "Rules, Page 10"

    def test_get_location_with_section_and_subsection(self):
        """get_location should show section > subsection."""
        chunk = Chunk(
            text="Content",
            section="Rules",
            subsection="Offside",
            page_number=15
        )
        assert chunk.get_location() == "Rules > Offside, Page 15"

    def test_get_location_without_page_number(self):
        """get_location should work without page number."""
        chunk = Chunk(
            text="Content",
            section="Rules",
            subsection="Offside",
            page_number=None
        )
        assert chunk.get_location() == "Rules > Offside"

    def test_get_location_unknown_section(self):
        """get_location should return 'Unknown section' when section is empty."""
        chunk = Chunk(
            text="Content",
            section="",
            subsection="",
            page_number=5
        )
        assert chunk.get_location() == "Unknown section, Page 5"

    def test_is_first_chunk_true(self):
        """is_first_chunk should return True for chunk 0."""
        chunk = Chunk(
            text="Content",
            chunk_index=0,
            total_chunks=10
        )
        assert chunk.is_first_chunk() is True

    def test_is_first_chunk_false(self):
        """is_first_chunk should return False for non-zero index."""
        chunk = Chunk(
            text="Content",
            chunk_index=1,
            total_chunks=10
        )
        assert chunk.is_first_chunk() is False

    def test_is_last_chunk_true(self):
        """is_last_chunk should return True for last chunk."""
        chunk = Chunk(
            text="Content",
            chunk_index=9,
            total_chunks=10
        )
        assert chunk.is_last_chunk() is True

    def test_is_last_chunk_false(self):
        """is_last_chunk should return False for non-last chunks."""
        chunk = Chunk(
            text="Content",
            chunk_index=5,
            total_chunks=10
        )
        assert chunk.is_last_chunk() is False

    def test_is_last_chunk_single_chunk(self):
        """is_last_chunk should work correctly for single chunk."""
        chunk = Chunk(
            text="Content",
            chunk_index=0,
            total_chunks=1
        )
        assert chunk.is_last_chunk() is True
        assert chunk.is_first_chunk() is True
