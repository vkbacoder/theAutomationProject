"""Standalone process runner for a single Scrapy crawl job.

Isolates Scrapy and Twisted reactor lifecycle inside a dedicated child process,
preventing reactor reuse conflicts and ensuring clean memory isolation.
"""

from __future__ import annotations

import argparse
import logging
import sys

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

import database
from crawler.settings import *  # Import settings dictionary
from crawler.spider import RecursiveLeadSpider
from models import CrawlJobStatus

logger = logging.getLogger("crawler.runner")


def run_job(job_id: int, db_path: str | None = None) -> int:
    """Execute a single crawl job using Scrapy CrawlerProcess."""
    job = database.get_crawl_job(job_id, db_path=db_path)
    if not job:
        logger.error("Job %d not found in database.", job_id)
        return 1

    # Check for early cancellation
    if database.is_cancellation_requested(job_id, db_path=db_path):
        logger.info("Job %d was already requested for cancellation.", job_id)
        database.update_crawl_job_status(job_id, CrawlJobStatus.CANCELLED, db_path=db_path)
        return 0

    # Build Scrapy Settings
    from scrapy.settings import Settings
    import crawler.settings as custom_settings

    settings = Settings()
    for key in dir(custom_settings):
        if key.isupper():
            settings.set(key, getattr(custom_settings, key))

    if db_path:
        settings.set("DB_PATH", db_path)

    process = CrawlerProcess(settings)
    crawler = process.create_crawler(RecursiveLeadSpider)

    try:
        process.crawl(
            crawler,
            job_id=job.id,
            seed_url=job.seed_url,
            allowed_domains=job.allowed_domains,
            max_depth=job.max_depth,
            max_pages=job.max_pages,
            max_pages_per_domain=job.max_pages_per_domain,
            workflow=job.workflow.value,
            company_id=job.company_id,
            db_path=db_path,
        )
        process.start()  # Blocks until spider finishes

        # Inspect Scrapy stats and stop reason
        stats = crawler.stats.get_stats() if hasattr(crawler, "stats") else {}
        finish_reason = stats.get("finish_reason")

        # Inspect final job status
        if database.is_cancellation_requested(job_id, db_path=db_path):
            database.update_crawl_job_status(job_id, CrawlJobStatus.CANCELLED, db_path=db_path)
            logger.info("Job %d finished with status CANCELLED.", job_id)
            final_outcome = "CANCELLED"
            stop_reason = finish_reason or "cancelled"
        else:
            database.update_crawl_job_status(job_id, CrawlJobStatus.COMPLETED, db_path=db_path)
            logger.info("Job %d finished with status COMPLETED.", job_id)
            final_outcome = "COMPLETED"
            stop_reason = finish_reason or "finished"

        database.finalize_crawl_job_metrics(
            job_id=job_id,
            scrapy_stats=stats,
            stop_reason=stop_reason,
            final_outcome=final_outcome,
            db_path=db_path,
        )
        return 0

    except Exception as e:
        logger.exception("Job %d encountered critical error: %s", job_id, e)
        stats = crawler.stats.get_stats() if hasattr(crawler, "stats") else {}
        database.update_crawl_job_status(
            job_id, CrawlJobStatus.FAILED, error_message=str(e), db_path=db_path
        )
        database.finalize_crawl_job_metrics(
            job_id=job_id,
            scrapy_stats=stats,
            stop_reason=f"error: {e}",
            final_outcome="FAILED",
            db_path=db_path,
        )
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run a Scrapy crawl job in an isolated process.")
    parser.add_argument("--job-id", type=int, required=True, help="Database ID of the crawl job.")
    parser.add_argument("--db-path", type=str, default=None, help="Optional SQLite database path.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    sys.exit(run_job(args.job_id, args.db_path))


if __name__ == "__main__":
    main()
