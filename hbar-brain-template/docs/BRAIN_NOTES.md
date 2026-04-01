# hbar Brain Layer - Integration Guide

Quick integration guide for the hbar brain layer extension on top of the existing LLM Private Assistant.

## 🚀 Quick Start

### 1. Start the Main System
```bash
# Start existing system
docker compose up -d

# Download a model (required)
docker exec llm-private-main-ollama-1 ollama pull mistral:7b
# OR for lighter systems:
docker exec llm-private-main-ollama-1 ollama pull llama3.2:1b

# Verify system health
curl http://localhost:8000/health
```

### 2. Test Brain Layer Components

```bash
# Test semantic database
python extensions/brain/semantic_db.py stats

# Test web fetch tool
python scripts/tools.py web.fetch --url https://example.com

# Test document ingestion (dry run)
python scripts/ingest_folder.py input_samples --dry-run

# Test planner (analysis only)
python scripts/planner.py "what is quantum computing?" --analyze-only
```

### 3. Full Integration Test

```bash
# 1. Upload some documents
python scripts/ingest_folder.py input_samples

# 2. Test RAG query
python scripts/planner.py "summarize my documents"

# 3. Test web fetch
python scripts/planner.py "fetch https://en.wikipedia.org/wiki/Quantum_computing"

# 4. Test document search
curl -X POST http://localhost:8000/documents/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quantum", "limit": 3}'
```

## 📁 File Structure Added

```
hbar-brain-slm/
├── extensions/brain/          # NEW: Brain layer components
│   ├── semantic_schema.sql    # SQLite schema for entities/relations
│   ├── semantic_db.py         # Database operations + CLI
│   ├── semantic.db           # SQLite database (auto-created)
│   └── README.md             # Brain layer documentation
├── scripts/                   # NEW: Host-side scripts
│   ├── ingest_folder.py      # Batch document upload
│   ├── tools.py              # web.fetch tool + registry
│   └── planner.py            # Simple plan→act→verify loop
└── docs/                     # NEW: Documentation
    └── BRAIN_NOTES.md        # This file
```

## 🔧 Environment Variables

```bash
# Optional: Override API endpoint
export API_BASE=http://localhost:8000

# Optional: Custom semantic DB location
export SEMANTIC_DB_PATH=/path/to/semantic.db
```

## 🧠 Brain Layer Capabilities

### 1. Semantic Database
- **Entities**: People, concepts, organizations, locations
- **Tags**: Flexible labeling with colors
- **Relations**: Entity-to-entity connections with strength scores
- **Document Links**: Connect entities to documents in main DB

### 2. Tools
- **web.fetch**: Fetch and parse web content with text extraction
- **Extensible**: Easy to add more tools via ToolRegistry

### 3. Planner
- **Intent Analysis**: Classify queries (web_fetch, document_search, rag_query, entity_search)
- **Action Planning**: Generate action sequences based on intent
- **Execution**: Execute actions and collect results
- **Verification**: Summarize results and success rates

## 📊 Usage Examples

### Document Ingestion
```bash
# Upload all PDFs from a folder
python scripts/ingest_folder.py ~/Documents/research

# Dry run to see what would be uploaded
python scripts/ingest_folder.py ~/Documents --dry-run --no-recursive
```

### Semantic Database Operations
```bash
# Add entities
python extensions/brain/semantic_db.py add-entity "Alice Smith" person "Quantum researcher"
python extensions/brain/semantic_db.py add-entity "VQE" concept "Variational Quantum Eigensolver"

# Add relations
python -c "
from extensions.brain.semantic_db import SemanticDB
db = SemanticDB()
db.add_relation('Alice Smith', 'VQE', 'researches', strength=0.9)
"

# Search entities
python extensions/brain/semantic_db.py search "quantum"
```

### Web Fetching
```bash
# Fetch a webpage
python scripts/tools.py web.fetch --url https://arxiv.org/abs/2301.00001

# Include links in the result
python scripts/tools.py web.fetch --url https://example.com --include-links

# Save result to file
python scripts/tools.py web.fetch --url https://example.com --output result.json
```

### Planning and Execution
```bash
# RAG query (uses existing documents)
python scripts/planner.py "what are the main concepts in my research notes?"

# Web fetch query
python scripts/planner.py "fetch the latest news from https://quantumcomputing.com"

# Document search
python scripts/planner.py "find papers about variational quantum algorithms"

# Entity search
python scripts/planner.py "who are the researchers mentioned in my documents?"

# Analysis only (no execution)
python scripts/planner.py "explain quantum entanglement" --analyze-only
```

## 🔗 Integration Points

### With Existing System
- **Documents**: Uses existing `/documents/upload` endpoint
- **Search**: Uses existing `/documents/search` endpoint  
- **RAG**: Uses existing `/chat/rag` endpoint
- **Database**: Links to PostgreSQL documents by name

### New Capabilities
- **Batch Upload**: `scripts/ingest_folder.py` for folder ingestion
- **Web Tools**: `scripts/tools.py` for web content fetching
- **Planning**: `scripts/planner.py` for query routing and orchestration
- **Semantic Layer**: `extensions/brain/` for entity/relation tracking

## 🚨 Troubleshooting

### API Connection Issues
```bash
# Check if API is running
curl http://localhost:8000/health

# Check Docker containers
docker compose ps

# View API logs
docker compose logs api
```

### Semantic Database Issues
```bash
# Check database stats
python extensions/brain/semantic_db.py stats

# Recreate database (will lose data!)
rm extensions/brain/semantic.db
python extensions/brain/semantic_db.py stats
```

### Tool Execution Issues
```bash
# Test tools individually
python scripts/tools.py list
python scripts/tools.py web.fetch --url https://httpbin.org/get

# Check network connectivity
curl -I https://example.com
```

### Planner Issues
```bash
# Run with verbose output
python scripts/planner.py "test query" --verbose

# Analyze query without execution
python scripts/planner.py "test query" --analyze-only

# Save full result for debugging
python scripts/planner.py "test query" --output debug.json
```

## 📈 Next Steps

The brain layer provides foundation for:

1. **Advanced Entity Extraction**: Automatically extract entities from uploaded documents
2. **Relation Discovery**: Find connections between entities across documents  
3. **Smart Query Routing**: Better intent classification and action selection
4. **Multi-step Reasoning**: Chain multiple tools and queries together
5. **Context Awareness**: Use entity/relation context to improve responses

## 🔒 Security Notes

- **Local Only**: All processing happens locally, no external API calls except for web.fetch
- **Sandboxed**: Brain layer operates in separate SQLite DB, cannot affect main system
- **Read-Only**: Only reads from main PostgreSQL DB, never writes to it
- **User Control**: All web fetching requires explicit user queries with URLs
