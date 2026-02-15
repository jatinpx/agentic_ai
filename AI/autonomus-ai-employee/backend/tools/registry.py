"""
Central Tool Registry
"""

from typing import Dict, Callable

from tools.web_search import web_search_tool
from tools.python_exec import python_exec_tool

# ==========================================
# TOOL REGISTRY
# ==========================================
TOOLS: Dict[str, Callable] = {
    "web_search": web_search_tool,
    "python_exec": python_exec_tool,
}

# ==========================================
# GET TOOL
# ==========================================
def get_tool(tool_name: str):
    return TOOLS.get(tool_name)


# ==========================================
# LIST TOOLS (MAIN)
# ==========================================
def list_available_tools():
    """Used by agent brain"""
    return list(TOOLS.keys())


# optional alias if you still use list_tools somewhere
def list_tools():
    return list_available_tools()


# ==========================================
# EXECUTE TOOL
# ==========================================
def execute_tool(tool_name: str, tool_input: str) -> str:
    tool = get_tool(tool_name)

    if not tool:
        return f"[ERROR] Tool '{tool_name}' not found."

    try:
        result = tool(tool_input)

        if result is None:
            return "[INFO] Tool returned empty result."

        return str(result)

    except Exception as e:
        return f"[ERROR executing {tool_name}] {str(e)}"
