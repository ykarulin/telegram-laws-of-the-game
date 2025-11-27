"""Tests for document service including relative_path preservation."""

import pytest
import os
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config import Config, Environment
from src.services.document_service import (
    DocumentService,
    DocumentInfo,
    DocumentContent,
)

# Use test database URL from environment or default
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://telegram_bot:telegram_bot_password@localhost/telegram_bot_test",
)


@pytest.fixture
def db_session():
    """Create a clean database session for testing."""
    engine = create_engine(TEST_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Clean up documents table before each test
    try:
        session.execute(text("DELETE FROM documents"))
        session.commit()
    except Exception:
        session.rollback()

    yield session

    # Cleanup after test
    try:
        session.execute(text("DELETE FROM documents"))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    class MockConfig:
        def __init__(self):
            self.environment = Environment.TESTING
            self.database_url = TEST_DATABASE_URL
            self.openai_api_key = "sk-test-key"
            self.embedding_model = "text-embedding-3-small"
            self.qdrant_host = "localhost"
            self.qdrant_port = 6333

    return MockConfig()


@pytest.fixture
def doc_service(mock_config, db_session):
    """Create a document service instance."""
    return DocumentService(mock_config, db_session)


class TestDocumentUpload:
    """Tests for document upload functionality."""

    def test_upload_document_basic(self, doc_service):
        """Test basic document upload without relative_path."""
        doc_id = doc_service.upload_document(
            name="Test Document",
            document_type="laws_of_game",
            content="This is test content",
            version="2024-25",
        )

        assert doc_id is not None
        assert isinstance(doc_id, int)
        assert doc_id > 0

    def test_upload_document_with_relative_path(self, doc_service):
        """Test document upload with relative_path preservation."""
        relative_path = "laws_of_game/laws_2024-25.pdf"

        doc_id = doc_service.upload_document(
            name="Laws 2024-25",
            document_type="laws_of_game",
            content="Laws of the Game content here",
            version="2024-25",
            relative_path=relative_path,
        )

        assert doc_id is not None

        # Retrieve and verify
        doc = doc_service.get_document(doc_id)
        assert doc is not None
        assert doc.relative_path == relative_path
        assert doc.document_type == "laws_of_game"
        assert doc.name == "Laws 2024-25"

    def test_upload_document_with_nested_path(self, doc_service):
        """Test relative_path with multiple folder levels."""
        relative_path = "laws_of_game/2024-25/laws_with_images.pdf"

        doc_id = doc_service.upload_document(
            name="Laws with Images",
            document_type="laws_of_game",
            content="Laws with detailed descriptions",
            version="2024-25",
            relative_path=relative_path,
        )

        doc = doc_service.get_document(doc_id)
        assert doc.relative_path == relative_path

    def test_upload_document_with_all_fields(self, doc_service):
        """Test upload with all optional fields including relative_path."""
        metadata = {"language": "en", "pages": 42}
        relative_path = "faq/general_faq_2024.txt"

        doc_id = doc_service.upload_document(
            name="General FAQ",
            document_type="faq",
            content="Frequently asked questions",
            version="2024",
            source_url="https://example.com/faq",
            uploaded_by="admin@example.com",
            metadata=metadata,
            relative_path=relative_path,
        )

        doc = doc_service.get_document(doc_id)
        assert doc.id == doc_id
        assert doc.name == "General FAQ"
        assert doc.document_type == "faq"
        assert doc.version == "2024"
        assert doc.source_url == "https://example.com/faq"
        assert doc.uploaded_by == "admin@example.com"
        assert doc.relative_path == relative_path
        assert doc.metadata == metadata
        assert doc.qdrant_status == "pending"


class TestDocumentRetrieval:
    """Tests for document retrieval with relative_path."""

    def test_get_document_includes_relative_path(self, doc_service):
        """Test that get_document returns relative_path."""
        relative_path = "tournament_rules/rules_2024.md"

        doc_id = doc_service.upload_document(
            name="Tournament Rules 2024",
            document_type="tournament_rules",
            content="Competition rules and regulations",
            relative_path=relative_path,
        )

        doc = doc_service.get_document(doc_id)
        assert doc is not None
        assert doc.relative_path == relative_path

    def test_get_document_with_null_relative_path(self, doc_service):
        """Test get_document when relative_path is not provided."""
        doc_id = doc_service.upload_document(
            name="Old Document",
            document_type="general",
            content="Content without relative path",
        )

        doc = doc_service.get_document(doc_id)
        assert doc is not None
        assert doc.relative_path is None

    def test_list_documents_includes_relative_path(self, doc_service):
        """Test that list_documents includes relative_path in results."""
        paths = [
            "laws_of_game/laws_2024-25.pdf",
            "faq/general_2024.txt",
            "tournament_rules/rules_2024.md",
        ]

        for i, relative_path in enumerate(paths):
            doc_service.upload_document(
                name=f"Document {i}",
                document_type="general",
                content=f"Content {i}",
                relative_path=relative_path,
            )

        docs = doc_service.list_documents()
        assert len(docs) == 3

        # Check that all relative_paths are present
        retrieved_paths = {doc.relative_path for doc in docs}
        assert retrieved_paths == set(paths)

    def test_list_documents_by_type_with_relative_path(self, doc_service):
        """Test filtering documents by type preserves relative_path."""
        doc_service.upload_document(
            name="Laws",
            document_type="laws_of_game",
            content="Laws content",
            relative_path="laws_of_game/laws.pdf",
        )

        doc_service.upload_document(
            name="FAQ",
            document_type="faq",
            content="FAQ content",
            relative_path="faq/faq.txt",
        )

        laws_docs = doc_service.list_documents(document_type="laws_of_game")
        assert len(laws_docs) == 1
        assert laws_docs[0].relative_path == "laws_of_game/laws.pdf"

        faq_docs = doc_service.list_documents(document_type="faq")
        assert len(faq_docs) == 1
        assert faq_docs[0].relative_path == "faq/faq.txt"


class TestDocumentSync:
    """Tests for document sync workflow with relative_path preservation."""

    def test_sync_workflow_preserves_structure(self, doc_service):
        """Test that sync workflow preserves folder structure via relative_path."""
        documents = [
            ("laws_of_game/laws_2024-25.pdf", "Laws 2024-25", "laws_of_game"),
            ("laws_of_game/interpretations_2024.pdf", "Interpretations", "laws_of_game"),
            ("faq/general_questions.txt", "General FAQ", "faq"),
            ("faq/technical_issues.txt", "Technical FAQ", "faq"),
            ("tournament_rules/league_rules.md", "League Rules", "tournament_rules"),
        ]

        uploaded_ids = []
        for relative_path, name, doc_type in documents:
            doc_id = doc_service.upload_document(
                name=name,
                document_type=doc_type,
                content=f"Content for {name}",
                relative_path=relative_path,
            )
            uploaded_ids.append(doc_id)

        # Verify all documents stored with correct structure
        all_docs = doc_service.list_documents()
        assert len(all_docs) == len(documents)

        # Check structure preservation by type
        laws_docs = doc_service.list_documents(document_type="laws_of_game")
        assert len(laws_docs) == 2
        assert all(d.relative_path.startswith("laws_of_game/") for d in laws_docs)

        faq_docs = doc_service.list_documents(document_type="faq")
        assert len(faq_docs) == 2
        assert all(d.relative_path.startswith("faq/") for d in faq_docs)

        rules_docs = doc_service.list_documents(document_type="tournament_rules")
        assert len(rules_docs) == 1
        assert rules_docs[0].relative_path == "tournament_rules/league_rules.md"

    def test_relative_path_survives_reset(self, doc_service):
        """Test that relative_path is preserved when resetting embeddings."""
        relative_path = "laws_of_game/laws_2024-25.pdf"

        doc_id = doc_service.upload_document(
            name="Laws",
            document_type="laws_of_game",
            content="Laws content",
            relative_path=relative_path,
        )

        # Simulate indexing
        doc_service.update_qdrant_status(doc_id, "indexed", "coll_123")

        # Verify indexed
        doc = doc_service.get_document(doc_id)
        assert doc.qdrant_status == "indexed"
        assert doc.relative_path == relative_path

        # Simulate reset (status back to pending, but relative_path preserved)
        doc_service.update_qdrant_status(doc_id, "pending")

        # Verify relative_path still there
        doc = doc_service.get_document(doc_id)
        assert doc.qdrant_status == "pending"
        assert doc.relative_path == relative_path  # PRESERVED!


class TestDocumentInfoDataclass:
    """Tests for DocumentInfo dataclass with relative_path."""

    def test_document_info_has_relative_path(self, doc_service):
        """Test that DocumentInfo includes relative_path field."""
        relative_path = "laws_of_game/laws.pdf"

        doc_id = doc_service.upload_document(
            name="Laws",
            document_type="laws_of_game",
            content="Content",
            relative_path=relative_path,
        )

        docs = doc_service.list_documents()
        assert len(docs) == 1

        doc_info = docs[0]
        assert isinstance(doc_info, DocumentInfo)
        assert hasattr(doc_info, 'relative_path')
        assert doc_info.relative_path == relative_path


class TestDocumentContentDataclass:
    """Tests for DocumentContent dataclass with relative_path."""

    def test_document_content_has_relative_path(self, doc_service):
        """Test that DocumentContent includes relative_path field."""
        relative_path = "faq/general.txt"

        doc_id = doc_service.upload_document(
            name="FAQ",
            document_type="faq",
            content="FAQ content",
            relative_path=relative_path,
        )

        doc = doc_service.get_document(doc_id)
        assert isinstance(doc, DocumentContent)
        assert hasattr(doc, 'relative_path')
        assert doc.relative_path == relative_path


class TestDocumentExists:
    """Tests for document existence checking."""

    def test_document_exists_ignores_relative_path(self, doc_service):
        """Test that document_exists checks name and type only."""
        doc_service.upload_document(
            name="Laws",
            document_type="laws_of_game",
            content="Content",
            relative_path="laws_of_game/laws_v1.pdf",
        )

        # Existence check only uses name and type
        assert doc_service.document_exists("Laws", "laws_of_game")
        assert not doc_service.document_exists("Laws", "faq")
        assert not doc_service.document_exists("Different", "laws_of_game")


class TestPendingAndIndexedDocuments:
    """Tests for pending/indexed document retrieval."""

    def test_get_pending_documents_with_relative_path(self, doc_service):
        """Test that pending documents include relative_path."""
        doc_service.upload_document(
            name="Pending Doc",
            document_type="laws_of_game",
            content="Content",
            relative_path="laws_of_game/pending.pdf",
        )

        pending = doc_service.get_pending_documents()
        assert len(pending) == 1
        assert pending[0].relative_path == "laws_of_game/pending.pdf"

    def test_get_indexed_documents_with_relative_path(self, doc_service):
        """Test that indexed documents include relative_path."""
        doc_id = doc_service.upload_document(
            name="Indexed Doc",
            document_type="laws_of_game",
            content="Content",
            relative_path="laws_of_game/indexed.pdf",
        )

        # Mark as indexed
        doc_service.update_qdrant_status(doc_id, "indexed", "coll_123")

        indexed = doc_service.get_indexed_documents()
        assert len(indexed) == 1
        assert indexed[0].relative_path == "laws_of_game/indexed.pdf"


class TestMetadataPreservation:
    """Tests to ensure metadata and relative_path work together."""

    def test_metadata_and_relative_path_both_preserved(self, doc_service):
        """Test that metadata and relative_path are both stored and retrieved."""
        metadata = {
            "language": "en",
            "pages": 50,
            "author": "FIFA",
            "file_size": 1024,
        }
        relative_path = "laws_of_game/laws_full_2024.pdf"

        doc_id = doc_service.upload_document(
            name="Full Laws",
            document_type="laws_of_game",
            content="Complete laws content",
            metadata=metadata,
            relative_path=relative_path,
        )

        doc = doc_service.get_document(doc_id)
        assert doc.metadata == metadata
        assert doc.relative_path == relative_path
        assert doc.name == "Full Laws"
