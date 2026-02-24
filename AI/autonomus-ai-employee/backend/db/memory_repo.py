import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DB_URL)


def insert_memory(content, embedding, mem_type, task_id=None):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO agent_memory (content, embedding, type, task_id)
        VALUES (%s, %s, %s, %s)
    """, (content, embedding, mem_type, task_id))

    conn.commit()
    cur.close()
    conn.close()


def search_memory(embedding, limit=5):
    conn = get_conn()
    cur = conn.cursor()

    # COUNT: 1st %s (Select), 2nd %s (Order By), 3rd %s (Limit)
    query = """
        SELECT content, (embedding <=> %s::vector) AS distance
        FROM agent_memory
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    
    # BSDK yahan 3 items bhejni hain kyunki upar 3 placeholders hain!
    params = (embedding, embedding, int(limit))
    
    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [(str(r[0]), float(r[1])) for r in rows]
    except Exception as e:
        print(f"❌ SQL Error: {e}")
        return []
    finally:
        cur.close()
        conn.close()

# Paginated thread/session listing
def list_threads(offset=0, limit=20):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT task_id
        FROM agent_memory
        WHERE task_id IS NOT NULL
        GROUP BY task_id
        ORDER BY MAX(id) DESC
        OFFSET %s LIMIT %s
    """
    try:
        cur.execute(query, (offset, limit))
        rows = cur.fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception as e:
        print(f"❌ SQL Error (list_threads): {e}")
        return []
    finally:
        cur.close()
        conn.close()
