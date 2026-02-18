# from sentence_transformers import SentenceTransformer

# _model = None

# def get_model():
#     global _model
#     if _model is None:
#         _model = SentenceTransformer("BAAI/bge-base-en-v1.5")
#     return _model

# def embed_text(text: str):
#     model = get_model()
#     return model.encode(text).tolist()


import ollama

_model_name = "qwen3-embedding:4b"
# Truncate to 1536 to stay under pgvector's HNSW 2000-dim limit
OUTPUT_DIM = 1536 

def embed_text(text: str, is_query: bool = False):
    """
    Generates truncated Qwen3 embeddings compatible with pgvector HNSW.
    """
    # Adding instructions significantly improves Qwen3's retrieval performance
    instruction = "Represent this query for retrieving relevant documents: " if is_query else ""
    
    response = ollama.embeddings(
        model=_model_name,
        prompt=instruction + text
    )
    
    # Truncate the 2560-dim vector to 1536
    return response['embedding'][:OUTPUT_DIM]