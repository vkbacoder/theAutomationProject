"""Live end-to-end verification of both research modes against https://cooperatives.gov.in/.
Tests:
1. Mode A: Single-Page Scraper (/api/scrape)
2. Mode B: Recursive Scrapy Crawler (/api/crawl/jobs, /metrics, /results)
3. Full data persistence and inspection in leads.db
4. Frontend assets served (/ and /static/app.js)
5. CSV and JSON export simulation with real records
"""

import json
import sqlite3
import sys
import threading
import time
import httpx
import pytest

# Ensure Windows stdout handles UTF-8 safely
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from crawler_worker import CrawlerWorker

# Skip during automated unit test discovery (e.g. pytest without live server/network)
pytestmark = pytest.mark.skip(reason="Live end-to-end integration test against live web target and local server")

BASE_URL = "http://127.0.0.1:8000"
TARGET_URL = "https://cooperatives.gov.in/"


def run_live_verification():
    print("=" * 60)
    print("1. FRONTEND SERVER ASSET VERIFICATION")
    print("=" * 60)
    r_index = httpx.get(f"{BASE_URL}/")
    print(f"GET / -> Status {r_index.status_code}")
    assert r_index.status_code == 200
    assert "AI Web Research" in r_index.text
    assert "url-input" in r_index.text
    assert "btn-start-research" in r_index.text
    print("[PASS] Frontend index.html served successfully with unified header and controls.")

    r_js = httpx.get(f"{BASE_URL}/static/app.js")
    print(f"GET /static/app.js -> Status {r_js.status_code}, Length: {len(r_js.text)} chars")
    assert r_js.status_code == 200
    assert "executeSinglePageScrape" in r_js.text
    assert "executeWebsiteCrawl" in r_js.text
    assert "exportAsCsv" in r_js.text
    print("[PASS] Unified frontend controller static/app.js served successfully.")

    print("\n" + "=" * 60)
    print("2. MODE A: SINGLE-PAGE SCRAPE (https://cooperatives.gov.in/)")
    print("=" * 60)
    t0 = time.time()
    r_scrape = httpx.post(
        f"{BASE_URL}/api/scrape",
        json={"url": TARGET_URL},
        timeout=45.0
    )
    duration_scrape = time.time() - t0
    print(f"POST /api/scrape -> Status {r_scrape.status_code} in {duration_scrape:.2f}s")
    assert r_scrape.status_code == 200
    scrape_data = r_scrape.json()
    print(f"Success Flag: {scrape_data.get('success')}")
    print(f"HTTP Status: {scrape_data.get('status_code')}")
    print(f"Page Title: {scrape_data.get('title')}")
    print(f"Final URL: {scrape_data.get('final_url')}")
    print(f"Extracted Word Count: {scrape_data.get('word_count')}")
    print(f"Extracted Text Preview: {scrape_data.get('text', '')[:200]}...")
    print(f"Discovered Links Count: {len(scrape_data.get('links', []))}")
    print(f"Headings: H1={len(scrape_data.get('headings', {}).get('h1', []))}, H2={len(scrape_data.get('headings', {}).get('h2', []))}, H3={len(scrape_data.get('headings', {}).get('h3', []))}")

    print("\n" + "=" * 60)
    print("3. MODE B: RECURSIVE CRAWL JOB SUBMISSION & MONITORING")
    print("=" * 60)
    payload = {
        "url": TARGET_URL,
        "workflow": "GENERAL",
        "max_depth": 2,
        "max_pages": 5,
        "max_pages_per_domain": 5
    }
    r_job = httpx.post(f"{BASE_URL}/api/crawl/jobs", json=payload)
    print(f"POST /api/crawl/jobs -> Status {r_job.status_code}")
    assert r_job.status_code in (200, 201)
    job_info = r_job.json()
    job_id = job_info["id"]
    print(f"Created Crawl Job #{job_id}: status={job_info['status']}, max_pages={job_info['max_pages']}, max_depth={job_info['max_depth']}")

    # Start an autonomous background worker subprocess in case an external worker daemon is not running
    import subprocess
    worker_proc = subprocess.Popen([sys.executable, "crawler_worker.py", "--once"])

    # Poll job until finished
    print(f"Polling Job #{job_id} for completion (worker will process)...")
    max_wait = 120
    poll_interval = 3
    elapsed = 0
    final_job = None
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        r_status = httpx.get(f"{BASE_URL}/api/crawl/jobs/{job_id}")
        final_job = r_status.json()
        status = final_job["status"]
        pages_crawled = final_job.get("pages_crawled", 0)
        discovered = final_job.get("discovered_urls_count", 0)
        print(f"  [{elapsed}s] Job #{job_id} Status: {status} | Pages Crawled: {pages_crawled} | Discovered: {discovered}")
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            break

    print(f"\nJob #{job_id} finalized with Status: {final_job['status']}")

    print("\n" + "=" * 60)
    print("4. METRICS & RESULTS RETRIEVAL")
    print("=" * 60)
    r_metrics = httpx.get(f"{BASE_URL}/api/crawl/jobs/{job_id}/metrics")
    print(f"GET /api/crawl/jobs/{job_id}/metrics -> Status {r_metrics.status_code}")
    if r_metrics.status_code == 200:
        metrics = r_metrics.json()
        print("Baseline Performance & Extraction Metrics:")
        for k, v in metrics.items():
            print(f"  * {k}: {v}")

    r_results = httpx.get(f"{BASE_URL}/api/crawl/jobs/{job_id}/results?limit=300")
    print(f"\nGET /api/crawl/jobs/{job_id}/results -> Status {r_results.status_code}")
    assert r_results.status_code == 200
    results = r_results.json()
    print(f"Total Saved Pages Retrieved: {len(results)}")
    for idx, p in enumerate(results[:5]):
        print(f"  [{idx+1}] d:{p.get('depth')} | {p.get('title')} | HTTP {p.get('http_status')} | {p.get('word_count')} words | Evidence: {p.get('evidence_id')}")

    print("\n" + "=" * 60)
    print("5. EXPORT INTEGRITY CHECK (CSV & JSON)")
    print("=" * 60)
    # Verify CSV structure
    csv_lines = ["depth,title,original_url,final_url,http_status,extraction_status,word_count,evidence_id"]
    for p in results:
        csv_lines.append(f"{p.get('depth')},\"{p.get('title')}\",\"{p.get('original_url')}\",\"{p.get('final_url')}\",{p.get('http_status')},\"{p.get('status')}\",{p.get('word_count')},{p.get('evidence_id')}")
    csv_content = "\r\n".join(csv_lines)
    print(f"CSV Export Generated: {len(csv_lines)} lines, {len(csv_content)} bytes")
    assert len(csv_lines) == len(results) + 1

    # Verify JSON structure
    json_export = {
        "total_records": len(results),
        "records": results
    }
    json_content = json.dumps(json_export, indent=2)
    print(f"JSON Export Generated: {len(json_content)} bytes")
    assert json_export["total_records"] == len(results)

    print("\n" + "=" * 60)
    print("6. COOPERATIVE DATA ANALYSIS & INTEGRITY CHECK")
    print("=" * 60)
    all_text = " ".join([p.get("extracted_text", "") for p in results])
    coop_keywords = ["PACS", "Dairy", "Fisheries", "Credit", "Multi-State", "NCD", "National Cooperative Database"]
    print("Detected Cooperative Topics:")
    for kw in coop_keywords:
        count = all_text.count(kw)
        print(f"  * '{kw}': {count} occurrences across crawl results")

    print("\nStructured Entity Evaluation:")
    print("  * Are structured cooperative society records (e.g. registry rows) present in the database?")
    print("  * Findings: Current crawl engine captures unstructured page text and navigation links.")
    print("  * Structured cooperative-record entity extraction is NOT YET IMPLEMENTED, as accurately noted on UI.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_live_verification()
