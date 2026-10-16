"""Recursive Scrapy Spider for Lead Research & Qualification.

Reuses existing HTML parsing and extraction functions from scraper.py.
Enforces depth limits, domain restrictions, robots.txt compliance,
and safe link recursion.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urldefrag, urlparse

import scrapy
from scrapy.http import Response
from twisted.python.failure import Failure

import database
from crawler.items import CrawledPageItem
from dedup import normalize_domain
from scraper import parse_html_data, clean_text

logger = logging.getLogger(__name__)


def normalize_crawl_url(url: str) -> Optional[str]:
    """Normalize URL by stripping fragments and trailing whitespace."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    defragged, _ = urldefrag(url)
    parsed = urlparse(defragged)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    # Reconstruct normalized URL with lowercase scheme and host
    norm_netloc = parsed.hostname.lower()
    if parsed.port and parsed.port not in (80, 443):
        norm_netloc = f"{norm_netloc}:{parsed.port}"
    path = parsed.path or "/"
    norm_url = f"{parsed.scheme.lower()}://{norm_netloc}{path}"
    if parsed.query:
        norm_url = f"{norm_url}?{parsed.query}"
    return norm_url


class RecursiveLeadSpider(scrapy.Spider):
    """Spider that recursively crawls a domain, extracting structured evidence."""

    name = "recursive_lead_spider"

    def __init__(
        self,
        job_id: int | str,
        seed_url: str,
        allowed_domains: Optional[str | List[str]] = None,
        max_depth: int | str = 2,
        max_pages: int | str = 100,
        max_pages_per_domain: int | str = 30,
        workflow: str = "GENERAL",
        company_id: Optional[int | str] = None,
        db_path: Optional[str] = None,
        enable_sitemap: bool | str = True,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.job_id = int(job_id)
        self.seed_url = seed_url.strip()
        self.max_depth = int(max_depth)
        self.max_pages = int(max_pages)
        self.max_pages_per_domain = int(max_pages_per_domain)
        self.workflow = workflow
        self.company_id = int(company_id) if company_id is not None and str(company_id).isdigit() else None
        self.db_path = db_path
        self.enable_sitemap = str(enable_sitemap).lower() in ("true", "1", "yes")

        # Parse allowed domains
        if isinstance(allowed_domains, str):
            try:
                self.allowed_domains = json.loads(allowed_domains)
            except Exception:
                self.allowed_domains = [d.strip() for d in allowed_domains.split(",") if d.strip()]
        elif isinstance(allowed_domains, list):
            self.allowed_domains = allowed_domains
        else:
            self.allowed_domains = []

        # If allowed domains not specified, derive from seed URL
        seed_domain = normalize_domain(self.seed_url)
        if seed_domain and not self.allowed_domains:
            self.allowed_domains = [seed_domain]

        # Initialize start_urls for Scrapy engine compatibility
        norm_seed = normalize_crawl_url(self.seed_url)
        self.start_urls = [norm_seed] if norm_seed else []

        # Tracking state
        self.domain_page_counts: Dict[str, int] = {}
        self.pages_crawled_count = 0
        self.discovered_urls: Set[str] = set()
        if norm_seed:
            self.discovered_urls.add(norm_seed)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=scrapy.signals.spider_closed)
        return spider

    def spider_closed(self, spider, reason):
        """Persist runtime Scrapy metrics on spider closure."""
        try:
            stats = self.crawler.stats.get_stats() if hasattr(self.crawler, "stats") else {}
            database.finalize_crawl_job_metrics(
                job_id=self.job_id,
                scrapy_stats=stats,
                stop_reason=reason,
                db_path=self.db_path,
            )
        except Exception as e:
            logger.error("Failed to record metrics in spider_closed: %s", e)

    async def start(self):
        """Scrapy 2.13+ asynchronous start generator."""
        norm_seed = normalize_crawl_url(self.seed_url)
        if not norm_seed:
            logger.error("Invalid seed URL: %s", self.seed_url)
            self.record_url_error(self.seed_url, "Invalid seed URL format", error_type="ValidationError")
            return

        yield scrapy.Request(
            url=norm_seed,
            callback=self.parse,
            errback=self.errback,
            meta={"depth": 0, "discovery_source_url": None, "original_url": norm_seed},
            dont_filter=False,
        )

        # Optional Sitemap discovery
        if self.enable_sitemap:
            parsed = urlparse(norm_seed)
            sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            yield scrapy.Request(
                url=sitemap_url,
                callback=self.parse_sitemap,
                errback=self.sitemap_errback,
                meta={"depth": 1, "is_sitemap": True},
                dont_filter=True,
            )

    def start_requests(self):
        """Synchronous start_requests generator fallback for earlier Scrapy versions."""
        norm_seed = normalize_crawl_url(self.seed_url)
        if not norm_seed:
            logger.error("Invalid seed URL: %s", self.seed_url)
            self.record_url_error(self.seed_url, "Invalid seed URL format", error_type="ValidationError")
            return

        yield scrapy.Request(
            url=norm_seed,
            callback=self.parse,
            errback=self.errback,
            meta={"depth": 0, "discovery_source_url": None, "original_url": norm_seed},
            dont_filter=False,
        )

        # Optional Sitemap discovery
        if self.enable_sitemap:
            parsed = urlparse(norm_seed)
            sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            yield scrapy.Request(
                url=sitemap_url,
                callback=self.parse_sitemap,
                errback=self.sitemap_errback,
                meta={"depth": 1, "is_sitemap": True},
                dont_filter=True,
            )

    def parse(self, response: Response):
        """Parse HTML page, yield evidence item, and discover subsequent links."""
        # 1. Cancellation check
        if database.is_cancellation_requested(self.job_id, db_path=self.db_path):
            logger.info("Job %s cancelled. Stopping spider.", self.job_id)
            self.crawler.engine.close_spider(self, "cancelled")
            return

        # 2. Check total page limit
        if self.pages_crawled_count >= self.max_pages:
            logger.info("Reached max pages limit (%d). Closing spider.", self.max_pages)
            self.crawler.engine.close_spider(self, "max_pages_reached")
            return

        current_depth = response.meta.get("depth", 0)
        original_url = response.meta.get("original_url") or response.url
        discovery_source = response.meta.get("discovery_source_url")

        # 3. Domain page limit check
        page_domain = normalize_domain(response.url)
        current_domain_count = self.domain_page_counts.get(page_domain, 0)
        if current_domain_count >= self.max_pages_per_domain:
            logger.info("Reached domain page limit (%d) for %s", self.max_pages_per_domain, page_domain)
            return

        self.domain_page_counts[page_domain] = current_domain_count + 1
        self.pages_crawled_count += 1

        # 4. Extract structured content using existing parse_html_data from scraper.py
        html_content = response.text
        parsed = parse_html_data(html_content, base_url=response.url)

        # 5. Yield CrawledPageItem
        now_str = datetime.datetime.now(timezone.utc).isoformat()
        item = CrawledPageItem(
            job_id=self.job_id,
            original_url=original_url,
            final_url=response.url,
            http_status=response.status,
            depth=current_depth,
            discovery_source_url=discovery_source,
            title=parsed["title"],
            extracted_text=parsed["text"],
            headings_json=parsed["headings"],
            metadata_json=parsed["metadata"],
            links_count=len(parsed["links"]),
            word_count=parsed["word_count"],
            status="SUCCESS",
            error_message=None,
            retrieved_at=now_str,
        )
        yield item

        # 6. Recursive link discovery (if depth < max_depth)
        if current_depth < self.max_depth:
            discovered_batch_count = 0
            for link_item in parsed["links"]:
                link_url = link_item.url
                norm_link = normalize_crawl_url(link_url)
                if not norm_link:
                    continue

                link_domain = normalize_domain(norm_link)
                # Check domain allowance
                if not self.is_domain_allowed(link_domain):
                    continue

                # Check per-domain limits
                if self.domain_page_counts.get(link_domain, 0) >= self.max_pages_per_domain:
                    continue

                if norm_link not in self.discovered_urls:
                    self.discovered_urls.add(norm_link)
                    discovered_batch_count += 1

                yield scrapy.Request(
                    url=norm_link,
                    callback=self.parse,
                    errback=self.errback,
                    meta={
                        "depth": current_depth + 1,
                        "discovery_source_url": response.url,
                        "original_url": norm_link,
                    },
                    dont_filter=False,  # Let Scrapy dupefilter handle duplicate requests
                )

            if discovered_batch_count > 0:
                database.increment_crawl_job_progress(
                    job_id=self.job_id,
                    discovered_inc=discovered_batch_count,
                    db_path=self.db_path,
                )

    def parse_sitemap(self, response: Response):
        """Parse sitemap.xml to seed discovered URLs within domain."""
        if response.status != 200:
            return

        try:
            # Simple XML loc extraction
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.body)
            # Handle XML namespace
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locs = root.findall(".//ns:loc", ns)
            if not locs:
                locs = root.findall(".//loc")

            discovered_batch = 0
            for loc in locs:
                if loc.text:
                    url = loc.text.strip()
                    norm_url = normalize_crawl_url(url)
                    if not norm_url:
                        continue
                    domain = normalize_domain(norm_url)
                    if self.is_domain_allowed(domain):
                        if norm_url not in self.discovered_urls:
                            self.discovered_urls.add(norm_url)
                            discovered_batch += 1
                            yield scrapy.Request(
                                url=norm_url,
                                callback=self.parse,
                                errback=self.errback,
                                meta={
                                    "depth": 1,
                                    "discovery_source_url": response.url,
                                    "original_url": norm_url,
                                },
                            )
            if discovered_batch > 0:
                database.increment_crawl_job_progress(
                    job_id=self.job_id,
                    discovered_inc=discovered_batch,
                    db_path=self.db_path,
                )
        except Exception as e:
            logger.debug("Sitemap parsing encountered non-fatal error: %s", e)

    def sitemap_errback(self, failure: Failure):
        """Silently ignore sitemap discovery 404 or connection errors."""
        logger.debug("Sitemap discovery skipped or failed: %s", failure.value)

    def errback(self, failure: Failure):
        """Capture HTTP, DNS, or timeout errors and persist failed page evidence."""
        request = failure.request
        url = request.url if request else "Unknown URL"
        depth = request.meta.get("depth", 0) if request else 0
        discovery_source = request.meta.get("discovery_source_url") if request else None

        error_msg = str(failure.value)
        status_code = None
        if hasattr(failure.value, "response") and failure.value.response:
            status_code = failure.value.response.status

        logger.warning("Crawl error on %s: %s", url, error_msg)

        now_str = datetime.datetime.now(timezone.utc).isoformat()
        item = CrawledPageItem(
            job_id=self.job_id,
            original_url=url,
            final_url=url,
            http_status=status_code,
            depth=depth,
            discovery_source_url=discovery_source,
            title=None,
            extracted_text=None,
            headings_json=None,
            metadata_json=None,
            links_count=0,
            word_count=0,
            status="FAILED",
            error_message=error_msg,
            retrieved_at=now_str,
        )
        yield item

    def is_domain_allowed(self, domain: Optional[str]) -> bool:
        """Check if a domain matches the allowed domain list."""
        if not domain:
            return False
        clean_domain = normalize_domain(domain)
        for allowed in self.allowed_domains:
            clean_allowed = normalize_domain(allowed)
            if clean_domain == clean_allowed or clean_domain.endswith(f".{clean_allowed}"):
                return True
        return False

    def record_url_error(self, url: str, error_message: str, error_type: str = "Error"):
        """Record an error directly to the database pipeline."""
        now_str = datetime.datetime.now(timezone.utc).isoformat()
        item = CrawledPageItem(
            job_id=self.job_id,
            original_url=url,
            final_url=url,
            http_status=400,
            depth=0,
            discovery_source_url=None,
            title=None,
            extracted_text=None,
            headings_json=None,
            metadata_json=None,
            links_count=0,
            word_count=0,
            status="FAILED",
            error_message=f"[{error_type}] {error_message}",
            retrieved_at=now_str,
        )
        # Yielding or saving via database
        try:
            page = database.CrawlPage(
                job_id=self.job_id,
                original_url=url,
                final_url=url,
                http_status=400,
                depth=0,
                status=database.CrawlPageStatus.FAILED,
                error_message=f"[{error_type}] {error_message}",
                retrieved_at=now_str,
            )
            database.save_crawled_page(page, db_path=self.db_path)
            database.increment_crawl_job_progress(job_id=self.job_id, pages_failed_inc=1, db_path=self.db_path)
        except Exception as e:
            logger.error("Failed to record url error: %s", e)

    def record_url_skipped(self, url: str, reason: str):
        """Record a skipped page (e.g. non-HTML content)."""
        now_str = datetime.datetime.now(timezone.utc).isoformat()
        try:
            page = database.CrawlPage(
                job_id=self.job_id,
                original_url=url,
                final_url=url,
                http_status=200,
                depth=0,
                status=database.CrawlPageStatus.SKIPPED,
                error_message=reason,
                retrieved_at=now_str,
            )
            database.save_crawled_page(page, db_path=self.db_path)
        except Exception as e:
            logger.error("Failed to record skipped url: %s", e)
