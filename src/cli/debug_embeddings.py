#!/usr/bin/env python3
"""
Debug script to compare embeddings and RAG retrieval between dev/prod environments.

Usage:
    # Compare query embeddings
    python debug_embeddings.py --query "Если вратарь держит мяч в руках слишком долго, то что за это бывает?"

    # Compare vector database contents
    python debug_embeddings.py --show-collection-stats

    # Export all documents from collection
    python debug_embeddings.py --export-collection output.json

    # Test specific documents
    python debug_embeddings.py --find-document "goalkeeper" --limit 10
"""

import argparse
import json
import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.config import load_config
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import VectorDatabase

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmbeddingDebugger:
    """Debug tool for embedding and retrieval issues."""

    def __init__(self):
        """Initialize debugger with config and services."""
        self.config = load_config()
        self.embedding_service = EmbeddingService()
        # Debug script doesn't use document-specific retrieval, so pass None for db_session
        self.retrieval_service = RetrievalService(
            self.config,
            self.embedding_service,
            db_session=None
        )
        self.vector_db = self.retrieval_service.vector_db

    def compare_query_embedding(self, query: str) -> Dict[str, Any]:
        """
        Embed a query and show detailed information.

        Args:
            query: The query to embed

        Returns:
            Dictionary with embedding details
        """
        print(f"\n{'='*80}")
        print(f"QUERY EMBEDDING DEBUG")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Query length: {len(query)} characters")

        embedding = self.embedding_service.embed_text(query)

        if embedding is None:
            print("ERROR: Failed to embed query")
            return {}

        result = {
            'query': query,
            'embedding_dims': len(embedding),
            'first_10_values': embedding[:10],
            'last_10_values': embedding[-10:],
            'min_value': min(embedding),
            'max_value': max(embedding),
            'mean_value': sum(embedding) / len(embedding),
            'std_dev': self._calculate_std_dev(embedding),
        }

        print(f"\nEmbedding Details:")
        print(f"  Dimensions: {result['embedding_dims']}")
        print(f"  Min value: {result['min_value']:.6f}")
        print(f"  Max value: {result['max_value']:.6f}")
        print(f"  Mean value: {result['mean_value']:.6f}")
        print(f"  Std dev: {result['std_dev']:.6f}")
        print(f"  First 10 values: {[f'{v:.6f}' for v in result['first_10_values']]}")
        print(f"  Last 10 values: {[f'{v:.6f}' for v in result['last_10_values']]}")

        return result

    def retrieve_and_compare(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents for a query and show detailed comparison.

        Args:
            query: The query
            top_k: Number of results
            threshold: Similarity threshold

        Returns:
            List of retrieved chunks with details
        """
        print(f"\n{'='*80}")
        print(f"RETRIEVAL DEBUG")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Top-K: {top_k or self.config.top_k_retrievals}")
        print(f"Threshold: {threshold or self.config.similarity_threshold}")

        chunks = self.retrieval_service.retrieve_context(query, top_k, threshold)

        results = []
        for i, chunk in enumerate(chunks, 1):
            result = {
                'rank': i,
                'score': chunk.score,
                'document_name': chunk.metadata.get('document_name', 'Unknown'),
                'section': chunk.metadata.get('section', 'Unknown'),
                'subsection': chunk.metadata.get('subsection', 'Unknown'),
                'text_preview': chunk.text[:150],
                'text_full': chunk.text,
                'chunk_id': chunk.chunk_id,
            }
            results.append(result)

            print(f"\n[Result {i}]")
            print(f"  Score: {result['score']:.4f}")
            print(f"  Document: {result['document_name']}")
            print(f"  Section: {result['section']}")
            print(f"  Subsection: {result['subsection']}")
            print(f"  Preview: {result['text_preview']}...")

        return results

    def show_collection_stats(self) -> Dict[str, Any]:
        """
        Show statistics about the vector collection.

        Returns:
            Dictionary with collection stats
        """
        print(f"\n{'='*80}")
        print(f"COLLECTION STATISTICS")
        print(f"{'='*80}")

        stats = self.retrieval_service.get_collection_stats()

        if not stats:
            print("ERROR: Failed to get collection stats")
            return {}

        print(f"Collection Name: {stats.get('name')}")
        print(f"Points Count: {stats.get('points_count', 'N/A')}")
        print(f"Vectors Count: {stats.get('vectors_count', 'N/A')}")
        print(f"Status: {stats.get('status', 'N/A')}")
        print(f"Vector Size: {stats.get('config', {}).get('vector_size', 'N/A')}")

        return stats

    def export_collection(self, output_file: str, limit: Optional[int] = None) -> int:
        """
        Export all documents from the collection to a JSON file.

        Args:
            output_file: Path to output JSON file
            limit: Maximum documents to export (None = all)

        Returns:
            Number of documents exported
        """
        print(f"\n{'='*80}")
        print(f"EXPORTING COLLECTION")
        print(f"{'='*80}")
        print(f"Output file: {output_file}")

        try:
            # Get collection info
            collection_info = self.vector_db.get_collection_info(
                self.config.qdrant_collection_name
            )
            point_count = collection_info['point_count']
            print(f"Total points in collection: {point_count}")

            all_points = []
            offset = 0
            batch_size = 100
            exported = 0

            while offset < point_count and (limit is None or exported < limit):
                # Scroll points - returns (points, next_page_offset)
                scroll_result = self.vector_db.client.scroll(
                    collection_name=self.config.qdrant_collection_name,
                    limit=batch_size,
                    offset=offset,
                )

                # Handle both tuple and object responses
                if isinstance(scroll_result, tuple):
                    points, next_offset = scroll_result
                else:
                    points = scroll_result.points
                    next_offset = None

                if not points:
                    break

                for point in points:
                    if limit and exported >= limit:
                        break

                    doc = {
                        'id': point.id,
                        'payload': point.payload,
                    }
                    all_points.append(doc)
                    exported += 1

                if next_offset is None or next_offset == offset:
                    break
                offset = next_offset or (offset + batch_size)

                print(f"  Exported {exported}/{min(point_count, limit or point_count)} documents",
                      end='\r')

            # Save to file
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_points, f, ensure_ascii=False, indent=2)

            print(f"\nExported {exported} documents to {output_file}")
            return exported

        except Exception as e:
            print(f"ERROR: Failed to export collection: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def find_documents_by_content(
        self,
        search_text: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find documents containing specific text (keyword search).

        Args:
            search_text: Text to search for
            limit: Maximum documents to return

        Returns:
            List of matching documents
        """
        print(f"\n{'='*80}")
        print(f"KEYWORD SEARCH (contains '{search_text}')")
        print(f"{'='*80}")

        try:
            offset = 0
            batch_size = 100

            collection_info = self.vector_db.get_collection_info(
                self.config.qdrant_collection_name
            )
            point_count = collection_info['point_count']

            matches = []

            while offset < point_count:
                scroll_result = self.vector_db.client.scroll(
                    collection_name=self.config.qdrant_collection_name,
                    limit=batch_size,
                    offset=offset,
                )

                # Handle both tuple and object responses
                if isinstance(scroll_result, tuple):
                    points, next_offset = scroll_result
                else:
                    points = scroll_result.points
                    next_offset = None

                if not points:
                    break

                for point in points:
                    text = point.payload.get('text', '').lower()
                    if search_text.lower() in text:
                        matches.append({
                            'id': point.id,
                            'document_name': point.payload.get('document_name'),
                            'section': point.payload.get('section'),
                            'text_preview': text[:150],
                        })
                        if len(matches) >= limit:
                            break

                if len(matches) >= limit:
                    break

                if next_offset is None or next_offset == offset:
                    break
                offset = next_offset or (offset + batch_size)

            print(f"Found {len(matches)} matching documents:")
            for i, match in enumerate(matches, 1):
                print(f"\n[Match {i}]")
                print(f"  ID: {match['id']}")
                print(f"  Document: {match['document_name']}")
                print(f"  Section: {match['section']}")
                print(f"  Preview: {match['text_preview']}...")

            return matches

        except Exception as e:
            print(f"ERROR: Search failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Debug embedding and RAG retrieval issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--query',
        help='Query to embed and retrieve results for'
    )
    parser.add_argument(
        '--show-collection-stats',
        action='store_true',
        help='Show collection statistics'
    )
    parser.add_argument(
        '--export-collection',
        metavar='FILE',
        help='Export all documents from collection to JSON file'
    )
    parser.add_argument(
        '--find-document',
        metavar='TEXT',
        help='Find documents containing this text'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Limit for document export/search (default: 10)'
    )

    args = parser.parse_args()

    if not any([args.query, args.show_collection_stats, args.export_collection, args.find_document]):
        parser.print_help()
        return 1

    try:
        debugger = EmbeddingDebugger()

        if args.query:
            debugger.compare_query_embedding(args.query)
            debugger.retrieve_and_compare(args.query)

        if args.show_collection_stats:
            debugger.show_collection_stats()

        if args.export_collection:
            debugger.export_collection(args.export_collection, args.limit)

        if args.find_document:
            debugger.find_documents_by_content(args.find_document, args.limit)

        return 0

    except Exception as e:
        logger.error(f"Debug script failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
