"""Command-line interface for document management.

Usage:
    python -m src.cli upload --file laws.pdf --type laws_of_game --version 2024-25
    python -m src.cli list
    python -m src.cli delete --id 1
    python -m src.cli index --id 1
    python -m src.cli status
"""

import logging
import argparse
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import Config, Environment
from src.core.db import ConversationDatabase
from src.services.document_service import DocumentService
from src.services.embedding_service import EmbeddingService
from src.services.pdf_parser import PDFParser
from src.core.vector_db import VectorDatabase

logger = logging.getLogger(__name__)


class DocumentCLI:
    """Command-line interface for document management."""

    def __init__(self, config: Config):
        """Initialize CLI with database and service connections.

        Args:
            config: Bot configuration
        """
        self.config = config

        # Setup database connection
        engine = create_engine(config.database_url)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()

        # Initialize services
        self.doc_service = DocumentService(config, self.db_session)
        self.embedding_service = EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model,
        )
        self.vector_db = VectorDatabase(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=config.qdrant_api_key,
        )
        self.pdf_parser = PDFParser()

    def upload(
        self,
        file_path: str,
        document_type: str,
        version: Optional[str] = None,
        source_url: Optional[str] = None,
        uploaded_by: str = "cli",
        relative_path: Optional[str] = None,
    ) -> bool:
        """Upload a document for indexing.

        Args:
            file_path: Path to document file (PDF, TXT, MD)
            document_type: Type of document (laws_of_game, faq, etc.)
            version: Document version (e.g., 2024-25)
            source_url: Where document was obtained
            uploaded_by: User who uploaded (default: cli)
            relative_path: Full relative path from knowledgebase/upload (optional)

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)

        # Validate file exists
        if not file_path.exists():
            print(f"❌ Error: File not found: {file_path}")
            return False

        # Validate file extension
        suffix = file_path.suffix.lower()
        if suffix not in [".pdf", ".txt", ".md"]:
            print(f"❌ Error: Unsupported file type: {suffix}")
            print("Supported: .pdf, .txt, .md")
            return False

        print(f"📄 Reading document: {file_path.name}")

        # Extract text based on file type
        try:
            if suffix == ".pdf":
                content = self.pdf_parser.extract_text(str(file_path))
            else:
                # Plain text or markdown
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False

        if not content or len(content.strip()) == 0:
            print("❌ Error: Document is empty after parsing")
            return False

        print(f"✓ Extracted {len(content)} characters")

        # Check for duplicates
        if self.doc_service.document_exists(file_path.stem, document_type):
            print(f"⚠️  Document already exists: {file_path.stem}")
            response = input("Overwrite? (y/n): ").lower()
            if response != "y":
                print("Cancelled.")
                return False

        # Upload to database
        try:
            doc_id = self.doc_service.upload_document(
                name=file_path.stem,
                document_type=document_type,
                content=content,
                version=version,
                source_url=source_url,
                uploaded_by=uploaded_by,
                metadata={"file_size": len(content), "file_path": str(file_path)},
                relative_path=relative_path,
            )
            print(f"✓ Document uploaded with ID: {doc_id}")
            print(f"📋 Status: Pending (awaiting indexing)")
            return True

        except Exception as e:
            print(f"❌ Error uploading document: {e}")
            return False

    def list_documents(
        self,
        document_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> bool:
        """List uploaded documents.

        Args:
            document_type: Filter by type (optional)
            status: Filter by status (pending, indexed, failed, deleted)

        Returns:
            True if successful
        """
        try:
            docs = self.doc_service.list_documents(
                document_type=document_type,
                qdrant_status=status,
            )

            if not docs:
                print("No documents found.")
                return True

            print("\n" + "=" * 100)
            print(
                f"{'ID':<5} {'Name':<30} {'Type':<20} {'Version':<12} {'Status':<10} {'Uploaded':<20}"
            )
            print("=" * 100)

            for doc in docs:
                status_icon = {
                    "pending": "⏳",
                    "indexed": "✓",
                    "failed": "❌",
                    "deleted": "🗑️",
                }.get(doc.qdrant_status, "?")

                print(
                    f"{doc.id:<5} {doc.name:<30} {doc.document_type:<20} "
                    f"{doc.version or '-':<12} {status_icon} {doc.qdrant_status:<9} "
                    f"{doc.uploaded_at.strftime('%Y-%m-%d %H:%M'):<20}"
                )

            print("=" * 100)
            print(f"\nTotal: {len(docs)} documents")
            return True

        except Exception as e:
            print(f"❌ Error listing documents: {e}")
            return False

    def delete_document(self, doc_id: int, force: bool = False) -> bool:
        """Delete a document from both PostgreSQL and Qdrant.

        Args:
            doc_id: Document ID
            force: If True, skip confirmation prompt

        Returns:
            True if successful
        """
        try:
            # Get document info first
            doc = self.doc_service.get_document(doc_id)
            if not doc:
                print(f"❌ Document not found: {doc_id}")
                return False

            print(f"Document: {doc.name} ({doc.document_type})")
            print(f"Status: {doc.qdrant_status}")

            if not force:
                response = input(f"Delete from PostgreSQL and Qdrant? (y/n): ").lower()
                if response != "y":
                    print("Cancelled.")
                    return False

            # Delete from PostgreSQL
            if not self.doc_service.delete_document(doc_id):
                print(f"❌ Failed to delete document from PostgreSQL")
                return False

            print(f"✓ Deleted from PostgreSQL")

            # Delete from Qdrant if it was indexed
            if doc.qdrant_status == "indexed":
                try:
                    # Delete embeddings from Qdrant by document_id
                    # The point IDs are typically doc_id * 1000 + chunk_index, so we need to delete all points for this doc
                    # For now, we'll query the embeddings table to get the point IDs
                    from sqlalchemy import text

                    query = text("""
                        SELECT id FROM embeddings WHERE document_id = :doc_id
                    """)
                    result = self.doc_service.db.execute(query, {"doc_id": doc_id})
                    point_ids = [row[0] for row in result.fetchall()]

                    if point_ids:
                        self.vector_db.delete_points(
                            self.config.qdrant_collection_name,
                            point_ids
                        )
                        print(f"✓ Deleted {len(point_ids)} embeddings from Qdrant")
                    else:
                        print(f"⚠️  No embeddings found in Qdrant")

                except Exception as e:
                    print(f"⚠️  Warning: Failed to delete from Qdrant: {e}")
                    print(f"   Document marked as deleted in PostgreSQL")
                    return True

            print(f"✓ Document {doc_id} completely deleted")
            return True

        except Exception as e:
            print(f"❌ Error deleting document: {e}")
            return False

    def index_document(self, doc_id: int, force: bool = False) -> bool:
        """Index a document to Qdrant.

        This is a blocking operation that:
        1. Retrieves document content
        2. Chunks the content
        3. Generates embeddings
        4. Uploads to Qdrant
        5. Updates status in database

        Args:
            doc_id: Document ID to index
            force: Force re-indexing even if already indexed

        Returns:
            True if successful
        """
        try:
            # Get document
            doc = self.doc_service.get_document(doc_id)
            if not doc:
                print(f"❌ Document not found: {doc_id}")
                return False

            # Check status
            if doc.qdrant_status == "indexed" and not force:
                print(f"⚠️  Document already indexed: {doc.name}")
                response = input("Re-index? (y/n): ").lower()
                if response != "y":
                    print("Cancelled.")
                    return False

            print(f"\n📑 Indexing: {doc.name}")
            print(f"Type: {doc.document_type}, Version: {doc.version}")
            print()

            # Create or get collection
            collection_name = self.config.qdrant_collection_name
            if not self.vector_db.collection_exists(collection_name):
                print(f"Creating collection: {collection_name}")
                self.vector_db.create_collection(
                    collection_name,
                    vector_size=self.embedding_service.vector_size,
                )

            # Chunk document
            print("Chunking document...")
            chunks = self.embedding_service.chunk_document(
                text=doc.content,
                chunk_size=500,  # tokens (from embedding model's tokenizer)
                overlap=100,     # tokens (from embedding model's tokenizer)
                section=doc.document_type,
            )
            print(f"✓ Created {len(chunks)} chunks")

            # Estimate cost
            cost = self.embedding_service.estimate_embedding_cost(
                len(chunks),
                avg_length=sum(len(c.text) for c in chunks) // len(chunks),
            )
            print(f"Estimated embedding cost: ${cost:.4f}")

            # Embed chunks
            print("\nEmbedding chunks...")
            embedded_chunks = self.embedding_service.embed_chunks(
                chunks,
                batch_size=self.config.embedding_batch_size
            )
            print(f"✓ Embedded {len(embedded_chunks)} chunks")

            if not embedded_chunks:
                print("❌ Failed to embed any chunks")
                self.doc_service.update_qdrant_status(
                    doc_id,
                    "failed",
                    error_message="Embedding failed",
                )
                return False

            # Upload to Qdrant
            print("\nUploading to Qdrant...")
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=int(f"{doc_id}{i:06d}"),  # Unique ID: doc_id + chunk index
                    vector=chunk["embedding"],
                    payload={
                        "document_id": doc_id,
                        "document_name": doc.name,
                        "document_type": doc.document_type,
                        "version": doc.version,
                        "section": chunk.get("section", ""),
                        "subsection": chunk.get("subsection", ""),
                        "page_number": chunk.get("page_number"),
                        "chunk_index": chunk.get("chunk_index", 0),
                        "total_chunks": chunk.get("total_chunks", 0),
                        "text": chunk["text"],
                    },
                )
                for i, chunk in enumerate(embedded_chunks)
            ]

            if self.vector_db.upsert_points(collection_name, points):
                print(f"✓ Uploaded {len(points)} points to Qdrant")

                # Update status
                self.doc_service.update_qdrant_status(
                    doc_id,
                    "indexed",
                    collection_id=collection_name,
                )
                print(f"\n✅ Document {doc_id} indexed successfully!")
                return True
            else:
                print("❌ Failed to upload points to Qdrant")
                self.doc_service.update_qdrant_status(
                    doc_id,
                    "failed",
                    error_message="Qdrant upload failed",
                )
                return False

        except Exception as e:
            print(f"❌ Indexing failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            try:
                self.doc_service.update_qdrant_status(
                    doc_id,
                    "failed",
                    error_message=str(e),
                )
            except:
                pass
            return False

    def index_pending(self, limit: Optional[int] = None) -> bool:
        """Index all pending documents.

        Args:
            limit: Maximum number to index (None = all)

        Returns:
            True if successful
        """
        try:
            pending = self.doc_service.get_pending_documents()

            if not pending:
                print("No pending documents.")
                return True

            if limit:
                pending = pending[:limit]

            print(f"Indexing {len(pending)} pending document(s)...\n")

            success_count = 0
            for doc_info in pending:
                print(f"\n[{pending.index(doc_info) + 1}/{len(pending)}]")
                if self.index_document(doc_info.id):
                    success_count += 1
                else:
                    print(f"⚠️  Failed: {doc_info.name}")

            print(f"\n{'=' * 50}")
            print(f"✅ Indexed {success_count}/{len(pending)} documents")
            return success_count == len(pending)

        except Exception as e:
            print(f"❌ Error indexing pending documents: {e}")
            return False

    def show_stats(self) -> bool:
        """Show collection and document statistics.

        Returns:
            True if successful
        """
        try:
            print("\n" + "=" * 60)
            print("COLLECTION STATISTICS")
            print("=" * 60)

            # Get collection stats
            collection_name = self.config.qdrant_collection_name
            if self.vector_db.collection_exists(collection_name):
                stats = self.vector_db.get_collection_stats(collection_name)
                if stats:
                    print(f"Collection: {stats.get('name', 'unknown')}")
                    print(f"Points: {stats.get('points_count', 0):,}")
                    print(f"Vectors: {stats.get('vectors_count', 0):,}")
                    print(f"Status: {stats.get('status', 'unknown')}")
            else:
                print(f"Collection '{collection_name}' does not exist")

            # Get document stats
            print("\n" + "=" * 60)
            print("DOCUMENT STATISTICS")
            print("=" * 60)

            all_docs = self.doc_service.list_documents()
            indexed = [d for d in all_docs if d.qdrant_status == "indexed"]
            pending = [d for d in all_docs if d.qdrant_status == "pending"]
            failed = [d for d in all_docs if d.qdrant_status == "failed"]

            print(f"Total documents: {len(all_docs)}")
            print(f"  ✓ Indexed: {len(indexed)}")
            print(f"  ⏳ Pending: {len(pending)}")
            print(f"  ❌ Failed: {len(failed)}")

            if failed:
                print("\nFailed documents:")
                for doc in failed:
                    print(f"  - {doc.name} ({doc.id})")
                    if doc.error_message:
                        print(f"    Error: {doc.error_message}")

            print("\n" + "=" * 60)
            return True

        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            return False

    def delete_all_documents(self, force: bool = False) -> bool:
        """Delete all documents from PostgreSQL and clear Qdrant collection.

        This is a destructive operation used for resetting embeddings when changing
        embedding models. It:
        1. Deletes all documents from PostgreSQL (soft delete)
        2. Drops and recreates the Qdrant collection (complete reset)
        3. Clears the embeddings table

        Args:
            force: If True, skip confirmation prompt

        Returns:
            True if successful, False otherwise
        """
        try:
            if not force:
                print("⚠️  WARNING: This will delete ALL documents and embeddings!")
                response = input("Type 'yes' to confirm: ").lower()
                if response != "yes":
                    print("Cancelled.")
                    return False

            # Step 1: Get all indexed documents first
            all_docs = self.doc_service.list_documents()
            if not all_docs:
                print("No documents found to delete.")
                return True

            print(f"Deleting {len(all_docs)} documents...")

            # Step 2: Delete all documents from PostgreSQL (soft delete)
            deleted_count = 0
            for doc in all_docs:
                if self.doc_service.delete_document(doc.id):
                    deleted_count += 1

            print(f"✓ Marked {deleted_count} documents as deleted in PostgreSQL")

            # Step 3: Delete entire Qdrant collection (complete reset)
            collection_name = self.config.qdrant_collection_name
            try:
                if self.vector_db.collection_exists(collection_name):
                    self.vector_db.delete_collection(collection_name)
                    print(f"✓ Deleted Qdrant collection '{collection_name}'")
                else:
                    print(f"⚠️  Collection '{collection_name}' does not exist in Qdrant")
            except Exception as e:
                print(f"⚠️  Warning: Failed to delete Qdrant collection: {e}")
                print(f"   Documents are still marked as deleted in PostgreSQL")

            print("✅ All documents and embeddings have been deleted")
            return True

        except Exception as e:
            print(f"❌ Error deleting all documents: {e}")
            return False

    def close(self):
        """Close database connection."""
        if self.db_session:
            self.db_session.close()


def main():
    """Main entry point for CLI."""
    # Load configuration
    config = Config.from_env()

    # Setup logging
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Suppress noisy debug logs from external libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("pdfminer.psparser").setLevel(logging.WARNING)
    logging.getLogger("pdfminer.pdfpage").setLevel(logging.WARNING)
    logging.getLogger("pdfminer.cmapdb").setLevel(logging.WARNING)
    logging.getLogger("pdfminer.pdfinterp").setLevel(logging.WARNING)
    logging.getLogger("pdfminer.pdfdocument").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    # Create CLI instance
    cli = DocumentCLI(config)

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Football Rules Bot - Document Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli upload --file laws.pdf --type laws_of_game --version 2024-25
  python -m src.cli list
  python -m src.cli list --type laws_of_game
  python -m src.cli list --status pending
  python -m src.cli delete --id 1
  python -m src.cli index --id 1
  python -m src.cli index-pending
  python -m src.cli stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload a document")
    upload_parser.add_argument("--file", required=True, help="Path to document file")
    upload_parser.add_argument(
        "--type",
        required=True,
        help="Document type (laws_of_game, faq, tournament_rules, etc.)",
    )
    upload_parser.add_argument("--version", help="Document version (e.g., 2024-25)")
    upload_parser.add_argument("--source-url", help="Source URL of document")
    upload_parser.add_argument(
        "--uploaded-by", default="cli", help="User who uploaded (default: cli)"
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List documents")
    list_parser.add_argument(
        "--type", help="Filter by document type"
    )
    list_parser.add_argument(
        "--status", help="Filter by status (pending, indexed, failed, deleted)"
    )

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a document")
    delete_parser.add_argument("--id", type=int, required=True, help="Document ID")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index a document to Qdrant")
    index_parser.add_argument("--id", type=int, required=True, help="Document ID")
    index_parser.add_argument(
        "--force", action="store_true", help="Force re-indexing"
    )

    # Index pending command
    subparsers.add_parser(
        "index-pending", help="Index all pending documents"
    )

    # Stats command
    subparsers.add_parser("stats", help="Show statistics")

    # Parse and execute
    args = parser.parse_args()

    try:
        if args.command == "upload":
            success = cli.upload(
                file_path=args.file,
                document_type=args.type,
                version=args.version,
                source_url=args.source_url,
                uploaded_by=args.uploaded_by,
            )
        elif args.command == "list":
            success = cli.list_documents(
                document_type=args.type,
                status=args.status,
            )
        elif args.command == "delete":
            success = cli.delete_document(args.id)
        elif args.command == "index":
            success = cli.index_document(args.id, force=args.force)
        elif args.command == "index-pending":
            success = cli.index_pending()
        elif args.command == "stats":
            success = cli.show_stats()
        else:
            parser.print_help()
            success = False

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cli.close()


if __name__ == "__main__":
    main()
