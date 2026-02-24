"""
Database migration: Create tables for automation workflow.

Tables:
- users: Extended user profiles for automation
- daily_suggestions: Daily topic suggestions sent to users
- chat_interactions: Chat history and state tracking
- published_posts: Posts generated via automation
"""

import uuid
from datetime import datetime


def upgrade(connection):
    """Create new tables for automation workflow."""
    cursor = connection.cursor()

    # Users table (extended profile)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        telegram_user_id BIGINT UNIQUE,
        telegram_username VARCHAR(255),
        whatsapp_phone VARCHAR(20) UNIQUE,
        tech_interests TEXT[] DEFAULT '{}',
        automation_enabled BOOLEAN DEFAULT false,
        suggestion_time TIME DEFAULT '08:00:00',
        timezone VARCHAR(50) DEFAULT 'UTC',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # Daily suggestions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_suggestions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        topics JSONB NOT NULL,
        sent_at TIMESTAMP DEFAULT NOW(),
        message_id VARCHAR(255),
        status VARCHAR(50) DEFAULT 'sent',
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_daily_suggestions_user_id ON daily_suggestions(user_id);
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_daily_suggestions_sent_at ON daily_suggestions(sent_at);
    """)

    # Chat interactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_interactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        interaction_type VARCHAR(50),
        data JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_chat_interactions_user_id ON chat_interactions(user_id);
    """)

    # Published posts from automation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS automation_posts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        linkedin_post_id VARCHAR(255),
        source_topics JSONB,
        generated_content TEXT,
        generated_angles TEXT[],
        status VARCHAR(50) DEFAULT 'draft',
        approval_date TIMESTAMP,
        published_date TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_automation_posts_user_id ON automation_posts(user_id);
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_automation_posts_status ON automation_posts(status);
    """)

    connection.commit()
    print("✅ Migration complete: Created users, daily_suggestions, chat_interactions, automation_posts tables")


def downgrade(connection):
    """Drop automation workflow tables."""
    cursor = connection.cursor()

    tables = [
        "automation_posts",
        "chat_interactions",
        "daily_suggestions",
        "users",
    ]

    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
        print(f"Dropped table: {table}")

    connection.commit()
    print("✅ Migration rollback complete")


if __name__ == "__main__":
    # For manual testing
    import psycopg2
    from psycopg2 import extensions

    conn = psycopg2.connect(
        host="localhost",
        database="ai_employee",
        user="postgres",
        password="postgres",
    )
    conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "down":
        downgrade(conn)
    else:
        upgrade(conn)

    conn.close()
