import anthropic
from api import providers as _providers
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import sqlite3
from fastapi import APIRouter
from fastapi.security import APIKeyHeader
import psycopg2
import requests
import json
import os
import sys
import socket
from typing import List, Optional, Annotated, Dict, Any, Union
from datetime import datetime
import uuid
import anthropic as _ant
_ants = _ant.Anthropic()
_anta = _ant.AsyncAnthropic()
CM = "claude-sonnet-4-6"
import anthropic as _ant
_ants=_ant.Anthropic()
_anta=_ant.AsyncAnthropic()
CM="claude-sonnet-4-6"
import PyPDF2
import docx
from PIL import Image
import pytesseract
import io
import numpy as np
from sentence_transformers import SentenceTransformer
import tempfile
import httpx
import time
from fastapi import Request, Header, Depends
from collections import defaultdict
import hashlib
import hmac
from pydantic import BaseModel, ConfigDict, StringConstraints, Field

from fastapi import Request
from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError

from fastapi.exceptions import RequestValidationError
from api.kernel.handlers import READ_ONLY_HANDLERS, MEMORY_APPEND_HANDLERS

from api.identity.core import verify_permit, verify_assertion
from api.identity.permits import normalize_permit_type

DEV_ENABLE_MEMORY_APPEND = os.getenv("DEV_ENABLE_MEMORY_APPEND", "false").lower() in ("true", "1", "yes")

_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
CLAUDE_MODEL = "claude-sonnet-4-6"   

HBAR_IDENTITY_SECRET = os.getenv("HBAR_IDENTITY_SECRET", "")

# --- v0.15 startup sanity hardening ---
if not DEV_ENABLE_MEMORY_APPEND:
    if not HBAR_IDENTITY_SECRET:
        raise RuntimeError(
            "Startup refused: HBAR_IDENTITY_SECRET must be set when DEV_ENABLE_MEMORY_APPEND is disabled."
        )

HBAR_ENV = os.getenv("HBAR_ENV", "dev").lower()

if HBAR_ENV != "dev" and DEV_ENABLE_MEMORY_APPEND:
    raise RuntimeError(
        "Startup refused: DEV_ENABLE_MEMORY_APPEND must not be set in non-dev environments. "
        "Remove it from .env or set HBAR_ENV=dev."
    )

if HBAR_ENV != "dev" and (not HBAR_IDENTITY_SECRET or HBAR_IDENTITY_SECRET == "dev-secret-please-change"):
    raise RuntimeError(
        "Startup refused: HBAR_IDENTITY_SECRET must be set to a strong secret in non-dev environments. "
        "Generate one with: openssl rand -hex 32"
    )


try:
    # Package layout
    from api.kernel.registry import (
        parse_normalized_command,
        get_command_spec,
        validate_command_payload,
        ExecutionClass,
    )
except ModuleNotFoundError:
    # Container flat layout (/app/main.py)
    from kernel.registry import (
        parse_normalized_command,
        get_command_spec,
        validate_command_payload,
        ExecutionClass,
    )



# Kernel imports (dual-layout: repo package vs container flat layout)
try:
    from api.kernel.errors import build_error
    from api.kernel.error_codes import KernelErrorCode
    from api.kernel.rate_limiter import KernelRateLimiter
    from api.kernel.exceptions import KernelException
except ModuleNotFoundError:
    from kernel.errors import build_error
    from kernel.error_codes import KernelErrorCode
    from kernel.rate_limiter import KernelRateLimiter
    from kernel.exceptions import KernelException

from pathlib import Path
import yaml
from fastapi import FastAPI, HTTPException, Security

# Version constant
HBAR_BRAIN_VERSION = "0.5.0"

APP_DIR = Path(__file__).resolve().parent
PERSONA_PATH = APP_DIR / "brain_persona.md"

def load_persona_text() -> str:
    try:
        return PERSONA_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""  # safe fallback

BRAIN_PERSONA = load_persona_text()


app = FastAPI(title="LLM Private Assistant API", version="2.0.0", docs_url=None, redoc_url=None, openapi_url=None)




from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError
from pydantic import ValidationError as PydanticValidationError

def _kernel_validation_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content=build_error(
            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
            message="Request validation failed (fail-closed)",
            details={"errors": exc.errors()},
        ).model_dump(),
    )

app.exception_handlers[FastAPIRequestValidationError] = _kernel_validation_handler
app.exception_handlers[PydanticValidationError] = _kernel_validation_handler


# -----------------------------
# -----------------------------
# Canonical error envelope
# -----------------------------

@app.exception_handler(KernelException)
async def kernel_exception_handler(request: Request, exc: KernelException):
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error(
            code=exc.code,
            message=exc.message,
            details=exc.details or {},
        ).model_dump(),
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error(
            code=KernelErrorCode.INTERNAL_ERROR,
            message=str(detail) if isinstance(detail, str) else "HTTP exception",
            details={"detail": detail, "status_code": exc.status_code},
        ).model_dump(),
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=build_error(
            code=KernelErrorCode.INTERNAL_ERROR,
            message="Internal error",
            details={"type": type(exc).__name__},
        ).model_dump(),
    )

# CORS: allow UI to call API from browser
_cors_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://127.0.0.1:3010',
        'http://localhost:3010',
    ] + _cors_extra,
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=[
        'Content-Type',
        'Authorization',
        'X-API-Key',
        'X-HBAR-Assertion',
        'X-HBAR-Permit',
    ],
)
IDENTITY_PATH = Path(__file__).parent / "brain_identity.yaml"

@app.get("/identity")
def get_identity():
    """
    Return brain identity YAML as JSON.
    Uses an absolute path relative to this file to avoid CWD issues.
    """
    identity_path = Path(__file__).resolve().parent / "brain_identity.yaml"

    try:
        raw = identity_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"brain_identity.yaml not found at {identity_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed reading {identity_path}: {type(e).__name__}: {e}")

    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed parsing YAML in {identity_path}: {type(e).__name__}: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"brain_identity.yaml must parse to a mapping/object, got {type(data).__name__}")

    return data

