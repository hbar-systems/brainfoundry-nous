#!/usr/bin/env python3
"""
BrainFoundryOS brain layer: Smoke test for semantic database
Initializes SQLite DB from schema, seeds test data, and prints as JSON
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from extensions.brain.semantic_db import SemanticDB

def smoke_test():
    """Initialize DB, seed test data, and print results"""
    print("🧪 BrainFoundryOS brain layer smoke test")
    
    # Initialize semantic database
    print("📊 Initializing semantic database...")
    db = SemanticDB()
    
    # Seed entities
    print("🌱 Seeding test entities...")
    alice_id = db.add_entity(
        name="Alice Smith",
        entity_type="person",
        description="Quantum computing researcher at MIT",
        metadata={"affiliation": "MIT", "field": "quantum_computing"}
    )
    
    vqe_id = db.add_entity(
        name="VQE Algorithm",
        entity_type="concept", 
        description="Variational Quantum Eigensolver for quantum chemistry",
        metadata={"category": "quantum_algorithm", "applications": ["chemistry", "optimization"]}
    )
    
    mit_id = db.add_entity(
        name="MIT",
        entity_type="organization",
        description="Massachusetts Institute of Technology",
        metadata={"type": "university", "location": "Cambridge, MA"}
    )
    
    # Seed tags
    print("🏷️  Seeding test tags...")
    quantum_tag_id = db.add_tag("quantum", "#8B5CF6", "Quantum computing related")
    research_tag_id = db.add_tag("research", "#10B981", "Research-related material")
    important_tag_id = db.add_tag("important", "#EF4444", "High priority content")
    
    # Create relations
    print("🔗 Creating test relations...")
    db.add_relation("Alice Smith", "VQE Algorithm", "researches", strength=0.9)
    db.add_relation("Alice Smith", "MIT", "works_at", strength=1.0)
    db.add_relation("VQE Algorithm", "MIT", "developed_at", strength=0.7)
    
    # Tag entities
    print("🏷️  Tagging entities...")
    db.tag_entity("Alice Smith", "quantum")
    db.tag_entity("Alice Smith", "research")
    db.tag_entity("VQE Algorithm", "quantum")
    db.tag_entity("VQE Algorithm", "important")
    db.tag_entity("MIT", "research")
    
    # Link to mock documents
    print("📄 Linking to mock documents...")
    db.link_document_entity("quantum_paper_2024.pdf", "Alice Smith", relevance=0.9, context="First author")
    db.link_document_entity("quantum_paper_2024.pdf", "VQE Algorithm", relevance=1.0, context="Main topic")
    db.link_document_entity("vqe_tutorial.md", "VQE Algorithm", relevance=1.0, context="Tutorial subject")
    
    # Gather results
    print("📊 Gathering results...")
    
    # Get all entities
    entities = db.search_entities(limit=10)
    
    # Get relations for Alice
    alice_relations = db.get_entity_relations("Alice Smith")
    
    # Get VQE relations  
    vqe_relations = db.get_entity_relations("VQE Algorithm")
    
    # Get document entities
    doc_entities = db.get_document_entities("quantum_paper_2024.pdf")
    
    # Get stats
    stats = db.get_stats()
    
    # Compile results
    results = {
        "smoke_test": "BrainFoundryOS brain layer",
        "status": "success",
        "database_stats": stats,
        "entities": entities,
        "relations": {
            "alice_smith": alice_relations,
            "vqe_algorithm": vqe_relations
        },
        "document_links": {
            "quantum_paper_2024.pdf": doc_entities
        }
    }
    
    # Print as formatted JSON
    print("\n📋 Smoke test results:")
    print(json.dumps(results, indent=2, default=str))
    
    print(f"\n✅ Smoke test completed successfully!")
    print(f"   Entities: {stats['entities']}")
    print(f"   Relations: {stats['relations']}")
    print(f"   Tags: {stats['tags']}")
    print(f"   Document links: {stats['document_links']}")
    
    return results

if __name__ == "__main__":
    try:
        smoke_test()
    except Exception as e:
        print(f"❌ Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
