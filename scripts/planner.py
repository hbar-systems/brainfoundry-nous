#!/usr/bin/env python3
"""
BrainFoundryOS brain layer: Simple plan → act → verify loop
Basic query routing and tool orchestration for the brain layer
"""

import os
import sys
import json
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from scripts.tools import ToolRegistry
from extensions.brain.semantic_db import SemanticDB

# Default values from environment
DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_MODEL = "mistral:7b"

class SimplePlanner:
    """Simple planner with plan → act → verify loop"""
    
    def __init__(self, api_base: str = None, default_model: str = None):
        """Initialize planner with API and tools"""
        self.api_base = api_base or os.getenv("API_BASE", DEFAULT_API_BASE)
        self.default_model = default_model or os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)
        self.tools = ToolRegistry()
        self.semantic_db = SemanticDB()
        
        # API endpoints
        self.search_url = f"{self.api_base}/documents/search"
        self.rag_url = f"{self.api_base}/chat/rag"
        self.health_url = f"{self.api_base}/health"
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze query to determine intent and routing
        
        Returns:
            Dictionary with intent, confidence, and suggested actions
        """
        query_lower = query.lower().strip()
        
        # URL detection patterns
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, query)
        
        # Intent classification (simple keyword-based)
        intents = {
            'web_fetch': {
                'keywords': ['fetch', 'get', 'download', 'scrape', 'url', 'website', 'web'],
                'patterns': [r'fetch\s+https?://', r'get\s+https?://', r'download\s+https?://'],
                'confidence': 0.0
            },
            'document_search': {
                'keywords': ['search', 'find', 'look for', 'documents', 'files', 'papers'],
                'patterns': [r'search\s+for', r'find\s+documents', r'look\s+for'],
                'confidence': 0.0
            },
            'rag_query': {
                'keywords': ['what', 'how', 'why', 'explain', 'summarize', 'tell me', 'about'],
                'patterns': [r'what\s+is', r'how\s+does', r'explain\s+', r'summarize\s+'],
                'confidence': 0.0
            },
            'entity_search': {
                'keywords': ['entity', 'entities', 'person', 'people', 'concept', 'relation'],
                'patterns': [r'who\s+is', r'entities\s+related', r'find\s+person'],
                'confidence': 0.0
            }
        }
        
        # Calculate confidence scores
        for intent_name, intent_data in intents.items():
            score = 0.0
            
            # Keyword matching
            for keyword in intent_data['keywords']:
                if keyword in query_lower:
                    score += 0.3
            
            # Pattern matching
            for pattern in intent_data['patterns']:
                if re.search(pattern, query_lower):
                    score += 0.5
            
            intent_data['confidence'] = min(score, 1.0)
        
        # Special cases
        if urls:
            intents['web_fetch']['confidence'] = max(intents['web_fetch']['confidence'], 0.8)
        
        # Find highest confidence intent
        best_intent = max(intents.items(), key=lambda x: x[1]['confidence'])
        
        return {
            'query': query,
            'urls_found': urls,
            'primary_intent': best_intent[0],
            'confidence': best_intent[1]['confidence'],
            'all_intents': {name: data['confidence'] for name, data in intents.items()},
            'suggested_actions': self._suggest_actions(best_intent[0], query, urls)
        }
    
    def _suggest_actions(self, intent: str, query: str, urls: List[str]) -> List[Dict[str, Any]]:
        """Suggest actions based on intent analysis"""
        actions = []
        
        if intent == 'web_fetch' and urls:
            for url in urls:
                actions.append({
                    'type': 'tool_call',
                    'tool': 'web.fetch',
                    'parameters': {'url': url, 'extract_text': True},
                    'description': f'Fetch content from {url}'
                })
        
        elif intent == 'document_search':
            actions.append({
                'type': 'api_call',
                'endpoint': 'documents/search',
                'parameters': {'query': query, 'limit': 5},
                'description': f'Search documents for: {query}'
            })
        
        elif intent == 'rag_query':
            actions.append({
                'type': 'api_call',
                'endpoint': 'chat/rag',
                'parameters': {
                    'messages': [{'role': 'user', 'content': query}],
                    'model': self.default_model
                },
                'description': f'RAG query: {query}'
            })
        
        elif intent == 'entity_search':
            actions.append({
                'type': 'semantic_search',
                'parameters': {'query': query},
                'description': f'Search entities for: {query}'
            })
        
        # Always add fallback RAG query if confidence is low
        if not actions or max(action.get('confidence', 0) for action in [{'confidence': 0.5}]) < 0.6:
            actions.append({
                'type': 'api_call',
                'endpoint': 'chat/rag',
                'parameters': {
                    'messages': [{'role': 'user', 'content': query}],
                    'model': self.default_model
                },
                'description': f'Fallback RAG query: {query}',
                'fallback': True
            })
        
        return actions
    
    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return result"""
        action_type = action['type']
        
        try:
            if action_type == 'tool_call':
                tool_name = action['tool']
                parameters = action.get('parameters', {})
                result = self.tools.call_tool(tool_name, **parameters)
                
                return {
                    'action': action,
                    'success': result.get('success', False),
                    'result': result,
                    'summary': self._summarize_tool_result(tool_name, result)
                }
            
            elif action_type == 'api_call':
                endpoint = action['endpoint']
                parameters = action.get('parameters', {})
                
                if endpoint == 'documents/search':
                    response = requests.post(self.search_url, json=parameters, timeout=30)
                elif endpoint == 'chat/rag':
                    response = requests.post(self.rag_url, json=parameters, timeout=120)
                else:
                    return {
                        'action': action,
                        'success': False,
                        'error': f'Unknown endpoint: {endpoint}'
                    }
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        'action': action,
                        'success': True,
                        'result': result,
                        'summary': self._summarize_api_result(endpoint, result)
                    }
                else:
                    return {
                        'action': action,
                        'success': False,
                        'error': f'API call failed: {response.status_code}',
                        'response_text': response.text
                    }
            
            elif action_type == 'semantic_search':
                parameters = action.get('parameters', {})
                query = parameters.get('query', '')
                
                entities = self.semantic_db.search_entities(query=query, limit=10)
                
                return {
                    'action': action,
                    'success': True,
                    'result': {'entities': entities},
                    'summary': f'Found {len(entities)} entities matching "{query}"'
                }
            
            else:
                return {
                    'action': action,
                    'success': False,
                    'error': f'Unknown action type: {action_type}'
                }
        
        except Exception as e:
            return {
                'action': action,
                'success': False,
                'error': f'Action execution failed: {str(e)}'
            }
    
    def _summarize_tool_result(self, tool_name: str, result: Dict[str, Any]) -> str:
        """Create human-readable summary of tool result"""
        if not result.get('success'):
            return f"Tool {tool_name} failed: {result.get('error', 'Unknown error')}"
        
        if tool_name == 'web.fetch':
            title = result.get('title', 'No title')
            word_count = result.get('metadata', {}).get('word_count', 0)
            return f"Fetched '{title}' ({word_count} words)"
        
        return f"Tool {tool_name} completed successfully"
    
    def _summarize_api_result(self, endpoint: str, result: Dict[str, Any]) -> str:
        """Create human-readable summary of API result"""
        if endpoint == 'documents/search':
            count = result.get('results_count', 0)
            return f"Found {count} relevant documents"
        
        elif endpoint == 'chat/rag':
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            word_count = len(content.split()) if content else 0
            sources = result.get('rag_metadata', {}).get('sources', [])
            return f"RAG response ({word_count} words, {len(sources)} sources)"
        
        return "API call completed"
    
    def plan_and_execute(self, query: str, max_actions: int = 3) -> Dict[str, Any]:
        """
        Main planning loop: analyze → plan → act → verify
        
        Args:
            query: User query to process
            max_actions: Maximum number of actions to execute
            
        Returns:
            Complete execution result with analysis, actions, and results
        """
        print(f"🧠 Planning for query: {query}")
        
        # Step 1: Analyze query
        analysis = self.analyze_query(query)
        print(f"📊 Intent: {analysis['primary_intent']} (confidence: {analysis['confidence']:.2f})")
        
        # Step 2: Plan actions
        actions = analysis['suggested_actions'][:max_actions]
        print(f"📋 Planned {len(actions)} actions:")
        for i, action in enumerate(actions, 1):
            print(f"   {i}. {action['description']}")
        
        # Step 3: Execute actions
        results = []
        for i, action in enumerate(actions, 1):
            print(f"\n⚡ Executing action {i}/{len(actions)}: {action['description']}")
            
            result = self.execute_action(action)
            results.append(result)
            
            if result['success']:
                print(f"   ✅ {result['summary']}")
            else:
                print(f"   ❌ {result.get('error', 'Unknown error')}")
                
                # Stop on critical failures (unless it's a fallback)
                if not action.get('fallback', False):
                    print("   🛑 Stopping execution due to failure")
                    break
        
        # Step 4: Compile final result
        successful_results = [r for r in results if r['success']]
        
        execution_result = {
            'query': query,
            'analysis': analysis,
            'actions_planned': len(actions),
            'actions_executed': len(results),
            'successful_actions': len(successful_results),
            'results': results,
            'summary': self._create_final_summary(query, analysis, results)
        }
        
        print(f"\n📄 Execution complete: {len(successful_results)}/{len(results)} actions successful")
        
        return execution_result
    
    def _create_final_summary(self, query: str, analysis: Dict[str, Any], 
                            results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create final summary of execution"""
        successful_results = [r for r in results if r['success']]
        
        # Extract key information from successful results
        content_pieces = []
        sources = []
        
        for result in successful_results:
            action_type = result['action']['type']
            
            if action_type == 'tool_call' and result['action']['tool'] == 'web.fetch':
                web_result = result['result']
                if web_result.get('text'):
                    content_pieces.append({
                        'type': 'web_content',
                        'source': web_result['url'],
                        'title': web_result.get('title', 'Web Page'),
                        'text': web_result['text'][:1000] + "..." if len(web_result['text']) > 1000 else web_result['text']
                    })
                    sources.append(web_result['url'])
            
            elif action_type == 'api_call':
                if result['action']['endpoint'] == 'documents/search':
                    search_result = result['result']
                    for doc in search_result.get('results', []):
                        content_pieces.append({
                            'type': 'document',
                            'source': doc['document_name'],
                            'text': doc['content'][:500] + "..." if len(doc['content']) > 500 else doc['content'],
                            'similarity': doc.get('similarity_score', 0)
                        })
                        sources.append(doc['document_name'])
                
                elif result['action']['endpoint'] == 'chat/rag':
                    rag_result = result['result']
                    choices = rag_result.get('choices', [])
                    if choices:
                        content_pieces.append({
                            'type': 'rag_response',
                            'text': choices[0]['message']['content'],
                            'sources': rag_result.get('rag_metadata', {}).get('sources', [])
                        })
            
            elif action_type == 'semantic_search':
                entities = result['result'].get('entities', [])
                if entities:
                    content_pieces.append({
                        'type': 'entities',
                        'entities': [{'name': e['name'], 'type': e['type']} for e in entities[:5]]
                    })
        
        return {
            'intent': analysis['primary_intent'],
            'confidence': analysis['confidence'],
            'success_rate': len(successful_results) / len(results) if results else 0,
            'content_pieces': content_pieces,
            'sources': list(set(sources)),
            'total_sources': len(set(sources))
        }


def main():
    """CLI interface for the planner"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="BrainFoundryOS brain layer planner - plan → act → verify loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # RAG query
  python scripts/planner.py "summarize my notes on VQE"
  
  # Web fetch
  python scripts/planner.py "fetch https://example.com"
  
  # Document search
  python scripts/planner.py "find documents about quantum computing"
  
  # Entity search
  python scripts/planner.py "who is mentioned in my research notes?"
  
  # Analysis only (no execution)
  python scripts/planner.py "what is quantum entanglement?" --analyze-only
        """
    )
    
    parser.add_argument(
        'query',
        help='Query to process'
    )
    
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only analyze the query, do not execute actions'
    )
    
    parser.add_argument(
        '--max-actions',
        type=int,
        default=3,
        help='Maximum number of actions to execute (default: 3)'
    )
    
    parser.add_argument(
        '--api-base',
        default=None,
        help=f'API base URL (default: {DEFAULT_API_BASE} or API_BASE env var)'
    )
    
    parser.add_argument(
        '--output',
        help='Save full result to JSON file'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed execution information'
    )
    
    args = parser.parse_args()
    
    try:
        planner = SimplePlanner(api_base=args.api_base)
        
        if args.analyze_only:
            # Analysis only
            analysis = planner.analyze_query(args.query)
            
            print(f"Query Analysis:")
            print(f"  Primary Intent: {analysis['primary_intent']} (confidence: {analysis['confidence']:.2f})")
            print(f"  URLs Found: {len(analysis['urls_found'])}")
            if analysis['urls_found']:
                for url in analysis['urls_found']:
                    print(f"    {url}")
            
            print(f"  All Intents:")
            for intent, confidence in analysis['all_intents'].items():
                print(f"    {intent}: {confidence:.2f}")
            
            print(f"  Suggested Actions ({len(analysis['suggested_actions'])}):")
            for i, action in enumerate(analysis['suggested_actions'], 1):
                print(f"    {i}. {action['description']}")
        
        else:
            # Full execution
            result = planner.plan_and_execute(args.query, max_actions=args.max_actions)
            
            # Show summary
            summary = result['summary']
            print(f"\n📋 Final Summary:")
            print(f"   Intent: {summary['intent']} (confidence: {summary['confidence']:.2f})")
            print(f"   Success Rate: {summary['success_rate']:.1%}")
            print(f"   Sources: {summary['total_sources']}")
            
            # Show content pieces
            if summary['content_pieces']:
                print(f"\n📄 Content Retrieved:")
                for i, piece in enumerate(summary['content_pieces'], 1):
                    if piece['type'] == 'rag_response':
                        print(f"   {i}. RAG Response:")
                        print(f"      {piece['text'][:200]}...")
                    elif piece['type'] == 'web_content':
                        print(f"   {i}. Web: {piece['title']}")
                        print(f"      {piece['text'][:200]}...")
                    elif piece['type'] == 'document':
                        print(f"   {i}. Document: {piece['source']}")
                        print(f"      {piece['text'][:200]}...")
                    elif piece['type'] == 'entities':
                        entities_str = ", ".join([f"{e['name']} ({e['type']})" for e in piece['entities']])
                        print(f"   {i}. Entities: {entities_str}")
            
            # Save to file if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"\n💾 Full result saved to: {args.output}")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Execution cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
