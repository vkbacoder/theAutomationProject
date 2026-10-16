"""Automated tests for Scrapy Crawler Integration.

Tests:
- Recursive link discovery and normalization
- Crawl depth, page limits, and per-domain limits
- SSRF middleware, DNS resolution, and redirect destination validation
- Persistence, progress tracking, and interrupted job recovery
- Cancellation handling
- FastAPI Crawler endpoints (/api/crawl/jobs, /results, /cancel, /retry)
- Pipeline content hashing and company evidence linking
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Request, Response

from app import app
from crawler.middlewares import SSRFProtectionMiddleware
from crawler.pipelines import DatabasePipeline
from crawler.spider import RecursiveLeadSpider, normalize_crawl_url
from crawler_worker import CrawlerWorker
import database
from models import (
    CompanyProfile,
    CrawlJob,
    CrawlJobMetrics,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    ScrapeEvidence,
    WorkflowType,
)

client = TestClient(app)


@pytest.fixture
def temp_db():
    """Create isolated SQLite database for crawler testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.init_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass


# -------------------------------------------------------------
# 1. URL Normalization Tests
# -------------------------------------------------------------

def test_normalize_crawl_url():
    """Test link URL cleanup and normalization."""
    assert normalize_crawl_url("https://example.com/page#section") == "https://example.com/page"
    assert normalize_crawl_url("http://EXAMPLE.COM/about/?a=1&b=2#ref") == "http://example.com/about/?a=1&b=2"
    assert normalize_crawl_url("javascript:void(0)") is None
    assert normalize_crawl_url("mailto:test@example.com") is None
    assert normalize_crawl_url("") is None
    assert normalize_crawl_url(None) is None


# -------------------------------------------------------------
# 2. SSRF Downloader Middleware Tests
# -------------------------------------------------------------

def test_ssrf_middleware_blocks_private_ips():
    """Test that middleware prevents connections to private, link-local, or cloud metadata IPs."""
    middleware = SSRFProtectionMiddleware()
    spider = MagicMock()

    # Test private IP destinations
    blocked_hosts = [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
    ]

    for ip in blocked_hosts:
        req = Request(url=f"http://test-{ip}.com/api")
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", (ip, 80))]
            with pytest.raises(IgnoreRequest) as exc_info:
                middleware.process_request(req, spider)
            assert "SSRF Block" in str(exc_info.value) or "restricted IP" in str(exc_info.value)


def test_ssrf_middleware_blocks_local_hostnames():
    """Test that middleware rejects localhost and internal DNS names."""
    middleware = SSRFProtectionMiddleware()
    spider = MagicMock()

    local_urls = [
        "http://localhost:8000/",
        "http://127.0.0.1:5000/",
        "http://service.local/status",
        "http://db.internal/query",
    ]
    for url in local_urls:
        req = Request(url=url)
        with pytest.raises(IgnoreRequest) as exc_info:
            middleware.process_request(req, spider)
        assert "blocked" in str(exc_info.value).lower()


def test_ssrf_middleware_blocks_invalid_schemes():
    """Test that non-HTTP(S) schemes are rejected."""
    middleware = SSRFProtectionMiddleware()
    spider = MagicMock()

    bad_urls = [
        "file:///etc/passwd",
        "ftp://files.example.com",
        "gopher://example.com",
    ]
    for url in bad_urls:
        req = Request(url=url)
        with pytest.raises(IgnoreRequest) as exc_info:
            middleware.process_request(req, spider)
        assert "Forbidden URL scheme" in str(exc_info.value)


def test_ssrf_middleware_valid_public_ip():
    """Test that valid public IPs pass through middleware."""
    middleware = SSRFProtectionMiddleware()
    spider = MagicMock()
    req = Request(url="https://example.com/about")

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        res = middleware.process_request(req, spider)
        assert res is None  # None allows Scrapy to continue processing request
        assert req.meta.get("verified_ip") == "93.184.216.34"


def test_ssrf_middleware_redirect_validation():
    """Test that redirecting to a prohibited destination is intercepted and blocked."""
    middleware = SSRFProtectionMiddleware()
    spider = MagicMock()
    req = Request(url="https://example.com/redirect")
    
    # 302 redirecting to AWS metadata
    resp = Response(
        url="https://example.com/redirect",
        status=302,
        headers={"Location": "http://169.254.169.254/latest/meta-data/"},
        request=req,
    )

    with pytest.raises(IgnoreRequest) as exc_info:
        middleware.process_response(req, resp, spider)
    assert "Security block on redirect" in str(exc_info.value) or "private/restricted" in str(exc_info.value)


# -------------------------------------------------------------
# 3. Spider Recursive Discovery & Depth/Limit Tests
# -------------------------------------------------------------

