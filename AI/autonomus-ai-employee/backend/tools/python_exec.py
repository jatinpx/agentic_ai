import io
import sys
import traceback

def python_exec_tool(code: str) -> str:
    print("[TOOL] 🐍 Executing Python code")

    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()

    try:
        exec(code, {})
        output = buffer.getvalue()
        return output if output else "Code executed successfully."
    except Exception:
        return traceback.format_exc()
    finally:
        sys.stdout = old_stdout
