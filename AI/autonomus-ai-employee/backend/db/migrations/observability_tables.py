"""
Observability Database Migrations

Creates tables for distributed tracing and event logging:
- event_logs: Span start/end events with correlation IDs
- exception_logs: Exception stack traces with context

Supports historical trace queries and post-mortem analysis.
"""

import psycopg2
from psycopg2 import sql
import logging

logger = logging.getLogger(__name__)


def upgrade(conn):
    """
    Create observability tables for tracing and event logging.
    
    Tables:
    - event_logs: Distributed traces (parent/child spans, correlation IDs)
    - exception_logs: Exception stack traces with system context
    
    Supports:
    - Historical trace retrieval by correlation_id
    - Node-level event aggregation
    - Exception analysis with local variable snapshots
    """
    
    cursor = conn.cursor()
    
    try:
        # Create event_logs table for distributed tracing
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS event_logs (
                id BIGSERIAL PRIMARY KEY,
                correlation_id UUID NOT NULL,
                span_id VARCHAR(50),
                parent_span_id VARCHAR(50),
                event_type VARCHAR(100) NOT NULL,
                node_name VARCHAR(200),
                operation VARCHAR(200),
                platform VARCHAR(50),  -- "linkedin" or "telegram"
                
                -- Timing information
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                latency_ms FLOAT,
                
                -- Event data
                status VARCHAR(20) DEFAULT 'ok',  -- "ok", "error", "pending"
                input_data JSONB,
                output_data JSONB,
                metadata JSONB,
                error_message TEXT,
                
                -- Context
                thread_id VARCHAR(100),
                user_id VARCHAR(100),
                chat_id VARCHAR(100),
                
                -- Indexing
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                
                -- Cleanup
                ttl_minutes INT DEFAULT 10080  -- 7 days
            );
            
            -- Indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_event_logs_correlation_id 
                ON event_logs(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_event_logs_node_name 
                ON event_logs(node_name);
            CREATE INDEX IF NOT EXISTS idx_event_logs_timestamp 
                ON event_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_event_logs_thread_id 
                ON event_logs(thread_id);
            CREATE INDEX IF NOT EXISTS idx_event_logs_user_id 
                ON event_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_event_logs_parent_span 
                ON event_logs(parent_span_id);
            CREATE INDEX IF NOT EXISTS idx_event_logs_span_id 
                ON event_logs(span_id);
        """))
        
        # Create exception_logs table for error tracking
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS exception_logs (
                id BIGSERIAL PRIMARY KEY,
                correlation_id UUID,
                span_id VARCHAR(50),
                
                -- Exception information
                error_type VARCHAR(200) NOT NULL,
                error_message TEXT,
                
                -- Stack trace
                stack_trace TEXT,
                traceback_frames JSONB,  -- List of {filename, lineno, function, locals}
                
                -- Context
                node_name VARCHAR(200),
                thread_id VARCHAR(100),
                user_id VARCHAR(100),
                
                -- Local variables snapshot
                local_vars JSONB,
                
                -- Event metadata
                metadata JSONB,
                additional_context JSONB,
                
                -- Timing
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                
                -- Cleanup
                ttl_minutes INT DEFAULT 10080  -- 7 days
            );
            
            -- Indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_exception_logs_correlation_id 
                ON exception_logs(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_exception_logs_error_type 
                ON exception_logs(error_type);
            CREATE INDEX IF NOT EXISTS idx_exception_logs_timestamp 
                ON exception_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_exception_logs_thread_id 
                ON exception_logs(thread_id);
            CREATE INDEX IF NOT EXISTS idx_exception_logs_node_name 
                ON exception_logs(node_name);
        """))
        
        conn.commit()
        logger.info("[Observability] event_logs and exception_logs tables created successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"[Observability] Migration failed: {e}")
        raise
    finally:
        cursor.close()


def downgrade(conn):
    """
    Drop observability tables (for rollback).
    """
    
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql.SQL("DROP TABLE IF EXISTS exception_logs CASCADE"))
        cursor.execute(sql.SQL("DROP TABLE IF EXISTS event_logs CASCADE"))
        
        conn.commit()
        logger.info("[Observability] event_logs and exception_logs tables dropped")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"[Observability] Rollback failed: {e}")
        raise
    finally:
        cursor.close()
