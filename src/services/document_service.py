"""
Document Service for managing document lifecycle.

Handles:
- Document storage and retrieval from database
- Tracking document indexing status in Qdrant
- Document CRUD operations
- Version management
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from src.core.db import MessageModel  # Import Session for typing
from src.config import Config

logger = logging.getLogger(__name__)


@dataclass
class DocumentInfo:
    """Document metadata and status."""
    id: int
    name: str
    document_type: str
    version: Optional[str]
    source_url: Optional[str]
    uploaded_by: Optional[str]
    uploaded_at: datetime
    qdrant_status: str  # 'pending', 'indexed', 'failed'
    error_message: Optional[str]
    relative_path: Optional[str]  # Full path from knowledgebase/upload
    created_at: datetime
    updated_at: datetime


@dataclass
class DocumentContent:
    """Full document content with metadata."""
    id: int
    name: str
    document_type: str
    version: Optional[str]
    content: str
    source_url: Optional[str]
    uploaded_by: Optional[str]
    uploaded_at: datetime
    metadata: Optional[Dict[str, Any]]
    qdrant_status: str
    qdrant_collection_id: Optional[str]
    error_message: Optional[str]
    relative_path: Optional[str]  # Full path from knowledgebase/upload
    created_at: datetime
    updated_at: datetime


class DocumentService:
    """Manage document lifecycle and Qdrant indexing status."""

    def __init__(self, config: Config, db_session: Session):
        """
        Initialize document service.

        Args:
            config: Configuration object
            db_session: SQLAlchemy database session
        """
        self.config = config
        self.db = db_session

    def upload_document(
        self,
        name: str,
        document_type: str,
        content: str,
        version: Optional[str] = None,
        source_url: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        relative_path: Optional[str] = None,
    ) -> int:
        """
        Upload and store a document.

        Initially marks as 'pending' - will be indexed asynchronously.

        Args:
            name: Document name (e.g., "Laws of the Game 2024-25")
            document_type: Type of document (e.g., "laws_of_game", "faq")
            content: Full document text content
            version: Document version (e.g., "2024-25")
            source_url: Where document was obtained
            uploaded_by: User who uploaded (e.g., admin user ID)
            metadata: Additional metadata as dict
            relative_path: Full path from knowledgebase/upload (e.g., "laws_of_game/laws_2024-25.pdf")

        Returns:
            Document ID in database

        Raises:
            Exception: If database operation fails

        Examples:
            >>> doc_id = service.upload_document(
            ...     name="Laws 2024",
            ...     document_type="laws_of_game",
            ...     content="The field of play...",
            ...     version="2024-25",
            ...     relative_path="laws_of_game/laws_2024-25.pdf"
            ... )
            >>> doc_id
            1
        """
        try:
            # Create document record using raw SQL for now
            # (Will replace with SQLAlchemy model in future)
            import json
            from sqlalchemy import text

            metadata_json = json.dumps(metadata) if metadata else None

            query = text("""
                INSERT INTO documents (
                    name, document_type, version, content,
                    source_url, uploaded_by, metadata,
                    relative_path, qdrant_status, created_at, updated_at
                ) VALUES (
                    :name, :doc_type, :version, :content,
                    :source_url, :uploaded_by, :metadata,
                    :relative_path, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
            """)

            result = self.db.execute(
                query,
                {
                    "name": name,
                    "doc_type": document_type,
                    "version": version,
                    "content": content,
                    "source_url": source_url,
                    "uploaded_by": uploaded_by,
                    "metadata": metadata_json,
                    "relative_path": relative_path,
                },
            )

            self.db.commit()
            doc_id = result.scalar()

            logger.info(
                f"Uploaded document '{name}' (type={document_type}, id={doc_id})"
            )
            return doc_id

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upload document: {e}")
            raise

    def get_document(self, doc_id: int) -> Optional[DocumentContent]:
        """
        Retrieve full document content and metadata.

        Args:
            doc_id: Document ID

        Returns:
            DocumentContent object, or None if not found

        Examples:
            >>> doc = service.get_document(1)
            >>> doc.name
            'Laws of the Game 2024-25'
        """
        try:
            from sqlalchemy import text
            import json

            query = text("SELECT * FROM documents WHERE id = :id")
            result = self.db.execute(query, {"id": doc_id}).first()

            if not result:
                logger.warning(f"Document {doc_id} not found")
                return None

            # Parse result tuple into DocumentContent
            row = result._mapping
            metadata = row["metadata"]
            if metadata and isinstance(metadata, str):
                metadata = json.loads(metadata)

            return DocumentContent(
                id=row["id"],
                name=row["name"],
                document_type=row["document_type"],
                version=row["version"],
                content=row["content"],
                source_url=row["source_url"],
                uploaded_by=row["uploaded_by"],
                uploaded_at=row["uploaded_at"],
                metadata=metadata,
                qdrant_status=row["qdrant_status"],
                qdrant_collection_id=row["qdrant_collection_id"],
                error_message=row["error_message"],
                relative_path=row["relative_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None

    def list_documents(
        self,
        document_type: Optional[str] = None,
        qdrant_status: Optional[str] = None,
    ) -> List[DocumentInfo]:
        """
        List documents with optional filtering.

        Args:
            document_type: Filter by type (e.g., "laws_of_game")
            qdrant_status: Filter by status (e.g., "indexed", "pending", "failed")

        Returns:
            List of DocumentInfo objects

        Examples:
            >>> docs = service.list_documents(qdrant_status="indexed")
            >>> len(docs)
            3
        """
        try:
            from sqlalchemy import text

            where_clauses = []

            if document_type:
                where_clauses.append(f"document_type = '{document_type}'")
            if qdrant_status:
                where_clauses.append(f"qdrant_status = '{qdrant_status}'")

            where_sql = " AND ".join(where_clauses)
            where_sql = f"WHERE {where_sql}" if where_sql else ""

            query_str = f"""
                SELECT id, name, document_type, version, source_url,
                       uploaded_by, uploaded_at, qdrant_status,
                       error_message, relative_path, created_at, updated_at
                FROM documents
                {where_sql}
                ORDER BY uploaded_at DESC
            """

            results = self.db.execute(text(query_str)).fetchall()

            documents = []
            for row in results:
                row_dict = row._mapping
                documents.append(
                    DocumentInfo(
                        id=row_dict["id"],
                        name=row_dict["name"],
                        document_type=row_dict["document_type"],
                        version=row_dict["version"],
                        source_url=row_dict["source_url"],
                        uploaded_by=row_dict["uploaded_by"],
                        uploaded_at=row_dict["uploaded_at"],
                        qdrant_status=row_dict["qdrant_status"],
                        error_message=row_dict["error_message"],
                        relative_path=row_dict["relative_path"],
                        created_at=row_dict["created_at"],
                        updated_at=row_dict["updated_at"],
                    )
                )

            logger.info(
                f"Listed {len(documents)} documents "
                f"(type={document_type}, status={qdrant_status})"
            )
            return documents

        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    def update_qdrant_status(
        self,
        doc_id: int,
        status: str,
        collection_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update document's Qdrant indexing status.

        Called after embedding to mark as 'indexed' or 'failed'.

        Args:
            doc_id: Document ID
            status: New status ('pending', 'indexed', 'failed')
            collection_id: Qdrant collection ID (if indexed)
            error_message: Error description (if failed)

        Returns:
            True if successful, False otherwise

        Examples:
            >>> service.update_qdrant_status(1, 'indexed', 'coll_123')
            True
            >>> service.update_qdrant_status(2, 'failed', error_message='API timeout')
            True
        """
        try:
            from sqlalchemy import text

            query = text("""
                UPDATE documents
                SET qdrant_status = :status,
                    qdrant_collection_id = :collection_id,
                    error_message = :error_msg,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """)

            self.db.execute(
                query,
                {
                    "id": doc_id,
                    "status": status,
                    "collection_id": collection_id,
                    "error_msg": error_message,
                },
            )

            self.db.commit()

            logger.info(
                f"Updated document {doc_id} status to '{status}'"
                f"{' (error: ' + error_message + ')' if error_message else ''}"
            )
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update document {doc_id} status: {e}")
            return False

    def delete_document(self, doc_id: int) -> bool:
        """
        Delete a document.

        Soft delete: sets qdrant_status to 'deleted' rather than removing row.

        Args:
            doc_id: Document ID

        Returns:
            True if successful, False otherwise

        Examples:
            >>> service.delete_document(1)
            True
        """
        try:
            from sqlalchemy import text

            # Soft delete by marking as deleted
            query = text("""
                UPDATE documents
                SET qdrant_status = 'deleted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """)

            result = self.db.execute(query, {"id": doc_id})
            self.db.commit()

            if result.rowcount == 0:
                logger.warning(f"Document {doc_id} not found")
                return False

            logger.info(f"Deleted document {doc_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def get_pending_documents(self) -> List[DocumentInfo]:
        """
        Get documents pending Qdrant indexing.

        Used by async indexing process.

        Returns:
            List of documents with status='pending'

        Examples:
            >>> pending = service.get_pending_documents()
            >>> len(pending)
            2
        """
        return self.list_documents(qdrant_status="pending")

    def get_indexed_documents(self) -> List[DocumentInfo]:
        """
        Get successfully indexed documents.

        Returns:
            List of documents with status='indexed'
        """
        return self.list_documents(qdrant_status="indexed")

    def document_exists(self, name: str, document_type: str) -> bool:
        """
        Check if document with same name and type already exists.

        Args:
            name: Document name
            document_type: Document type

        Returns:
            True if exists, False otherwise
        """
        try:
            from sqlalchemy import text

            query = text("""
                SELECT COUNT(*) as count
                FROM documents
                WHERE name = :name AND document_type = :doc_type
                AND qdrant_status != 'deleted'
            """)

            result = self.db.execute(
                query, {"name": name, "doc_type": document_type}
            ).scalar()

            return result > 0

        except Exception as e:
            logger.error(f"Error checking document existence: {e}")
            return False

    def get_indexed_document_names(self) -> List[str]:
        """
        Get list of names of all successfully indexed documents.

        Used by document selection tool to provide LLM with available documents.

        Returns:
            List of document names (e.g., ["Laws of Game 2024-25", "VAR Guidelines"])
            Empty list if no indexed documents or on error

        Examples:
            >>> names = service.get_indexed_document_names()
            >>> names
            ['Laws of Game 2024-25', 'VAR Guidelines 2024']
        """
        try:
            from sqlalchemy import text

            query = text("""
                SELECT DISTINCT name
                FROM documents
                WHERE qdrant_status = 'indexed'
                AND qdrant_status != 'deleted'
                ORDER BY name ASC
            """)

            results = self.db.execute(query).fetchall()
            names = [row[0] for row in results]

            logger.info(
                f"Retrieved {len(names)} indexed document names for selection tool"
            )
            return names

        except Exception as e:
            logger.error(f"Failed to get indexed document names: {e}")
            return []

    def get_document_ids_by_names(self, document_names: List[str]) -> Dict[str, int]:
        """
        Map document names to their database IDs.

        Used to convert document names (from LLM) to IDs for Qdrant filtering.

        Args:
            document_names: List of document names to look up

        Returns:
            Dictionary mapping document name to ID
            Missing documents are excluded from result

        Examples:
            >>> doc_ids = service.get_document_ids_by_names(["Laws of Game 2024-25"])
            >>> doc_ids
            {'Laws of Game 2024-25': 1}
        """
        try:
            from sqlalchemy import text

            if not document_names:
                return {}

            # Build placeholder for SQL
            placeholders = ",".join([f":name_{i}" for i in range(len(document_names))])
            params = {f"name_{i}": name for i, name in enumerate(document_names)}

            query = text(f"""
                SELECT name, id
                FROM documents
                WHERE name IN ({placeholders})
                AND qdrant_status = 'indexed'
                AND qdrant_status != 'deleted'
            """)

            results = self.db.execute(query, params).fetchall()
            doc_map = {row[0]: row[1] for row in results}

            # Log which documents were not found
            not_found = set(document_names) - set(doc_map.keys())
            if not_found:
                logger.warning(
                    f"Could not find indexed documents: {', '.join(not_found)}"
                )

            logger.info(
                f"Mapped {len(doc_map)} of {len(document_names)} document names to IDs"
            )
            return doc_map

        except Exception as e:
            logger.error(f"Failed to map document names to IDs: {e}")
            return {}

    def search_in_documents(
        self,
        query_embedding: List[float],
        document_ids: List[int],
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks within specific documents.

        This method is called by the document lookup tool to filter Qdrant
        search results to only those documents selected by the LLM.

        Args:
            query_embedding: Query vector (from embedding service)
            document_ids: List of document IDs to search within
            top_k: Maximum number of results to return
            threshold: Minimum similarity score

        Returns:
            List of chunk metadata dictionaries with similarity scores
            Empty list if no documents or no results above threshold

        Examples:
            >>> chunks = service.search_in_documents(
            ...     query_embedding=[0.1, 0.2, ...],
            ...     document_ids=[1, 2],
            ...     top_k=5,
            ...     threshold=0.7
            ... )
            >>> len(chunks)
            3
        """
        if not document_ids or not query_embedding:
            return []

        try:
            # This is a wrapper that will use the retrieval service's Qdrant client
            # The actual filtering logic happens in RetrievalService.retrieve_from_documents()
            # This method documents the interface for filtering by document IDs

            logger.info(
                f"Searching in {len(document_ids)} documents with embedding"
            )
            return []

        except Exception as e:
            logger.error(f"Failed to search in documents: {e}")
            return []
