# BrainFoundryOS Brain Layer Extension

A minimal, non-invasive semantic layer on top of the existing LLM Private Assistant system.

## Overview

The BrainFoundryOS brain layer adds entity/relation tracking and basic planning capabilities without modifying the existing RAG + API/UI system. It operates as a separate SQLite database alongside the main PostgreSQL vector store.

## Components

### 1. Semantic Database (`semantic_db.py`)
- **Purpose**: Track entities, tags, relations, and document associations
- **Storage**: SQLite database (`extensions/brain/semantic.db`)
- **Schema**: Defined in `semantic_schema.sql`

**Key Features:**
- Entity management (people, concepts, organizations, locations)
- Flexible tagging system with colors
- Relation tracking between entities (with strength scores)
- Document-entity linking (connects to main DB by document name)

### 2. Database Schema (`semantic_schema.sql`)
**Tables:**
- `entities` - Core entities with type and metadata
- `tags` - Flexible labeling system
- `relations` - Entity-to-entity connections
- `entity_tags` - Many-to-many entity-tag associations
- `document_entities` - Links entities to documents in main DB

### 3. Integration Points
- **Non-invasive**: No changes to existing API endpoints
- **Complementary**: Works alongside existing vector search
- **Linked**: References documents by name from main PostgreSQL DB

## Usage

### CLI Operations
```bash
# Show statistics
python extensions/brain/semantic_db.py stats

# Add entities
python extensions/brain/semantic_db.py add-entity "John Doe" person "Research scientist"
python extensions/brain/semantic_db.py add-entity "VQE Algorithm" concept "Variational Quantum Eigensolver"

# Add tags
python extensions/brain/semantic_db.py add-tag "quantum" "#8B5CF6" "Quantum computing related"

# Search entities
python extensions/brain/semantic_db.py search "quantum"

# View relations
python extensions/brain/semantic_db.py relations "John Doe"
```

### Python API
```python
from extensions.brain.semantic_db import SemanticDB

db = SemanticDB()

# Add entities and relations
db.add_entity("Alice Smith", "person", "Quantum researcher")
db.add_entity("QAOA", "concept", "Quantum Approximate Optimization Algorithm")
db.add_relation("Alice Smith", "QAOA", "researches", strength=0.9)

# Tag entities
db.add_tag("research", "#10B981", "Research-related")
db.tag_entity("Alice Smith", "research")

# Link to documents (from main DB)
db.link_document_entity("quantum_paper.pdf", "Alice Smith", relevance=0.8)

# Search and explore
entities = db.search_entities(query="quantum", tag_name="research")
relations = db.get_entity_relations("Alice Smith")
doc_entities = db.get_document_entities("quantum_paper.pdf")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Existing System                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Next.js   │    │   FastAPI   │    │ PostgreSQL  │     │
│  │     UI      │◄──►│     API     │◄──►│ + pgvector  │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (document names)
┌─────────────────────────────────────────────────────────────┐
│                 BrainFoundryOS Brain Layer                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Scripts   │    │  Semantic   │    │   SQLite    │     │
│  │ (ingest,    │◄──►│     DB      │◄──►│  Database   │     │
│  │  planner)   │    │   (Python)  │    │ (entities)  │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## File Structure

```
extensions/brain/
├── semantic_schema.sql     # SQLite schema definition
├── semantic_db.py         # Database operations and CLI
├── semantic.db            # SQLite database (created automatically)
└── README.md              # This file
```

## Environment

- **Python 3.11+**
- **Dependencies**: Built-in SQLite3, no additional packages required
- **Timezone**: Europe/Berlin for timestamps
- **Database**: Auto-created at `extensions/brain/semantic.db`

## Integration with Main System

The brain layer is designed to complement, not replace, the existing system:

1. **Documents**: Still uploaded via `/documents/upload` endpoint
2. **Search**: Still uses pgvector for semantic similarity
3. **RAG**: Still uses existing `/chat/rag` endpoint
4. **Enhancement**: Adds entity tracking and relation mapping
5. **Planning**: Enables query routing and tool selection

## Next Steps

This semantic layer provides the foundation for:
- Advanced entity extraction from documents
- Relation discovery and mapping
- Query routing (RAG vs web tools)
- Contextual planning and reasoning
