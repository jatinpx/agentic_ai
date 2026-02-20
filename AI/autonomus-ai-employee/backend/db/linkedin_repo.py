import os
import uuid
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DB_URL)


def _to_vector_literal(embedding):
    """Convert a Python embedding list into pgvector literal format: [0.1,0.2,...]."""
    if embedding is None:
        return None
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


# ==========================================
# TABLE CREATION
# ==========================================

def create_linkedin_tables():
    """Create linkedin_posts and linkedin_viral_templates tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Ensure pgvector extension
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_posts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                content TEXT NOT NULL,
                hook TEXT,
                cta TEXT,
                hashtags TEXT[],
                embedding vector(1536),
                viral_score FLOAT,
                tone TEXT,
                audience TEXT,
                topic TEXT,
                status TEXT DEFAULT 'draft',
                publish_url TEXT,
                reasoning TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_viral_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                content TEXT,
                hook_pattern TEXT,
                category TEXT,
                embedding vector(1536),
                engagement_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        conn.commit()
        print("LinkedIn tables created successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error creating LinkedIn tables: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ==========================================
# LINKEDIN POSTS CRUD
# ==========================================

def insert_post(content, hook, cta, hashtags, embedding, viral_score,
                tone, audience, topic, reasoning, status="draft"):
    """Insert a generated LinkedIn post into the database."""
    conn = get_conn()
    cur = conn.cursor()
    post_id = str(uuid.uuid4())

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute("""
            INSERT INTO linkedin_posts
                (id, content, hook, cta, hashtags, embedding, viral_score,
                 tone, audience, topic, reasoning, status)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            post_id, content, hook, cta, hashtags, vector_literal, viral_score,
            tone, audience, topic, reasoning, status
        ))
        conn.commit()
        return post_id
    except Exception as e:
        conn.rollback()
        print(f"Error inserting LinkedIn post: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def search_similar_posts(embedding, limit=5):
    """Search linkedin_posts by embedding similarity (cosine distance)."""
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT id, content, hook, cta, viral_score,
               (embedding <=> %s::vector) AS distance
        FROM linkedin_posts
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute(query, (vector_literal, vector_literal, int(limit)))
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "hook": r[2],
                "cta": r[3],
                "viral_score": float(r[4]) if r[4] else 0.0,
                "distance": float(r[5]),
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Error searching similar posts: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def get_top_posts(limit=5, min_score=7.0):
    """Get highest-scoring posts from the database."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, content, hook, cta, viral_score, topic
            FROM linkedin_posts
            WHERE viral_score >= %s
            ORDER BY viral_score DESC, created_at DESC
            LIMIT %s
        """, (min_score, int(limit)))
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "hook": r[2],
                "cta": r[3],
                "viral_score": float(r[4]) if r[4] else 0.0,
                "topic": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Error getting top posts: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def get_all_posts(limit=50):
    """Get all posts ordered by creation date."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, content, hook, cta, hashtags, viral_score,
                   tone, audience, topic, status, publish_url,
                   reasoning, created_at
            FROM linkedin_posts
            ORDER BY created_at DESC
            LIMIT %s
        """, (int(limit),))
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "hook": r[2],
                "cta": r[3],
                "hashtags": r[4] or [],
                "viral_score": float(r[5]) if r[5] else 0.0,
                "tone": r[6],
                "audience": r[7],
                "topic": r[8],
                "status": r[9],
                "publish_url": r[10],
                "reasoning": r[11],
                "created_at": str(r[12]) if r[12] else None,
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Error getting all posts: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def get_post_by_id(post_id):
    """Get a single post by UUID."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, content, hook, cta, hashtags, viral_score,
                   tone, audience, topic, status, publish_url,
                   reasoning, created_at
            FROM linkedin_posts
            WHERE id = %s
        """, (post_id,))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": str(r[0]),
            "content": r[1],
            "hook": r[2],
            "cta": r[3],
            "hashtags": r[4] or [],
            "viral_score": float(r[5]) if r[5] else 0.0,
            "tone": r[6],
            "audience": r[7],
            "topic": r[8],
            "status": r[9],
            "publish_url": r[10],
            "reasoning": r[11],
            "created_at": str(r[12]) if r[12] else None,
        }
    except Exception as e:
        print(f"Error getting post: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def update_post_status(post_id, status, publish_url=None):
    """Update post status (draft → approved → published) and optionally set publish URL."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        if publish_url:
            cur.execute("""
                UPDATE linkedin_posts
                SET status = %s, publish_url = %s
                WHERE id = %s
            """, (status, publish_url, post_id))
        else:
            cur.execute("""
                UPDATE linkedin_posts
                SET status = %s
                WHERE id = %s
            """, (status, post_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error updating post status: {e}")
        return False
    finally:
        cur.close()
        conn.close()


# ==========================================
# VIRAL TEMPLATES CRUD
# ==========================================

def insert_viral_template(content, hook_pattern, category, embedding, engagement_score):
    """Insert a viral template for reference."""
    conn = get_conn()
    cur = conn.cursor()
    template_id = str(uuid.uuid4())

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute("""
            INSERT INTO linkedin_viral_templates
                (id, content, hook_pattern, category, embedding, engagement_score)
            VALUES (%s, %s, %s, %s, %s::vector, %s)
        """, (template_id, content, hook_pattern, category, vector_literal, engagement_score))
        conn.commit()
        return template_id
    except Exception as e:
        conn.rollback()
        print(f"Error inserting viral template: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def search_viral_templates(embedding, limit=5):
    """Search viral templates by embedding similarity."""
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT id, content, hook_pattern, category, engagement_score,
               (embedding <=> %s::vector) AS distance
        FROM linkedin_viral_templates
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute(query, (vector_literal, vector_literal, int(limit)))
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "hook_pattern": r[2],
                "category": r[3],
                "engagement_score": float(r[4]) if r[4] else 0.0,
                "distance": float(r[5]),
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Error searching viral templates: {e}")
        return []
    finally:
        cur.close()
        conn.close()
