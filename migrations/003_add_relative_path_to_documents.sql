-- Migration: Add relative_path column to documents table
-- Purpose: Store full folder structure path to preserve document organization
-- Example: "laws_of_game/laws_2024-25.pdf" instead of just "laws_of_game" in document_type

-- Add relative_path column to documents table
ALTER TABLE documents
ADD COLUMN relative_path VARCHAR(512);

-- Add index for queries filtering by relative path
CREATE INDEX IF NOT EXISTS idx_documents_relative_path ON documents(relative_path);

-- Add comment explaining the new column
COMMENT ON COLUMN documents.relative_path IS 'Full relative path from knowledgebase/upload, preserves folder structure (e.g., "laws_of_game/laws_2024-25.pdf")';
