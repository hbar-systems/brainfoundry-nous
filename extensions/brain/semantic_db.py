#!/usr/bin/env python3
"""
BrainFoundryOS brain layer: Semantic/Identity micro-DB operations
SQLite database operations for entities, tags, and relations (separate from main pgvector DB)
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SemanticDB:
    """SQLite-based semantic database for entities, tags, and relations"""
    
    def __init__(self, db_path: str = None):
        """Initialize semantic database connection"""
        if db_path is None:
            # Check environment variable first
            db_path = os.getenv("SEMANTIC_DB_PATH")
            if not db_path:
                # Default to extensions/brain/semantic.db in repo root
                repo_root = Path(__file__).parent.parent.parent
                db_path = repo_root / "extensions" / "brain" / "semantic.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database with schema
        self._init_database()
    
    def _init_database(self):
        """Initialize database with schema from semantic_schema.sql"""
        schema_path = self.db_path.parent / "semantic_schema.sql"
        
        with sqlite3.connect(self.db_path) as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Load and execute schema
            if schema_path.exists():
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
            else:
                raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    def add_entity(self, name: str, entity_type: str, description: str = None, 
                   metadata: Dict[str, Any] = None) -> int:
        """Add or update an entity, return entity ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Insert or update entity
            cursor = conn.execute("""
                INSERT INTO entities (name, type, description, metadata, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    type = excluded.type,
                    description = excluded.description,
                    metadata = excluded.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (name, entity_type, description, metadata_json))
            
            return cursor.fetchone()[0]
    
    def add_tag(self, name: str, color: str = "#3B82F6", description: str = None) -> int:
        """Add a tag, return tag ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO tags (name, color, description)
                VALUES (?, ?, ?)
                RETURNING id
            """, (name, color, description))
            
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                # Tag already exists, get its ID
                cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (name,))
                return cursor.fetchone()[0]
    
    def add_relation(self, source_name: str, target_name: str, relation_type: str,
                     strength: float = 1.0, metadata: Dict[str, Any] = None) -> int:
        """Add a relation between entities by name"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Get entity IDs
            cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (source_name,))
            source_result = cursor.fetchone()
            if not source_result:
                raise ValueError(f"Source entity '{source_name}' not found")
            source_id = source_result[0]
            
            cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (target_name,))
            target_result = cursor.fetchone()
            if not target_result:
                raise ValueError(f"Target entity '{target_name}' not found")
            target_id = target_result[0]
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Insert relation (ON CONFLICT UPDATE strength and metadata)
            cursor = conn.execute("""
                INSERT INTO relations (source_entity_id, target_entity_id, relation_type, strength, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_entity_id, target_entity_id, relation_type) DO UPDATE SET
                    strength = excluded.strength,
                    metadata = excluded.metadata
                RETURNING id
            """, (source_id, target_id, relation_type, strength, metadata_json))
            
            return cursor.fetchone()[0]
    
    def tag_entity(self, entity_name: str, tag_name: str):
        """Associate a tag with an entity"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Get IDs
            cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,))
            entity_result = cursor.fetchone()
            if not entity_result:
                raise ValueError(f"Entity '{entity_name}' not found")
            entity_id = entity_result[0]
            
            cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_result = cursor.fetchone()
            if not tag_result:
                raise ValueError(f"Tag '{tag_name}' not found")
            tag_id = tag_result[0]
            
            # Insert association
            conn.execute("""
                INSERT OR IGNORE INTO entity_tags (entity_id, tag_id)
                VALUES (?, ?)
            """, (entity_id, tag_id))
    
    def link_document_entity(self, document_name: str, entity_name: str, 
                           relevance: float = 1.0, context: str = None):
        """Link a document to an entity"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Get entity ID
            cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,))
            entity_result = cursor.fetchone()
            if not entity_result:
                raise ValueError(f"Entity '{entity_name}' not found")
            entity_id = entity_result[0]
            
            # Insert document-entity link
            conn.execute("""
                INSERT OR REPLACE INTO document_entities 
                (document_name, entity_id, relevance, context)
                VALUES (?, ?, ?, ?)
            """, (document_name, entity_id, relevance, context))
    
    def search_entities(self, query: str = None, entity_type: str = None, 
                       tag_name: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search entities with optional filters"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            sql = """
                SELECT DISTINCT e.id, e.name, e.type, e.description, e.metadata, e.created_at
                FROM entities e
                LEFT JOIN entity_tags et ON e.id = et.entity_id
                LEFT JOIN tags t ON et.tag_id = t.id
                WHERE 1=1
            """
            params = []
            
            if query:
                sql += " AND (e.name LIKE ? OR e.description LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
            
            if entity_type:
                sql += " AND e.type = ?"
                params.append(entity_type)
            
            if tag_name:
                sql += " AND t.name = ?"
                params.append(tag_name)
            
            sql += " ORDER BY e.name LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(sql, params)
            results = []
            
            for row in cursor.fetchall():
                entity = dict(row)
                entity['metadata'] = json.loads(entity['metadata']) if entity['metadata'] else {}
                
                # Get tags for this entity
                tag_cursor = conn.execute("""
                    SELECT t.name, t.color FROM tags t
                    JOIN entity_tags et ON t.id = et.tag_id
                    WHERE et.entity_id = ?
                """, (entity['id'],))
                entity['tags'] = [dict(tag_row) for tag_row in tag_cursor.fetchall()]
                
                results.append(entity)
            
            return results
    
    def get_entity_relations(self, entity_name: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get all relations for an entity (both incoming and outgoing)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get entity ID
            cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,))
            entity_result = cursor.fetchone()
            if not entity_result:
                return {"outgoing": [], "incoming": []}
            entity_id = entity_result[0]
            
            # Outgoing relations
            outgoing_cursor = conn.execute("""
                SELECT r.relation_type, r.strength, r.metadata, e.name as target_name, e.type as target_type
                FROM relations r
                JOIN entities e ON r.target_entity_id = e.id
                WHERE r.source_entity_id = ?
                ORDER BY r.strength DESC
            """, (entity_id,))
            
            outgoing = []
            for row in outgoing_cursor.fetchall():
                rel = dict(row)
                rel['metadata'] = json.loads(rel['metadata']) if rel['metadata'] else {}
                outgoing.append(rel)
            
            # Incoming relations
            incoming_cursor = conn.execute("""
                SELECT r.relation_type, r.strength, r.metadata, e.name as source_name, e.type as source_type
                FROM relations r
                JOIN entities e ON r.source_entity_id = e.id
                WHERE r.target_entity_id = ?
                ORDER BY r.strength DESC
            """, (entity_id,))
            
            incoming = []
            for row in incoming_cursor.fetchall():
                rel = dict(row)
                rel['metadata'] = json.loads(rel['metadata']) if rel['metadata'] else {}
                incoming.append(rel)
            
            return {"outgoing": outgoing, "incoming": incoming}
    
    def get_document_entities(self, document_name: str) -> List[Dict[str, Any]]:
        """Get all entities linked to a document"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT e.name, e.type, e.description, de.relevance, de.context
                FROM document_entities de
                JOIN entities e ON de.entity_id = e.id
                WHERE de.document_name = ?
                ORDER BY de.relevance DESC
            """, (document_name,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            
            cursor = conn.execute("SELECT COUNT(*) FROM entities")
            stats['entities'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            stats['tags'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM relations")
            stats['relations'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM document_entities")
            stats['document_links'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(DISTINCT document_name) FROM document_entities")
            stats['linked_documents'] = cursor.fetchone()[0]
            
            return stats


def main():
    """CLI interface for testing semantic DB operations"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python semantic_db.py <command> [args...]")
        print("Commands:")
        print("  stats                           - Show database statistics")
        print("  add-entity <name> <type> [desc] - Add an entity")
        print("  add-tag <name> [color] [desc]   - Add a tag")
        print("  search [query]                  - Search entities")
        print("  relations <entity_name>         - Show entity relations")
        return
    
    db = SemanticDB()
    command = sys.argv[1]
    
    if command == "stats":
        stats = db.get_stats()
        print("Semantic DB Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    elif command == "add-entity" and len(sys.argv) >= 4:
        name, entity_type = sys.argv[2], sys.argv[3]
        description = sys.argv[4] if len(sys.argv) > 4 else None
        entity_id = db.add_entity(name, entity_type, description)
        print(f"Added entity '{name}' with ID {entity_id}")
    
    elif command == "add-tag" and len(sys.argv) >= 3:
        name = sys.argv[2]
        color = sys.argv[3] if len(sys.argv) > 3 else "#3B82F6"
        description = sys.argv[4] if len(sys.argv) > 4 else None
        tag_id = db.add_tag(name, color, description)
        print(f"Added tag '{name}' with ID {tag_id}")
    
    elif command == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else None
        results = db.search_entities(query=query)
        print(f"Found {len(results)} entities:")
        for entity in results:
            tags_str = ", ".join([tag['name'] for tag in entity['tags']])
            print(f"  {entity['name']} ({entity['type']}) - Tags: [{tags_str}]")
    
    elif command == "relations" and len(sys.argv) >= 3:
        entity_name = sys.argv[2]
        relations = db.get_entity_relations(entity_name)
        print(f"Relations for '{entity_name}':")
        print(f"  Outgoing ({len(relations['outgoing'])}):")
        for rel in relations['outgoing']:
            print(f"    --{rel['relation_type']}--> {rel['target_name']} (strength: {rel['strength']})")
        print(f"  Incoming ({len(relations['incoming'])}):")
        for rel in relations['incoming']:
            print(f"    <--{rel['relation_type']}-- {rel['source_name']} (strength: {rel['strength']})")
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
