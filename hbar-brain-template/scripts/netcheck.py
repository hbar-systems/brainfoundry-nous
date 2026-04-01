#!/usr/bin/env python3
"""
Network connectivity checker for Ollama service
Uses httpx for async HTTP requests with proper timeout handling
"""
import asyncio
import json
import os
import sys
import httpx

async def check_ollama(url: str, timeout: float = 3.0) -> dict:
    """Check Ollama service health"""
    result = {
        "endpoint": url,
        "status": "unknown",
        "models": 0,
        "error": None,
        "response_time_ms": None
    }
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            import time
            start = time.time()
            response = await client.get(f"{url}/api/tags")
            end = time.time()
            
            result["response_time_ms"] = round((end - start) * 1000, 2)
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                result.update({
                    "status": "healthy",
                    "models": len(models),
                    "error": None
                })
            else:
                result.update({
                    "status": "error",
                    "error": f"HTTP {response.status_code}"
                })
                
    except httpx.TimeoutException:
        result.update({
            "status": "timeout",
            "error": f"Connection timeout ({timeout}s)"
        })
    except httpx.ConnectError:
        result.update({
            "status": "unreachable",
            "error": "Connection refused"
        })
    except Exception as e:
        result.update({
            "status": "error",
            "error": str(e)
        })
    
    return result

async def main():
    """Main function"""
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    timeout = float(os.getenv("TIMEOUT", "3.0"))
    
    if len(sys.argv) > 1:
        ollama_url = sys.argv[1]
    
    print(f"Checking Ollama at: {ollama_url}")
    result = await check_ollama(ollama_url, timeout)
    
    # Pretty print result
    print(json.dumps(result, indent=2))
    
    # Exit with appropriate code
    if result["status"] == "healthy":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
