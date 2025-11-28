-- Migration to support 64-bit Telegram IDs
-- Telegram chat and message IDs can exceed 32-bit integer limits
-- This migration converts the relevant columns from INTEGER to BIGINT
-- Fixes: "integer out of range" errors for large chat IDs (e.g., 5872238465)

-- Convert message_id to BIGINT
ALTER TABLE messages ALTER COLUMN message_id TYPE BIGINT;

-- Convert chat_id to BIGINT
ALTER TABLE messages ALTER COLUMN chat_id TYPE BIGINT;

-- Convert reply_to_message_id to BIGINT
ALTER TABLE messages ALTER COLUMN reply_to_message_id TYPE BIGINT;

-- Recreate indexes to use the new BIGINT column types
DROP INDEX IF EXISTS idx_messages_message_id;
CREATE INDEX idx_messages_message_id ON messages(message_id);

DROP INDEX IF EXISTS idx_messages_chat_id;
CREATE INDEX idx_messages_chat_id ON messages(chat_id);

DROP INDEX IF EXISTS idx_messages_reply_to;
CREATE INDEX idx_messages_reply_to ON messages(reply_to_message_id);
