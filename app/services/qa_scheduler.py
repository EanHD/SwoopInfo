"""
QA Scheduler Service - Continuous Auto-QA
Runs daily QA and Repair jobs automatically
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from services.supabase_client import supabase_service
from services.qa_agent import qa_agent
from services.qa_repair import qa_repair_agent

logger = logging.getLogger(__name__)


class QAScheduler:
    def __init__(self):
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.last_run_status: str = "never_run"
        self.next_scheduled_run: Optional[datetime] = None
        self.currently_processing = False
        self.run_interval_hours = 24
        self.batch_size_run = 50
        self.batch_size_repair = 20
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Start the scheduler loop"""
        if self.is_running:
            return

        self.is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("QA Scheduler started")

    def stop(self):
        """Stop the scheduler loop"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("QA Scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.is_running:
            now = datetime.utcnow()

            # Determine if we should run
            should_run = False
            if not self.last_run:
                should_run = (
                    True  # Run immediately on first start (or maybe wait a bit?)
                )
                # Let's wait 1 minute after startup to let things settle
                await asyncio.sleep(60)
                should_run = True
            elif now >= self.next_scheduled_run:
                should_run = True

            if should_run:
                await self.run_daily_cycle()

                # Schedule next run
                self.last_run = datetime.utcnow()
                self.next_scheduled_run = self.last_run + timedelta(
                    hours=self.run_interval_hours
                )

            # Sleep for a bit before checking again
            await asyncio.sleep(60)

    async def run_daily_cycle(self):
        """Execute the full daily QA cycle"""
        if self.currently_processing:
            logger.warning("QA cycle skipped - already processing")
            return

        self.currently_processing = True
        logger.info("Starting Daily QA Cycle...")

        try:
            # 1. Run QA (Detection)
            await self._run_qa_phase()

            # 2. Run Repair (Healing)
            await self._run_repair_phase()

            # 3. Generate & Save Report
            await self._generate_daily_report()

            self.last_run_status = "success"
            logger.info("Daily QA Cycle Completed Successfully")

        except Exception as e:
            self.last_run_status = f"failed: {str(e)}"
            logger.error(f"Daily QA Cycle Failed: {e}")
        finally:
            self.currently_processing = False

    async def _run_qa_phase(self):
        """Run QA detection on pending chunks"""
        logger.info("Phase 1: QA Detection")
        while True:
            chunks = await supabase_service.get_pending_qa_chunks(
                limit=self.batch_size_run
            )
            if not chunks:
                break

            for chunk in chunks:
                qa_result = await qa_agent.process_chunk(chunk)
                await supabase_service.update_chunk_qa_status(
                    chunk_id=chunk.id,
                    qa_status=qa_result["status"],
                    qa_notes=qa_result["notes"],
                    last_qa_reviewed_at=datetime.utcnow().isoformat(),
                )

            # Small pause to be nice to DB
            await asyncio.sleep(1)

    async def _run_repair_phase(self):
        """Run repair on failed chunks"""
        logger.info("Phase 2: QA Repair")
        # We only try to repair chunks that failed recently or haven't hit max retries
        # The repair agent handles max retry logic

        while True:
            chunks = await supabase_service.get_failed_chunks(
                limit=self.batch_size_repair
            )
            if not chunks:
                break

            processed_count = 0
            for chunk in chunks:
                # Skip if max retries reached (optimization to avoid fetching them repeatedly)
                if chunk.regeneration_attempts >= qa_repair_agent.max_attempts:
                    continue

                await qa_repair_agent.repair_chunk(chunk)
                processed_count += 1

            if processed_count == 0:
                break  # No repairable chunks left

            await asyncio.sleep(1)

    async def _generate_daily_report(self):
        """Generate and save daily report"""
        logger.info("Phase 3: Reporting")
        stats = await supabase_service.get_qa_stats()

        report = {
            "date": datetime.utcnow().date().isoformat(),
            "stats": stats,
            "summary": f"Total: {stats['total']} | Pass: {stats['pass']} | Fail: {stats['fail']}",
        }

        # Save to qa_history_daily table
        try:
            supabase_service.client.table("qa_history_daily").insert(
                {
                    "report_date": report["date"],
                    "stats": report["stats"],
                    "summary": report["summary"],
                }
            ).execute()
        except Exception as e:
            # Ignore duplicate key error if run multiple times same day
            if "duplicate key" not in str(e).lower():
                logger.error(f"Failed to save daily report: {e}")

    def get_health(self) -> Dict[str, Any]:
        """Get scheduler health status"""
        return {
            "is_running": self.is_running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_run_status": self.last_run_status,
            "next_scheduled_run": (
                self.next_scheduled_run.isoformat() if self.next_scheduled_run else None
            ),
            "currently_processing": self.currently_processing,
        }


qa_scheduler = QAScheduler()