@app.get("/capabilities")
def capabilities():
    """
    Static runtime capabilities for orchestrator handshake.
    Keep this stable; add fields only (don't rename/remove) once orchestrator depends on it.
    """
    return {
        "endpoints": {
            "identity": "/identity",
            "capabilities": "/capabilities",
            "health": "/health",
            "models": "/models",
            "chat_completions": "/chat/completions",
        },
        "features": {
            "streaming": False,
            "tools": False,
            "memory": False,
            "rag": True,
        },
        "limits": {
            "max_request_bytes": None,
            "max_response_tokens": None,
        }
    }

@app.get("/persona")
def get_persona():
    """Return the loaded brain persona text (debug/verification)."""
    return {"persona": BRAIN_PERSONA}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """
    Readiness: reports whether heavyweight dependencies are ready.
    IMPORTANT: does NOT force-load the embedding model.
    """
    from api.embeddings.model import is_model_loaded, model_error

    loaded = is_model_loaded()
    return {
        "ok": loaded,
        "model": {
            "loaded": loaded,
            "error": model_error(),
        },
    }

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
KERNEL_RATE_LIMIT_MAX = int(os.getenv("KERNEL_RATE_LIMIT_MAX", "30"))
KERNEL_RATE_LIMIT_WINDOW = int(os.getenv("KERNEL_RATE_LIMIT_WINDOW", "60"))


NODEOS_URL = os.getenv("NODEOS_URL", "http://nodeos:8001")
HBAR_BRAIN_API_KEY = os.getenv("HBAR_BRAIN_API_KEY", "")

def _verify_loop_permit(permit_id: str) -> dict:
    """Verify a loop permit is ACTIVE and not expired. Raises 403 on failure."""
    if not permit_id:
        raise HTTPException(status_code=403, detail="permit_id is required. Obtain a loop permit from NodeOS first (POST /v1/loops/request).")
    try:
        resp = requests.get(f"{NODEOS_URL}/v1/loops/status/{permit_id}", timeout=5)
    except Exception:
        raise HTTPException(status_code=503, detail="NodeOS unreachable — inference denied (fail closed).")
    if resp.status_code == 404:
        raise HTTPException(status_code=403, detail=f"Permit {permit_id} not found.")
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ACTIVE":
        raise HTTPException(status_code=403, detail=f"Permit {permit_id} is {data.get('status')} — not ACTIVE.")
    if data.get("expires_at_unix", 0) < int(time.time()):
        raise HTTPException(status_code=403, detail=f"Permit {permit_id} has expired.")
    return data


# Initialize embedding model (will download on first use)
embedding_model = None

def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        try:
            from api.embeddings.model import get_model
            embedding_model = get_model()
            # embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            print(f"Failed to load embedding model: {e}")
            embedding_model = None
    return embedding_model

# NOTE: Do NOT preload embedding model on startup.
# Keep startup deterministic; model loads on first embedding use.
# @app.on_event("startup")
# def preload_models() -> None:
#     _ = get_embedding_model()  # force load on boot


def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF extraction failed: {str(e)}")

def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from Word document"""
    try:
        doc_file = io.BytesIO(file_content)
        doc = docx.Document(doc_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DOCX extraction failed: {str(e)}")

def extract_text_from_image(file_content: bytes) -> str:
    """Extract text from image using OCR"""
    try:
        image = Image.open(io.BytesIO(file_content))
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR extraction failed: {str(e)}")

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks for better embeddings"""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())
    
    return chunks

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for text chunks"""
    model = get_embedding_model()
    if model is None:
        raise HTTPException(status_code=500, detail="Embedding model not available")
    
    try:
        embeddings = model.encode(texts)
        return embeddings.tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

def search_similar_documents(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search for similar documents with tier-weighted injection.

    RAG tier folders (optional conventions — rename to match your corpus):
    Tier 1 (always 2 results): identity/        — who you are, core context
    Tier 2 (always 1 each):    thinking/        — active reasoning, notes
                               projects/        — current work, in-progress docs
                               writing/         — essays, blog posts, published work
    Tier 3: similarity search over everything else (general corpus)

    To use different folder names, set env vars:
      RAG_TIER1=identity
      RAG_TIER2A=thinking
      RAG_TIER2B=projects
      RAG_TIER2C=writing
    """
    _t1  = os.getenv("RAG_TIER1",  "identity")
    _t2a = os.getenv("RAG_TIER2A", "thinking")
    _t2b = os.getenv("RAG_TIER2B", "projects")
    _t2c = os.getenv("RAG_TIER2C", "writing")

    try:
        query_embedding = generate_embeddings([query])[0]
        conn = get_db_connection()
        cursor = conn.cursor()
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        def fetch_tier(pattern, n):
            cursor.execute(
                """
                SELECT document_name, content, metadata,
                       embedding <-> %s::vector as distance
                FROM document_embeddings
                WHERE document_name LIKE %s
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                (embedding_str, pattern, embedding_str, n)
            )
            return cursor.fetchall()

        tier1 = fetch_tier(f'{_t1}/%', 2)
        tier2a = fetch_tier(f'{_t2a}/%', 1)
        tier2b = fetch_tier(f'{_t2b}/%', 1)
        tier2c = fetch_tier(f'{_t2c}/%', 1)

        # Tier 3: similarity search excluding tiered folders
        cursor.execute(
            """
            SELECT document_name, content, metadata,
                   embedding <-> %s::vector as distance
            FROM document_embeddings
            WHERE document_name NOT LIKE %s
              AND document_name NOT LIKE %s
              AND document_name NOT LIKE %s
              AND document_name NOT LIKE %s
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            (embedding_str, f'{_t1}/%', f'{_t2a}/%', f'{_t2b}/%', f'{_t2c}/%', embedding_str, limit)
        )
        tier3 = cursor.fetchall()
        cursor.close()
        conn.close()

        all_results = tier1 + tier2a + tier2b + tier2c + tier3
        return [
            {
                "document_name": r[0],
                "content": r[1],
                "metadata": r[2] or {},
                "similarity_score": float(1 - r[3])
            }
            for r in all_results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/")
def read_root():
    return {
        "message": "🤖 LLM Private Assistant API v2.0",
        "status": "running",
        "features": {
            "chat": "OpenAI-compatible chat completions",
            "rag": "Retrieval Augmented Generation",
            "documents": "PDF, DOCX, Image processing",
            "embeddings": "Semantic search with vector database"
        },
        "endpoints": {
            "health": "/health",
            "chat": "/chat/completions",
            "rag_chat": "/chat/rag",
            "models": "/models",
            "upload": "/documents/upload",
            "search": "/documents/search",
            "sessions": "/sessions"
        },
        "database_url": DATABASE_URL[:50] + "..." if DATABASE_URL else "Not set",
        "ollama_url": OLLAMA_URL
    }

@app.get("/health")
def health_check():
    # Test database connection (v0.4.0: lightweight ping with proper error handling)
    db_status = {"status": "unknown"}
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Lightweight ping
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            db_status = {"status": "healthy"}
        except Exception as e:
            db_status = {"status": "error", "detail": str(e)[:100]}
    else:
        db_status = {"status": "error", "detail": "DATABASE_URL not configured"}
    
    # Test Ollama connection with detailed status
    ollama_status = {
        "status": "unknown",
        "endpoint": OLLAMA_URL,
        "models": 0,
        "error": None
    }
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if response.status_code == 200:
            models = response.json().get("models", [])
            ollama_status = {
                "status": "healthy",
                "endpoint": OLLAMA_URL,
                "models": len(models),
                "error": None
            }
        else:
            ollama_status = {
                "status": "error",
                "endpoint": OLLAMA_URL,
                "models": 0,
                "error": f"HTTP {response.status_code}"
            }
    except requests.exceptions.Timeout:
        ollama_status = {
            "status": "timeout",
            "endpoint": OLLAMA_URL,
            "models": 0,
            "error": "Connection timeout (3s)"
        }
    except requests.exceptions.ConnectionError:
        ollama_status = {
            "status": "unreachable",
            "endpoint": OLLAMA_URL,
            "models": 0,
            "error": "Connection refused"
        }
    except Exception as e:
        ollama_status = {
            "status": "error",
            "endpoint": OLLAMA_URL,
            "models": 0,
            "error": str(e)
        }
    
    # Test embedding model
    from api.embeddings.model import is_model_loaded, model_error
    embedding_status = "healthy" if is_model_loaded() else "not_loaded"
    embedding_error = model_error()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "ollama": ollama_status,
            "embeddings": {
                "status": embedding_status,
                "error": embedding_error,
           },
        },
    }

