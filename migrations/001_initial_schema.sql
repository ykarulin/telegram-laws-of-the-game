-- Initial schema migration for Football Rules Expert Bot
-- This script creates the messages table for storing conversations
-- NOTE: This migration is idempotent and skips statements for existing objects

-- Create messages table with all necessary columns and constraints
-- Note: If table already exists with different schema, this will be skipped
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    sender_type VARCHAR(50),
    sender_id VARCHAR(255),
    text TEXT NOT NULL,
    reply_to_message_id INTEGER,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common query patterns (if they don't exist)
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_chat_timestamp ON messages(chat_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_reply_to ON messages(reply_to_message_id);
