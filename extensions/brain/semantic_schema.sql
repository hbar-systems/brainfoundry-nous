-- BrainFoundryOS brain layer: Semantic/Identity micro-DB schema
-- SQLite database for entities, tags, and relations (separate from main pgvector DB)

-- Enable foreign key constraints and WAL mode for better performance
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Entities table: people, concepts, organizations, etc.
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL, -- 'person', 'concept', 'organization', 'location', etc.
    description TEXT,
    metadata TEXT, -- JSON string for flexible attributes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tags table: flexible labeling system
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#3B82F6', -- hex color for UI
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Relations table: connections between entities
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL,
    target_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL, -- 'works_with', 'related_to', 'mentions', etc.
    strength REAL DEFAULT 1.0, -- 0.0 to 1.0 confidence/strength
    metadata TEXT, -- JSON string for additional context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(source_entity_id, target_entity_id, relation_type)
);

-- Entity-Tag associations (many-to-many)
CREATE TABLE IF NOT EXISTS entity_tags (
    entity_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_id, tag_id),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- Document-Entity associations (link to main DB documents by name)
CREATE TABLE IF NOT EXISTS document_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_name TEXT NOT NULL, -- matches document_name in main pgvector DB
    entity_id INTEGER NOT NULL,
    relevance REAL DEFAULT 1.0, -- how relevant this entity is to the document
    context TEXT, -- where/how the entity appears in the document
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_document_entities_doc ON document_entities(document_name);
CREATE INDEX IF NOT EXISTS idx_document_entities_entity ON document_entities(entity_id);

-- Insert some default tags
INSERT OR IGNORE INTO tags (name, color, description) VALUES 
    ('important', '#EF4444', 'High priority or significant content'),
    ('research', '#8B5CF6', 'Research-related material'),
    ('meeting', '#10B981', 'Meeting notes or discussions'),
    ('todo', '#F59E0B', 'Action items or tasks'),
    ('reference', '#6B7280', 'Reference material or documentation');