@app.get("/models")
def list_models():
    """Get all available models across configured providers + local Ollama"""
    return {"models": _providers.get_available_models()}


@app.post("/chat/completions")
async def chat_completion(request: dict):
    """Chat completion endpoint compatible with OpenAI format - supports streaming"""
    try:
        _verify_loop_permit(request.get("permit_id"))
        model = request.get("model", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
        messages = request.get("messages", [])

        # Inject brain persona as system message (if caller didn't provide one)

        if BRAIN_PERSONA:
            has_system = any(m.get("role") == "system" for m in messages)
            if not has_system:
                messages = [{"role": "system", "content": BRAIN_PERSONA}] + messages


        do_stream = request.get("stream", False)
        session_id = request.get("session_id")  # Optional session ID for persistence

        # non-streaming — route to correct provider via providers.py
        if not do_stream:
            assistant_message = await _providers.complete(model, messages, max_tokens=request.get("max_tokens", 2048))

            # Save to database if session_id provided
            if session_id and messages:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()

                    # Save the latest user message
                    latest_user_msg = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
                    if latest_user_msg:
                        cursor.execute(
                            "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
                            (session_id, "user", latest_user_msg.get("content", ""))
                        )

                    # Save the assistant response
                    cursor.execute(
                        "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
                        (session_id, "assistant", assistant_message)
                    )

                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as db_error:
                    print(f"Database save error: {db_error}")  # Log but don't fail the request

            response_body = {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(datetime.utcnow().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_message
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                },
            }

            return JSONResponse(
                content=response_body,
                headers={
                    "X-Brain-Persona-Injected": "1" if BRAIN_PERSONA else "0"
                }
            )


        # streaming path (SSE: "data: {...}\n\n" frames)
        async def event_stream():
            sm = next((m["content"] for m in messages if m.get("role") == "system"), None)
            cm = [m for m in messages if m.get("role") != "system"]
            async with _anta.messages.stream(model=CM, max_tokens=2048, messages=cm, **( {"system": sm} if sm else {} )) as stream:
                async for text in stream.text_stream:
                    chunk = {"id": f"chatcmpl-{uuid.uuid4()}", "object": "chat.completion.chunk", "model": CM, "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat completion error: {str(e)}")

@app.post("/chat/rag")
def rag_chat_completion(request: dict):
    """RAG-enhanced chat completion - chat with your documents!"""
    try:
        _verify_loop_permit(request.get("permit_id"))
        model = request.get("model", "llama3.2:3b")
        messages = request.get("messages", [])
        search_limit = request.get("search_limit", 3)
        
        # Extract user query from latest message
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break
        
        # Fallback: support callers that send {"query": "..."} instead of messages[]
        if not user_query:
            user_query = request.get("query", "")

        # Search for relevant documents
        relevant_docs = search_similar_documents(user_query, limit=search_limit)
        
        # Build context from relevant documents
        context = ""
        if relevant_docs:
            context = "\n\nRelevant documents:\n"
            for i, doc in enumerate(relevant_docs, 1):
                context += f"\n[Document {i}: {doc['document_name']}]\n{doc['content']}\n"
        
        # Build prompt with context
        prompt = "You are a helpful assistant. Use the provided documents to answer questions accurately."
        if context:
            prompt += context
        prompt += "\n\nConversation:\n"
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"System: {content}\n"
            elif role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"
        
        prompt += "Assistant: "
        
        # Call Claude
        cr = _ants.messages.create(model=CM, max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        reply = cr.content[0].text
        return {
            "id": f"chatcmpl-rag-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "model": CM,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            "rag_metadata": {"documents_used": len(relevant_docs), "search_query": user_query, "sources": [d["document_name"] for d in relevant_docs]},
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(reply.split()), "total_tokens": len(prompt.split()) + len(reply.split())}
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG chat completion error: {str(e)}")

def _nodeos_propose_memory(memory_type: str, content: str, permit_id: str, source_refs: dict = None) -> dict:
    """Propose a memory write to NodeOS. Returns proposal dict or raises."""
    try:
        resp = requests.post(
            f"{NODEOS_URL}/v1/memory/propose",
            json={
                "permit_id": permit_id,
                "memory_type": memory_type,
                "content": content,
                "source_refs": source_refs,
            },
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="NodeOS authority service unreachable — memory write denied (fail closed)")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=503, detail="NodeOS authority service timeout — memory write denied (fail closed)")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NodeOS proposal failed: {str(e)}")


def _nodeos_check_proposal(proposal_id: str) -> str:
    """Check a memory proposal status via NodeOS. Returns status string or raises."""
    try:
        resp = requests.get(
            f"{NODEOS_URL}/v1/memory/proposals/{proposal_id}",
            timeout=5,
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
        resp.raise_for_status()
        return resp.json().get("status", "UNKNOWN")
    except HTTPException:
        raise
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="NodeOS authority service unreachable — memory write denied (fail closed)")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=503, detail="NodeOS authority service timeout — memory write denied (fail closed)")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NodeOS proposal check failed: {str(e)}")


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), proposal_id: Optional[str] = None, permit_id: Optional[str] = None):
    """Upload and process document for embeddings and RAG.
    
    Memory governance (deny-by-default):
    - Without proposal_id: proposes memory to NodeOS, returns 202 PENDING. No embeddings written.
    - With proposal_id: verifies APPROVED status via NodeOS before writing embeddings.
    - Requires permit_id for initial proposal (loop permit from NodeOS).
    """
    try:
        content = await file.read()
        
        # Extract text based on file type
        text = ""
        if file.content_type == "application/pdf":
            text = extract_text_from_pdf(content)
        elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text = extract_text_from_docx(content)
        elif file.content_type.startswith("image/"):
            text = extract_text_from_image(content)
        else:
            # Try to decode as text
            try:
                text = content.decode("utf-8")
            except:
                raise HTTPException(status_code=400, detail="Unsupported file type")
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text content extracted from file")
        
        # ── Memory governance gate (deny-by-default) ──────────────────
        # Document embeddings are long-term memory. They require NodeOS approval.
        
        if proposal_id is None:
            # Path A: No proposal yet — propose to NodeOS, return 202 PENDING.
            if not permit_id:
                raise HTTPException(
                    status_code=400,
                    detail="permit_id is required to propose a document upload. "
                           "Obtain a loop permit from NodeOS first (POST /v1/loops/request)."
                )
            proposal = _nodeos_propose_memory(
                memory_type="document_embedding",
                content=f"Document upload: {file.filename} ({len(text)} chars, {file.content_type})",
                permit_id=permit_id,
                source_refs={"filename": file.filename, "content_type": file.content_type, "size": len(content)},
            )
            return JSONResponse(
                status_code=202,
                content={
                    "filename": file.filename,
                    "status": "PENDING",
                    "proposal_id": proposal["proposal_id"],
                    "message": "Memory proposal submitted to NodeOS. Approve the proposal, then re-upload with proposal_id to persist embeddings.",
                },
            )
        
        # Path B: proposal_id provided — verify it is APPROVED before writing.
        proposal_status = _nodeos_check_proposal(proposal_id)
        if proposal_status != "APPROVED":
            raise HTTPException(
                status_code=403,
                detail=f"Memory proposal {proposal_id} is {proposal_status}, not APPROVED. Embeddings write denied."
            )
        
        # ── Approved — proceed to write embeddings ────────────────────
        
        # Split into chunks
        chunks = chunk_text(text)
        
        # Generate embeddings
        embeddings = generate_embeddings(chunks)
        
        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stored_chunks = 0
        for chunk, embedding in zip(chunks, embeddings):
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            
            cursor.execute(
                """
                INSERT INTO document_embeddings (document_name, content, embedding, metadata) 
                VALUES (%s, %s, %s::vector, %s)
                """,
                (
                    file.filename,
                    chunk,
                    embedding_str,
                    json.dumps({
                        "file_size": len(content),
                        "content_type": file.content_type,
                        "upload_timestamp": datetime.utcnow().isoformat(),
                        "chunk_index": stored_chunks,
                        "proposal_id": proposal_id
                    })
                )
            )
            stored_chunks += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "filename": file.filename,
            "size": len(content),
            "content_type": file.content_type,
            "text_length": len(text),
            "chunks_created": len(chunks),
            "embeddings_stored": stored_chunks,
            "proposal_id": proposal_id,
            "status": "success",
            "message": f"Document processed and ready for RAG! Created {stored_chunks} searchable chunks."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")