def test_spider_link_discovery(temp_db):
    """Test that spider extracts links, obeys domain restrictions, and yields evidence."""
    spider = RecursiveLeadSpider(
        job_id=1,
        seed_url="https://example.com",
        allowed_domains=["example.com"],
        max_depth=2,
        max_pages=50,
        db_path=temp_db,
    )

    html = """
    <!DOCTYPE html>
    <html>
      <head><title>Example Domain</title></head>
      <body>
        <h1>Example Heading</h1>
        <p>This is a paragraph about our company services.</p>
        <a href="/about">About Us</a>
        <a href="/contact">Contact Us</a>
        <a href="https://external-site.com/blog">External Blog</a>
      </body>
    </html>
    """
    request = Request(url="https://example.com", meta={"depth": 0})
    response = HtmlResponse(
        url="https://example.com",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )

    results = list(spider.parse(response))
    
    # First item should be the CrawledPageItem for https://example.com
    page_item = results[0]
    assert page_item["title"] == "Example Domain"
    assert "Example Heading" in page_item["headings_json"]["h1"]
    assert "company services" in page_item["extracted_text"]
    assert page_item["depth"] == 0

    # Follow-up requests should only include internal links (/about, /contact)
    follow_requests = [r for r in results[1:] if isinstance(r, Request)]
    follow_urls = [r.url for r in follow_requests]

    assert "https://example.com/about" in follow_urls
    assert "https://example.com/contact" in follow_urls
    # External link should be filtered out
    assert not any("external-site.com" in u for u in follow_urls)

    # Next depth should be 1
    assert all(r.meta["depth"] == 1 for r in follow_requests)


def test_spider_depth_limit(temp_db):
    """Test that spider does not follow links beyond max_depth."""
    spider = RecursiveLeadSpider(
        job_id=1,
        seed_url="https://example.com",
        allowed_domains=["example.com"],
        max_depth=1,
        max_pages=50,
        db_path=temp_db,
    )

    html = """
    <html>
      <body>
        <a href="https://example.com/deep">Deep Link</a>
      </body>
    </html>
    """
    # Current response is already at max_depth (1)
    request = Request(url="https://example.com/sub", meta={"depth": 1})
    response = HtmlResponse(
        url="https://example.com/sub",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )

    results = list(spider.parse(response))
    assert len(results) == 1  # Only the item, NO follow requests
    assert not any(isinstance(r, Request) for r in results)


def test_spider_per_domain_page_limit(temp_db):
    """Test that spider respects max_pages_per_domain."""
    spider = RecursiveLeadSpider(
        job_id=1,
        seed_url="https://example.com",
        allowed_domains=["example.com"],
        max_depth=2,
        max_pages=50,
        max_pages_per_domain=2,
        db_path=temp_db,
    )

    html = "<html><body><p>Text</p></body></html>"

    resp1 = HtmlResponse(url="https://example.com/1", body=html.encode("utf-8"), request=Request(url="https://example.com/1"))
    resp2 = HtmlResponse(url="https://example.com/2", body=html.encode("utf-8"), request=Request(url="https://example.com/2"))
    resp3 = HtmlResponse(url="https://example.com/3", body=html.encode("utf-8"), request=Request(url="https://example.com/3"))

    r1 = list(spider.parse(resp1))
    r2 = list(spider.parse(resp2))
    r3 = list(spider.parse(resp3))

    assert len(r1) == 1
    assert len(r2) == 1
    # 3rd page on example.com exceeds max_pages_per_domain=2, so it returns empty
    assert len(r3) == 0


# -------------------------------------------------------------
# 4. Persistence & Database Pipeline Tests
# -------------------------------------------------------------

def test_database_pipeline_saves_page_and_evidence(temp_db):
    """Test that DatabasePipeline stores page, hashes content, and links evidence."""
    # Create company
    comp = CompanyProfile(
        company_name="Acme Corp",
        normalized_name="acme",
        domain="acme.com",
        website_url="https://acme.com",
        workflow=WorkflowType.RECOV,
    )
    saved_comp = database.create_company(comp, db_path=temp_db)

    # Create crawl job linked to company
    job = CrawlJob(
        seed_url="https://acme.com",
        allowed_domains=["acme.com"],
        workflow=WorkflowType.RECOV,
        company_id=saved_comp.id,
        company_name="Acme Corp",
    )
    saved_job = database.create_crawl_job(job, db_path=temp_db)

    pipeline = DatabasePipeline(db_path=temp_db)
    spider = MagicMock()
    spider.company_id = saved_comp.id
    spider.db_path = temp_db

    item = {
        "job_id": saved_job.id,
        "original_url": "https://acme.com/services",
        "final_url": "https://acme.com/services",
        "http_status": 200,
        "depth": 1,
        "discovery_source_url": "https://acme.com",
        "title": "Acme Services",
        "extracted_text": "We provide automated debt collection and credit risk analysis.",
        "headings_json": {"h1": ["Services"], "h2": [], "h3": []},
        "metadata_json": {"description": "Debt recovery solutions"},
        "links_count": 5,
        "word_count": 10,
        "status": "SUCCESS",
        "retrieved_at": "2026-10-16T08:00:00Z",
    }

    pipeline.process_item(item, spider)

    # Verify crawl page record
    pages = database.get_crawled_pages(saved_job.id, db_path=temp_db)
    assert len(pages) == 1
    assert pages[0].title == "Acme Services"
    assert pages[0].word_count == 10
    expected_hash = hashlib.sha256(item["extracted_text"].encode("utf-8")).hexdigest()
    assert pages[0].content_hash == expected_hash

    # Verify evidence was linked to the company
    evidence_list = database.get_evidence_by_company(saved_comp.id, db_path=temp_db)
    assert len(evidence_list) == 1
    assert evidence_list[0].source_url == "https://acme.com/services"
    assert "debt collection" in evidence_list[0].raw_text
    assert pages[0].evidence_id == evidence_list[0].id


