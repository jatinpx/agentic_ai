from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("BAAI/bge-base-en-v1.5")
    return _model

def embed_text(text: str):
    model = get_model()
    return model.encode(text).tolist()
