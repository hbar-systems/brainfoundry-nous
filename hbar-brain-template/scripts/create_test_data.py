#!/usr/bin/env python3
"""
Create sample Linear Algebra data for testing the export functionality
"""

import os
import sys
import json
import sqlite3
import psycopg2
from pathlib import Path

# Add the parent directory to the path to import from extensions
sys.path.append(str(Path(__file__).parent.parent))

def load_config():
    """Load configuration from .env file"""
    config = {}
    
    # Try to load from .env file
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    
    # Override with environment variables
    config.update({
        'POSTGRES_HOST': os.getenv('POSTGRES_HOST', config.get('POSTGRES_HOST', 'localhost')),
        'POSTGRES_PORT': os.getenv('POSTGRES_PORT', config.get('POSTGRES_PORT', '54322')),
        'POSTGRES_DB': os.getenv('POSTGRES_DB', config.get('POSTGRES_DB', 'llm_db')),
        'POSTGRES_USER': os.getenv('POSTGRES_USER', config.get('POSTGRES_USER', 'postgres')),
        'POSTGRES_PASSWORD': os.getenv('POSTGRES_PASSWORD', config.get('POSTGRES_PASSWORD', 'postgres')),
        'SEMANTIC_DB_PATH': os.getenv('SEMANTIC_DB_PATH', config.get('SEMANTIC_DB_PATH', 'extensions/brain/semantic.db'))
    })
    
    return config

def create_sample_documents():
    """Create sample Linear Algebra documents in PostgreSQL"""
    config = load_config()
    postgres_url = f"postgresql://{config['POSTGRES_USER']}:{config['POSTGRES_PASSWORD']}@{config['POSTGRES_HOST']}:{config['POSTGRES_PORT']}/{config['POSTGRES_DB']}"
    
    # Sample documents with Linear Algebra content
    documents = [
        {
            'name': 'linear-algebra-01-vectors.pdf',
            'chunks': [
                'A vector is a mathematical object that has both magnitude and direction. In linear algebra, vectors are fundamental building blocks used to represent quantities in multi-dimensional space.',
                'Vector addition follows the parallelogram rule. When adding two vectors, the result is a new vector that represents the combined effect of both original vectors.',
                'The dot product of two vectors is a scalar value that measures how much one vector extends in the direction of another. It is calculated as the sum of the products of corresponding components.'
            ]
        },
        {
            'name': 'linear-algebra-02-matrices.pdf', 
            'chunks': [
                'A matrix is a rectangular array of numbers arranged in rows and columns. Matrices are used to represent linear transformations and systems of linear equations.',
                'Matrix multiplication is defined such that the element in row i and column j of the product matrix is the dot product of row i from the first matrix and column j from the second matrix.',
                'The determinant of a matrix is a scalar value that provides important information about the matrix, including whether it is invertible and the scaling factor of the linear transformation it represents.'
            ]
        },
        {
            'name': 'linear-algebra-03-eigenvalues.pdf',
            'chunks': [
                'An eigenvalue is a scalar λ such that when a matrix A is multiplied by an eigenvector v, the result is the same as multiplying the eigenvector by the eigenvalue: Av = λv.',
                'Eigenvectors are non-zero vectors that, when multiplied by a matrix, result in a scalar multiple of themselves. They represent directions that are preserved under the linear transformation.',
                'The characteristic polynomial of a matrix is obtained by computing det(A - λI), where I is the identity matrix. The roots of this polynomial are the eigenvalues.'
            ]
        },
        {
            'name': 'linear-algebra-04-projections.pdf',
            'chunks': [
                'Vector projection is the operation of projecting one vector onto another. The projection of vector a onto vector b is the component of a in the direction of b.',
                'Orthogonal projection onto a subspace finds the closest point in the subspace to a given vector. This is fundamental in least squares approximation and data fitting.',
                'The projection matrix P has the property that P² = P, meaning applying the projection twice gives the same result as applying it once.'
            ]
        },
        {
            'name': 'linear-algebra-05-linear-systems.pdf',
            'chunks': [
                'A system of linear equations can be represented in matrix form as Ax = b, where A is the coefficient matrix, x is the vector of unknowns, and b is the constant vector.',
                'Gaussian elimination is a method for solving systems of linear equations by performing row operations to transform the augmented matrix into row echelon form.',
                'The rank of a matrix is the dimension of the vector space spanned by its rows (or columns). It determines the number of linearly independent equations in a system.'
            ]
        }
    ]
    
    try:
        conn = psycopg2.connect(postgres_url)
        cursor = conn.cursor()
        
        print("Creating sample Linear Algebra documents...")
        
        for doc in documents:
            for i, chunk in enumerate(doc['chunks']):
                # Create a simple embedding (all zeros for testing)
                embedding = [0.0] * 384  # 384 dimensions for all-MiniLM-L6-v2
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                
                metadata = {
                    "file_size": len(chunk),
                    "content_type": "application/pdf",
                    "upload_timestamp": "2025-10-05T11:29:58+02:00",
                    "chunk_index": i,
                    "section": f"Section {i+1}",
                    "tags": ["mathematics", "linear-algebra"]
                }
                
                cursor.execute("""
                    INSERT INTO document_embeddings (document_name, content, embedding, metadata) 
                    VALUES (%s, %s, %s::vector, %s)
                    ON CONFLICT DO NOTHING
                """, (doc['name'], chunk, embedding_str, json.dumps(metadata)))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Sample documents created in PostgreSQL")
        
    except Exception as e:
        print(f"❌ Failed to create sample documents: {e}")
        return False
    
    return True

