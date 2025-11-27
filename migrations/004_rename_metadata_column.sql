-- Migration to rename metadata column to document_metadata
-- This avoids SQLAlchemy's reserved attribute name conflict

ALTER TABLE documents RENAME COLUMN metadata TO document_metadata;

-- Update the comment for the renamed column
COMMENT ON COLUMN documents.document_metadata IS 'Additional metadata (language, pages, author, etc.)';
