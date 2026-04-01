from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import psycopg2
import requests
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import PyPDF2
import docx
from PIL import Image
import pytesseract
import io
import numpy as np
from sentence_transformers import SentenceTransformer
import tempfile
import httpx

# api/main.py (add near other imports)
import sqlite3
from fastapi import APIRouter

app = FastAPI(title="LLM Private Assistant API", version="2.0.0")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Dockerized UI
        "http://localhost:3001",   # Local dev UI
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# Initialize embedding model (will download on first use)
embedding_model = None

def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        try:
            embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            print(f"Failed to load embedding model: {e}")
            embedding_model = None
    return embedding_model

@app.on_event("startup")
def preload_models() -> None:
    _ = get_embedding_model()  # force load on boot

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
    """Search for similar documents using vector similarity"""
    try:
        # Generate query embedding
        query_embedding = generate_embeddings([query])[0]
        
        # Search database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Convert Python list to PostgreSQL array format
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        cursor.execute(
            """
            SELECT document_name, content, metadata, 
                   embedding <-> %s::vector as distance
            FROM document_embeddings 
            ORDER BY embedding <-> %s::vector 
            LIMIT %s
            """,
            (embedding_str, embedding_str, limit)
        )
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [
            {
                "document_name": result[0],
                "content": result[1],
                "metadata": result[2] or {},
                "similarity_score": float(1 - result[3])  # Convert distance to similarity
            }
            for result in results
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
    # Test database connection
    db_status = "unknown"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM document_embeddings")
        doc_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        db_status = f"healthy ({doc_count} documents)"
    except:
        db_status = "error"
    
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
    embedding_status = "healthy" if get_embedding_model() is not None else "loading"
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "ollama": ollama_status,
            "embeddings": embedding_status
        }
    }

@app.get("/models")
def list_models():
    """Get available Ollama models"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags")
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch models")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Ollama connection error: {str(e)}")

@app.post("/chat/completions")
async def chat_completion(request: dict):
    """Chat completion endpoint compatible with OpenAI format - supports streaming"""
    try:
        model = request.get("model", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
        messages = request.get("messages", [])
        do_stream = request.get("stream", False)
        session_id = request.get("session_id")  # Optional session ID for persistence

        # non-streaming stays the same
        if not do_stream:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=120)) as client:
                r = await client.post(f"{OLLAMA_URL}/api/chat",
                                      json={"model": model, "messages": messages, "stream": False})
                r.raise_for_status()
                data = r.json()
                
                assistant_message = data.get("message", {}).get("content", "")
                
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
                
                return {
                    "id": f"chatcmpl-{uuid.uuid4()}",
                    "object": "chat.completion",
                    "created": int(datetime.utcnow().timestamp()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant",
                                    "content": assistant_message},
                        "finish_reason": "stop"
                    }],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }

        # streaming path (SSE: "data: {...}\n\n" frames)
        async def event_stream():
            timeout = httpx.Timeout(10.0, read=None)  # don't timeout while tokens arrive
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{OLLAMA_URL}/api/chat",
                                         json={"model": model, "messages": messages, "stream": True}) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            o = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        chunk = {
                            "id": f"chatcmpl-{uuid.uuid4()}",
                            "object": "chat.completion.chunk",
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": o.get("message", {}).get("content", "")},
                                "finish_reason": "stop" if o.get("done") else None,
                            }],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat completion error: {str(e)}")

@app.post("/chat/rag")
def rag_chat_completion(request: dict):
    """RAG-enhanced chat completion - chat with your documents!"""
    try:
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
        
        # Call Ollama
        ollama_request = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=ollama_request,
            timeout=120
        )
        
        if response.status_code == 200:
            ollama_response = response.json()
            
            return {
                "id": f"chatcmpl-rag-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(datetime.utcnow().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": ollama_response.get("response", "")
                    },
                    "finish_reason": "stop"
                }],
                "rag_metadata": {
                    "documents_used": len(relevant_docs),
                    "search_query": user_query,
                    "sources": [doc['document_name'] for doc in relevant_docs]
                },
                "usage": {
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": len(ollama_response.get("response", "").split()),
                    "total_tokens": len(prompt.split()) + len(ollama_response.get("response", "").split())
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Ollama generation failed")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG chat completion error: {str(e)}")

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and process document for embeddings and RAG"""
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
                        "chunk_index": stored_chunks
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
            "status": "success",
            "message": f"Document processed and ready for RAG! Created {stored_chunks} searchable chunks."
        }
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
        title = request.get("title", "")
        if not title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET title = %s WHERE session_id = %s",
            (title.strip(), session_id)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {"message": "Title updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update title: {str(e)}")

SQLITE_PATH = "/app/extensions/brain/semantic.db"

router = APIRouter()

def _sqlite_conn():
    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    return con

@router.get("/brain/tags")
def brain_tags():
    con = _sqlite_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT t.name AS name,
               COUNT(DISTINCT de.document_name) AS doc_count
        FROM tags t
        LEFT JOIN entity_tags et      ON et.tag_id   = t.id
        LEFT JOIN document_entities de ON de.entity_id = et.entity_id
        GROUP BY t.id, t.name
        ORDER BY doc_count DESC, t.name
    """)
    rows = [{"name": r["name"], "count": r["doc_count"]} for r in cur.fetchall()]
    con.close()
    return rows

@router.get("/brain/docs")
def brain_docs(tags: str = ""):
    con = _sqlite_conn()
    cur = con.cursor()
    if not tags.strip():
        cur.execute("SELECT DISTINCT document_name FROM document_entities ORDER BY document_name")
        docs = [r["document_name"] for r in cur.fetchall()]
        con.close()
        return {"documents": docs, "filter_tags": [], "count": len(docs)}

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    qmarks = ",".join(["?"] * len(tag_list))
    cur.execute(f"""
        SELECT DISTINCT de.document_name AS document_name
        FROM document_entities de
        JOIN entity_tags et ON de.entity_id = et.entity_id
        JOIN tags t         ON et.tag_id   = t.id
        WHERE LOWER(t.name) IN ({qmarks})
        ORDER BY de.document_name
    """, tag_list)
    docs = [r["document_name"] for r in cur.fetchall()]
    con.close()
    return {"documents": docs, "filter_tags": tag_list, "count": len(docs)}

app.include_router(router)