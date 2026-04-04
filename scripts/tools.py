#!/usr/bin/env python3
"""
BrainFoundryOS brain layer: Tools implementation
Simple web.fetch tool and other utilities for the planner
"""

import requests
from typing import Dict, Any, Optional, List
import json
import time
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class WebFetchTool:
    """Simple web content fetcher with basic parsing"""
    
    def __init__(self, timeout: int = 30, max_content_length: int = 1024 * 1024):
        """Initialize web fetch tool with limits"""
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.session = requests.Session()
        
        # Set a reasonable User-Agent
        self.session.headers.update({
            'User-Agent': 'brainfoundry-node/1.0'
        })
    
    def fetch(self, url: str, extract_text: bool = True, 
              include_links: bool = False) -> Dict[str, Any]:
        """
        Fetch content from a URL and return structured data
        
        Args:
            url: URL to fetch
            extract_text: Whether to extract clean text content
            include_links: Whether to include found links
            
        Returns:
            Dictionary with url, status, content, metadata, etc.
        """
        result = {
            'url': url,
            'success': False,
            'status_code': None,
            'content_type': None,
            'title': None,
            'text': None,
            'html': None,
            'links': [],
            'metadata': {},
            'error': None,
            'timestamp': time.time()
        }
        
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                result['error'] = "Invalid URL format"
                return result
            
            if parsed.scheme not in ['http', 'https']:
                result['error'] = "Only HTTP/HTTPS URLs are supported"
                return result
            
            # Fetch content
            response = self.session.get(
                url, 
                timeout=self.timeout,
                stream=True,
                allow_redirects=True
            )
            
            result['status_code'] = response.status_code
            result['content_type'] = response.headers.get('content-type', '').lower()
            
            if response.status_code != 200:
                result['error'] = f"HTTP {response.status_code}: {response.reason}"
                return result
            
            # Check content length
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.max_content_length:
                result['error'] = f"Content too large: {content_length} bytes"
                return result
            
            # Read content with size limit
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.max_content_length:
                    result['error'] = f"Content exceeds size limit: {len(content)} bytes"
                    return result
            
            # Decode content
            try:
                html_content = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    html_content = content.decode('latin-1')
                except UnicodeDecodeError:
                    result['error'] = "Cannot decode content as text"
                    return result
            
            result['html'] = html_content
            
            # Parse HTML if it's HTML content
            if 'text/html' in result['content_type']:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extract title
                title_tag = soup.find('title')
                if title_tag:
                    result['title'] = title_tag.get_text().strip()
                
                # Extract clean text
                if extract_text:
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    # Get text content
                    text = soup.get_text()
                    
                    # Clean up whitespace
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    result['text'] = '\n'.join(chunk for chunk in chunks if chunk)
                
                # Extract links
                if include_links:
                    links = []
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            href = urljoin(url, href)
                        elif not href.startswith(('http://', 'https://')):
                            continue
                        
                        links.append({
                            'url': href,
                            'text': link.get_text().strip(),
                            'title': link.get('title', '')
                        })
                    result['links'] = links[:50]  # Limit to first 50 links
                
                # Extract metadata
                result['metadata'] = {
                    'word_count': len(result['text'].split()) if result['text'] else 0,
                    'char_count': len(result['text']) if result['text'] else 0,
                    'link_count': len(result['links']),
                    'final_url': response.url,  # After redirects
                    'encoding': response.encoding
                }
            
            else:
                # Non-HTML content
                result['text'] = html_content
                result['metadata'] = {
                    'content_length': len(html_content),
                    'final_url': response.url,
                    'encoding': response.encoding
                }
            
            result['success'] = True
            
        except requests.RequestException as e:
            result['error'] = f"Request failed: {str(e)}"
        except Exception as e:
            result['error'] = f"Unexpected error: {str(e)}"
        
        return result
    
    def fetch_multiple(self, urls: List[str], delay: float = 1.0) -> List[Dict[str, Any]]:
        """Fetch multiple URLs with delay between requests"""
        results = []
        
        for i, url in enumerate(urls):
            result = self.fetch(url)
            results.append(result)
            
            # Add delay between requests (except for the last one)
            if i < len(urls) - 1:
                time.sleep(delay)
        
        return results