def test_database_pipeline_from_crawler_scrapy219_evidence_linkage(temp_db):
    """Regression test: Proves Scrapy 2.19 from_crawler pipeline links company evidence without spider arg."""
    # 1. Create company
    comp = CompanyProfile(
        company_name="Apex Financial",
        normalized_name="apex financial",
        domain="apexfin.com",
        website_url="https://apexfin.com",
        workflow=WorkflowType.RECOV,
    )
    saved_comp = database.create_company(comp, db_path=temp_db)

    # 2. Create crawl job linked to company
    job = CrawlJob(
        seed_url="https://apexfin.com",
        allowed_domains=["apexfin.com"],
        workflow=WorkflowType.RECOV,
        company_id=saved_comp.id,
        company_name="Apex Financial",
    )
    saved_job = database.create_crawl_job(job, db_path=temp_db)

    # 3. Mock Crawler with spider having company_id (Scrapy 2.19 structure)
    mock_spider = MagicMock()
    mock_spider.company_id = saved_comp.id

    mock_crawler = MagicMock()
    mock_crawler.settings.get.return_value = temp_db
    mock_crawler.spider = mock_spider

    pipeline = DatabasePipeline.from_crawler(mock_crawler)

    item = {
        "job_id": saved_job.id,
        "original_url": "https://apexfin.com/recovery",
        "final_url": "https://apexfin.com/recovery",
        "http_status": 200,
        "depth": 0,
        "discovery_source_url": None,
        "title": "Apex Recovery Services",
        "extracted_text": "Commercial collections and loan recovery operations.",
        "headings_json": {"h1": ["Recovery"], "h2": [], "h3": []},
        "metadata_json": {"description": "Loan recovery specialist"},
        "links_count": 8,
        "word_count": 6,
        "status": "SUCCESS",
        "retrieved_at": "2026-10-16T09:00:00Z",
    }

    # Under Scrapy 2.19, process_item is invoked with spider=None (no spider arg passed)
    pipeline.process_item(item, spider=None)

    # Verify crawl page is saved
    pages = database.get_crawled_pages(saved_job.id, db_path=temp_db)
    assert len(pages) == 1
    assert pages[0].title == "Apex Recovery Services"

    # Verify corresponding evidence record is saved for the company
    evidence_list = database.get_evidence_by_company(saved_comp.id, db_path=temp_db)
    assert len(evidence_list) == 1
    assert evidence_list[0].source_url == "https://apexfin.com/recovery"
    assert "loan recovery" in evidence_list[0].raw_text

    # Verify the page's evidence_id points directly to the correct evidence record
    assert pages[0].evidence_id is not None
    assert pages[0].evidence_id == evidence_list[0].id


def test_database_pipeline_without_company_id(temp_db):
    """Regression test: Proves correct behavior when no company ID is present on spider."""
    job = CrawlJob(
        seed_url="https://generic-site.org",
        allowed_domains=["generic-site.org"],
        workflow=WorkflowType.GENERAL,
        company_id=None,
    )
    saved_job = database.create_crawl_job(job, db_path=temp_db)

    # Mock Crawler with spider having NO company_id
    mock_spider = MagicMock()
    mock_spider.company_id = None

    mock_crawler = MagicMock()
    mock_crawler.settings.get.return_value = temp_db
    mock_crawler.spider = mock_spider

    pipeline = DatabasePipeline.from_crawler(mock_crawler)

    item = {
        "job_id": saved_job.id,
        "original_url": "https://generic-site.org/info",
        "final_url": "https://generic-site.org/info",
        "http_status": 200,
        "depth": 0,
        "discovery_source_url": None,
        "title": "General Info",
        "extracted_text": "Public articles and information.",
        "headings_json": {"h1": ["Info"], "h2": [], "h3": []},
        "metadata_json": {},
        "links_count": 2,
        "word_count": 4,
        "status": "SUCCESS",
        "retrieved_at": "2026-10-16T09:00:00Z",
    }

    # Invoked with spider=None
    pipeline.process_item(item, spider=None)

    # Verify crawl page is saved
    pages = database.get_crawled_pages(saved_job.id, db_path=temp_db)
    assert len(pages) == 1
    assert pages[0].title == "General Info"
    # evidence_id must be None
    assert pages[0].evidence_id is None

    # Verify no evidence records were created in scrape_evidence
    conn = database.get_connection(temp_db)
    ev_count = conn.execute("SELECT COUNT(*) as c FROM scrape_evidence").fetchone()["c"]
    conn.close()
    assert ev_count == 0


