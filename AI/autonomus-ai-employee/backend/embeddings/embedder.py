import json
import importlib
import os
import urllib.error
import urllib.request
import ollama


# Keep in sync with pgvector schema (vector(1536))
OUTPUT_DIM = 1536

# Ollama defaults
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:4b")

# Gemini defaults
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")


def _get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _normalize_dim(vector):
    values = [float(v) for v in vector]
    if len(values) >= OUTPUT_DIM:
        return values[:OUTPUT_DIM]
    return values + [0.0] * (OUTPUT_DIM - len(values))


def _embed_with_ollama(text: str, is_query: bool = False):
    ollama = importlib.import_module("ollama")

    instruction = "Represent this query for retrieving relevant documents: " if is_query else ""
    response = ollama.embeddings(
        model=OLLAMA_EMBED_MODEL,
        prompt=instruction + text,
    )
    embedding = response.get("embedding")
    if not embedding:
        raise RuntimeError("Ollama embedding response missing 'embedding'")
    return _normalize_dim(embedding)


def _embed_with_gemini(text: str, is_query: bool = False):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    payload = {
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
        "outputDimensionality": OUTPUT_DIM,
    }

    candidate_models = [GEMINI_EMBED_MODEL]
    if GEMINI_EMBED_MODEL != "gemini-embedding-001":
        candidate_models.append("gemini-embedding-001")

    last_error = None
    raw = ""
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as http_err:
            last_error = http_err
            if http_err.code == 404:
                continue
            raise

    if not raw:
        if last_error:
            raise last_error
        raise RuntimeError("Gemini embedding request failed")

    parsed = json.loads(raw)
    embedding = parsed.get("embedding", {}).get("values")
    if not embedding:
        raise RuntimeError("Gemini embedding response missing 'embedding.values'")
    return _normalize_dim(embedding)


def embed_text(text: str, is_query: bool = False):
    """
    Generate 1536-dim embeddings for pgvector.
    Respects LLM_PROVIDER from env: gemini or ollama.
    """
    provider = _get_provider()
    if provider == "gemini":
        return _embed_with_gemini(text, is_query=is_query)
    return _embed_with_ollama(text, is_query=is_query)