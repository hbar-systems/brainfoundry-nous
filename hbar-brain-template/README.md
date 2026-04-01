# 🤖 LLM Private Assistant

A containerized private LLM assistant with document processing, vector search, and RAG capabilities. Built with FastAPI, Next.js, PostgreSQL with pgvector, and Ollama.

![Architecture](https://img.shields.io/badge/Architecture-Microservices-blue) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED) ![Python](https://img.shields.io/badge/Python-3.11-3776AB) ![Node.js](https://img.shields.io/badge/Node.js-18+-339933)

## ✨ Features

- **🤖 LLM Chat**: OpenAI-compatible API with Mistral 7B model
- **📄 Document Processing**: PDF, DOCX, and image text extraction with OCR
- **🔍 Vector Search**: Semantic search using pgvector extension
- **💬 RAG Support**: Retrieval Augmented Generation for document-based Q&A
- **🖥️ Modern UI**: Clean Next.js frontend with real-time service monitoring
- **🐳 Containerized**: Full Docker Compose orchestration
- **🔒 Private**: Everything runs locally, no external API calls

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Next.js UI    │    │   FastAPI       │    │     Ollama      │
│   Port: 3000    │◄──►│   Port: 8000    │◄──►│   Port: 11434   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │   + pgvector    │
                    │   Port: 54322   │
                    └─────────────────┘
```

## 📋 System Requirements

### Minimum Requirements
- **OS**: macOS, Linux, or Windows with WSL2
- **RAM**: 8GB+ (16GB+ recommended for full functionality)
- **Storage**: 10GB free space
- **Docker**: Docker Desktop or Docker Engine + Docker Compose

### Recommended for Best Performance
- **RAM**: 16GB+ (for Mistral 7B model)
- **CPU**: 4+ cores
- **Storage**: SSD with 20GB+ free space
- **GPU**: NVIDIA GPU with 8GB+ VRAM (for future 70B model support)

## 🚀 Setup Instructions

### 1. Install Docker Desktop
- **Download and install**: https://docs.docker.com/desktop/install/

### 2. Choose Your Ollama Setup

This project supports two Ollama configurations:

#### Option A: Host Ollama (Recommended - Faster)
Run Ollama directly on your Mac for better performance:

```bash
# Install Ollama on macOS
brew install ollama

# Start Ollama service
brew services start ollama

# Pull the model
ollama pull llama3.2:3b

# Configure for host mode
cp .env.example .env
# Edit .env and set:
# OLLAMA_BASE=host.docker.internal:11434
```

#### Option B: Container Ollama
Run Ollama in Docker (slower but fully containerized):

```bash
# Configure for container mode
cp .env.example .env
# Edit .env and set:
# OLLAMA_BASE=ollama:11434
```

### 3. Environment Configuration

Copy and configure the environment file:

```bash
cp .env.example .env
```

Key configuration options in `.env`:
- `OLLAMA_BASE`: Toggle between `host.docker.internal:11434` (host) or `ollama:11434` (container)
- `DEFAULT_MODEL`: Set your preferred model (default: `llama3.2:3b`)

### 4. Start the Services

```bash
# Start the stack
docker compose up -d

# For host Ollama mode, start only postgres and API
docker compose up -d postgres api

# For container Ollama mode, start all services
docker compose up -d
```

## 🔧 Troubleshooting

### Health Check Commands

```bash
# Check overall API health
curl -sS localhost:8000/health | jq

# Check Ollama connectivity specifically
curl -sS localhost:8000/health | jq '.services.ollama'

# Test Ollama directly (host mode)
curl -sS localhost:11434/api/tags

# Test Ollama directly (container mode)
curl -sS localhost:11434/api/tags

# Check environment variables in API container
docker compose exec api printenv | grep OLLAMA

# Use the built-in network checker
docker compose exec api python /app/scripts/netcheck.py

# Check with curl inside API container
docker compose exec api curl -sS $OLLAMA_URL/api/tags
```

### Switching Between Host and Container Ollama

1. **Edit `.env` file:**
   ```bash
   # For host Ollama (faster)
   OLLAMA_BASE=host.docker.internal:11434
   
   # For container Ollama (fully containerized)
   OLLAMA_BASE=ollama:11434
   ```

2. **Restart API service:**
   ```bash
   docker compose up -d --force-recreate --no-deps api
   ```

3. **Verify the change:**
   ```bash
   curl -sS localhost:8000/health | jq '.services.ollama.endpoint'
   ```

### Common Issues

**Ollama Connection Issues:**
- **Host mode**: Ensure `brew services start ollama` is running
- **Container mode**: Ensure `docker compose up -d ollama` is running
- **Network**: Check firewall settings for port 11434

**API Container Issues:**
```bash
# Check API logs
docker compose logs -f api

# Restart API with fresh build
docker compose up -d --build --force-recreate api
```

**Database Issues:**
```bash
# Check database connection
docker compose exec api python -c "import psycopg2; print('DB OK')"

# Reset database
docker compose down -v
docker compose up -d postgres
```

### Expected Health Response

Healthy system should return:
```json
{
  "status": "healthy",
  "services": {
    "database": "healthy (X documents)",
    "ollama": {
      "status": "healthy",
      "endpoint": "http://host.docker.internal:11434",
      "models": 1,
      "error": null
    },
    "embeddings": "healthy"
  }
}
```
- **Download Ollama from**: https://ollama.com/download
- **After installation**, open terminal and run:
  ```bash
  ollama run llama3
  ```
  This will download and run the base model. You can replace `llama3` with any model you want to use.

### 3. Clone the Repository
```bash
git clone https://github.com/yuryuri/llm-private-main.git
cd llm-private-main
```

### 4. Start the System
```bash
# For systems with 16GB+ RAM (full functionality)
docker compose up -d

# For systems with 8-16GB RAM (development mode with lighter models)
docker compose -f docker-compose.dev.yml up -d
```

⚠️ **Note**: If you see a warning about the `version` attribute in `docker-compose.yml`, it's safe to ignore or you can delete that line from the file.

### 5. Download LLM Models (REQUIRED!)
```bash
# ⚠️ CRITICAL: Models must be downloaded manually after containers start
# Choose based on your system's available memory:

# For 16GB+ RAM (full functionality):
docker exec llm-private-main-ollama-1 ollama pull mistral:7b

# For 8-16GB RAM (recommended for most systems):
docker exec llm-private-main-ollama-1 ollama pull llama3.2:1b

# For 4-8GB RAM (minimal but functional):
docker exec llm-private-main-ollama-1 ollama pull llama3.2:1b
```

### 6. Verify Everything Works
```bash
# Check all services are running
docker compose ps

# Verify models are downloaded
docker exec llm-private-main-ollama-1 ollama list

# Test the API
curl http://localhost:8000/health

# Access the UI
open http://localhost:3000
```

## 🔧 Configuration Options

### Production Mode (`docker-compose.yml`)
- **Ollama**: Mistral 7B model (requires ~6GB RAM)
- **Best for**: Systems with 16GB+ RAM
- **Performance**: Full LLM capabilities

### Development Mode (`docker-compose.dev.yml`)
- **Ollama**: Lighter models (Llama 3.2 1B, Qwen 2.5 3B)
- **Best for**: Systems with 8-16GB RAM
- **Performance**: Faster startup, lighter resource usage

### Minimal Mode (`docker-compose.minimal.yml`)
- **Ollama**: Disabled (API only mode)
- **Best for**: Testing without LLM inference
- **Performance**: Minimal resource usage

## 📖 Usage Guide

### First-Time Setup: Download Models
```bash
# IMPORTANT: Download a model first (required for all LLM features)
# Choose one based on your available RAM:

# 16GB+ RAM (best performance):
docker exec llm-private-main-ollama-1 ollama pull mistral:7b

# 8GB+ RAM (good balance):
docker exec llm-private-main-ollama-1 ollama pull llama3.2:1b

# Verify download completed:
docker exec llm-private-main-ollama-1 ollama list
```

### Testing the Chat API
```bash
# Test chat completion (OpenAI-compatible)
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral:7b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

### Upload and Process Documents
```bash
# Upload a document for vector search
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@your_document.pdf" \
  -F "document_name=My Document"

# Search documents
curl -X POST http://localhost:8000/documents/search \
  -H "Content-Type: application/json" \
  -d '{"query": "your search query", "limit": 5}'
```

### RAG Chat (Document-based Q&A)
```bash
# Chat with your documents
curl -X POST http://localhost:8000/chat/rag \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does the document say about...?",
    "model": "mistral:latest"
  }'
```

## 🛠️ Available Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/` | GET | API information and status |
| `/health` | GET | Service health check |
| `/models` | GET | Available LLM models |
| `/chat/completions` | POST | OpenAI-compatible chat |
| `/chat/rag` | POST | Document-based Q&A |
| `/documents/upload` | POST | Upload documents |
| `/documents/search` | POST | Vector similarity search |

## 🔍 Troubleshooting

### Windows Docker Desktop Connection Issues
**Error**: `error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`

**Cause**: Docker Desktop is not running or WSL2 integration is not properly configured.

**Solutions**:
1. **Start Docker Desktop**: Look for Docker Desktop in your system tray and make sure it's running
2. **Enable WSL2 Integration**: 
   - Open Docker Desktop Settings
   - Go to Resources → WSL Integration  
   - Enable integration with your WSL2 distro
   - Click "Apply & Restart"
3. **Restart Terminal**: Close and reopen your terminal/command prompt
4. **Verify Docker is Working**: Run `docker --version` to confirm Docker is accessible

### "Ollama Generation Failed" Error
**Error**: Chat API returns `"Ollama generation failed"` or `500: Ollama generation failed`

**Cause**: No LLM models are downloaded yet (common issue!)

**Solution**:
```bash
# Check if any models are available
docker exec llm-private-main-ollama-1 ollama list

# If empty, download a model based on your RAM:
# 16GB+ RAM:
docker exec llm-private-main-ollama-1 ollama pull mistral:7b

# 8GB+ RAM:
docker exec llm-private-main-ollama-1 ollama pull llama3.2:1b

# Wait for download to complete, then test:
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:1b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### Memory Issues
**Error**: `model requires more system memory (5.5 GiB) than is available`

**Solutions**:
1. Use development mode: `docker compose -f docker-compose.dev.yml up -d`
2. Increase Docker memory limit in Docker Desktop settings
3. Close other applications to free up RAM

### Port Conflicts
**Error**: `bind: address already in use`

**Solutions**:
```bash
# Find process using the port
lsof -i :3000  # or :8000, :11434, :54322

# Kill the process
kill <PID>

# Or modify ports in docker-compose.yml
```

### Container Build Issues
```bash
# Rebuild containers
docker compose build --no-cache

# Clean Docker system
docker system prune -a
```

### Database Connection Issues
```bash
# Check database logs
docker compose logs postgres

# Reset database
docker compose down -v
docker compose up -d
```

## 📁 Project Structure

```
llm-private-main/
├── api/                     # FastAPI backend
│   └── Dockerfile          # API container definition
├── ui/                      # Next.js frontend
│   ├── pages/              # React pages
│   ├── components/         # React components
│   └── Dockerfile          # UI container definition
├── vector-db/              # Database initialization
│   └── init.sql            # PostgreSQL + pgvector setup
├── input_samples/          # Sample documents folder
├── docker-compose.yml      # Production configuration
├── docker-compose.dev.yml  # Development configuration
└── docker-compose.minimal.yml # Minimal configuration
```

## 🔄 Development

### Adding New Features
1. **API Changes**: Edit `api/Dockerfile` (FastAPI code is embedded)
2. **UI Changes**: Edit files in `ui/pages/` and `ui/components/`
3. **Database**: Modify `vector-db/init.sql`

### Rebuilding After Changes
```bash
# Rebuild specific service
docker compose build api  # or ui

# Restart services
docker compose up -d
```

### Viewing Logs
```bash
# All services
docker compose logs

# Specific service
docker compose logs api
docker compose logs ui
docker compose logs ollama
docker compose logs postgres
```

## 📊 Monitoring

### Service Status
- **UI**: http://localhost:3000 (shows real-time service status)
- **API Health**: http://localhost:8000/health
- **Ollama**: http://localhost:11434/api/tags

### Database Monitoring
```bash
# Connect to database
docker exec -it llm-private-main-postgres-1 psql -U postgres -d llm_db

# Check document count
SELECT COUNT(*) FROM document_embeddings;

# Check chat sessions
SELECT COUNT(*) FROM chat_sessions;
```

## 🧠 hbar Brain Layer (MVP)

**NEW**: A minimal, non-invasive semantic layer extension that adds entity tracking and planning capabilities without modifying the existing system.

### Features
- **Semantic Database**: SQLite-based entity/relation tracking (separate from main PostgreSQL)
- **Batch Ingestion**: Upload entire folders via `scripts/ingest_folder.py`
- **Web Tools**: Fetch web content with `scripts/tools.py`
- **Smart Planning**: Query routing and orchestration via `scripts/planner.py`

### Quick Start
```bash
# Install brain layer dependencies
pip install -r requirements.txt

# Test semantic database
python extensions/brain/smoke.py

# Upload documents from a folder
python scripts/ingest_folder.py input_samples

# Test web fetch
python scripts/planner.py "fetch https://example.com"

# Test RAG query
python scripts/planner.py "summarize my documents"
```

### Brain Layer Components
- `extensions/brain/` - Semantic database and schema
- `scripts/` - Ingestion, tools, and planning scripts
- `docs/BRAIN_NOTES.md` - Detailed integration guide

### Tag Browsing API
```bash
# List all tags with document counts
curl -s http://127.0.0.1:8000/brain/tags | jq .

# Get documents filtered by tags (comma-separated)
curl -s 'http://127.0.0.1:8000/brain/docs?tags=project:hbar-brain' | jq .
```

## 📤 Export for hbar.blog

The system includes an export feature that generates a site-ready `index.json` file for the hbar.blog agent.

### Running the Exporter

```bash
# Export Linear Algebra course content
python scripts/export_index.py --course "Linear Algebra" --out export/index.json

# Export with verbose logging
python scripts/export_index.py --course "Linear Algebra" --out export/index.json --verbose
```

### Export Format

The exporter creates a JSON file with the following structure:
```json
{
  "items": [
    {
      "id": "document-chunk-0",
      "course": "Linear Algebra", 
      "concept_id": "vectors",
      "source": "/courses/linear-algebra/vectors.html#def",
      "text": "A vector is a mathematical object...",
      "meta": {
        "section": "Introduction",
        "tags": ["mathematics", "linear-algebra"],
        "document_name": "01-vectors.pdf",
        "chunk_index": 0,
        "entities": ["vector", "linear-algebra"]
      }
    }
  ],
  "stats": {
    "total_items": 25,
    "concepts": {"vectors": 5, "matrices": 8, "eigenvalues": 3},
    "generated_at": "2025-10-05T11:29:58+02:00",
    "course": "Linear Algebra"
  }
}
```

### Concept Mapping

The exporter maps document chunks to concepts using:
1. **Semantic DB entities**: Links from `document_entities` → `entities` tables
2. **Filename heuristics**: Extracts concepts from filenames (e.g., "vectors", "dot-product")
3. **Graceful fallbacks**: Continues processing even if some chunks fail

### Deploying to hbar.blog

After generating the export file:
```bash
# Copy the export to hbar.blog
cp export/index.json /path/to/hbar.blog/brain/index.json

# Or upload via your deployment process
```

The export generates relative source paths like `/courses/linear-algebra/vectors.html#def` that should resolve to actual content pages on hbar.blog.

## 🎯 Next Steps (Phase 2)

This system is designed to scale. Planned enhancements include:

- **70B Model Support**: Upgrade to vLLM for larger models
- **Advanced Entity Extraction**: Auto-extract entities from documents
- **Vision API**: Gemini Vision integration
- **Advanced Sessions**: Multi-tab chat interface
- **Export Features**: PDF/Word/Markdown export

## 🤝 Support

- **Issues**: Create an issue on GitHub
- **Documentation**: See individual service Dockerfiles for implementation details
- **Logs**: Use `docker compose logs [service]` for debugging

## 📄 License

Private project for educational and personal use.

---

**Built with ❤️ using Docker, FastAPI, Next.js, PostgreSQL, and Ollama** 