@app.post("/documents/search")
def search_documents(request: dict):
    """Search documents using semantic similarity"""
    try:
        query = request.get("query", "")
        limit = request.get("limit", 5)
        
        if not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        results = search_similar_documents(query, limit)
        
        return {
            "query": query,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/documents/stats")
def get_document_stats():
    """Get statistics about stored documents"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get document statistics
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_chunks,
                COUNT(DISTINCT document_name) as unique_documents
            FROM document_embeddings
            """
        )
        stats = cursor.fetchone()
        
        # Get recent documents
        cursor.execute(
            """
            SELECT DISTINCT document_name, 
                   COUNT(*) as chunks,
                   MAX(created_at) as last_updated
            FROM document_embeddings 
            GROUP BY document_name 
            ORDER BY last_updated DESC 
            LIMIT 10
            """
        )
        recent_docs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "total_chunks": stats[0],
            "unique_documents": stats[1],
            "recent_documents": [
                {
                    "name": doc[0],
                    "chunks": doc[1],
                    "last_updated": doc[2].isoformat() if doc[2] else None
                }
                for doc in recent_docs
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

# Session Management Endpoints
@app.get("/sessions")
def list_chat_sessions():
    """List all chat sessions with message counts and preview"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                s.session_id, 
                s.model_name, 
                s.title,
                s.created_at,
                COUNT(m.id) as message_count,
                (SELECT content FROM chat_messages WHERE session_id = s.session_id ORDER BY created_at DESC LIMIT 1) as last_message
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.session_id = m.session_id
            GROUP BY s.session_id, s.model_name, s.title, s.created_at
            ORDER BY s.created_at DESC 
            LIMIT 50
            """
        )
        sessions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return {
            "sessions": [
                {
                    "session_id": str(session[0]),
                    "model_name": session[1],
                    "title": session[2] or "New Chat",
                    "created_at": session[3].isoformat() if session[3] else None,
                    "message_count": session[4],
                    "last_message": session[5][:100] + "..." if session[5] and len(session[5]) > 100 else session[5]
                } for session in sessions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sessions: {str(e)}")

@app.post("/sessions")
def create_chat_session(request: dict):
    """Create a new chat session"""
    try:
        model_name = request.get("model_name", "llama3.2:3b")
        title = request.get("title", "New Chat")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (model_name, title) VALUES (%s, %s) RETURNING session_id",
            (model_name, title)
        )
        session_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "session_id": str(session_id),
            "model_name": model_name,
            "title": title,
            "created_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@app.delete("/sessions/{session_id}")
def delete_chat_session(session_id: str):
    """Delete a chat session and all its messages"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete messages first (foreign key constraint)
        cursor.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
        
        # Delete session
        cursor.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {"message": "Session deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    """Get all messages for a specific session"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content, created_at 
            FROM chat_messages 
            WHERE session_id = %s 
            ORDER BY created_at ASC
            """,
            (session_id,)
        )
        messages = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": msg[0],
                    "content": msg[1],
                    "created_at": msg[2].isoformat() if msg[2] else None
                } for msg in messages
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")

@app.put("/sessions/{session_id}/title")
def update_session_title(session_id: str, request: dict):
    """Update a session's title"""
    try:
        title = request.get("title", "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_sessions SET title = %s WHERE id = %s RETURNING id",
                (title, session_id)
            )
            result = cursor.fetchone()
            conn.commit()
            
        if not result:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            
        return {"message": "Session title updated", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update title: {str(e)}")


# Command endpoint models and authentication
class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    confirm_token: Optional[str] = None
    client_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    payload: Dict[str, Any] = Field(default_factory=dict)

# API key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_token = APIKeyHeader(name="Authorization", auto_error=False)

def get_api_key(
    x_api_key: str = Security(api_key_header),
    authorization: str = Security(bearer_token),
) -> str:
    """Get API key from either X-API-Key header or Authorization header (Bearer token)"""
    # If HBAR_BRAIN_API_KEY is not set, allow in dev mode only — log a loud warning
    if not HBAR_BRAIN_API_KEY:
        _env = os.getenv("HBAR_ENV", "dev").lower()
        if _env != "dev":
            raise HTTPException(status_code=500, detail="Server misconfigured: HBAR_BRAIN_API_KEY not set.")
        print("WARNING: HBAR_BRAIN_API_KEY is not set. All requests are unauthenticated. Set this before production use.")
        return "dev_mode"
    
    # Check X-API-Key header
    if x_api_key and x_api_key == HBAR_BRAIN_API_KEY:
        return x_api_key
    
    # Check Authorization header (Bearer token)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        if token == HBAR_BRAIN_API_KEY:
            return token
    
    # If we get here and HBAR_BRAIN_API_KEY is set, authentication failed
    raise HTTPException(
        status_code=401,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )

_kernel_rate_limiter = KernelRateLimiter()


@app.post("/v1/brain/command")
async def brain_command(
    request: CommandRequest,
    http_request: Request,
    api_key: str = Depends(get_api_key),
):


    def ok(data: dict):
        return {"ok": True, "data": data}


    # --- Kernel Rate Limit (client_id-based, Redis, fail-closed) ---
    client_id = (request.client_id or "").strip()
    if not client_id:
        return JSONResponse(
            status_code=401,
            content=build_error(
                code=KernelErrorCode.MISSING_CLIENT_ID,
                message="client_id is required for kernel access",
                details={},
            ).model_dump()
        )

    rl = _kernel_rate_limiter.check(client_id)
    if rl:
        if rl.get("error") == "RATE_LIMITED":
            return JSONResponse(
                status_code=429,
                content=build_error(
                    code=KernelErrorCode.RATE_LIMITED,
                    message="Too many requests to kernel",
                    details={
                        "max": int(os.getenv("KERNEL_RATE_LIMIT_MAX", "30")),
                        "window_s": int(os.getenv("KERNEL_RATE_LIMIT_WINDOW", "60")),
                        "key_type": "client_id",
                        "retry_after_s": rl.get("retry_after"),
                    },
                ).model_dump()
            )

        return JSONResponse(
            status_code=429,
            content=build_error(
                code=KernelErrorCode.RATE_LIMITER_FAILURE,
                message="Kernel rate limiter failure (fail-closed)",
                details={},
            ).model_dump()
        )


    # Create ops/audit directory if it doesn't exist
    ops_dir = Path(__file__).resolve().parent.parent / "ops"
    audit_dir = ops_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    proposals_file = audit_dir / "proposals.jsonl"
    audit_file = audit_dir / "command_audit.jsonl"
    
    # Normalize command
    normalized_command = " ".join(request.command.strip().lower().split())
    

    # --- v0.6: Command registry enforcement (fail-closed) ---
    command_key, command_params = parse_normalized_command(normalized_command)
    command_spec = get_command_spec(command_key)

    if not command_spec:
        return JSONResponse(
            status_code=400,
            content=build_error(
                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                message="Command is not registered in kernel registry",
                details={"normalized_command": normalized_command},
            ).model_dump()
        )


    # --- v0.7: Command Execution Contract (payload validation, fail-closed) ---
    try:
        validate_command_payload(command_key, request.payload or {})
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content=build_error(
                code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                message="Command payload validation failed (fail-closed)",
                details={"reason": str(e)},
            ).model_dump()
        )


    # Log the request
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "client_id": request.client_id,
        "raw_command": request.command,
        "normalized_command": normalized_command,
        "confirm_token": request.confirm_token,
    }
    
    # CONFIRM flow
    if request.confirm_token:
        log_entry["action"] = "confirm_attempt"
        
        # Find the proposal in proposals.jsonl
        proposal = None
        token_found = False
        
        if proposals_file.exists():
            with open(proposals_file, "r") as f:
                for line in f:
                    try:
                        prop = json.loads(line)
                        if prop.get("token") == request.confirm_token:
                            token_found = True
                            # Check if token is expired (30 minutes TTL)
                            proposal_time = datetime.fromisoformat(prop["timestamp"])
                            current_time = datetime.utcnow()
                            time_diff = (current_time - proposal_time).total_seconds()
                            
                            if time_diff > 1800:  # 30 minutes TTL
                                log_entry["decision"] = "confirm_rejected"
                                log_entry["reason"] = "token_expired"
                                break

                            # Registry-based confirm revalidation
                            current_command_key, current_params = parse_normalized_command(normalized_command)
                            current_spec = get_command_spec(current_command_key)

                            if not current_spec:
                                log_entry["decision"] = "confirm_rejected"
                                log_entry["reason"] = "kernel_unknown_command_confirm"
                                audit_append(log_entry)

                                return JSONResponse(
                                    status_code=400,
                                    content=build_error(
                                        code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                        message="Command not in registry at confirm time.",
                                        details={"command_key": current_command_key},
                                    ).dict(),
                                )

                            current_params_hash = hashlib.sha256(
                                json.dumps(current_params, sort_keys=True, separators=(",", ":")).encode("utf-8")
                            ).hexdigest()

                            if prop.get("command_key") != current_command_key:
                                log_entry["decision"] = "confirm_rejected"
                                log_entry["reason"] = "kernel_spec_mismatch"
                                audit_append(log_entry)
                                return JSONResponse(
                                    status_code=409,
                                    content=build_error(
                                        code=KernelErrorCode.KERNEL_SPEC_MISMATCH,
                                        message="Proposal spec mismatch at confirm.",
                                        details={
                                            "expected_command_key": prop.get("command_key"),
                                            "got_command_key": current_command_key,
                                        },
                                    ).dict(),
                                )


                            if prop.get("execution_class") != current_spec.execution_class.value:
                                log_entry["decision"] = "confirm_rejected"
                                log_entry["reason"] = "kernel_spec_mismatch"
                                audit_append(log_entry)
                                return JSONResponse(
                                   status_code=409,
                                   content=build_error(
                                       code=KernelErrorCode.KERNEL_SPEC_MISMATCH,
                                       message="Proposal spec mismatch at confirm.",
                                       details={
                                             "expected_execution_class": prop.get("execution_class"),
                                             "got_execution_class": current_spec.execution_class.value,
                                       },
                                   ).dict(),
                               )


                            if prop.get("params_hash") != current_params_hash:
                                log_entry["decision"] = "confirm_rejected"
                                log_entry["reason"] = "kernel_params_mismatch"
                                audit_append(log_entry)
                                return JSONResponse(
                                   status_code=409,
                                   content=build_error(
                                       code=KernelErrorCode.KERNEL_PARAMS_MISMATCH,
                                       message="Proposal params mismatch at confirm.",
                                       details={
                                              "expected_params_hash": prop.get("params_hash"),
                                              "got_params_hash": current_params_hash,
                                       },
                                   ).dict(),
                                )


                            # Valid token and command match
                            proposal = prop
                            log_entry["decision"] = "confirm_accepted_v0_6"
                            break
                    except json.JSONDecodeError:
                        continue
        
        if not token_found:
            log_entry["decision"] = "confirm_rejected"
            log_entry["reason"] = "token_not_found"
        
        # Append to audit log
        with open(audit_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Return appropriate response
        if proposal:
            # Check if command is in the read-only whitelist
            # v0.4.0: expanded whitelist with help, version, audit tail
            # --- v0.6: execution class gate (registry-based, fail-closed) ---

            execution_class = command_spec.execution_class

            if execution_class == ExecutionClass.READ_ONLY:
                  # v0.16: permit issuance is a read-only command but requires root assertion
                  if command_key == "permit issue":
                      assertion = http_request.headers.get("X-HBAR-Assertion")
                      if not assertion:
                          return JSONResponse(
                              status_code=401,
                              content=build_error(
                                  code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                                  message="Missing X-HBAR-Assertion header",
                                  details={"command_key": command_key},
                              ).dict(),
                          )

                      identity_secret = os.getenv("HBAR_IDENTITY_SECRET", "")
                      if not identity_secret:
                          return JSONResponse(
                              status_code=500,
                              content=build_error(
                                  code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                                  message="HBAR_IDENTITY_SECRET not configured",
                                  details={},
                              ).dict(),
                          )

                      try:
                          _claims = verify_assertion(
                              secret=identity_secret,
                              token=assertion,
                              expected_aud=request.client_id,
                          )
                      except Exception as e:
                          return JSONResponse(
                              status_code=403,
                              content=build_error(
                                  code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                                  message="Invalid assertion",
                                  details={"reason": str(e)},
                              ).dict(),
                          )

                      if _claims.get("trust_tier") != "root":
                          return JSONResponse(
                              status_code=403,
                              content=build_error(
                                  code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                                  message="permit issue requires trust_tier=root.",
                                  details={"trust_tier": _claims.get("trust_tier")},
                              ).dict(),
                          )

            elif execution_class == ExecutionClass.MEMORY_APPEND:
                assertion = http_request.headers.get("X-HBAR-Assertion")
                if not assertion:
                    return JSONResponse(
                        status_code=401,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Missing X-HBAR-Assertion header",
                            details={"execution_class": execution_class.value},
                        ).dict(),
                    )

                identity_secret = os.getenv("HBAR_IDENTITY_SECRET", "")
                if not identity_secret:
                    return JSONResponse(
                        status_code=500,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="HBAR_IDENTITY_SECRET not configured",
                            details={},
                        ).dict(),
                    )

                try:
                    _claims = verify_assertion(
                        secret=identity_secret,
                        token=assertion,
                        expected_aud=request.client_id,
                    )
                except Exception as e:
                    return JSONResponse(
                        status_code=403,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Invalid assertion",
                            details={"reason": str(e)},
                        ).dict(),
                    )

                permit = http_request.headers.get("X-HBAR-Permit")
                if not permit:
                    return JSONResponse(
                        status_code=401,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Missing X-HBAR-Permit header",
                            details={"execution_class": execution_class.value},
                        ).dict(),
                    )

                try:
                    _permit_claims = verify_permit(
                        secret=identity_secret,
                        token=permit,
                    )
                except Exception as e:
                    return JSONResponse(
                        status_code=403,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Invalid permit",
                            details={"reason": str(e)},
                        ).dict(),
                    )

                if normalize_permit_type(_permit_claims.get("typ")) != "MEMORY_WRITE":
                    return JSONResponse(
                        status_code=403,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                            message="Permit type not sufficient for MEMORY_APPEND.",
                            details={"permit_typ": _permit_claims.get("typ")},
                        ).dict(),
                    )

                if not DEV_ENABLE_MEMORY_APPEND:
                    return JSONResponse(
                        status_code=403,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                            message="MEMORY_APPEND not permitted in this build.",
                            details={"execution_class": execution_class.value},
                        ).dict(),
                    )

                # DEV: allow MEMORY_APPEND only for root assertions
                if _claims.get("trust_tier") != "root":
                    return JSONResponse(
                        status_code=403,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                            message="MEMORY_APPEND requires trust_tier=root in dev mode.",
                            details={"trust_tier": _claims.get("trust_tier")},
                        ).dict(),
                    )



                handler = MEMORY_APPEND_HANDLERS.get(command_key)
                if not handler:
                    return JSONResponse(
                        status_code=404,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                            message="No handler registered for command",
                            details={"command_key": command_key},
                        ).dict(),
                    )

                payload = request.payload or {}
                result = handler(
                    ctx={
                        "client_id": request.client_id,
                        "operator_id": _claims.get("sub"),
                        "strain_id": _claims.get("strain_id"),
                    },
                    payload=payload,
                )
                return ok(
                    {
                        "status": "CONFIRMED",
                        "effect": "memory_append",
                        "command": request.command,
                        "result": result,
                    }
                )


            elif execution_class == ExecutionClass.STATE_MUTATION:
                assertion = http_request.headers.get("X-HBAR-Assertion")
                if not assertion:
                    return JSONResponse(
                        status_code=401,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Missing X-HBAR-Assertion header",
                            details={"execution_class": execution_class.value},
                        ).dict(),
                    )

                return JSONResponse(
                    status_code=403,
                    content=build_error(
                        code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                        message="STATE_MUTATION not permitted in this build.",
                        details={"execution_class": execution_class.value},
                    ).dict(),
                )




            elif execution_class == ExecutionClass.EXTERNAL_SIDE_EFFECT:
                assertion = http_request.headers.get("X-HBAR-Assertion")
                if not assertion:
                    return JSONResponse(
                        status_code=401,
                        content=build_error(
                            code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                            message="Missing X-HBAR-Assertion header",
                            details={"execution_class": execution_class.value},
                        ).dict(),
                    )

                return JSONResponse(
                    status_code=403,
                    content=build_error(
                        code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                        message="EXTERNAL_SIDE_EFFECT not permitted in this build.",
                        details={"execution_class": execution_class.value},
                    ).dict(),
                )





            is_audit_tail = (command_key == "audit tail")
            audit_tail_n = int(command_params.get("n", 50)) if isinstance(command_params, dict) else 50

            if execution_class == ExecutionClass.READ_ONLY:
                # Execute read-only command
                result = None
                error = None
                api_status = None
                nodeos_status = None
                ollama_status = None
                db_status = None
                status_mode = False
                
                try:

                    if normalized_command == "health":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}
                        result = handler(
                            ctx={
                                "client_id": request.client_id,
                                "kernel_version": HBAR_BRAIN_VERSION,
                                "host": socket.gethostname(),
                                "health_check": health_check,
                            },
                            payload=payload,
                        )


                    elif normalized_command == "whoami":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}

                        ctx = {
                            "client_id": request.client_id,
                            "kernel_version": HBAR_BRAIN_VERSION,
                            "host": socket.gethostname(),
                            "health_check": health_check,
                        }


                        result = handler(
                            ctx=ctx,
                            payload=payload,
                        )


                    elif command_key == "permit issue":
                        print("DEBUG normalized:", normalized_command)
                        print("DEBUG command_key:", command_key)
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )

                        payload = command_params or {}

                        ctx = {
                            "client_id": request.client_id,
                            "kernel_version": HBAR_BRAIN_VERSION,
                            "host": socket.gethostname(),
                            "health_check": health_check,
                        }

                        # Require root assertion for permit issuance
                        assertion = http_request.headers.get("X-HBAR-Assertion")
                        if not assertion:
                            return JSONResponse(
                                status_code=401,
                                content=build_error(
                                    code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                                    message="Missing X-HBAR-Assertion header",
                                    details={"command_key": command_key},
                                ).dict(),
                            )

                        identity_secret = os.getenv("HBAR_IDENTITY_SECRET", "")
                        try:
                            _claims = verify_assertion(
                                secret=identity_secret,
                                token=assertion,
                                expected_aud=request.client_id,
                            )
                        except Exception as e:
                            return JSONResponse(
                                status_code=403,
                                content=build_error(
                                    code=KernelErrorCode.KERNEL_VALIDATION_ERROR,
                                    message="Invalid assertion",
                                    details={"reason": str(e)},
                                ).dict(),
                            )

                        if _claims.get("trust_tier") != "root":
                            return JSONResponse(
                                status_code=403,
                                content=build_error(
                                    code=KernelErrorCode.KERNEL_EXECUTION_CLASS_FORBIDDEN,
                                    message="permit issue requires trust_tier=root.",
                                    details={"trust_tier": _claims.get("trust_tier")},
                                ).dict(),
                            )

                        ctx.update(
                            {
                                "operator_id": _claims.get("sub"),
                                "identity_secret": identity_secret,
                            }
                        )

                        result = handler(
                            ctx=ctx,
                            payload=payload,
                        )


                    elif normalized_command == "help":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}
                        result = handler(
                            ctx={
                                "client_id": request.client_id,
                                "kernel_version": HBAR_BRAIN_VERSION,
                                "host": socket.gethostname(),
                            },
                            payload=payload,
                        )

                    elif normalized_command == "version":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}
                        result = handler(
                            ctx={
                                "client_id": request.client_id,
                                "kernel_version": HBAR_BRAIN_VERSION,
                                "host": socket.gethostname(),
                                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                                "git_commit": os.getenv("HBAR_GIT_COMMIT", "unknown"),
                                "build_time": os.getenv("HBAR_BUILD_TIME", "unknown"),
                            },
                            payload=payload,
                        )




                    elif is_audit_tail:
                        handler = READ_ONLY_HANDLERS.get("audit tail")
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": "audit tail"},
                            )
                        result = handler(
                            ctx={
                                "client_id": request.client_id,
                                "audit_file": audit_file,
                                "json": json,
                                "n": audit_tail_n,
                            },
                            payload={},
                        )




                    elif normalized_command == "status":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}
                        result = handler(
                            ctx={
                                "client_id": request.client_id,
                                "kernel_version": HBAR_BRAIN_VERSION,
                                "host": socket.gethostname(),
                                "requests": requests,
                                "nodeos_url": NODEOS_URL,
                                "ollama_url": OLLAMA_URL,
                                "database_url": DATABASE_URL,
                                "get_db_connection": get_db_connection,
                            },
                            payload=payload,
                        )


                    elif normalized_command == "echo":
                        handler = READ_ONLY_HANDLERS.get(command_key)
                        if not handler:
                            raise KernelException(
                                code=KernelErrorCode.KERNEL_UNKNOWN_COMMAND,
                                message="No handler registered for command",
                                details={"command_key": command_key},
                            )
                        payload = request.payload or {}
                        result = handler(ctx={"client_id": request.client_id}, payload=payload)















        

                    # ── brain custom commands ─────────────────────────────────
                    elif normalized_command in {
                        'remember', 'recall', 'forget', 'memories',
                        'context.show', 'context.set', 'context.clear',
                        'peers', 'peers.introduce', 'peers.ping', 'peers.remove', 'introduce',
                        'model', 'model.list', 'model.use',
                        'audit', 'audit.clear', 'policy',
                        'ingest', 'think',
                    }:
                        from api.hbar_commands import handle_hbar_command
                        result = await handle_hbar_command(
                            command=normalized_command,
                            payload=request.payload or {},
                            client_id=request.client_id,
                            ollama_url=os.getenv('OLLAMA_URL', 'http://ollama:11434'),
                            model=os.getenv('OLLAMA_MODEL', 'mistral:7b'),
                        )
                    # ── end brain custom commands ──────────────────────────────
                    # Log successful execution
                    execution_log = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "client_id": request.client_id,
                        "command": normalized_command,
                        "action": "read_only_executed",
                        "decision": "allowed" if not error else "partial",
                        "effect": "read_only"
                    }
                    
                    if error:
                        execution_log["error"] = error
                    
                    with open(audit_file, "a") as f:
                        f.write(json.dumps(execution_log) + "\n")
                    
                    return ok({
                        "status": "CONFIRMED",
                        "effect": "read_only",
                        "command": normalized_command,
                        "result": result
                    })

                    
                except Exception as e:
                    # Log execution error
                    execution_log = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "client_id": request.client_id,
                        "command": normalized_command,
                        "action": "read_only_executed",
                        "decision": "partial",
                        "effect": "read_only",
                        "error": str(e)
                    }
                    
                    with open(audit_file, "a") as f:
                        f.write(json.dumps(execution_log) + "\n")
                    
                    # Return partial result
                    return JSONResponse(
                        status_code=500,
                        content=build_error(
                            code=KernelErrorCode.READ_ONLY_EXECUTION_ERROR,
                            message="Read-only command execution failed",
                            details={"command": normalized_command, "error": str(e)},
                        ).model_dump()
                    )

            else:
                # Non-whitelisted command
                return ok({
                    "status": "CONFIRMED",
                    "message": "Command confirmed successfully",
                    "effect": "none",
                    "executed": False,
                    "note": "NO EXECUTION IN V0"
                })

        else:
            error_reason = log_entry.get("reason", "unknown")

            return JSONResponse(
                status_code=403,
                content=build_error(
                    code=KernelErrorCode.CONFIRMATION_FAILED,
                    message="Confirmation failed",
                    details={"reason": error_reason},
                ).model_dump()
            )

    
    # PROPOSE flow
    else:
        # Generate confirmation token
        token_hex = hashlib.md5(f"{normalized_command}:{time.time()}".encode()).hexdigest()[:8]
        confirmation_token = f"CONFIRM-{token_hex}"

        command_key, params = parse_normalized_command(normalized_command)

        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        # Create proposal
        proposal = {
            "timestamp": datetime.utcnow().isoformat(),
            "token": confirmation_token,
            "normalized_command": normalized_command,
            "raw_command": request.command,
            "client_id": request.client_id,
            "command_key": command_key,
            "execution_class": command_spec.execution_class.value,
            "params_hash": params_hash
        }
        
        # Append to proposals file
        with open(proposals_file, "a") as f:
            f.write(json.dumps(proposal) + "\n")
        
        # Update log entry and append to audit log
        log_entry["action"] = "proposal_created"
        log_entry["token"] = confirmation_token
        
        with open(audit_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Return response
        return ok({
            "status": "PROPOSED",
            "token": confirmation_token,
            "ttl_seconds": 1800,
            "instructions": f"Re-run the command with confirm_token='{confirmation_token}' to confirm"
        })


SQLITE_PATH = "/app/extensions/brain/semantic.db"

router = APIRouter()

def _sqlite_conn():
    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    return con

@router.get("/brain/tags")
def brain_tags():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT split_part(metadata->>'source', '/', 1) AS name,
               COUNT(DISTINCT metadata->>'source') AS doc_count
        FROM document_embeddings
        WHERE metadata->>'source' IS NOT NULL
          AND split_part(metadata->>'source', '/', 1) != ''
          AND metadata->>'source' LIKE '%/%'
        GROUP BY name
        ORDER BY doc_count DESC
    """)
    rows = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

@router.get("/brain/docs")
def brain_docs(tags: str = ""):
    conn = get_db_connection()
    cur = conn.cursor()
    if not tags.strip():
        cur.execute("""
            SELECT DISTINCT metadata->>'source' AS source
            FROM document_embeddings
            WHERE metadata->>'source' IS NOT NULL
            ORDER BY source
        """)
        docs = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"documents": docs, "filter_tags": [], "count": len(docs)}

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    conditions = " OR ".join([f"LOWER(split_part(metadata->>'source', '/', 1)) = %s" for _ in tag_list])
    cur.execute(f"""
        SELECT DISTINCT metadata->>'source' AS source
        FROM document_embeddings
        WHERE metadata->>'source' IS NOT NULL
          AND ({conditions})
        ORDER BY source
    """, tag_list)
    docs = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {"documents": docs, "filter_tags": tag_list, "count": len(docs)}

app.include_router(router)
