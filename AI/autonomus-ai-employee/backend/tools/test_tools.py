from tools.registry import execute_tool

print("WEB SEARCH TEST:\n")
print(execute_tool("web_search", "latest nvidia gpu"))

print("\nPYTHON EXEC TEST:\n")
print(execute_tool("python_exec", "print(5+5)"))
