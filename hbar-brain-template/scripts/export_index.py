#!/usr/bin/env python3
"""
Export script for hbar.blog agent
Produces site-ready export at export/index.json

Usage:
    python scripts/export_index.py --course "Linear Algebra" --out export/index.json
"""

import argparse
import json
import os
import sqlite3
import psycopg2
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExportIndexer:
    def __init__(self, postgres_url: str, semantic_db_path: str):
        self.postgres_url = postgres_url
        self.semantic_db_path = semantic_db_path
        self.concept_counts = defaultdict(int)
        
    def get_postgres_connection(self):
        """Get PostgreSQL connection"""
        try:
            return psycopg2.connect(self.postgres_url)
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def get_sqlite_connection(self):
        """Get SQLite connection"""
        try:
            conn = sqlite3.connect(self.semantic_db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise
    
    def extract_concept_from_filename(self, document_name: str) -> str:
        """
        Extract concept_id from filename using specific mapping
        Examples:
        - "Linear-Algebra-01-Vectors.pdf" -> "vector"
        - "Linear-Algebra-02-Matrices.pdf" -> "matrix"
        - "Linear-Algebra-03-Eigenvalues.pdf" -> "eigenvalue"
        """
        # Concept mapping
        concept_map = {
            "Vectors": "vector",
            "Matrices": "matrix", 
            "Eigenvalues": "eigenvalue",
            "Projections": "projection",
            "Dot-Product": "dot-product"
        }
        
        # Extract token after number: Linear-Algebra-01-<Token>.pdf
        match = re.search(r'Linear-Algebra-\d+-([^.]+)', document_name)
        if match:
            token = match.group(1)
            return concept_map.get(token, token.lower().replace('-', '_'))
        
        # Fallback: use original logic
        name = Path(document_name).stem
        name = re.sub(r'^[\d\-_]+', '', name)
        name = re.sub(r'^(chapter|section|part)[-_]?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[_\s]+', '-', name.lower())
        name = name.strip('-_')
        
        if not name:
            name = Path(document_name).stem.lower()
        
        return name
    
    def get_document_entities(self, document_name: str) -> List[Dict[str, Any]]:
        """Get entities linked to a document from semantic DB"""
        try:
            with self.get_sqlite_connection() as conn:
                cursor = conn.execute("""
                    SELECT e.name, e.type, e.description, de.relevance, de.context
                    FROM document_entities de
                    JOIN entities e ON de.entity_id = e.id
                    WHERE de.document_name = ?
                    ORDER BY de.relevance DESC
                """, (document_name,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"Failed to get entities for {document_name}: {e}")
            return []
    
    def get_document_chunks(self, course_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get document chunks from PostgreSQL using filename prefix match"""
        try:
            with self.get_postgres_connection() as conn:
                cursor = conn.cursor()
                
                if course_filter:
                    # Use filename prefix match
                    doc_prefix = course_filter.replace(" ", "-")
                    cursor.execute("""
                        SELECT document_name, content, metadata
                        FROM document_embeddings
                        WHERE document_name ILIKE %s
                        ORDER BY document_name
                    """, (f"{doc_prefix}-%",))
                else:
                    cursor.execute("""
                        SELECT document_name, content, metadata
                        FROM document_embeddings 
                        ORDER BY document_name
                    """)
                
                results = []
                for row in cursor.fetchall():
                    document_name, content, metadata = row
                    
                    # Parse metadata if it's a JSON string
                    try:
                        if isinstance(metadata, str):
                            metadata = json.loads(metadata)
                        elif metadata is None:
                            metadata = {}
                    except json.JSONDecodeError:
                        metadata = {}
                    
                    results.append({
                        'document_name': document_name,
                        'content': content,
                        'metadata': metadata
                    })
                
                logger.info(f"Retrieved {len(results)} chunks from PostgreSQL")
                return results
                
        except Exception as e:
            logger.error(f"Failed to get document chunks: {e}")
            raise
    
    def generate_source_path(self, document_name: str, chunk_index: int = 0) -> str:
        """
        Generate a relative source path for the document
        """
        return f"/docs/{document_name}"
    
    def export_index(self, course: str, output_path: str) -> Dict[str, Any]:
        """Export index for the specified course"""
        logger.info(f"Starting export for course: {course}")
        
        # Get document chunks
        chunks = self.get_document_chunks(course_filter=course)
        
        if not chunks:
            logger.warning(f"No chunks found for course: {course}")
            return {"items": [], "stats": {"total_items": 0, "concepts": {}}}
        
        items = []
        chunk_counter = 0
        
        # Group chunks by document
        docs_chunks = defaultdict(list)
        for chunk in chunks:
            docs_chunks[chunk['document_name']].append(chunk)
        
        for document_name, doc_chunks in docs_chunks.items():
            logger.info(f"Processing document: {document_name} ({len(doc_chunks)} chunks)")
            
            # Get entities for this document (for concept mapping)
            entities = self.get_document_entities(document_name)
            
            # Determine concept_id
            concept_id = None
            if entities:
                # Use the first entity with type 'concept' or highest relevance
                concept_entities = [e for e in entities if e['type'] == 'concept']
                if concept_entities:
                    concept_id = concept_entities[0]['name'].lower().replace(' ', '-')
                else:
                    # Use highest relevance entity
                    concept_id = entities[0]['name'].lower().replace(' ', '-')
            
            # Fallback to filename heuristics
            if not concept_id:
                concept_id = self.extract_concept_from_filename(document_name)
            
            # Process each chunk
            for i, chunk in enumerate(doc_chunks):
                try:
                    # Extract section and tags from metadata
                    metadata = chunk.get('metadata', {})
                    section = metadata.get('section')
                    tags = metadata.get('tags', [])
                    
                    # Generate unique ID
                    item_id = f"{document_name}-chunk-{i}"
                    
                    # Generate source path
                    source_path = self.generate_source_path(document_name, i)
                    
                    # Create export item
                    item = {
                        "id": item_id,
                        "course": course,
                        "concept_id": concept_id,
                        "source": source_path,
                        "text": chunk['content'],
                        "meta": {
                            "section": section,
                            "tags": tags
                        }
                    }
                    
                    items.append(item)
                    self.concept_counts[concept_id] += 1
                    chunk_counter += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to process chunk {i} of {document_name}: {e}")
                    continue
        
        # Create export data
        export_data = {
            "items": items,
            "stats": {
                "total_items": len(items),
                "concepts": dict(self.concept_counts),
                "generated_at": "2025-10-05T11:29:58+02:00",
                "course": course
            }
        }
        
        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Export completed: {len(items)} items written to {output_path}")
        
        # Log concept counts
        logger.info("Concept counts:")
        for concept_id, count in sorted(self.concept_counts.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {concept_id}: {count}")
        
        return export_data

def load_config() -> Dict[str, str]:
    """Load configuration from .env file and environment variables"""
    config = {}
    
    # Check for DATABASE_URL first (used in Docker containers)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        config['DATABASE_URL'] = database_url
        logger.info("Using DATABASE_URL from environment")
    else:
        # Try to load from .env file
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        
        # Build DATABASE_URL from individual components
        config.update({
            'POSTGRES_HOST': os.getenv('POSTGRES_HOST', config.get('POSTGRES_HOST', 'localhost')),
            'POSTGRES_PORT': os.getenv('POSTGRES_PORT', config.get('POSTGRES_PORT', '54322')),
            'POSTGRES_DB': os.getenv('POSTGRES_DB', config.get('POSTGRES_DB', 'llm_db')),
            'POSTGRES_USER': os.getenv('POSTGRES_USER', config.get('POSTGRES_USER', 'postgres')),
            'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', config.get('POSTGRES_PASSWORD', 'postgres')),
        })
        
        # Build DATABASE_URL
        config['DATABASE_URL'] = f"postgresql://{config['POSTGRES_USER']}:{config['POSTGRES_PASSWORD']}@{config['POSTGRES_HOST']}:{config['POSTGRES_PORT']}/{config['POSTGRES_DB']}"
    
    # Semantic DB path
    config['SEMANTIC_DB_PATH'] = os.getenv('SEMANTIC_DB_PATH', config.get('SEMANTIC_DB_PATH', 'extensions/brain/semantic.db'))
    
    return config

def main():
    parser = argparse.ArgumentParser(description='Export index for hbar.blog agent')
    parser.add_argument('--course', help='Course name to export (e.g., "Linear Algebra")', default="Linear Algebra")
    parser.add_argument('--out', required=True, help='Output file path (e.g., export/index.json)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    config = load_config()
    
    # Get PostgreSQL connection string
    postgres_url = config['DATABASE_URL']
    
    # Resolve semantic DB path
    semantic_db_path = Path(config['SEMANTIC_DB_PATH'])
    if not semantic_db_path.is_absolute():
        # Make relative to script's parent directory (repo root)
        semantic_db_path = Path(__file__).parent.parent / semantic_db_path
    
    # Mask password in logs
    masked_url = postgres_url
    if '@' in postgres_url and ':' in postgres_url:
        parts = postgres_url.split('@')
        if len(parts) == 2:
            auth_part = parts[0].split('://')[-1]
            if ':' in auth_part:
                user, password = auth_part.split(':', 1)
                masked_url = postgres_url.replace(f':{password}@', ':***@')
    
    logger.info(f"PostgreSQL URL: {masked_url}")
    logger.info(f"Semantic DB path: {semantic_db_path}")
    
    # Create exporter and run
    try:
        exporter = ExportIndexer(postgres_url, str(semantic_db_path))
        result = exporter.export_index(args.course or "Linear Algebra", args.out)
        
        print(f"✅ Export completed successfully!")
        print(f"📊 Total items: {result['stats']['total_items']}")
        print(f"📁 Output file: {args.out}")
        
        # Print concept breakdown
        if result['stats']['concepts']:
            print("\n📈 Concept breakdown:")
            for concept, count in sorted(result['stats']['concepts'].items()):
                print(f"   {concept}: {count} items")
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
