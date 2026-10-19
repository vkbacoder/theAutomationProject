"""Scrapy Item Pipeline for persisting crawl results to SQLite."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import database
from dedup import infer_company_name_from_title, normalize_company_name, normalize_domain
from models import CompanyProfile, CrawlPage, CrawlPageStatus, ResearchStatus, ScrapeEvidence, WorkflowType

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

        # Check if item is a DiscoveredDocumentItem
        if "document_url" in item:
            try:
                from models import DiscoveredDocument
                doc = DiscoveredDocument(
                    job_id=job_id,
                    source_page_url=item.get("source_page_url") or "",
                    document_url=item.get("document_url") or "",
                    file_name=item.get("file_name") or "",
                    file_format=item.get("file_format") or "UNKNOWN",
                    content_type=item.get("content_type"),
                    file_size_bytes=item.get("file_size_bytes") or 0,
                    download_status=item.get("download_status") or "PENDING",
                    extraction_status=item.get("extraction_status") or "PENDING",
                    error_message=item.get("error_message"),
                    extracted_text=item.get("extracted_text"),
                    metadata_json=item.get("metadata_json"),
                    sections_json=item.get("sections_json"),
                )
                database.save_discovered_document(doc, db_path=self.db_path)
            except Exception as e:
                logger.error("Failed to save discovered document for job %d: %s", job_id, e)
            return item

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

        # Fallback: if company_id is not bound to spider, resolve from job or derive from page domain
        if not company_id and page_status == CrawlPageStatus.SUCCESS:
            try:
                job = database.get_crawl_job(job_id, db_path=self.db_path)
                if job and job.company_id:
                    company_id = job.company_id
                else:
                    page_url = item.get("final_url") or item.get("original_url")
                    domain = normalize_domain(page_url)
                    workflow_val = getattr(active_spider, "workflow", None) or (job.workflow.value if job else "GENERAL")
                    if domain:
                        existing = database.find_company_by_domain(domain, workflow_val, db_path=self.db_path)
                        if existing:
                            company_id = existing.id
                        else:
                            inferred = infer_company_name_from_title(item.get("title"), domain)
                            new_comp = CompanyProfile(
                                company_name=inferred,
                                normalized_name=normalize_company_name(inferred),
                                domain=domain,
                                website_url=page_url,
                                workflow=WorkflowType(workflow_val) if isinstance(workflow_val, str) else workflow_val,
                                research_status=ResearchStatus.SCRAPED,
                            )
                            created = database.create_company(new_comp, db_path=self.db_path)
                            company_id = created.id
                if active_spider and company_id:
                    active_spider.company_id = company_id
            except Exception as e:
                logger.error("Failed to auto-resolve company for evidence in job %s: %s", job_id, e)

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