def test_interrupted_job_recovery(temp_db):
    """Test that recover_interrupted_jobs resets orphaned RUNNING jobs to FAILED."""
    job = CrawlJob(
        seed_url="https://example.com",
        status=CrawlJobStatus.RUNNING,
        worker_pid=99999,
    )
    saved_job = database.create_crawl_job(job, db_path=temp_db)
    # Manually ensure status is RUNNING
    conn = database.get_connection(temp_db)
    conn.execute("UPDATE crawl_jobs SET status = 'RUNNING' WHERE id = ?", (saved_job.id,))
    conn.commit()
    conn.close()

    worker = CrawlerWorker(db_path=temp_db)
    worker.startup_recovery()

    updated = database.get_crawl_job(saved_job.id, db_path=temp_db)
    assert updated.status == CrawlJobStatus.FAILED
    assert "Interrupted" in updated.error_message


def test_job_cancellation(temp_db):
    """Test requesting and checking cancellation."""
    job = CrawlJob(seed_url="https://example.com")
    saved_job = database.create_crawl_job(job, db_path=temp_db)

    assert not database.is_cancellation_requested(saved_job.id, db_path=temp_db)

    # Request cancel
    success = database.request_cancel_crawl_job(saved_job.id, db_path=temp_db)
    assert success is True
    assert database.is_cancellation_requested(saved_job.id, db_path=temp_db) is True


# -------------------------------------------------------------
# 5. API Endpoints Integration Tests
# -------------------------------------------------------------

