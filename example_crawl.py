"""Minimal example demonstrating recursive crawling with Scrapy in the Lead Research System.

Creates a crawl job, runs the background worker for that job, and displays
the discovered pages, recursive depth, content hashes, and structured evidence.
"""

from __future__ import annotations

import sys
import time

import database
from crawler_worker import CrawlerWorker
from models import CrawlJob, CrawlJobStatus, WorkflowType


def run_demonstration():
    print("=" * 70)
    print("   AI Lead Research System - Scrapy Recursive Crawling Demo")
    print("=" * 70)

    # 1. Initialize DB and create a crawl job
    database.init_db()

    target_seed = "https://quotes.toscrape.com/"
    print(f"\n[1] Submitting Crawl Job...")
    print(f"    Seed URL:             {target_seed}")
    print(f"    Allowed Domains:      ['quotes.toscrape.com']")
    print(f"    Max Depth:            1")
    print(f"    Max Pages:            3")
    print(f"    Workflow:             GENERAL")

    job = CrawlJob(
        seed_url=target_seed,
        allowed_domains=["quotes.toscrape.com"],
        workflow=WorkflowType.GENERAL,
        max_depth=1,
        max_pages=3,
        max_pages_per_domain=3,
    )
    saved_job = database.create_crawl_job(job)
    print(f"    [+] Job #{saved_job.id} created with status '{saved_job.status.value}'")

    # 2. Run the crawler worker to process the job
    print(f"\n[2] Executing Crawler Worker (subprocess isolation)...")
    worker = CrawlerWorker()
    worker.start(run_once=True)

    # 3. Retrieve final job state
    finished_job = database.get_crawl_job(saved_job.id)
    print(f"\n[3] Job Execution Finished:")
    print(f"    Final Status:         {finished_job.status.value}")
    print(f"    Pages Crawled:        {finished_job.pages_crawled}")
    print(f"    Pages Failed:         {finished_job.pages_failed}")
    print(f"    Discovered URLs:      {finished_job.discovered_urls_count}")
    print(f"    Started At:           {finished_job.started_at}")
    print(f"    Finished At:          {finished_job.finished_at}")

    # 4. Display crawled evidence pages
    pages = database.get_crawled_pages(saved_job.id)
    print(f"\n[4] Crawled Page Evidence ({len(pages)} pages retrieved):")
    print("-" * 70)
    for p in pages:
        print(f"  * Depth {p.depth} | HTTP {p.http_status} | {p.status.value}")
        print(f"    Title:        {p.title}")
        print(f"    URL:          {p.final_url or p.original_url}")
        print(f"    Discovered:   {p.discovery_source_url or 'Seed URL'}")
        print(f"    Word Count:   {p.word_count} words")
        print(f"    Content Hash: {p.content_hash[:16]}... (SHA-256)" if p.content_hash else "    Content Hash: None")
        print()

    print("=" * 70)
    print("Demo completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    run_demonstration()
