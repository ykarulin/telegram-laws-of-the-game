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
from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.orm import Session

from src.core.db import DocumentModel
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
    document_metadata: Optional[Dict[str, Any]]
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
            # Validate inputs at boundary
            if not name or not name.strip():
                raise ValueError("Document name cannot be empty")
            if not document_type or not document_type.strip():
                raise ValueError("Document type cannot be empty")
            if not content or not content.strip():
                raise ValueError("Document content cannot be empty")

            # Create document record using SQLAlchemy ORM
            document = DocumentModel(
                name=name.strip(),
                document_type=document_type.strip(),
                version=version.strip() if version else None,
                content=content,
                source_url=source_url.strip() if source_url else None,
                uploaded_by=uploaded_by.strip() if uploaded_by else None,
                document_metadata=metadata,  # SQLAlchemy JSON column handles serialization
                relative_path=relative_path.strip() if relative_path else None,
                qdrant_status='pending',
            )

            self.db.add(document)
            self.db.flush()  # Get the ID without committing
            doc_id = document.id
            self.db.commit()

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
            model = self.db.query(DocumentModel).filter(
                DocumentModel.id == doc_id
            ).first()

            if not model:
                logger.warning(f"Document {doc_id} not found")
                return None

            return DocumentContent(
                id=model.id,
                name=model.name,
                document_type=model.document_type,
                version=model.version,
                content=model.content,
                source_url=model.source_url,
                uploaded_by=model.uploaded_by,
                uploaded_at=model.uploaded_at,
                document_metadata=model.document_metadata,
                qdrant_status=model.qdrant_status,
                qdrant_collection_id=model.qdrant_collection_id,
                error_message=model.error_message,
                relative_path=model.relative_path,
                created_at=model.created_at,
                updated_at=model.updated_at,
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
            # Validate inputs at boundary
            if document_type and not isinstance(document_type, str):
                raise ValueError("document_type must be a string")
            if qdrant_status and not isinstance(qdrant_status, str):
                raise ValueError("qdrant_status must be a string")

            # Build query with ORM filters
            query = self.db.query(DocumentModel)

            if document_type:
                query = query.filter(DocumentModel.document_type == document_type.strip())
            if qdrant_status:
                query = query.filter(DocumentModel.qdrant_status == qdrant_status)

            query = query.order_by(DocumentModel.uploaded_at.desc())
            models = query.all()

            documents = []
            for model in models:
                documents.append(
                    DocumentInfo(
                        id=model.id,
                        name=model.name,
                        document_type=model.document_type,
                        version=model.version,
                        source_url=model.source_url,
                        uploaded_by=model.uploaded_by,
                        uploaded_at=model.uploaded_at,
                        qdrant_status=model.qdrant_status,
                        error_message=model.error_message,
                        relative_path=model.relative_path,
                        created_at=model.created_at,
                        updated_at=model.updated_at,
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
            model = self.db.query(DocumentModel).filter(
                DocumentModel.id == doc_id
            ).first()

            if not model:
                logger.warning(f"Document {doc_id} not found")
                return False

            model.qdrant_status = status
            model.qdrant_collection_id = collection_id
            model.error_message = error_message
            model.updated_at = datetime.now(timezone.utc)

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
            # Soft delete by marking as deleted
            model = self.db.query(DocumentModel).filter(
                DocumentModel.id == doc_id
            ).first()

            if not model:
                logger.warning(f"Document {doc_id} not found")
                return False

            model.qdrant_status = 'deleted'
            model.updated_at = datetime.now(timezone.utc)

            self.db.commit()

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
            count = self.db.query(DocumentModel).filter(
                and_(
                    DocumentModel.name == name,
                    DocumentModel.document_type == document_type,
                    DocumentModel.qdrant_status != 'deleted'
                )
            ).count()

            return count > 0

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
            models = self.db.query(DocumentModel.name).filter(
                and_(
                    DocumentModel.qdrant_status == 'indexed',
                    DocumentModel.qdrant_status != 'deleted'
                )
            ).distinct().order_by(DocumentModel.name.asc()).all()

            names = [model[0] for model in models]

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
            if not document_names:
                return {}

            models = self.db.query(DocumentModel.name, DocumentModel.id).filter(
                and_(
                    DocumentModel.name.in_(document_names),
                    DocumentModel.qdrant_status == 'indexed',
                    DocumentModel.qdrant_status != 'deleted'
                )
            ).all()

            doc_map = {model[0]: model[1] for model in models}

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
