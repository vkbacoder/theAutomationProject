"""Scrapy Item Pipeline for persisting crawl results to SQLite."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import database
from models import CrawlPage, CrawlPageStatus, ScrapeEvidence

logger = logging.getLogger(__name__)


class DatabasePipeline:
    """Pipeline to persist crawled pages and link evidence to company leads."""

    def __init__(self, db_path: Optional[str] = None, crawler=None):
        self.db_path = db_path
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        db_path = crawler.settings.get("DB_PATH") or database.get_db_path()
        return cls(db_path=db_path, crawler=crawler)

    def process_item(self, item, spider=None):
        job_id = int(item.get("job_id"))
        status_str = item.get("status", "SUCCESS")
        page_status = CrawlPageStatus(status_str)

        # Compute content hash if text exists
        raw_text = item.get("extracted_text") or ""
        content_hash = item.get("content_hash")
        if not content_hash and raw_text:
            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        evidence_id = None
        # Resolve active spider instance (direct argument or via crawler instance)
        active_spider = spider or getattr(self.crawler, "spider", None)
        company_id = getattr(active_spider, "company_id", None)
        if company_id and page_status == CrawlPageStatus.SUCCESS:
            try:
                evidence = ScrapeEvidence(
                    company_id=company_id,
                    source_url=item.get("final_url") or item.get("original_url"),
                    http_status=item.get("http_status"),
                    title=item.get("title"),
                    meta_description=(item.get("metadata_json") or {}).get("description"),
                    canonical_url=item.get("final_url"),
                    raw_text=raw_text,
                    headings_json=item.get("headings_json"),
                    metadata_json=item.get("metadata_json"),
                    links_count=item.get("links_count", 0),
                    word_count=item.get("word_count", 0),
                    scraped_at=item.get("retrieved_at"),
                )
                saved_ev = database.add_scrape_evidence(evidence, db_path=self.db_path)
                evidence_id = saved_ev.id
            except Exception as e:
                logger.error("Failed to save ScrapeEvidence for company %s: %s", company_id, e)

        # Save to crawl_pages table
        crawl_page = CrawlPage(
            job_id=job_id,
            original_url=item.get("original_url"),
            final_url=item.get("final_url"),
            http_status=item.get("http_status"),
            depth=item.get("depth", 0),
            discovery_source_url=item.get("discovery_source_url"),
            title=item.get("title"),
            extracted_text=raw_text,
            headings_json=item.get("headings_json"),
            metadata_json=item.get("metadata_json"),
            links_count=item.get("links_count", 0),
            word_count=item.get("word_count", 0),
            content_hash=content_hash,
            status=page_status,
            error_message=item.get("error_message"),
            evidence_id=evidence_id,
            retrieved_at=item.get("retrieved_at"),
        )

        try:
            database.save_crawled_page(crawl_page, db_path=self.db_path)

            # Update job progress in database
            if page_status == CrawlPageStatus.SUCCESS:
                database.increment_crawl_job_progress(
                    job_id=job_id,
                    pages_crawled_inc=1,
                    db_path=self.db_path,
                )
            elif page_status == CrawlPageStatus.FAILED:
                database.increment_crawl_job_progress(
                    job_id=job_id,
                    pages_failed_inc=1,
                    db_path=self.db_path,
                )
        except Exception as e:
            logger.error("Failed to persist crawl page item for job %s: %s", job_id, e)

        return item