def create_sample_entities():
    """Create sample entities and links in SQLite semantic DB"""
    config = load_config()
    semantic_db_path = Path(config['SEMANTIC_DB_PATH'])
    if not semantic_db_path.is_absolute():
        semantic_db_path = Path(__file__).parent.parent / semantic_db_path
    
    try:
        conn = sqlite3.connect(str(semantic_db_path))
        cursor = conn.cursor()
        
        print("Creating sample entities and links...")
        
        # Create entities
        entities = [
            ('vector', 'concept', 'Mathematical object with magnitude and direction'),
            ('matrix', 'concept', 'Rectangular array of numbers'),
            ('eigenvalue', 'concept', 'Scalar value in eigenvalue equation'),
            ('eigenvector', 'concept', 'Vector preserved under linear transformation'),
            ('projection', 'concept', 'Operation of projecting one vector onto another'),
            ('linear-system', 'concept', 'System of linear equations'),
            ('dot-product', 'concept', 'Scalar product of two vectors'),
            ('determinant', 'concept', 'Scalar value derived from matrix'),
            ('gaussian-elimination', 'concept', 'Method for solving linear systems'),
            ('rank', 'concept', 'Dimension of vector space spanned by matrix rows')
        ]
        
        for name, entity_type, description in entities:
            cursor.execute("""
                INSERT OR IGNORE INTO entities (name, type, description)
                VALUES (?, ?, ?)
            """, (name, entity_type, description))
        
        # Create tags
        tags = [
            ('mathematics', '#3B82F6', 'Mathematical concepts'),
            ('linear-algebra', '#8B5CF6', 'Linear algebra topics'),
            ('fundamental', '#EF4444', 'Fundamental concepts'),
            ('advanced', '#F59E0B', 'Advanced topics')
        ]
        
        for name, color, description in tags:
            cursor.execute("""
                INSERT OR IGNORE INTO tags (name, color, description)
                VALUES (?, ?, ?)
            """, (name, color, description))
        
        # Link entities to documents
        document_entities = [
            ('linear-algebra-01-vectors.pdf', 'vector', 1.0, 'Main topic'),
            ('linear-algebra-01-vectors.pdf', 'dot-product', 0.8, 'Important concept'),
            ('linear-algebra-02-matrices.pdf', 'matrix', 1.0, 'Main topic'),
            ('linear-algebra-02-matrices.pdf', 'determinant', 0.9, 'Key concept'),
            ('linear-algebra-03-eigenvalues.pdf', 'eigenvalue', 1.0, 'Main topic'),
            ('linear-algebra-03-eigenvalues.pdf', 'eigenvector', 1.0, 'Main topic'),
            ('linear-algebra-04-projections.pdf', 'projection', 1.0, 'Main topic'),
            ('linear-algebra-05-linear-systems.pdf', 'linear-system', 1.0, 'Main topic'),
            ('linear-algebra-05-linear-systems.pdf', 'gaussian-elimination', 0.9, 'Key method'),
            ('linear-algebra-05-linear-systems.pdf', 'rank', 0.8, 'Important concept')
        ]
        
        for doc_name, entity_name, relevance, context in document_entities:
            # Get entity ID
            cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_name,))
            entity_result = cursor.fetchone()
            if entity_result:
                entity_id = entity_result[0]
                cursor.execute("""
                    INSERT OR REPLACE INTO document_entities 
                    (document_name, entity_id, relevance, context)
                    VALUES (?, ?, ?, ?)
                """, (doc_name, entity_id, relevance, context))
        
        # Tag entities
        entity_tags = [
            ('vector', 'mathematics'),
            ('vector', 'linear-algebra'),
            ('vector', 'fundamental'),
            ('matrix', 'mathematics'),
            ('matrix', 'linear-algebra'),
            ('matrix', 'fundamental'),
            ('eigenvalue', 'mathematics'),
            ('eigenvalue', 'linear-algebra'),
            ('eigenvalue', 'advanced'),
            ('projection', 'mathematics'),
            ('projection', 'linear-algebra')
        ]
        
        for entity_name, tag_name in entity_tags:
            # Get IDs
            cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_name,))
            entity_result = cursor.fetchone()
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_result = cursor.fetchone()
            
            if entity_result and tag_result:
                entity_id, tag_id = entity_result[0], tag_result[0]
                cursor.execute("""
                    INSERT OR IGNORE INTO entity_tags (entity_id, tag_id)
                    VALUES (?, ?)
                """, (entity_id, tag_id))
        
        conn.commit()
        conn.close()
        print("✅ Sample entities and links created in SQLite")
        
    except Exception as e:
        print(f"❌ Failed to create sample entities: {e}")
        return False
    
    return True

def main():
    print("🧪 Creating sample Linear Algebra test data...")
    
    success = True
    success &= create_sample_documents()
    success &= create_sample_entities()
    
    if success:
        print("\n✅ Test data creation completed successfully!")
        print("You can now run: python scripts/export_index.py --course 'Linear Algebra' --out export/index.json")
    else:
        print("\n❌ Test data creation failed!")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
