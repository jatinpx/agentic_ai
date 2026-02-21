import os
from typing import Optional, Dict, Any
from tavily import TavilyClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize client globally or within a class for better resource management
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY not found in environment variables.")

client = TavilyClient(api_key=TAVILY_API_KEY)


def tavily_search_structured(query: str, max_results: int = 20) -> Dict[str, Any]:
    """
    Structured Tavily response for downstream claim extraction and verification.
    """
    try:
        response = client.search(
            query=query,
            max_results=min(max_results, 20),
            search_depth="advanced",
            include_raw_content=False,
        )

        results_list = response.get("results", []) or []
        normalized = []
        for result in results_list:
            normalized.append({
                "title": result.get("title", "No Title"),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "published_date": result.get("published_date") or result.get("date") or "",
                "source": result.get("source") or "",
            })

        return {
            "query": query,
            "results": normalized,
            "count": len(normalized),
            "error": "",
        }
    except Exception as e:
        return {
            "query": query,
            "results": [],
            "count": 0,
            "error": str(e),
        }

def tavily_search(query: str, max_results: int = 20) -> str:
    """
    Performs an advanced web search using Tavily.
    
    Args:
        query: The search string.
        max_results: Max results to return (Tavily's current max is 20 per request).
        
    Returns:
        A formatted string of titles, URLs, and content snippets.
    """
    try:
        # 'advanced' search depth provides higher quality/more context
        structured = tavily_search_structured(query=query, max_results=max_results)
        if structured.get("error"):
            return f"⚠️ Tavily Search Error: {structured.get('error')}"

        results_list = structured.get("results", [])
        if not results_list:
            return f"No relevant results found for: '{query}'"
        
        formatted_output = [f"### Search Results for: {query}\n"]
        
        for idx, result in enumerate(results_list, 1):
            title = result.get('title', 'No Title')
            url = result.get('url', '#')
            content = result.get('content', 'No content snippet available.')
            
            formatted_output.append(f"{idx}. **[{title}]({url})**")
            formatted_output.append(f"   {content}\n")
            
        return "\n".join(formatted_output)
        
    except Exception as e:
        # Log the error more specifically in a real app
        return f"⚠️ Tavily Search Error: {e}"

# Example Usage:
# print(tavily_search("Latest developments in Sarvam AI 2026", max_results=20))