class ToolRegistry:
    """Registry for available tools"""
    
    def __init__(self):
        """Initialize tool registry"""
        self.tools = {}
        self.web_fetch = WebFetchTool()
        
        # Register built-in tools
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register built-in tools"""
        self.tools['web.fetch'] = {
            'name': 'web.fetch',
            'description': 'Fetch content from a web URL',
            'parameters': {
                'url': {'type': 'string', 'required': True, 'description': 'URL to fetch'},
                'extract_text': {'type': 'boolean', 'default': True, 'description': 'Extract clean text'},
                'include_links': {'type': 'boolean', 'default': False, 'description': 'Include found links'}
            },
            'handler': self._handle_web_fetch
        }
    
    def _handle_web_fetch(self, **kwargs) -> Dict[str, Any]:
        """Handle web.fetch tool calls"""
        url = kwargs.get('url')
        if not url:
            return {'success': False, 'error': 'URL parameter is required'}
        
        extract_text = kwargs.get('extract_text', True)
        include_links = kwargs.get('include_links', False)
        
        return self.web_fetch.fetch(
            url=url,
            extract_text=extract_text,
            include_links=include_links
        )
    
    def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool definition by name"""
        return self.tools.get(tool_name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        return list(self.tools.values())
    
    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Call a tool by name with parameters"""
        tool = self.get_tool(tool_name)
        if not tool:
            return {'success': False, 'error': f'Tool not found: {tool_name}'}
        
        try:
            handler = tool['handler']
            return handler(**kwargs)
        except Exception as e:
            return {'success': False, 'error': f'Tool execution failed: {str(e)}'}


def main():
    """CLI interface for testing tools"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test BrainFoundryOS brain layer tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch a web page
  python scripts/tools.py web.fetch --url https://example.com
  
  # Fetch with links included
  python scripts/tools.py web.fetch --url https://example.com --include-links
  
  # List available tools
  python scripts/tools.py list
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List tools command
    list_parser = subparsers.add_parser('list', help='List available tools')
    
    # Web fetch command
    fetch_parser = subparsers.add_parser('web.fetch', help='Fetch web content')
    fetch_parser.add_argument('--url', required=True, help='URL to fetch')
    fetch_parser.add_argument('--include-links', action='store_true', help='Include found links')
    fetch_parser.add_argument('--no-text', action='store_true', help='Skip text extraction')
    fetch_parser.add_argument('--output', help='Save result to JSON file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    registry = ToolRegistry()
    
    if args.command == 'list':
        tools = registry.list_tools()
        print(f"Available tools ({len(tools)}):")
        for tool in tools:
            print(f"  {tool['name']}: {tool['description']}")
            for param_name, param_info in tool['parameters'].items():
                required = " (required)" if param_info.get('required') else ""
                default = f" [default: {param_info.get('default')}]" if 'default' in param_info else ""
                print(f"    --{param_name}: {param_info['description']}{required}{default}")
    
    elif args.command == 'web.fetch':
        print(f"🌐 Fetching: {args.url}")
        
        result = registry.call_tool(
            'web.fetch',
            url=args.url,
            extract_text=not args.no_text,
            include_links=args.include_links
        )
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"💾 Result saved to: {args.output}")
        else:
            # Pretty print result
            if result['success']:
                print(f"✅ Success: {result['status_code']} {result['content_type']}")
                if result['title']:
                    print(f"📄 Title: {result['title']}")
                
                if result['text']:
                    text_preview = result['text'][:500]
                    if len(result['text']) > 500:
                        text_preview += "..."
                    print(f"📝 Text preview:\n{text_preview}")
                
                if result['links']:
                    print(f"🔗 Found {len(result['links'])} links:")
                    for link in result['links'][:5]:
                        print(f"   {link['text'][:50]} -> {link['url']}")
                
                metadata = result['metadata']
                print(f"📊 Metadata: {json.dumps(metadata, indent=2)}")
            else:
                print(f"❌ Failed: {result['error']}")
                sys.exit(1)


if __name__ == "__main__":
    main()
