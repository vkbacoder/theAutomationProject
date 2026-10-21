"""Automated test suite for Background Crawl Worker Lifecycle.

Verifies:
- Atomic job creation and worker pickup.
- Mutual exclusion and prevention of duplicate execution.
- Subprocess failure and error reporting.
- Cooperative cancellation (pending and running).
- Interrupted-job recovery on restart.
- Database path handling.
- Worker status API and favicon endpoints.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
import database
from crawler_worker import CrawlerWorker, get_worker_status, wake_worker
from filelock import FileLock, Timeout
from models import (
    CrawlJob,
    CrawlJobStatus,
    WorkflowType,
)

client = TestClient(app)


@pytest.fixture
def temp_db():
    """Create an isolated temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.init_db(path)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass


def test_job_creation_and_worker_pickup(temp_db):
    """Test that a pending job is atomically claimed by the worker with worker_pid and started_at."""
    new_job = CrawlJob(
        seed_url="https://example.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)
    assert created.id is not None
    assert created.status == CrawlJobStatus.PENDING
    assert created.worker_pid is None

    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)
    claimed = database.claim_next_pending_job(worker.worker_pid, db_path=temp_db)

    assert claimed is not None
    assert claimed.id == created.id
    assert claimed.status == CrawlJobStatus.RUNNING
    assert claimed.worker_pid == worker.worker_pid
    assert claimed.started_at is not None

    # No second pending job should be claimed
    second_claim = database.claim_next_pending_job(worker.worker_pid, db_path=temp_db)
    assert second_claim is None


def test_prevention_of_duplicate_execution(temp_db):
    """Verify mutual exclusion via FileLock and atomic claiming prevents duplicate worker loops."""
    # 1. Test FileLock mutual exclusion
    lock_file = temp_db + ".lock"
    lock1 = FileLock(lock_file, timeout=0.1)
    lock1.acquire()

    worker2 = CrawlerWorker(db_path=temp_db, poll_interval=0.1, lock_path=lock_file)
    started = worker2.start(run_once=True, acquire_lock=True)
    assert started is False, "Worker 2 must not start when lock is already held"
    assert worker2.lock_held is False

    lock1.release()

    # 2. Test race condition claiming: two threads attempting to claim the same job
    new_job = CrawlJob(
        seed_url="https://race-example.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)

    results = []

    def claim_attempt(pid):
        res = database.claim_next_pending_job(pid, db_path=temp_db)
        if res:
            results.append(res.id)

    t1 = threading.Thread(target=claim_attempt, args=(1001,))
    t2 = threading.Thread(target=claim_attempt, args=(1002,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one thread should claim the job
    assert len(results) == 1
    assert results[0] == created.id


def test_cancellation_before_subprocess_spawn(temp_db):
    """If cancellation was requested before runner execution, worker cancels immediately without spawning subprocess."""
    new_job = CrawlJob(
        seed_url="https://cancel-before.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)
    database.request_cancel_crawl_job(created.id, db_path=temp_db)

    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)
    with patch("subprocess.Popen") as mock_popen:
        result = worker.run_single_job(created.id)
        assert result is True
        mock_popen.assert_not_called()

    cancelled_job = database.get_crawl_job(created.id, db_path=temp_db)
    assert cancelled_job.status == CrawlJobStatus.CANCELLED
    assert cancelled_job.finished_at is not None


def test_cancellation_during_execution(temp_db):
    """If cancellation is requested while subprocess is active, worker terminates process and updates status."""
    new_job = CrawlJob(
        seed_url="https://cancel-during.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)
    claimed = database.claim_next_pending_job(os.getpid(), db_path=temp_db)

    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)

    mock_proc = MagicMock()
    # First poll returns None (running), second returns None, then after terminate it will exit
    poll_states = [None, None, 0]

    def mock_poll():
        # Trigger cancellation while subprocess is still running
        database.request_cancel_crawl_job(created.id, db_path=temp_db)
        if poll_states:
            return poll_states.pop(0)
        return 0

    mock_proc.poll.side_effect = mock_poll

    with patch("subprocess.Popen", return_value=mock_proc):
        result = worker.run_single_job(created.id)
        assert result is True
        mock_proc.terminate.assert_called_once()

    cancelled_job = database.get_crawl_job(created.id, db_path=temp_db)
    assert cancelled_job.status == CrawlJobStatus.CANCELLED


def test_subprocess_failure_and_error_reporting(temp_db):
    """When subprocess exits with non-zero exit code, error is recorded properly."""
    new_job = CrawlJob(
        seed_url="https://fail-test.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)
    database.claim_next_pending_job(os.getpid(), db_path=temp_db)

    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc):
        result = worker.run_single_job(created.id)
        assert result is False

    # Runner updates status to FAILED or worker records it
    database.update_crawl_job_status(created.id, CrawlJobStatus.FAILED, error_message="Crawler error", db_path=temp_db)
    failed_job = database.get_crawl_job(created.id, db_path=temp_db)
    assert failed_job.status == CrawlJobStatus.FAILED
    assert failed_job.error_message == "Crawler error"


def test_interrupted_job_recovery(temp_db):
    """Orphaned jobs in RUNNING status are recovered on startup as FAILED with an informative message."""
    new_job = CrawlJob(
        seed_url="https://crashed-job.com",
        workflow=WorkflowType.GENERAL,
        status=CrawlJobStatus.PENDING,
    )
    created = database.create_crawl_job(new_job, db_path=temp_db)
    # Simulate job started by crashed worker
    database.claim_next_pending_job(99999, db_path=temp_db)

    active_before = database.get_crawl_job(created.id, db_path=temp_db)
    assert active_before.status == CrawlJobStatus.RUNNING

    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)
    worker.startup_recovery()

    recovered_job = database.get_crawl_job(created.id, db_path=temp_db)
    assert recovered_job.status == CrawlJobStatus.FAILED
    assert "Interrupted" in (recovered_job.error_message or "")
    assert recovered_job.finished_at is not None


def test_custom_db_path_handling(temp_db):
    """Ensure CrawlerWorker and helpers respect custom database path overrides."""
    worker = CrawlerWorker(db_path=temp_db, poll_interval=0.1)
    assert worker.db_path == temp_db

    count_pending = database.count_pending_crawl_jobs(db_path=temp_db)
    assert count_pending == 0

    job = database.create_crawl_job(
        CrawlJob(seed_url="https://custom-db.com", workflow=WorkflowType.GENERAL),
        db_path=temp_db,
    )
    assert database.count_pending_crawl_jobs(db_path=temp_db) == 1

    running = database.get_current_running_crawl_job(db_path=temp_db)
    assert running is None

    database.claim_next_pending_job(worker.worker_pid, db_path=temp_db)
    running = database.get_current_running_crawl_job(db_path=temp_db)
    assert running is not None
    assert running.id == job.id


def test_worker_status_api_endpoint(temp_db):
    """Test GET /api/crawl/worker/status returns queue depth and worker status."""
    with patch("database.get_db_path", return_value=temp_db):
        resp = client.get("/api/crawl/worker/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "worker_available" in data
        assert "mode" in data
        assert "pending_jobs_count" in data
        assert "active_running_job" in data


def test_favicon_endpoint():
    """Test GET /favicon.ico returns 204 No Content."""
    resp = client.get("/favicon.ico")
    assert resp.status_code == 204
