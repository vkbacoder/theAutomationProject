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
import threading
import time
from typing import Optional

from filelock import FileLock, Timeout

import database
from models import CrawlJobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker %(process)d] %(message)s",
)
logger = logging.getLogger("crawler_worker")

# Global reference for embedded worker running in-process
_global_worker: Optional[CrawlerWorker] = None
_global_worker_thread: Optional[threading.Thread] = None


class CrawlerWorker:
    """Worker daemon executing recursive crawl jobs from the SQLite database."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        poll_interval: float = 2.0,
        lock_path: Optional[str] = None,
    ):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.lock_path = lock_path
        self.worker_pid = os.getpid()
        self.running = True
        self.lock_held = False
        self._file_lock: Optional[FileLock] = None
        self.wake_event = threading.Event()
        self.current_process: Optional[subprocess.Popen] = None
        self.current_job_id: Optional[int] = None

        # Ensure database tables exist
        database.init_db(self.db_path)

        # Register signal handlers for graceful shutdown if running in main thread
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            except (ValueError, AttributeError):
                pass

    def _handle_signal(self, signum, frame):
        logger.info("Received termination signal (%s). Shutting down worker...", signum)
        self.stop(timeout=5.0)

    def wake_up(self):
        """Wake up the worker loop immediately if it is waiting."""
        self.wake_event.set()

    def stop(self, timeout: float = 5.0):
        """Signal worker to stop, interrupt wait, and terminate any active child process."""
        self.running = False
        self.wake_event.set()

        if self.current_process and self.current_process.poll() is None:
            logger.info("Terminating active child crawler process (PID %d)...", self.current_process.pid)
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=timeout)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass

            if self.current_job_id:
                try:
                    database.update_crawl_job_status(
                        self.current_job_id,
                        CrawlJobStatus.FAILED,
                        error_message="Worker terminated by signal/stop",
                        db_path=self.db_path,
                    )
                    database.finalize_crawl_job_metrics(
                        job_id=self.current_job_id,
                        stop_reason="worker_stopped",
                        final_outcome="FAILED",
                        db_path=self.db_path,
                    )
                except Exception as e:
                    logger.error("Failed to update status on worker stop: %s", e)

    def startup_recovery(self):
        """Recover any jobs left in RUNNING status from a previous crashed run."""
        recovered = database.recover_interrupted_jobs(db_path=self.db_path)
        if recovered > 0:
            logger.warning("Recovered %d orphaned/interrupted jobs from previous run.", recovered)

    def run_single_job(self, job_id: int) -> bool:
        """Execute a specific crawl job in an isolated subprocess."""
        # 1. Check for cancellation before spawning subprocess
        if database.is_cancellation_requested(job_id, db_path=self.db_path):
            logger.info("Job #%d was cancelled before crawler process could be spawned.", job_id)
            database.update_crawl_job_status(
                job_id, CrawlJobStatus.CANCELLED, db_path=self.db_path
            )
            database.finalize_crawl_job_metrics(
                job_id=job_id,
                stop_reason="cancelled_before_start",
                final_outcome="CANCELLED",
                db_path=self.db_path,
            )
            return True

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

    def start(self, run_once: bool = False, acquire_lock: bool = True) -> bool:
        """Main worker loop."""
        if acquire_lock:
            lock_file = self.lock_path or os.path.join(
                os.path.dirname(os.path.abspath(self.db_path or database.get_db_path())),
                "crawler_worker.lock",
            )
            self._file_lock = FileLock(lock_file, timeout=0.1)
            try:
                self._file_lock.acquire()
                self.lock_held = True
                logger.info("Acquired crawler worker lock: %s", lock_file)
            except Timeout:
                logger.warning(
                    "Another crawler worker process already holds the lock (%s). Standing down.",
                    lock_file,
                )
                return False

        try:
            logger.info(
                "Crawler worker started. PID=%d, DB=%s",
                self.worker_pid,
                self.db_path or database.get_db_path(),
            )
            self.startup_recovery()

            while self.running:
                try:
                    # Atomically claim oldest pending job
                    job = database.claim_next_pending_job(self.worker_pid, db_path=self.db_path)
                    if job:
                        logger.info(
                            "Claimed Job #%d [Seed: %s, Max Depth: %d, Max Pages: %d]",
                            job.id,
                            job.seed_url,
                            job.max_depth,
                            job.max_pages,
                        )
                        self.run_single_job(job.id)
                        if run_once:
                            break
                    else:
                        if run_once:
                            logger.info("No pending jobs found. Exiting (--once).")
                            break
                        # Wait for poll interval or early wake event
                        self.wake_event.wait(timeout=self.poll_interval)
                        self.wake_event.clear()
                except Exception as e:
                    logger.exception("Error in worker polling loop: %s", e)
                    self.wake_event.wait(timeout=self.poll_interval)
                    self.wake_event.clear()

            logger.info("Crawler worker stopped.")
            return True
        finally:
            if self._file_lock and self.lock_held:
                try:
                    self._file_lock.release()
                except Exception:
                    pass
                self.lock_held = False


def start_embedded_worker(
    db_path: Optional[str] = None,
    poll_interval: float = 2.0,
    lock_path: Optional[str] = None,
) -> Optional[CrawlerWorker]:
    """Start an embedded background worker thread in the current process."""
    global _global_worker, _global_worker_thread

    # Check environment override
    if os.environ.get("DISABLE_EMBEDDED_WORKER", "").lower() in ("1", "true", "yes"):
        logger.info("Embedded crawler worker disabled by DISABLE_EMBEDDED_WORKER.")
        return None

    if _global_worker and _global_worker.running:
        logger.info("Embedded crawler worker is already running.")
        return _global_worker

    worker = CrawlerWorker(db_path=db_path, poll_interval=poll_interval, lock_path=lock_path)
    _global_worker = worker

    def _worker_thread_target():
        worker.start(run_once=False, acquire_lock=True)

    thread = threading.Thread(
        target=_worker_thread_target,
        name="CrawlerWorkerThread",
        daemon=True,
    )
    _global_worker_thread = thread
    thread.start()
    logger.info("Embedded crawler worker thread started.")
    return worker


def stop_embedded_worker(timeout: float = 5.0):
    """Gracefully stop the embedded background worker thread if running."""
    global _global_worker, _global_worker_thread

    if _global_worker:
        logger.info("Stopping embedded crawler worker...")
        _global_worker.stop(timeout=timeout)
        if _global_worker_thread and _global_worker_thread.is_alive():
            _global_worker_thread.join(timeout=timeout)
        _global_worker = None
        _global_worker_thread = None
        logger.info("Embedded crawler worker stopped successfully.")


def wake_worker():
    """Wake up the active embedded worker to process newly queued jobs immediately."""
    global _global_worker
    if _global_worker and _global_worker.running:
        _global_worker.wake_up()


def get_worker_status() -> dict:
    """Return status dictionary of the embedded crawler worker."""
    global _global_worker
    if _global_worker:
        return {
            "worker_available": True,
            "mode": "embedded",
            "worker_pid": _global_worker.worker_pid,
            "is_running": _global_worker.running,
            "lock_held": _global_worker.lock_held,
            "current_job_id": _global_worker.current_job_id,
        }
    return {
        "worker_available": False,
        "mode": "standalone_or_none",
        "worker_pid": None,
        "is_running": False,
        "lock_held": False,
        "current_job_id": None,
    }


def main():
    parser = argparse.ArgumentParser(description="AI Lead Research Scrapy Crawler Worker Daemon.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Process currently pending jobs and exit.")
    parser.add_argument("--run-job", type=int, default=None, help="Execute a specific job ID directly.")
    parser.add_argument("--no-lock", action="store_true", help="Bypass mutual exclusion file lock.")
    args = parser.parse_args()

    worker = CrawlerWorker(db_path=args.db_path, poll_interval=args.poll_interval)
    if args.run_job:
        worker.run_single_job(args.run_job)
    else:
        worker.start(run_once=args.once, acquire_lock=not args.no_lock)


if __name__ == "__main__":
    main()
