import os
import uuid
import json
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
                score_breakdown JSONB,
                realism_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_research_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                topic TEXT NOT NULL,
                trend_candidates JSONB,
                extracted_claims JSONB,
                verified_claims JSONB,
                research_confidence FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_angle_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID,
                topic TEXT,
                angle_type TEXT,
                best_angle TEXT,
                risk_level TEXT,
                viral_score FLOAT,
                realism_score FLOAT,
                supporting_facts JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_post_engagement (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID,
                publish_url TEXT,
                linkedin_post_urn TEXT,
                impressions INT,
                reactions INT,
                comments INT,
                reposts INT,
                engagement_rate FLOAT,
                payload JSONB,
                fetched_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Safe additive migration for existing installations
        cur.execute("ALTER TABLE linkedin_posts ADD COLUMN IF NOT EXISTS score_breakdown JSONB;")
        cur.execute("ALTER TABLE linkedin_posts ADD COLUMN IF NOT EXISTS realism_score FLOAT;")

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
                tone, audience, topic, reasoning, status="draft",
                score_breakdown=None, realism_score=None):
    """Insert a generated LinkedIn post into the database."""
    conn = get_conn()
    cur = conn.cursor()
    post_id = str(uuid.uuid4())

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute("""
            INSERT INTO linkedin_posts
                (id, content, hook, cta, hashtags, embedding, viral_score,
                 tone, audience, topic, reasoning, status, score_breakdown, realism_score)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        """, (
            post_id, content, hook, cta, hashtags, vector_literal, viral_score,
            tone, audience, topic, reasoning, status,
            json.dumps(score_breakdown or {}), realism_score,
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


def search_similar_posts(embedding, limit=5, max_distance=0.45, min_score=0.0):
    """
    Search linkedin_posts by embedding similarity (cosine distance).

    Rules:
        - max_distance: only return posts within this cosine distance (tighter = more relevant)
        - min_score: only return posts with viral_score >= this value
    """
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT id, content, hook, cta, viral_score,
               (embedding <=> %s::vector) AS distance
        FROM linkedin_posts
        WHERE embedding IS NOT NULL
          AND (embedding <=> %s::vector) <= %s
          AND COALESCE(viral_score, 0) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute(query, (
            vector_literal, vector_literal, float(max_distance),
            float(min_score), vector_literal, int(limit),
        ))
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


def get_all_posts(limit=50, offset=0):
    """Get all posts ordered by creation date."""
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, viral_score, topic, status, created_at
            FROM linkedin_posts
            ORDER BY created_at DESC
            OFFSET %s
            LIMIT %s
        """, (int(offset), int(limit)))
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "viral_score": float(r[1]) if r[1] else 0.0,
                "topic": r[2],
                "status": r[3],
                "created_at": str(r[4]) if r[4] else None,
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
    try:
        normalized_post_id = str(uuid.UUID(str(post_id)))
    except (ValueError, TypeError, AttributeError):
        return None

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, content, hook, cta, hashtags, viral_score,
                     tone, audience, topic, status, publish_url,
                   reasoning, created_at
            FROM linkedin_posts
            WHERE id = %s
                """, (normalized_post_id,))
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


def insert_research_snapshot(topic, trend_candidates, extracted_claims, verified_claims, research_confidence):
    """Store a full research run snapshot for learning loops."""
    conn = get_conn()
    cur = conn.cursor()
    run_id = str(uuid.uuid4())
    try:
        cur.execute("""
            INSERT INTO linkedin_research_runs
                (id, topic, trend_candidates, extracted_claims, verified_claims, research_confidence)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        """, (
            run_id,
            topic,
            json.dumps(trend_candidates or []),
            json.dumps(extracted_claims or []),
            json.dumps(verified_claims or []),
            float(research_confidence or 0.0),
        ))
        conn.commit()
        return run_id
    except Exception as e:
        conn.rollback()
        print(f"Error inserting research snapshot: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def insert_angle_result(post_id, topic, angle_type, best_angle, risk_level, viral_score, realism_score, supporting_facts):
    """Store selected angle and outcomes for self-learning."""
    conn = get_conn()
    cur = conn.cursor()
    angle_id = str(uuid.uuid4())
    try:
        cur.execute("""
            INSERT INTO linkedin_angle_results
                (id, post_id, topic, angle_type, best_angle, risk_level, viral_score, realism_score, supporting_facts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """, (
            angle_id,
            post_id,
            topic,
            angle_type,
            best_angle,
            risk_level,
            float(viral_score or 0.0),
            float(realism_score or 0.0),
            json.dumps(supporting_facts or []),
        ))
        conn.commit()
        return angle_id
    except Exception as e:
        conn.rollback()
        print(f"Error inserting angle result: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def insert_post_engagement(post_id, publish_url, linkedin_post_urn, impressions, reactions, comments, reposts, payload):
    """Store fetched engagement snapshot for published post."""
    conn = get_conn()
    cur = conn.cursor()
    engagement_id = str(uuid.uuid4())
    try:
        imp = int(impressions or 0)
        react = int(reactions or 0)
        comm = int(comments or 0)
        rep = int(reposts or 0)
        denom = max(imp, 1)
        engagement_rate = round((react + comm + rep) / denom, 6)

        cur.execute("""
            INSERT INTO linkedin_post_engagement
                (id, post_id, publish_url, linkedin_post_urn, impressions, reactions, comments, reposts, engagement_rate, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """, (
            engagement_id,
            post_id,
            publish_url,
            linkedin_post_urn,
            imp,
            react,
            comm,
            rep,
            engagement_rate,
            json.dumps(payload or {}),
        ))
        conn.commit()
        return engagement_id
    except Exception as e:
        conn.rollback()
        print(f"Error inserting post engagement: {e}")
        return None
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


def search_viral_templates(embedding, limit=5, max_distance=0.50):
    """
    Search viral templates by embedding similarity.
    Only returns templates within max_distance threshold.
    """
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT id, content, hook_pattern, category, engagement_score,
               (embedding <=> %s::vector) AS distance
        FROM linkedin_viral_templates
        WHERE embedding IS NOT NULL
          AND (embedding <=> %s::vector) <= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    try:
        vector_literal = _to_vector_literal(embedding)
        cur.execute(query, (vector_literal, vector_literal, float(max_distance), vector_literal, int(limit)))
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
