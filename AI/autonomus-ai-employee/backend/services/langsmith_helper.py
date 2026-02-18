import os


def init_langsmith_tracing() -> None:
    """
    Enable LangSmith tracing only when API key is present.
    Safe no-op if key is missing.
    """
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        return

    # New env names
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGSMITH_PROJECT", "autonomous_ai")

    # Backward compatibility with older LangChain tracing flag
    os.environ["LANGCHAIN_TRACING_V2"] = "true"