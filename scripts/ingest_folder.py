#!/usr/bin/env python3
"""
BrainFoundryOS brain layer: Ingestion script (host-side)
Batch upload documents from a local folder to the existing /documents/upload endpoint
"""

import os
import sys
import requests
from pathlib import Path
from typing import List, Dict, Any
import mimetypes
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Default values
DEFAULT_API_BASE = "http://localhost:8010"
DEFAULT_DOCS_DIR = "./input_samples"

class DocumentIngester:
    """Batch document uploader using existing FastAPI endpoints"""

    def __init__(self, api_base: str = None):
        """Initialize ingester with API base URL"""
        self.api_base = api_base or os.getenv("API_BASE", DEFAULT_API_BASE)
        self.upload_url = f"{self.api_base}/documents/upload"
        self.health_url = f"{self.api_base}/health"
        api_key = os.getenv("BRAIN_API_KEY", "")
        self.auth_headers = {"X-Api-Key": api_key} if api_key else {}
        
        # Supported file extensions (matching existing API)
        self.supported_extensions = {
            '.pdf', '.docx', '.txt', '.md', '.py', '.js', '.html', '.css',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'
        }
    
    def check_api_health(self) -> bool:
        """Check if the API is accessible"""
        try:
            response = requests.get(self.health_url, headers=self.auth_headers, timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ API healthy: {health_data.get('status', 'unknown')}")
                
                # Show service status
                services = health_data.get('services', {})
                for service, status in services.items():
                    print(f"   {service}: {status}")
                
                return True
            else:
                print(f"❌ API health check failed: {response.status_code}")
                return False
        except requests.RequestException as e:
            print(f"❌ Cannot connect to API at {self.api_base}: {e}")
            return False
    
    def find_documents(self, folder_path: Path, recursive: bool = True) -> List[Path]:
        """Find all supported documents in folder"""
        documents = []
        
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        
        if not folder_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")
        
        # Search pattern based on recursive flag
        pattern = "**/*" if recursive else "*"
        
        for file_path in folder_path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                documents.append(file_path)
        
        return sorted(documents)
    
    def upload_document(self, file_path: Path) -> Dict[str, Any]:
        """Upload a single document to the API"""
        try:
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Prepare file for upload
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, mime_type)
                }
                
                # Upload to existing endpoint
                response = requests.post(
                    self.upload_url,
                    files=files,
                    headers=self.auth_headers,
                    timeout=120  # Allow time for processing
                )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'filename': result.get('filename'),
                    'chunks_created': result.get('chunks_created', 0),
                    'size': result.get('size', 0),
                    'message': result.get('message', 'Success')
                }
            else:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', str(error_data))
                except:
                    error_detail = response.text or f"HTTP {response.status_code}"
                
                return {
                    'success': False,
                    'error': error_detail,
                    'status_code': response.status_code
                }
        
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Network error: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"File error: {e}"
            }
    
    def ingest_folder(self, folder_path: str, recursive: bool = True, 
                     dry_run: bool = False) -> Dict[str, Any]:
        """Ingest all documents from a folder"""
        folder = Path(folder_path).expanduser().resolve()
        
        print(f"🔍 Scanning folder: {folder}")
        print(f"   Recursive: {recursive}")
        print(f"   Dry run: {dry_run}")
        
        # Find documents
        documents = self.find_documents(folder, recursive)
        print(f"📄 Found {len(documents)} supported documents")
        
        if not documents:
            return {
                'total_files': 0,
                'successful': 0,
                'failed': 0,
                'results': []
            }
        
        # Show file list
        for doc in documents:
            rel_path = doc.relative_to(folder)
            size_mb = doc.stat().st_size / (1024 * 1024)
            print(f"   {rel_path} ({size_mb:.1f} MB)")
        
        if dry_run:
            print("\n🔍 Dry run complete - no files uploaded")
            return {
                'total_files': len(documents),
                'successful': 0,
                'failed': 0,
                'results': [],
                'dry_run': True
            }
        
        # Check API health before starting
        if not self.check_api_health():
            raise ConnectionError("API is not accessible")
        
        print(f"\n📤 Starting upload to {self.api_base}")
        
        # Upload documents
        results = []
        successful = 0
        failed = 0
        
        for i, doc_path in enumerate(documents, 1):
            rel_path = doc_path.relative_to(folder)
            print(f"\n[{i}/{len(documents)}] Uploading: {rel_path}")
            
            result = self.upload_document(doc_path)
            result['file_path'] = str(rel_path)
            results.append(result)
            
            if result['success']:
                successful += 1
                chunks = result.get('chunks_created', 0)
                size_kb = result.get('size', 0) / 1024
                print(f"   ✅ Success: {chunks} chunks, {size_kb:.1f} KB")
            else:
                failed += 1
                error = result.get('error', 'Unknown error')
                print(f"   ❌ Failed: {error}")
            
            # Brief pause between uploads to be nice to the API
            if i < len(documents):
                time.sleep(0.5)
        
        # Summary
        print(f"\n📊 Upload Summary:")
        print(f"   Total files: {len(documents)}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        
        if failed > 0:
            print(f"\n❌ Failed uploads:")
            for result in results:
                if not result['success']:
                    print(f"   {result['file_path']}: {result['error']}")
        
        return {
            'total_files': len(documents),
            'successful': successful,
            'failed': failed,
            'results': results
        }


def main():
    """CLI interface for document ingestion"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Batch upload documents to BrainFoundryOS brain layer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload all documents from a folder
  python scripts/ingest_folder.py ~/Documents/research
  
  # Dry run to see what would be uploaded
  python scripts/ingest_folder.py ~/Documents/research --dry-run
  
  # Upload only from current directory (not recursive)
  python scripts/ingest_folder.py . --no-recursive
  
  # Use custom API endpoint
  API_BASE=http://YOUR_SERVER_IP:8010 python scripts/ingest_folder.py ~/docs
        """
    )
    
    parser.add_argument(
        'folder',
        nargs='?',
        default=None,
        help='Folder path to scan for documents (default: DOCS_DIR_HOST env var or ./input_samples)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be uploaded without actually uploading'
    )
    
    parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Only scan the specified folder, not subdirectories'
    )
    
    parser.add_argument(
        '--api-base',
        default=None,
        help=f'API base URL (default: {DEFAULT_API_BASE} or API_BASE env var)'
    )
    
    args = parser.parse_args()
    
    try:
        ingester = DocumentIngester(api_base=args.api_base)
        
        # Determine folder path
        folder_path = args.folder
        if not folder_path:
            folder_path = os.getenv("DOCS_DIR_HOST", DEFAULT_DOCS_DIR)
        
        result = ingester.ingest_folder(
            folder_path=folder_path,
            recursive=not args.no_recursive,
            dry_run=args.dry_run
        )
        
        # Exit with error code if any uploads failed
        if result['failed'] > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Upload cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
