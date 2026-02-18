import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def tavily_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using Tavily API.
    
    Args:
        query: Search query string
        max_results: Max number of results to return
        
    Returns:
        Formatted search results as string
    """
    try:
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced"  # or "basic" for faster results
        )
        
        results = []
        for idx, result in enumerate(response.get("results", []), 1):
            results.append(
                f"{idx}. [{result['title']}]({result['url']})\n"
                f"   {result['content']}\n"
            )
        
        return "\n".join(results) if results else "No results found."
        
    except Exception as e:
        return f"Tavily search error: {str(e)}"