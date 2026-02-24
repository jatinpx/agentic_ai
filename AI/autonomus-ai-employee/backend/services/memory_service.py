from embeddings.embedder import embed_text
from db.memory_repo import insert_memory, search_memory, list_threads
def get_threads_paginated(offset=0, limit=20):
    return list_threads(offset, limit)


def store_memory(content: str, mem_type="general", task_id=None):
    emb = embed_text(content)
    insert_memory(content, emb, mem_type, task_id)


def recall_memory(text: str, limit=5):
    emb = embed_text(text, is_query=True)
    # Direct return karo, string mein convert MAT karo yahan
    return search_memory(emb, limit)