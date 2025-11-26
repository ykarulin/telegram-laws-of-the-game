"""Qdrant Vector Database manager for document embeddings."""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
    FieldCondition,
    MatchValue,
    Filter,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """Represents a chunk retrieved from Qdrant."""

    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary representation.

        Returns:
            Dictionary with all chunk fields
        """
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
        }

    def get_source(self) -> str:
        """Get the source document name from metadata.

        Returns:
            Source document name, or 'Unknown' if not available
        """
        return self.metadata.get("document_name", "Unknown")

    def get_section(self) -> str:
        """Get the section name from metadata.

        Returns:
            Section name, or 'Unknown' if not available
        """
        return self.metadata.get("section", "Unknown")


class VectorDatabase:
    """Qdrant vector database manager for semantic search over documents."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Initialize Qdrant client connection.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            api_key: API key for secure instances (optional)
            timeout: Connection timeout in seconds (default 60 for large uploads)
        """
        self.host = host
        self.port = port
        self.api_key = api_key
        self.timeout = timeout

        try:
            # Connect to Qdrant
            if api_key:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    api_key=api_key,
                    timeout=timeout,
                )
            else:
                self.client = QdrantClient(
                    host=host,
                    port=port,
                    timeout=timeout,
                )
            logger.info(f"Connected to Qdrant at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists.

        Args:
            collection_name: Name of the collection

        Returns:
            True if collection exists, False otherwise
        """
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1024,  # multilingual-e5-large uses 1024 dims
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """Create a new vector collection.

        Args:
            collection_name: Name for the collection
            vector_size: Size of embedding vectors
            distance: Distance metric (COSINE, EUCLID, DOT)

        Returns:
            True if collection created or already exists
        """
        try:
            if self.collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' already exists")
                return True

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )
            logger.info(f"Created collection '{collection_name}' with {vector_size}-dim vectors")
            return True
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            raise

    def upsert_points(
        self,
        collection_name: str,
        points: List[PointStruct],
        batch_size: int = 256,
    ) -> bool:
        """Upsert points (vectors with metadata) into a collection.

        Automatically batches large uploads to avoid timeout issues.
        Large documents are split into batches of 256 points each.

        Args:
            collection_name: Target collection name
            points: List of PointStruct objects with vectors and metadata
            batch_size: Number of points per batch (default 256)

        Returns:
            True if successful
        """
        try:
            total_points = len(points)

            # If small batch, upload directly
            if total_points <= batch_size:
                self.client.upsert(
                    collection_name=collection_name,
                    points=points,
                )
                logger.debug(f"Upserted {total_points} points to '{collection_name}'")
                return True

            # For large batches, split into smaller chunks
            logger.info(f"Uploading {total_points} points in batches of {batch_size}")
            for i in range(0, total_points, batch_size):
                batch = points[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_points + batch_size - 1) // batch_size

                logger.debug(f"Uploading batch {batch_num}/{total_batches} ({len(batch)} points)")

                self.client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )

            logger.info(f"Successfully upserted all {total_points} points to '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert points to '{collection_name}': {e}")
            raise

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        min_score: float = 0.0,
        metadata_filter: Optional[Filter] = None,
    ) -> List[RetrievedChunk]:
        """Search for similar vectors in a collection.

        Args:
            collection_name: Collection to search in
            query_vector: Query embedding vector
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold
            metadata_filter: Optional filter by metadata

        Returns:
            List of RetrievedChunk objects, ordered by similarity score (descending)
        """
        try:
            results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=min_score,
                query_filter=metadata_filter,
            ).points

            chunks = []
            for point in results:
                chunk = RetrievedChunk(
                    chunk_id=str(point.id),
                    text=point.payload.get("text", ""),
                    score=point.score,
                    metadata={
                        k: v
                        for k, v in point.payload.items()
                        if k != "text" and k != "vector"
                    },
                )
                chunks.append(chunk)

            logger.debug(f"Search returned {len(chunks)} results with min_score={min_score}")
            return chunks
        except Exception as e:
            logger.error(f"Search failed in '{collection_name}': {e}")
            raise

    def delete_points(
        self,
        collection_name: str,
        point_ids: List[int],
    ) -> bool:
        """Delete points from a collection.

        Args:
            collection_name: Target collection
            point_ids: List of point IDs to delete

        Returns:
            True if successful
        """
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=point_ids,
            )
            logger.info(f"Deleted {len(point_ids)} points from '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete points from '{collection_name}': {e}")
            raise

    def delete_collection(self, collection_name: str) -> bool:
        """Delete an entire collection.

        Args:
            collection_name: Name of collection to delete

        Returns:
            True if successful
        """
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection '{collection_name}': {e}")
            raise

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Get information about a collection.

        Args:
            collection_name: Collection to query

        Returns:
            Dictionary with collection info (point count, vector config, etc.)
        """
        try:
            collection = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "point_count": collection.points_count,
                "vector_size": collection.config.params.vectors.size,
                "distance": str(collection.config.params.vectors.distance),
                "indexed_vectors_count": collection.indexed_vectors_count,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info for '{collection_name}': {e}")
            raise

    def health_check(self) -> bool:
        """Check if Qdrant server is healthy.

        Returns:
            True if server is accessible
        """
        try:
            # Simple health check by listing collections
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
