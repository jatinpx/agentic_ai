"""
Database service for automation workflow tables.

Handles CRUD operations for users, daily suggestions, chat interactions.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


class AutomationDBService:
    """Database service for automation workflow."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.connection_string)

    # ==================== Users ====================

    async def get_or_create_user(
        self,
        telegram_user_id: Optional[int] = None,
        telegram_username: Optional[str] = None,
        whatsapp_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get existing user or create new one."""
        try:
            if not telegram_user_id and not whatsapp_phone:
                raise ValueError("Either telegram_user_id or whatsapp_phone is required")

            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    user_id = str(uuid.uuid4())

                    if telegram_user_id:
                        cursor.execute(
                            """
                            INSERT INTO users (id, telegram_user_id, telegram_username, whatsapp_phone)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (telegram_user_id)
                            DO UPDATE SET
                                telegram_username = COALESCE(EXCLUDED.telegram_username, users.telegram_username),
                                updated_at = NOW()
                            RETURNING *
                            """,
                            (user_id, telegram_user_id, telegram_username, whatsapp_phone),
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO users (id, telegram_user_id, telegram_username, whatsapp_phone)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (whatsapp_phone)
                            DO UPDATE SET updated_at = NOW()
                            RETURNING *
                            """,
                            (user_id, telegram_user_id, telegram_username, whatsapp_phone),
                        )

                    user = cursor.fetchone()

            if not user:
                raise RuntimeError("Failed to fetch user record after upsert")

            return dict(user)

        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            raise

    async def update_user_profile(
        self,
        user_id: str,
        tech_interests: Optional[List[str]] = None,
        automation_enabled: Optional[bool] = None,
        suggestion_time: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update user profile."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            updates = []
            params = []

            if tech_interests is not None:
                updates.append("tech_interests = %s")
                params.append(tech_interests)

            if automation_enabled is not None:
                updates.append("automation_enabled = %s")
                params.append(automation_enabled)

            if suggestion_time is not None:
                updates.append("suggestion_time = %s")
                params.append(suggestion_time)

            if timezone is not None:
                updates.append("timezone = %s")
                params.append(timezone)

            if not updates:
                return {}

            updates.append("updated_at = NOW()")
            params.append(user_id)

            query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s RETURNING *"
            cursor.execute(query, params)

            conn.commit()
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            logger.info(f"Updated user profile: {user_id}")
            return dict(user) if user else {}

        except Exception as e:
            logger.error(f"Error in update_user_profile: {e}")
            raise

    async def get_AutomationEnabledUsers(self) -> List[Dict[str, Any]]:
        """Get all users with automation enabled."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute("SELECT * FROM users WHERE automation_enabled = true")
            users = cursor.fetchall()
            cursor.close()
            conn.close()

            return [dict(u) for u in users]

        except Exception as e:
            logger.error(f"Error fetching automation-enabled users: {e}")
            return []

    # ==================== Daily Suggestions ====================

    async def save_daily_suggestions(
        self,
        user_id: str,
        topics: List[Dict[str, Any]],
        message_id: Optional[str] = None,
    ) -> str:
        """Save daily topic suggestions."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            suggestion_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO daily_suggestions (id, user_id, topics, message_id, status)
                VALUES (%s, %s, %s, %s, 'sent')
                """,
                (suggestion_id, user_id, Json(topics), message_id),
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Saved suggestions for user {user_id}: {suggestion_id}")
            return str(suggestion_id)

        except Exception as e:
            logger.error(f"Error saving daily suggestions: {e}")
            raise

    async def get_latest_suggestions(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get latest suggestions for user."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT * FROM daily_suggestions WHERE user_id = %s ORDER BY sent_at DESC LIMIT 1",
                (user_id,),
            )

            suggestion = cursor.fetchone()
            cursor.close()
            conn.close()

            return dict(suggestion) if suggestion else None

        except Exception as e:
            logger.error(f"Error fetching latest suggestions: {e}")
            return None

    async def mark_suggestions_as_selected(
        self,
        suggestion_id: str,
    ) -> bool:
        """Mark suggestions as 'selected' by user."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE daily_suggestions SET status = 'selected' WHERE id = %s",
                (suggestion_id,),
            )

            conn.commit()
            cursor.close()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error marking suggestions as selected: {e}")
            return False

    # ==================== Chat Interactions ====================

    async def log_chat_interaction(
        self,
        user_id: str,
        interaction_type: str,
        data: Dict[str, Any],
    ) -> str:
        """Log user chat interaction."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            interaction_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO chat_interactions (id, user_id, interaction_type, data)
                VALUES (%s, %s, %s, %s)
                """,
                (interaction_id, user_id, interaction_type, Json(data)),
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Logged interaction for user {user_id}: {interaction_type}")
            return str(interaction_id)

        except Exception as e:
            logger.error(f"Error logging chat interaction: {e}")
            raise

    async def get_user_interaction_history(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get user's chat interaction history."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT * FROM chat_interactions WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )

            interactions = cursor.fetchall()
            cursor.close()
            conn.close()

            return [dict(i) for i in interactions]

        except Exception as e:
            logger.error(f"Error fetching interaction history: {e}")
            return []

    # ==================== Automation Posts ====================

    async def save_automation_post(
        self,
        user_id: str,
        source_topics: List[Dict[str, Any]],
        generated_content: str,
        generated_angles: List[str],
    ) -> str:
        """Save generated post from automation."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            post_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO automation_posts 
                (id, user_id, source_topics, generated_content, generated_angles, status)
                VALUES (%s, %s, %s, %s, %s, 'draft')
                """,
                (
                    post_id,
                    user_id,
                    Json(source_topics),
                    generated_content,
                    generated_angles,
                ),
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Saved automation post: {post_id}")
            return str(post_id)

        except Exception as e:
            logger.error(f"Error saving automation post: {e}")
            raise

    async def publish_automation_post(
        self,
        post_id: str,
        linkedin_post_id: str,
    ) -> bool:
        """Mark post as published to LinkedIn."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE automation_posts 
                SET status = 'published', linkedin_post_id = %s, published_date = NOW()
                WHERE id = %s
                """,
                (linkedin_post_id, post_id),
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Published automation post: {post_id}")
            return True

        except Exception as e:
            logger.error(f"Error publishing automation post: {e}")
            return False

    async def get_user_automation_posts(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get user's automation posts."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if status:
                cursor.execute(
                    "SELECT * FROM automation_posts WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, status, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM automation_posts WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit),
                )

            posts = cursor.fetchall()
            cursor.close()
            conn.close()

            return [dict(p) for p in posts]

        except Exception as e:
            logger.error(f"Error fetching automation posts: {e}")
            return []


# Global instance
_automation_db = None


def get_automation_db(connection_string: Optional[str] = None) -> AutomationDBService:
    """Get or create global automation DB service."""
    global _automation_db

    if _automation_db is None:
        if not connection_string:
            import os
            connection_string = os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/ai_employee"
            )
        _automation_db = AutomationDBService(connection_string)

    return _automation_db