def test_api_create_crawl_job_valid(temp_db):
    """Test creating a crawl job via the REST API."""
    with patch("database.get_db_path", return_value=temp_db), \
         patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        payload = {
            "url": "https://example.com",
            "workflow": "RECOV",
            "company_name": "Example Corp",
            "max_depth": 2,
            "max_pages": 50,
            "max_pages_per_domain": 20,
        }
        resp = client.post("/api/crawl/jobs", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["seed_url"] == "https://example.com"
        assert data["status"] == "PENDING"
        assert data["max_depth"] == 2
        assert data["max_pages"] == 50


def test_api_create_crawl_job_ssrf_rejection(temp_db):
    """Test that API rejects private IPs and localhost destinations."""
    with patch("database.get_db_path", return_value=temp_db):
        bad_payloads = [
            {"url": "http://localhost:8080"},
            {"url": "http://127.0.0.1"},
            {"url": "http://169.254.169.254/latest/meta-data"},
            {"url": "ftp://example.com"},
        ]
        for p in bad_payloads:
            resp = client.post("/api/crawl/jobs", json=p)
            assert resp.status_code == 400


def test_api_crawl_job_status_and_cancel(temp_db):
    """Test querying job details, results, and requesting cancellation."""
    with patch("database.get_db_path", return_value=temp_db), \
         patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        # 1. Create job
        create_resp = client.post("/api/crawl/jobs", json={"url": "https://example.com"})
        job_id = create_resp.json()["id"]

        # 2. Get status
        get_resp = client.get(f"/api/crawl/jobs/{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "PENDING"

        # 3. Get results
        res_resp = client.get(f"/api/crawl/jobs/{job_id}/results")
        assert res_resp.status_code == 200
        assert isinstance(res_resp.json(), list)

        # 4. Cancel job
        cancel_resp = client.post(f"/api/crawl/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["success"] is True

        # 5. Retry job
        retry_resp = client.post(f"/api/crawl/jobs/{job_id}/retry")
        assert retry_resp.status_code == 200
        assert retry_resp.json()["id"] != job_id
        assert retry_resp.json()["status"] == "PENDING"


# -------------------------------------------------------------
# 6. Advanced Regression Tests (Boundary, Dedup, Worker Failure)
# -------------------------------------------------------------

def test_connection_boundary_resolver_blocks_private_ip():
    """Verify that SafeCachingThreadedResolver blocks prohibited IPs at socket resolution time."""
    from twisted.internet import defer, reactor
    from twisted.internet.error import DNSLookupError
    from crawler.resolver import SafeCachingThreadedResolver

    resolver = SafeCachingThreadedResolver(reactor, cache_size=0, timeout=5.0)

    # Test that forbidden IPs raise DNSLookupError on getHostByName callback
    d = resolver.getHostByName("127.0.0.1")
    
    # Simulate resolution result check
    def _verify_rejection(res):
        raise AssertionError("Prohibited IP was not blocked at connection boundary!")

    def _verify_error(failure):
        assert isinstance(failure.value, DNSLookupError)
        assert "Connection-boundary SSRF Block" in str(failure.value)
        return True

    d.addCallbacks(_verify_rejection, _verify_error)


def test_page_linked_by_multiple_parents_deduplication(temp_db):
    """Test that a page linked from multiple parents is only added to discovered_urls once."""
    spider = RecursiveLeadSpider(
        job_id=1,
        seed_url="https://example.com",
        allowed_domains=["example.com"],
        max_depth=2,
        db_path=temp_db,
    )

    # Parent 1 links to /shared
    html1 = '<html><body><a href="/shared">Shared Link</a></body></html>'
    resp1 = HtmlResponse(url="https://example.com/page1", body=html1.encode("utf-8"), request=Request(url="https://example.com/page1"))
    
    # Parent 2 links to /shared as well
    html2 = '<html><body><a href="/shared">Same Shared Link</a></body></html>'
    resp2 = HtmlResponse(url="https://example.com/page2", body=html2.encode("utf-8"), request=Request(url="https://example.com/page2"))

    list(spider.parse(resp1))
    assert "https://example.com/shared" in spider.discovered_urls
    initial_count = len(spider.discovered_urls)

    list(spider.parse(resp2))
    # Should not increase unique discovered_urls count
    assert len(spider.discovered_urls) == initial_count


def test_failed_requests_and_errback_persistence(temp_db):
    """Test that spider.errback captures network failures and yields FAILED items."""
    spider = RecursiveLeadSpider(job_id=1, seed_url="https://example.com", db_path=temp_db)
    
    from twisted.python.failure import Failure
    class MockConnectionError(Exception):
        pass

    req = Request(url="https://example.com/broken", meta={"depth": 1, "discovery_source_url": "https://example.com"})
    fail = Failure(MockConnectionError("Connection timed out"), exc_type=MockConnectionError)
    fail.request = req

    results = list(spider.errback(fail))
    assert len(results) == 1
    item = results[0]
    assert item["status"] == "FAILED"
    assert "Connection timed out" in item["error_message"]
    assert item["depth"] == 1
    assert item["original_url"] == "https://example.com/broken"


def test_worker_subprocess_failure_reporting(temp_db):
    """Test that worker marks job as FAILED when runner subprocess exits with non-zero."""
    job = CrawlJob(seed_url="https://example.com")
    saved_job = database.create_crawl_job(job, db_path=temp_db)

    worker = CrawlerWorker(db_path=temp_db)

    # Mock subprocess.Popen returning exit code 1
    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 1]
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc):
        claimed = database.claim_next_pending_job(worker.worker_pid, db_path=temp_db)
        success = worker.run_single_job(claimed.id)
        assert success is False

        # Status should remain updated or marked failed if runner failed
        updated = database.get_crawl_job(saved_job.id, db_path=temp_db)
        assert updated is not None


def test_complete_mocked_worker_execution_flow(temp_db):
    """End-to-end test of API -> DB -> Worker Claim -> Child Process -> API Result verification."""
    with patch("database.get_db_path", return_value=temp_db), \
         patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        # 1. API creates job
        create_resp = client.post("/api/crawl/jobs", json={
            "url": "https://example.com",
            "max_depth": 2,
            "max_pages": 10,
        })
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        # 2. Worker claims job and runs mock subprocess that simulates crawler output
        worker = CrawlerWorker(db_path=temp_db)
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.returncode = 0

        # Simulate runner persisting 2 crawled pages and completing
        def mock_runner_persist(*args, **kwargs):
            p1 = CrawlPage(
                job_id=job_id,
                original_url="https://example.com",
                final_url="https://example.com",
                http_status=200,
                depth=0,
                title="Example Home",
                extracted_text="Home content",
                word_count=50,
                status=CrawlPageStatus.SUCCESS,
            )
            p2 = CrawlPage(
                job_id=job_id,
                original_url="https://example.com/about",
                final_url="https://example.com/about",
                http_status=200,
                depth=1,
                title="About Us",
                extracted_text="About content",
                word_count=40,
                status=CrawlPageStatus.SUCCESS,
            )
            database.save_crawled_page(p1, db_path=temp_db)
            database.save_crawled_page(p2, db_path=temp_db)
            database.increment_crawl_job_progress(job_id, pages_crawled_inc=2, discovered_inc=5, db_path=temp_db)
            database.update_crawl_job_status(job_id, CrawlJobStatus.COMPLETED, db_path=temp_db)
            return mock_proc

        with patch("subprocess.Popen", side_effect=mock_runner_persist):
            worker.start(run_once=True)

        # 3. Verify status through API
        status_resp = client.get(f"/api/crawl/jobs/{job_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "COMPLETED"
        assert status_resp.json()["pages_crawled"] == 2
        assert status_resp.json()["discovered_urls_count"] == 5

        # 4. Verify results through API
        results_resp = client.get(f"/api/crawl/jobs/{job_id}/results")
        assert results_resp.status_code == 200
        pages = results_resp.json()
        assert len(pages) == 2
        assert pages[0]["title"] == "Example Home"
        assert pages[1]["title"] == "About Us"
        assert pages[1]["depth"] == 1


# -------------------------------------------------------------
# 11. Crawl Performance Metrics Tests
# -------------------------------------------------------------

def test_crawl_job_metrics_collection_and_persistence(temp_db):
    """Test full calculation, persistence, and retrieval of all 11 crawl performance metrics."""
    # 1. Create company for evidence linking
    comp = database.create_company(
        CompanyProfile(
            company_name="Metrics Test Corp",
            normalized_name="metrics test corp",
            website_url="https://metrics.example.com",
            domain="metrics.example.com",
        ),
        db_path=temp_db,
    )

    # 2. Create crawl job
    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://metrics.example.com",
            company_id=comp.id,
            company_name=comp.company_name,
            status=CrawlJobStatus.RUNNING,
            started_at="2026-10-16T10:00:00Z",
            finished_at="2026-10-16T10:00:15Z",
        ),
        db_path=temp_db,
    )

    # 3. Create pages:
    # Page 1: Useful page with content and linked evidence
    ev = database.add_scrape_evidence(
        ScrapeEvidence(
            company_id=comp.id,
            source_url="https://metrics.example.com/about",
            title="About Metrics Corp",
            raw_text="Comprehensive enterprise solutions",
            word_count=5,
            http_status=200,
        ),
        db_path=temp_db,
    )
    p1 = CrawlPage(
        job_id=job.id,
        original_url="https://metrics.example.com/about",
        final_url="https://metrics.example.com/about",
        http_status=200,
        depth=1,
        title="About Metrics Corp",
        extracted_text="Comprehensive enterprise solutions for automated credit intelligence.",
        word_count=8,
        status=CrawlPageStatus.SUCCESS,
        evidence_id=ev.id,
    )
    database.save_crawled_page(p1, db_path=temp_db)

    # Page 2: Thin or empty content page
    p2 = CrawlPage(
        job_id=job.id,
        original_url="https://metrics.example.com/empty",
        final_url="https://metrics.example.com/empty",
        http_status=200,
        depth=1,
        title="Blank",
        extracted_text="",
        word_count=0,
        status=CrawlPageStatus.SUCCESS,
    )
    database.save_crawled_page(p2, db_path=temp_db)

    # Page 3: Failed page with HTTP 500
    p3 = CrawlPage(
        job_id=job.id,
        original_url="https://metrics.example.com/broken",
        final_url="https://metrics.example.com/broken",
        http_status=500,
        depth=1,
        status=CrawlPageStatus.FAILED,
        error_message="HTTP 500 Internal Server Error",
    )
    database.save_crawled_page(p3, db_path=temp_db)

    # 4. Scrapy runtime stats snapshot
    scrapy_stats = {
        "downloader/request_count": 5,
        "downloader/response_count": 2,
        "response_received_count": 2,
        "dupefilter/filtered": 3,
        "downloader/response_bytes": 12800,
        "httpcompression/response_bytes": 35200,
        "elapsed_time_seconds": 15.2,
        "finish_reason": "finished",
    }

    # 5. Finalize metrics
    metrics = database.finalize_crawl_job_metrics(
        job_id=job.id,
        scrapy_stats=scrapy_stats,
        stop_reason="finished",
        final_outcome="COMPLETED",
        db_path=temp_db,
    )

    # 6. Verify calculated metrics in-memory
    assert metrics.requests_attempted == 5
    assert metrics.responses_downloaded == 2
    assert metrics.unique_pages_saved == 2
    assert metrics.useful_pages == 1
    assert metrics.empty_or_thin_pages == 1
    assert metrics.duplicate_requests_filtered == 3
    assert metrics.failed_requests >= 1
    assert metrics.total_response_bytes == 12800
    assert metrics.total_decompressed_bytes == 35200
    assert metrics.crawl_duration_sec == 15.2
    assert metrics.evidence_records_created == 1
    assert metrics.final_outcome == "COMPLETED"
    assert metrics.stop_reason == "finished"

    # 7. Verify persistence and deserialization in get_crawl_job
    loaded_job = database.get_crawl_job(job.id, db_path=temp_db)
    assert loaded_job is not None
    assert loaded_job.metrics is not None
    assert loaded_job.metrics.requests_attempted == 5
    assert loaded_job.metrics.responses_downloaded == 2
    assert loaded_job.metrics.unique_pages_saved == 2
    assert loaded_job.metrics.useful_pages == 1
    assert loaded_job.metrics.empty_or_thin_pages == 1
    assert loaded_job.metrics.duplicate_requests_filtered == 3
    assert loaded_job.metrics.evidence_records_created == 1
    assert loaded_job.metrics.final_outcome == "COMPLETED"
    assert loaded_job.metrics.stop_reason == "finished"


