import chromadb
from sentence_transformers import SentenceTransformer

# init embedding model
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# create local db
client = chromadb.Client()
collection = client.create_collection("memory")

def store_memory(text):
    embedding = embed_model.encode(text).tolist()
    collection.add(
        embeddings=[embedding],
        documents=[text],
        ids=[str(hash(text))]
    )

def recall_memory(query):
    embedding = embed_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=2
    )

    if results["documents"]:
        return "\n".join(results["documents"][0])
    return ""
