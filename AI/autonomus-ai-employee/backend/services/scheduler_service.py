"""
Scheduler Service

Manages daily automation triggers using APScheduler.
Runs news aggregation → topic ranking → Telegram messaging pipeline.
Handles task scheduling, job execution, and error logging.
"""

import asyncio
import logging
from typing import Optional, Callable, Any
from datetime import datetime, time
import os

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    BackgroundScheduler = None
    CronTrigger = None
    IntervalTrigger = None

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages daily automation workflow scheduling."""

    def __init__(self):
        self.scheduler = None
        self.is_running = False
        self._init_scheduler()

    def _init_scheduler(self):
        """Initialize APScheduler instance."""
        if not BackgroundScheduler:
            logger.warning("APScheduler not installed")
            return

        self.scheduler = BackgroundScheduler()
        self.scheduler.configure(
            jobstores={
                'default': {
                    'type': 'memory',  # Use memory store for MVP (no persistent DB)
                }
            },
            executors={
                'default': {
                    'type': 'threadpool',
                    'max_workers': 5,
                }
            },
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
            },
            timezone='UTC',
        )

    def start(self):
        """Start the scheduler."""
        if not self.scheduler:
            logger.error("Scheduler not initialized")
            return False

        if self.is_running:
            logger.warning("Scheduler already running")
            return False

        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("Scheduler started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            return False

    def stop(self):
        """Stop the scheduler."""
        if not self.scheduler or not self.is_running:
            return

        try:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def schedule_daily_news_pipeline(
        self,
        callback: Callable,
        hour: int = 8,
        minute: int = 0,
        job_id: str = "daily_news_pipeline",
    ) -> bool:
        """
        Schedule daily news aggregation → ranking → Telegram messaging.
        
        Args:
            callback: Async function to execute (receives job context)
            hour: Hour of day to run (0-23, UTC)
            minute: Minute of hour (0-59)
            job_id: Unique job identifier
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        if not self.scheduler:
            logger.error("Scheduler not initialized")
            return False

        try:
            trigger = CronTrigger(hour=hour, minute=minute, timezone='UTC')
            
            self.scheduler.add_job(
                func=self._run_async_job,
                args=(callback,),
                trigger=trigger,
                id=job_id,
                name=f"Daily News Pipeline ({hour:02d}:{minute:02d} UTC)",
                replace_existing=True,
                misfire_grace_time=600,  # 10 min grace period
            )
            
            logger.info(f"Scheduled job '{job_id}' for {hour:02d}:{minute:02d} UTC")
            return True

        except Exception as e:
            logger.error(f"Failed to schedule job '{job_id}': {e}")
            return False

    def schedule_test_job(
        self,
        callback: Callable,
        delay_seconds: int = 5,
        job_id: str = "test_job",
    ) -> bool:
        """
        Schedule a test job to run after a delay (useful for testing).
        
        Args:
            callback: Async function to execute
            delay_seconds: Seconds from now to run the job
            job_id: Unique job identifier
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        if not self.scheduler:
            logger.error("Scheduler not initialized")
            return False

        try:
            trigger = IntervalTrigger(seconds=delay_seconds)
            
            self.scheduler.add_job(
                func=self._run_async_job,
                args=(callback,),
                trigger=trigger,
                id=job_id,
                name=f"Test Job ({delay_seconds}s delay)",
                replace_existing=True,
                misfire_grace_time=10,
            )
            
            logger.info(f"Scheduled test job '{job_id}' for {delay_seconds}s from now")
            return True

        except Exception as e:
            logger.error(f"Failed to schedule test job '{job_id}': {e}")
            return False

    def unschedule_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if not self.scheduler:
            return False

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job '{job_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job '{job_id}': {e}")
            return False

    def get_job(self, job_id: str) -> Optional[Any]:
        """Get job details."""
        if not self.scheduler:
            return None

        return self.scheduler.get_job(job_id)

    def list_jobs(self) -> list:
        """List all scheduled jobs."""
        if not self.scheduler:
            return []

        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    def _run_async_job(self, callback: Callable):
        """Wrapper to run async callback from sync scheduler."""
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the async callback
            if asyncio.iscoroutinefunction(callback):
                result = loop.run_until_complete(callback())
            else:
                result = callback()

            logger.info(f"Job completed: {callback.__name__}")
            return result

        except Exception as e:
            logger.error(f"Error running job {callback.__name__}: {e}", exc_info=True)
            raise


# Global instance
_scheduler_instance = None


def get_scheduler() -> SchedulerService:
    """Get or create global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SchedulerService()
    return _scheduler_instance


def start_scheduler() -> bool:
    """Start global scheduler."""
    scheduler = get_scheduler()
    return scheduler.start()


def stop_scheduler():
    """Stop global scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()


def is_scheduler_running() -> bool:
    """Check if scheduler is running."""
    scheduler = get_scheduler()
    return scheduler.is_running


# Logging setup
def configure_scheduler_logging(log_level=logging.INFO):
    """Configure logging for scheduler."""
    scheduler_logger = logging.getLogger('apscheduler')
    scheduler_logger.setLevel(log_level)

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    scheduler_logger.addHandler(handler)

    logger.setLevel(log_level)
    logger.addHandler(handler)
