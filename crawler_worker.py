"""Autonomous background worker process for executing Scrapy crawl jobs.

Monitors SQLite database for pending jobs, ensures mutual exclusion,
manages isolated child runner processes, supports cancellation,
and recovers interrupted jobs on startup.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

import database
from models import CrawlJobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker %(process)d] %(message)s",
)
logger = logging.getLogger("crawler_worker")


class CrawlerWorker:
    """Worker daemon executing recursive crawl jobs from the SQLite database."""

    def __init__(self, db_path: Optional[str] = None, poll_interval: float = 2.0):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.worker_pid = os.getpid()
        self.running = True
        self.current_process: Optional[subprocess.Popen] = None
        self.current_job_id: Optional[int] = None

        # Ensure database tables exist
        database.init_db(self.db_path)

        # Register signal handlers for graceful shutdown if running in main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            except (ValueError, AttributeError):
                pass

    def _handle_signal(self, signum, frame):
        logger.info("Received termination signal (%s). Shutting down worker...", signum)
        self.running = False
        if self.current_process and self.current_process.poll() is None:
            logger.info("Terminating active child crawler process (PID %d)...", self.current_process.pid)
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            except Exception:
                self.current_process.kill()
            if self.current_job_id:
                database.update_crawl_job_status(
                    self.current_job_id,
                    CrawlJobStatus.FAILED,
                    error_message="Worker terminated by signal",
                    db_path=self.db_path,
                )
                database.finalize_crawl_job_metrics(
                    job_id=self.current_job_id,
                    stop_reason="worker_signal_terminated",
                    final_outcome="FAILED",
                    db_path=self.db_path,
                )

    def startup_recovery(self):
        """Recover any jobs left in RUNNING status from a previous crashed run."""
        recovered = database.recover_interrupted_jobs(db_path=self.db_path)
        if recovered > 0:
            logger.warning("Recovered %d orphaned/interrupted jobs from previous run.", recovered)

    def run_single_job(self, job_id: int) -> bool:
        """Execute a specific crawl job in an isolated subprocess."""
        cmd = [
            sys.executable,
            "-m",
            "crawler.runner",
            "--job-id",
            str(job_id),
        ]
        if self.db_path:
            cmd.extend(["--db-path", self.db_path])

        logger.info("Starting crawler subprocess for Job #%d: %s", job_id, " ".join(cmd))
        self.current_job_id = job_id
        proc = subprocess.Popen(cmd)
        self.current_process = proc

        try:
            while proc.poll() is None:
                # Check for cancellation requested from API or UI
                if database.is_cancellation_requested(job_id, db_path=self.db_path):
                    logger.warning("Cancellation requested for Job #%d. Terminating subprocess...", job_id)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    database.update_crawl_job_status(
                        job_id, CrawlJobStatus.CANCELLED, db_path=self.db_path
                    )
                    database.finalize_crawl_job_metrics(
                        job_id=job_id,
                        stop_reason="cancelled",
                        final_outcome="CANCELLED",
                        db_path=self.db_path,
                    )
                    return True

                time.sleep(0.5)

            exit_code = proc.returncode
            logger.info("Subprocess for Job #%d completed with exit code %d.", job_id, exit_code)
            return exit_code == 0
        finally:
            self.current_process = None
            self.current_job_id = None

    def start(self, run_once: bool = False):
        """Main worker loop."""
        logger.info("Crawler worker started. PID=%d, DB=%s", self.worker_pid, self.db_path or database.get_db_path())
        self.startup_recovery()

        while self.running:
            try:
                # Atomically claim oldest pending job
                job = database.claim_next_pending_job(self.worker_pid, db_path=self.db_path)
                if job:
                    logger.info("Claimed Job #%d [Seed: %s, Max Depth: %d, Max Pages: %d]",
                                job.id, job.seed_url, job.max_depth, job.max_pages)
                    self.run_single_job(job.id)
                    if run_once:
                        break
                else:
                    if run_once:
                        logger.info("No pending jobs found. Exiting (--once).")
                        break
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.exception("Error in worker polling loop: %s", e)
                time.sleep(self.poll_interval)

        logger.info("Crawler worker stopped.")


def main():
    parser = argparse.ArgumentParser(description="AI Lead Research Scrapy Crawler Worker Daemon.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Process currently pending jobs and exit.")
    parser.add_argument("--run-job", type=int, default=None, help="Execute a specific job ID directly.")
    args = parser.parse_args()

    worker = CrawlerWorker(db_path=args.db_path, poll_interval=args.poll_interval)
    if args.run_job:
        worker.run_single_job(args.run_job)
    else:
        worker.start(run_once=args.once)


if __name__ == "__main__":
    main()
