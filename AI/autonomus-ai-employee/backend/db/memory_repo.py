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

    cur.execute("""
        SELECT content
        FROM agent_memory
        ORDER BY embedding <-> %s::vector
        LIMIT %s
        """, (embedding, limit))


    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [r[0] for r in rows]