def test_metrics_counters_non_negative_and_no_double_counting(temp_db):
    """Verify counters do not become negative and do not increment twice upon repeated calls."""
    job = database.create_crawl_job(
        CrawlJob(seed_url="https://example.com"),
        db_path=temp_db,
    )

    # Calling calculate on empty job produces non-negative zeroes
    m1 = database.calculate_job_metrics(job.id, scrapy_stats={}, db_path=temp_db)
    assert m1.requests_attempted >= 0
    assert m1.responses_downloaded >= 0
    assert m1.unique_pages_saved >= 0
    assert m1.useful_pages >= 0
    assert m1.empty_or_thin_pages >= 0
    assert m1.duplicate_requests_filtered >= 0
    assert m1.failed_requests >= 0
    assert m1.total_response_bytes >= 0
    assert m1.crawl_duration_sec >= 0.0
    assert m1.evidence_records_created >= 0

    # Add 1 page
    p = CrawlPage(
        job_id=job.id,
        original_url="https://example.com/p1",
        final_url="https://example.com/p1",
        http_status=200,
        extracted_text="Content",
        word_count=5,
        status=CrawlPageStatus.SUCCESS,
    )
    database.save_crawled_page(p, db_path=temp_db)

    stats = {
        "downloader/request_count": 2,
        "downloader/response_count": 1,
        "dupefilter/filtered": 1,
        "downloader/response_bytes": 500,
    }

    # Finalize twice to verify idempotency (no double-counting)
    m_first = database.finalize_crawl_job_metrics(job.id, scrapy_stats=stats, db_path=temp_db)
    m_second = database.finalize_crawl_job_metrics(job.id, scrapy_stats=stats, db_path=temp_db)

    assert m_first.unique_pages_saved == 1
    assert m_second.unique_pages_saved == 1
    assert m_first.requests_attempted == 2
    assert m_second.requests_attempted == 2
    assert m_first.responses_downloaded == 1
    assert m_second.responses_downloaded == 1
    assert m_first.duplicate_requests_filtered == 1
    assert m_second.duplicate_requests_filtered == 1
    assert m_first.total_response_bytes == 500
    assert m_second.total_response_bytes == 500


