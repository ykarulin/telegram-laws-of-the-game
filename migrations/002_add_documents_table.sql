-- Migration for Qdrant vector database integration
-- Adds documents table to track uploaded documents and their indexing status

-- Create documents table for tracking uploaded documents
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,  -- e.g., 'laws_of_game', 'faq', 'tournament_rules'
    version VARCHAR(50),
    content TEXT,  -- Full document text after extraction
    source_url VARCHAR(512),
    uploaded_by VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,  -- Extra metadata as JSON (language, author, etc.)
    qdrant_status VARCHAR(20) DEFAULT 'pending',  -- pending, indexed, failed
    qdrant_collection_id VARCHAR(255),  -- Reference to Qdrant collection
    error_message TEXT,  -- Error details if indexing failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(qdrant_status);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at DESC);

-- Create composite index for filtering by type and status
CREATE INDEX IF NOT EXISTS idx_documents_type_status ON documents(document_type, qdrant_status);

-- Add comments explaining the table
COMMENT ON TABLE documents IS 'Tracks uploaded documents and their Qdrant vector database indexing status';
COMMENT ON COLUMN documents.name IS 'Human-readable document name';
COMMENT ON COLUMN documents.document_type IS 'Type of document (laws_of_game, faq, tournament_rules, etc.)';
COMMENT ON COLUMN documents.version IS 'Document version (e.g., 2024-25, 2024-2025)';
COMMENT ON COLUMN documents.content IS 'Full extracted text content from the document';
COMMENT ON COLUMN documents.source_url IS 'Original URL where document was obtained';
COMMENT ON COLUMN documents.uploaded_by IS 'User or system that uploaded the document';
-- COMMENT MOVED TO MIGRATION 004 WHERE COLUMN IS RENAMED
COMMENT ON COLUMN documents.qdrant_status IS 'Indexing status: pending, indexed, or failed';
COMMENT ON COLUMN documents.qdrant_collection_id IS 'ID of Qdrant collection containing this document''s chunks';
COMMENT ON COLUMN documents.error_message IS 'Error details if indexing failed';
