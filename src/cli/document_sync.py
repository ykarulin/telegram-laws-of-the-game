"""Document folder monitor and auto-sync to Qdrant.

Watches the knowledgebase/upload folder for new documents and automatically
indexes them to Qdrant.

Usage:
    python -m src.cli.document_sync [--watch] [--dry-run]
"""

import logging
import argparse
import sys
import os
from pathlib import Path
import json
import hashlib
from typing import Dict, Set

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import Config
from src.services.document_service import DocumentService
from src.cli.document_commands import DocumentCLI

logger = logging.getLogger(__name__)

# Suppress noisy debug logs from external libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)


class DocumentSyncManager:
    """Monitor and sync documents from upload folder to Qdrant."""

    UPLOAD_FOLDER = Path("knowledgebase/upload")
    INDEXED_FOLDER = Path("knowledgebase/indexed")
    ARCHIVE_FOLDER = Path("knowledgebase/archive")

    @staticmethod
    def get_sync_state_file() -> Path:
        """Get environment-specific sync state file.

        Returns a path like:
        - knowledgebase/.sync_state.development.json (for ENVIRONMENT=development)
        - knowledgebase/.sync_state.testing.json (for ENVIRONMENT=testing)
        - knowledgebase/.sync_state.production.json (for ENVIRONMENT=production)
        """
        env = os.environ.get("ENVIRONMENT", "development")
        return Path(f"knowledgebase/.sync_state.{env}.json")

    def __init__(self, config: Config, dry_run: bool = False):
        """Initialize sync manager.

        Args:
            config: Bot configuration
            dry_run: If True, don't actually upload/index documents
        """
        self.config = config
        self.dry_run = dry_run

        # Setup database
        engine = create_engine(config.database_url)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()

        # Initialize CLI (has all document operations)
        self.cli = DocumentCLI(config)

        # Get environment-specific sync state file
        self.sync_state_file = self.get_sync_state_file()

        # Load sync state
        self.sync_state = self._load_sync_state()

    def _load_sync_state(self) -> Dict[str, str]:
        """Load previous sync state (file hashes).

        Returns:
            Dictionary of {filename: hash}
        """
        if self.sync_state_file.exists():
            try:
                with open(self.sync_state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load sync state: {e}")
                return {}
        return {}

    def _save_sync_state(self) -> None:
        """Save current sync state to file."""
        try:
            self.sync_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.sync_state_file, "w") as f:
                json.dump(self.sync_state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sync state: {e}")

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        """Calculate SHA256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            Hex string hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_pending_files(self) -> Dict[str, Path]:
        """Find new or modified files in upload folder.

        Returns:
            Dictionary of {filename: Path} for pending files
        """
        if not self.UPLOAD_FOLDER.exists():
            logger.warning(f"Upload folder does not exist: {self.UPLOAD_FOLDER}")
            return {}

        pending = {}

        for file_path in self.UPLOAD_FOLDER.rglob("*"):
            # Skip directories and hidden files
            if file_path.is_dir() or file_path.name.startswith("."):
                continue

            # Check supported extensions
            if file_path.suffix.lower() not in [".pdf", ".txt", ".md"]:
                logger.debug(f"Skipping unsupported file type: {file_path.name}")
                continue

            # Calculate hash
            file_hash = self._hash_file(file_path)

            # Check if file is new or modified
            relative_path = str(file_path.relative_to(self.UPLOAD_FOLDER))
            if relative_path not in self.sync_state or self.sync_state[relative_path] != file_hash:
                pending[relative_path] = file_path
                logger.debug(f"Found pending file: {relative_path}")

        return pending

    def sync_documents(self) -> bool:
        """Find and upload pending documents.

        Returns:
            True if all documents synced successfully
        """
        pending = self.get_pending_files()

        if not pending:
            print("✓ No new documents to sync.")
            return True

        print(f"\n📁 Found {len(pending)} document(s) to sync:\n")

        success_count = 0
        failed_docs = []

        for idx, (relative_path, file_path) in enumerate(pending.items(), 1):
            print(f"  [{idx}/{len(pending)}] {relative_path}")

            if self.dry_run:
                print(f"      [DRY-RUN] Would upload: {file_path}")
                success_count += 1
                continue

            try:
                # Infer document type from folder structure
                # e.g., documents/upload/laws_of_game/laws_2024-25.pdf
                parts = Path(relative_path).parts
                doc_type = parts[0] if len(parts) > 1 else "general"
                filename = file_path.stem

                print(f"      Type: {doc_type}")
                print(f"      Uploading...")

                # Upload document
                if self.cli.upload(
                    file_path=str(file_path),
                    document_type=doc_type,
                    version=self._extract_version(filename),
                    uploaded_by="sync",
                ):
                    # Move to indexed folder (after successful upload)
                    dest_path = (Path.cwd() / self.INDEXED_FOLDER / relative_path).resolve()
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.rename(dest_path)
                    print(f"      ✓ Moved to {dest_path.relative_to(Path.cwd())}")

                    # Update sync state
                    self.sync_state[relative_path] = self._hash_file(dest_path)
                    success_count += 1
                else:
                    failed_docs.append(relative_path)
                    print(f"      ✗ Upload failed")

            except Exception as e:
                logger.error(f"Error syncing {relative_path}: {e}")
                failed_docs.append(relative_path)
                print(f"      ✗ Error: {e}")

        # Save updated sync state
        self._save_sync_state()

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"✅ Synced {success_count}/{len(pending)} document(s)")

        if failed_docs:
            print(f"\n⚠️  Failed documents:")
            for doc in failed_docs:
                print(f"  - {doc}")
                print(f"    Fix and move back to documents/upload/ to retry")

        return len(failed_docs) == 0

    @staticmethod
    def _extract_version(filename: str) -> str:
        """Try to extract version from filename.

        Examples:
            laws_2024-25.pdf → "2024-25"
            laws_of_game_2024.txt → "2024"
            document_v1.2.md → "1.2"

        Args:
            filename: Filename without extension

        Returns:
            Version string or empty string if not found
        """
        import re

        # Look for patterns like 2024-25, 2024, v1.2, etc.
        patterns = [
            r"(\d{4}-\d{2})",  # 2024-25
            r"v(\d+\.\d+)",    # v1.2
            r"(\d{4})",        # 2024
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)

        return ""

    def index_uploaded_documents(self, limit: int = None) -> bool:
        """Index all uploaded documents that are ready.

        Args:
            limit: Maximum number to index

        Returns:
            True if successful
        """
        print("\n🔄 Indexing uploaded documents...\n")

        pending = self.cli.doc_service.get_pending_documents()

        if not pending:
            print("✓ No pending documents to index.")
            return True

        if limit:
            pending = pending[:limit]

        success_count = 0
        for i, doc_info in enumerate(pending, 1):
            print(f"[{i}/{len(pending)}] Indexing: {doc_info.name}")

            if self.dry_run:
                print(f"    [DRY-RUN] Would index document {doc_info.id}")
                success_count += 1
                continue

            if self.cli.index_document(doc_info.id):
                success_count += 1
            else:
                print(f"    ✗ Failed to index {doc_info.name}")

        print(f"\n{'=' * 60}")
        print(f"✅ Indexed {success_count}/{len(pending)} document(s)")

        return success_count == len(pending)

    def close(self):
        """Close connections."""
        self.cli.close()


def main():
    """Main entry point."""
    # Load configuration
    config = Config.from_env()

    # Setup logging
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Document folder monitor and auto-sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Folder Structure:
  documents/upload/     - Put new documents here
  documents/indexed/    - Successfully indexed docs (moved here)
  documents/archive/    - Old/deprecated documents

Examples:
  python -m src.cli.document_sync              # Sync once
  python -m src.cli.document_sync --dry-run    # See what would happen
  make sync-documents                          # Via Makefile

Document Organization:
  documents/upload/laws_of_game/laws_2024-25.pdf
  documents/upload/faq/faq_2024.txt
  documents/upload/tournament_rules/rules_2024.md
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually syncing",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Only index pending documents, don't sync from folder",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch folder for changes and sync continuously (future)",
    )

    args = parser.parse_args()

    if args.watch:
        print("⚠️  Watch mode not yet implemented")
        print("Use a scheduler (cron, systemd timer) or CI/CD to run this periodically")
        return 1

    # Create sync manager
    sync = DocumentSyncManager(config, dry_run=args.dry_run)

    try:
        if args.dry_run:
            print("\n[DRY-RUN MODE] - No changes will be made\n")

        if args.index_only:
            # Only index existing pending documents
            success = sync.index_uploaded_documents()
        else:
            # Sync from folder and then index
            success = sync.sync_documents()
            if success and not args.dry_run:
                # After syncing, index the newly uploaded documents
                print("\n" + "=" * 60)
                success = sync.index_uploaded_documents()

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        sync.close()


if __name__ == "__main__":
    sys.exit(main())