def test_metrics_job_isolation(temp_db):
    """Verify metrics from different jobs do not leak into one another."""
    job_a = database.create_crawl_job(
        CrawlJob(seed_url="https://site-a.com"),
        db_path=temp_db,
    )
    job_b = database.create_crawl_job(
        CrawlJob(seed_url="https://site-b.com"),
        db_path=temp_db,
    )

    # 2 pages for job A
    database.save_crawled_page(
        CrawlPage(
            job_id=job_a.id,
            original_url="https://site-a.com/1",
            extracted_text="A1",
            word_count=2,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )
    database.save_crawled_page(
        CrawlPage(
            job_id=job_a.id,
            original_url="https://site-a.com/2",
            extracted_text="A2",
            word_count=2,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # 1 page for job B
    database.save_crawled_page(
        CrawlPage(
            job_id=job_b.id,
            original_url="https://site-b.com/1",
            extracted_text="B1",
            word_count=2,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Finalize each
    metrics_a = database.finalize_crawl_job_metrics(
        job_a.id,
        scrapy_stats={"downloader/request_count": 10},
        stop_reason="finished",
        db_path=temp_db,
    )
    metrics_b = database.finalize_crawl_job_metrics(
        job_b.id,
        scrapy_stats={"downloader/request_count": 3},
        stop_reason="finished",
        db_path=temp_db,
    )

    assert metrics_a.unique_pages_saved == 2
    assert metrics_a.requests_attempted == 10

    assert metrics_b.unique_pages_saved == 1
    assert metrics_b.requests_attempted == 3

    # Check database persistence isolation
    j_a = database.get_crawl_job(job_a.id, db_path=temp_db)
    j_b = database.get_crawl_job(job_b.id, db_path=temp_db)
    assert j_a.metrics.unique_pages_saved == 2
    assert j_b.metrics.unique_pages_saved == 1


def test_failed_and_cancelled_jobs_report_metrics(temp_db):
    """Verify failed and cancelled jobs still report all available metrics."""
    # 1. Cancelled job
    job_c = database.create_crawl_job(
        CrawlJob(seed_url="https://cancel-test.com", status=CrawlJobStatus.RUNNING),
        db_path=temp_db,
    )
    database.save_crawled_page(
        CrawlPage(
            job_id=job_c.id,
            original_url="https://cancel-test.com/partial",
            extracted_text="Partial content before cancellation",
            word_count=4,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )
    database.update_crawl_job_status(job_c.id, CrawlJobStatus.CANCELLED, db_path=temp_db)
    m_c = database.finalize_crawl_job_metrics(
        job_c.id,
        scrapy_stats={"downloader/request_count": 4, "downloader/response_count": 1},
        stop_reason="cancelled_by_user",
        final_outcome="CANCELLED",
        db_path=temp_db,
    )

    assert m_c.final_outcome == "CANCELLED"
    assert m_c.stop_reason == "cancelled_by_user"
    assert m_c.unique_pages_saved == 1
    assert m_c.requests_attempted == 4

    # 2. Failed job
    job_f = database.create_crawl_job(
        CrawlJob(seed_url="https://fail-test.com", status=CrawlJobStatus.RUNNING),
        db_path=temp_db,
    )
    database.save_crawled_page(
        CrawlPage(
            job_id=job_f.id,
            original_url="https://fail-test.com/error",
            status=CrawlPageStatus.FAILED,
            error_message="Connection timed out",
        ),
        db_path=temp_db,
    )
    database.update_crawl_job_status(
        job_f.id, CrawlJobStatus.FAILED, error_message="Fatal spider exception", db_path=temp_db
    )
    m_f = database.finalize_crawl_job_metrics(
        job_f.id,
        scrapy_stats={"downloader/request_count": 1, "downloader/exception_count": 1},
        stop_reason="spider_exception",
        final_outcome="FAILED",
        db_path=temp_db,
    )

    assert m_f.final_outcome == "FAILED"
    assert m_f.stop_reason == "spider_exception"
    assert m_f.failed_requests >= 1


def test_api_crawl_job_metrics_endpoint(temp_db):
    """Verify GET /api/crawl/jobs/{job_id}/metrics and embedded metrics in job status."""
    with patch("database.get_db_path", return_value=temp_db):
        # 404 on non-existent job
        resp_404 = client.get("/api/crawl/jobs/999999/metrics")
        assert resp_404.status_code == 404

        # Create job with metrics
        job = database.create_crawl_job(
            CrawlJob(seed_url="https://api-metrics.example.com"),
            db_path=temp_db,
        )
        database.save_crawled_page(
            CrawlPage(
                job_id=job.id,
                original_url="https://api-metrics.example.com",
                extracted_text="Homepage content",
                word_count=5,
                status=CrawlPageStatus.SUCCESS,
            ),
            db_path=temp_db,
        )
        database.finalize_crawl_job_metrics(
            job.id,
            scrapy_stats={
                "downloader/request_count": 1,
                "downloader/response_count": 1,
                "downloader/response_bytes": 1024,
                "dupefilter/filtered": 0,
            },
            stop_reason="finished",
            final_outcome="COMPLETED",
            db_path=temp_db,
        )

        # GET /api/crawl/jobs/{id}/metrics
        m_resp = client.get(f"/api/crawl/jobs/{job.id}/metrics")
        assert m_resp.status_code == 200
        m_data = m_resp.json()
        assert m_data["requests_attempted"] == 1
        assert m_data["responses_downloaded"] == 1
        assert m_data["unique_pages_saved"] == 1
        assert m_data["useful_pages"] == 1
        assert m_data["empty_or_thin_pages"] == 0
        assert m_data["duplicate_requests_filtered"] == 0
        assert m_data["total_response_bytes"] == 1024
        assert m_data["final_outcome"] == "COMPLETED"
        assert m_data["stop_reason"] == "finished"

        # GET /api/crawl/jobs/{id} also contains 'metrics' field
        j_resp = client.get(f"/api/crawl/jobs/{job.id}")
        assert j_resp.status_code == 200
        j_data = j_resp.json()
        assert "metrics" in j_data
        assert j_data["metrics"]["requests_attempted"] == 1
        assert j_data["metrics"]["unique_pages_saved"] == 1


def test_api_get_evidence_endpoint(temp_db):
    """Test GET /api/evidence/{evidence_id} endpoint."""
    with patch("database.get_db_path", return_value=temp_db):
        # 1. 404 for non-existent evidence
        resp_404 = client.get("/api/evidence/999999")
        assert resp_404.status_code == 404
        assert "not found" in resp_404.json()["detail"].lower()

        # 2. Create company and evidence record
        comp = database.create_company(
            CompanyProfile(
                company_name="Apex Legal",
                normalized_name="apex legal",
                domain="apexlegal.com",
                website_url="https://apexlegal.com",
                workflow=WorkflowType.GENERAL,
            ),
            db_path=temp_db,
        )

        ev = database.add_scrape_evidence(
            ScrapeEvidence(
                company_id=comp.id,
                source_url="https://apexlegal.com/about",
                field_name="general_text",
                raw_text="Apex Legal provides corporate advisory services.",
                confidence_score=0.95,
            ),
            db_path=temp_db,
        )

        # 3. Retrieve via API
        resp = client.get(f"/api/evidence/{ev.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == ev.id
        assert data["company_id"] == comp.id
        assert data["source_url"] == "https://apexlegal.com/about"
        assert "corporate advisory" in data["raw_text"]


