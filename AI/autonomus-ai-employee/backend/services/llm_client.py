import json
import os
import urllib.request
from typing import Any, Dict, List, Optional


def _get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _normalize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            role = "user"
            content = f"SYSTEM:\n{content}"
        elif role not in ("user", "assistant"):
            role = "user"
        normalized.append({"role": role, "content": content})
    return normalized


def _gemini_chat(messages: List[Dict[str, str]], model: Optional[str]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model_name = model if model and model.startswith("gemini") else os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    contents = []
    for msg in _normalize_messages(messages):
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {"contents": contents}
    data = json.dumps(payload).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8")

    parsed = json.loads(raw)
    candidates = parsed.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned empty content")

    return parts[0].get("text", "")


def _ollama_chat(messages: List[Dict[str, str]], model: Optional[str]) -> str:
    import ollama

    use_model = model or os.getenv("OLLAMA_MODEL_DEFAULT", "qwen2.5:7b-instruct")
    response = ollama.chat(model=use_model, messages=_normalize_messages(messages))
    return response["message"]["content"]


def chat(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    provider = _get_provider()
    if provider == "gemini":
        return _gemini_chat(messages, model)
    return _ollama_chat(messages, model)
