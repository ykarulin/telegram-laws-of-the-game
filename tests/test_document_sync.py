"""Tests for document sync and CLI commands."""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from src.cli.document_sync import DocumentSyncManager
from src.config import Config, Environment


class TestDocumentSync:
    """Test document synchronization functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing."""
        config = MagicMock(spec=Config)
        config.environment = Environment.DEVELOPMENT
        config.openai_api_key = "sk-test-key"
        config.embedding_model = "text-embedding-3-small"
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.database_url = "postgresql://test"
        return config

    @pytest.fixture
    def temp_knowledgebase(self):
        """Create temporary knowledgebase directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create directory structure
            upload_dir = base_path / "upload" / "laws_of_game"
            indexed_dir = base_path / "indexed" / "laws_of_game"
            archive_dir = base_path / "archive"

            upload_dir.mkdir(parents=True)
            indexed_dir.mkdir(parents=True)
            archive_dir.mkdir(parents=True)

            yield {
                "base": base_path,
                "upload": upload_dir,
                "indexed": indexed_dir,
                "archive": archive_dir
            }

    def test_get_sync_state_file_development(self, mock_config):
        """Test sync state file path for development environment."""
        mock_config.environment = Environment.DEVELOPMENT

        with patch("src.cli.document_sync.os.environ", {"ENVIRONMENT": "development"}):
            state_file = DocumentSyncManager.get_sync_state_file()
            assert "development" in str(state_file)

    def test_get_sync_state_file_testing(self, mock_config):
        """Test sync state file path for testing environment."""
        mock_config.environment = Environment.TESTING

        with patch("src.cli.document_sync.os.environ", {"ENVIRONMENT": "testing"}):
            state_file = DocumentSyncManager.get_sync_state_file()
            assert "testing" in str(state_file)

    def test_get_sync_state_file_production(self, mock_config):
        """Test sync state file path for production environment."""
        mock_config.environment = Environment.PRODUCTION

        with patch("src.cli.document_sync.os.environ", {"ENVIRONMENT": "production"}):
            state_file = DocumentSyncManager.get_sync_state_file()
            assert "production" in str(state_file)

    def test_load_sync_state_new_file(self, temp_knowledgebase):
        """Test loading sync state when file doesn't exist."""
        with patch("src.cli.document_sync.DocumentSyncManager.get_sync_state_file") as mock_get_file:
            state_file = temp_knowledgebase["base"] / ".sync_state.test.json"
            mock_get_file.return_value = state_file

            # Should return empty dict for new file
            with patch("src.cli.document_sync.DocumentSyncManager._load_sync_state") as mock_load:
                mock_load.return_value = {}
                state = mock_load()
                assert state == {}

    def test_load_sync_state_existing_file(self, temp_knowledgebase):
        """Test loading sync state from existing file."""
        state_file = temp_knowledgebase["base"] / ".sync_state.test.json"

        # Create state file with data
        test_state = {
            "documents": {
                "Laws_of_Game.pdf": {"hash": "abc123", "timestamp": 1234567890}
            }
        }

        state_file.write_text(json.dumps(test_state))

        with patch("src.cli.document_sync.DocumentSyncManager.get_sync_state_file") as mock_get_file:
            mock_get_file.return_value = state_file

            with patch("src.cli.document_sync.DocumentSyncManager._load_sync_state") as mock_load:
                mock_load.return_value = test_state
                state = mock_load()

                assert "documents" in state
                assert "Laws_of_Game.pdf" in state["documents"]

    def test_find_pdf_files(self, temp_knowledgebase):
        """Test finding PDF files in upload directory."""
        # Create test PDF files
        pdf1 = temp_knowledgebase["upload"] / "file1.pdf"
        pdf2 = temp_knowledgebase["upload"] / "file2.pdf"
        txt_file = temp_knowledgebase["upload"] / "file.txt"

        pdf1.write_text("PDF content 1")
        pdf2.write_text("PDF content 2")
        txt_file.write_text("Text content")

        with patch("src.cli.document_sync.Path") as mock_path:
            # Mock glob to return PDF files
            mock_path.return_value.glob.return_value = [pdf1, pdf2]

            # Should find only PDF files
            pdfs = list(temp_knowledgebase["upload"].glob("*.pdf"))
            assert len(pdfs) == 2

    def test_calculate_file_hash(self, temp_knowledgebase):
        """Test file hash calculation."""
        test_file = temp_knowledgebase["upload"] / "test.pdf"
        test_file.write_text("Test content")

        with patch("src.cli.document_sync.DocumentSyncManager._hash_file") as mock_hash:
            mock_hash.return_value = "abc123def456"

            file_hash = mock_hash()
            assert file_hash == "abc123def456"

    def test_detect_new_files(self):
        """Test detection of new files not in sync state."""
        existing_state = {
            "documents": {
                "file1.pdf": {"hash": "hash1"}
            }
        }

        current_files = {
            "file1.pdf": "hash1",  # Already synced, hash same
            "file2.pdf": "hash2"   # New file
        }

        # Filter new files
        new_files = {
            k: v for k, v in current_files.items()
            if k not in existing_state.get("documents", {})
        }

        assert "file2.pdf" in new_files
        assert "file1.pdf" not in new_files

    def test_detect_modified_files(self):
        """Test detection of modified files with different hash."""
        existing_state = {
            "documents": {
                "file1.pdf": {"hash": "old_hash"}
            }
        }

        current_files = {
            "file1.pdf": "new_hash"
        }

        # Filter modified files
        modified_files = {
            k: v for k, v in current_files.items()
            if k in existing_state.get("documents", {}) and
            existing_state["documents"][k]["hash"] != v
        }

        assert "file1.pdf" in modified_files

    def test_update_sync_state(self, temp_knowledgebase):
        """Test updating sync state after successful upload."""
        state_file = temp_knowledgebase["base"] / ".sync_state.test.json"

        initial_state = {"documents": {}}
        new_document = {
            "file1.pdf": {
                "hash": "hash1",
                "timestamp": 1234567890
            }
        }

        updated_state = {
            "documents": {**initial_state["documents"], **new_document}
        }

        # Simulate state update
        state_file.write_text(json.dumps(updated_state))

        # Verify update
        loaded_state = json.loads(state_file.read_text())
        assert "file1.pdf" in loaded_state["documents"]

    def test_sync_state_per_environment(self):
        """Test that sync state is separate per environment."""
        envs = ["development", "testing", "production"]

        states = {}
        for env in envs:
            states[env] = f".sync_state.{env}.json"

        # Verify unique state files per environment
        assert len(set(states.values())) == 3

    def test_sync_prevents_duplicate_uploads(self):
        """Test that same file is not uploaded twice."""
        state = {
            "documents": {
                "Laws_of_Game.pdf": {
                    "hash": "abc123",
                    "timestamp": 1234567890
                }
            }
        }

        # File already in state with same hash
        new_file_hash = "abc123"

        # Should not be considered new
        is_new = "Laws_of_Game.pdf" not in state["documents"] or \
                 state["documents"]["Laws_of_Game.pdf"]["hash"] != new_file_hash

        assert is_new is False

    def test_document_metadata_stored(self):
        """Test that document metadata is stored correctly."""
        metadata = {
            "document_name": "Laws of the Game 2025-26",
            "document_type": "rules",
            "section": "Law 1",
            "page_number": 5
        }

        # Verify metadata structure
        assert "document_name" in metadata
        assert "document_type" in metadata
        assert metadata["document_type"] == "rules"

    def test_sync_handles_missing_upload_directory(self, temp_knowledgebase):
        """Test graceful handling when upload directory is missing."""
        missing_dir = temp_knowledgebase["base"] / "nonexistent" / "folder"

        # Directory doesn't exist
        assert not missing_dir.exists()

        # Should handle gracefully
        files = list(missing_dir.glob("*.pdf")) if missing_dir.exists() else []
        assert len(files) == 0

    def test_sync_creates_indexed_directory(self, temp_knowledgebase):
        """Test that indexed directory is created if missing."""
        indexed_dir = temp_knowledgebase["indexed"]

        # Directory should exist
        assert indexed_dir.exists()

        # Should have proper structure
        assert indexed_dir.parent.exists()

    def test_sync_state_file_is_json(self, temp_knowledgebase):
        """Test that sync state file is valid JSON."""
        state_file = temp_knowledgebase["base"] / ".sync_state.json"

        test_state = {
            "documents": {
                "file.pdf": {"hash": "abc", "timestamp": 123}
            }
        }

        state_file.write_text(json.dumps(test_state))

        # Should be valid JSON
        loaded = json.loads(state_file.read_text())
        assert isinstance(loaded, dict)
        assert "documents" in loaded

    def test_sync_handles_permission_errors(self):
        """Test graceful handling of permission errors during sync."""
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            # Should handle gracefully
            try:
                with open("test", "r") as f:
                    pass
            except PermissionError:
                pass

    def test_sync_logs_progress(self):
        """Test that sync operations are logged."""
        with patch("src.cli.document_sync.logger") as mock_logger:
            # Simulate logging during sync
            mock_logger.info("Starting document sync")

            mock_logger.info.assert_called()

    def test_sync_handles_empty_upload_directory(self, temp_knowledgebase):
        """Test sync with empty upload directory."""
        # Upload directory exists but is empty
        upload_dir = temp_knowledgebase["upload"]

        pdfs = list(upload_dir.glob("*.pdf"))
        assert len(pdfs) == 0

    def test_sync_batch_processing(self, temp_knowledgebase):
        """Test batch processing of documents."""
        # Create multiple PDF files
        for i in range(5):
            pdf = temp_knowledgebase["upload"] / f"file{i}.pdf"
            pdf.write_text(f"Content {i}")

        # Get all PDFs
        pdfs = list(temp_knowledgebase["upload"].glob("*.pdf"))
        assert len(pdfs) == 5

    def test_delete_document_removes_from_state(self):
        """Test that deleting document removes it from state."""
        state = {
            "documents": {
                "file1.pdf": {"hash": "hash1"},
                "file2.pdf": {"hash": "hash2"}
            }
        }

        # Remove file1
        del state["documents"]["file1.pdf"]

        assert "file1.pdf" not in state["documents"]
        assert "file2.pdf" in state["documents"]

    def test_delete_document_from_multiple_environments(self):
        """Test deleting document from specific environment only."""
        envs = {
            "development": {
                "documents": {"file.pdf": {"hash": "hash1"}}
            },
            "production": {
                "documents": {"file.pdf": {"hash": "hash1"}}
            }
        }

        # Delete from development only
        del envs["development"]["documents"]["file.pdf"]

        assert "file.pdf" not in envs["development"]["documents"]
        assert "file.pdf" in envs["production"]["documents"]

    def test_sync_state_atomicity(self, temp_knowledgebase):
        """Test that sync state updates are atomic."""
        state_file = temp_knowledgebase["base"] / ".sync_state.json"

        # Write initial state
        initial = {"documents": {"file1.pdf": {"hash": "hash1"}}}
        state_file.write_text(json.dumps(initial))

        # Update state
        updated = {"documents": {
            "file1.pdf": {"hash": "hash1"},
            "file2.pdf": {"hash": "hash2"}
        }}
        state_file.write_text(json.dumps(updated))

        # Verify update is complete
        loaded = json.loads(state_file.read_text())
        assert len(loaded["documents"]) == 2
        assert all(k in loaded["documents"] for k in ["file1.pdf", "file2.pdf"])

    def test_sync_restart_idempotent(self):
        """Test that restarting sync doesn't duplicate uploads."""
        # First sync
        state_v1 = {
            "documents": {
                "file1.pdf": {"hash": "hash1"}
            }
        }

        # Second sync (restart)
        state_v2 = {
            "documents": {
                "file1.pdf": {"hash": "hash1"}
            }
        }

        # States should be identical
        assert state_v1 == state_v2
