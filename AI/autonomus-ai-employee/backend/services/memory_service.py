from embeddings.embedder import embed_text
from db.memory_repo import insert_memory, search_memory


def store_memory(content: str, mem_type="general", task_id=None):
    emb = embed_text(content)
    insert_memory(content, emb, mem_type, task_id)


def recall_memory(text: str, limit=5):
    emb = embed_text(text, is_query=True)
    # Direct return karo, string mein convert MAT karo yahan
    return search_memory(emb, limit)