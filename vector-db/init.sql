-- Initialize pgvector extension and basic schema for LLM assistant

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a table for document embeddings
CREATE TABLE IF NOT EXISTS document_embeddings (
    id SERIAL PRIMARY KEY,
    document_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024), -- matches BAAI/bge-large-en-v1.5 (1024-dim); see api/embeddings/model.py
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create an index for vector similarity search
CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx
ON document_embeddings USING ivfflat (embedding vector_cosine_ops);

-- v0.8.x: index layer lookups. Partial index keeps it small — only chunks
-- that were actually scoped to a memory layer are indexed.
CREATE INDEX IF NOT EXISTS document_embeddings_layer_idx
ON document_embeddings ((metadata->>'layer'))
WHERE metadata->>'layer' IS NOT NULL;

-- Create a table for chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    session_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create a table for chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES chat_sessions(session_id),
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS chat_messages_created_at_idx ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS chat_sessions_created_at_idx ON chat_sessions(created_at);

-- hbar.harmonics coherence ledger (SPEC s4). Append-only: rows are never
-- updated or deleted. Standing is derived on read, never stored.
-- Existing brains also get this table via api/harmonics.init_tables() on boot.
CREATE TABLE IF NOT EXISTS coherence_events (
    id              SERIAL PRIMARY KEY,
    peer_pubkey     TEXT NOT NULL,
    role            TEXT NOT NULL,            -- 'contributor' | 'receiver'
    cos             DOUBLE PRECISION NOT NULL,
    sin             DOUBLE PRECISION NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    content_hash    TEXT NOT NULL,
    sig             TEXT,                     -- ed25519:<b64url> over the event
    event_timestamp BIGINT NOT NULL,          -- unix epoch seconds, UTC
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ce_role_idx ON coherence_events (role);
CREATE INDEX IF NOT EXISTS ce_peer_idx ON coherence_events (peer_pubkey);