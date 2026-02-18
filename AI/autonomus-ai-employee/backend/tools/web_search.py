from ddgs import DDGS

def web_search_tool(query: str) -> str:
    """
    Real web search using DDGS (official new package).
    """
    print(f"[TOOL] 🌐 Web search running: {query}")

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(r["body"])

        if not results:
            return "No results found."

        return "\n".join(results)

    except Exception as e:
        return f"Web search error: {str(e)}"
    

