-- Initial schema migration for Football Rules Expert Bot
-- This script creates the messages table for storing conversations

-- Create messages table with all necessary columns and constraints
CREATE TABLE IF NOT EXISTS messages (
    message_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    reply_to_message_id BIGINT REFERENCES messages(message_id) ON DELETE SET NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_id_timestamp ON messages(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_reply_to ON messages(reply_to_message_id);

-- Create a composite index for conversation chain traversal
CREATE INDEX IF NOT EXISTS idx_messages_user_reply_chain ON messages(user_id, reply_to_message_id);

-- Add comment to table explaining its purpose
COMMENT ON TABLE messages IS 'Stores all messages and bot responses for conversation history';

COMMENT ON COLUMN messages.message_id IS 'Unique Telegram message ID';
COMMENT ON COLUMN messages.user_id IS 'Telegram user ID for grouping conversations';
COMMENT ON COLUMN messages.text IS 'Original user message text';
COMMENT ON COLUMN messages.bot_response IS 'Bot response to the user message';
COMMENT ON COLUMN messages.reply_to_message_id IS 'Message ID this message is replying to, for building conversation chains';
COMMENT ON COLUMN messages.timestamp IS 'When the message was processed';
COMMENT ON COLUMN messages.created_at IS 'When the record was created in the database';
