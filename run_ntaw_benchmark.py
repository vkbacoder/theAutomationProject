"""National Tyre & Wheel (NTAW) Benchmark Execution Script.

Executes the intelligent search-guided lead research workflow on National Tyre & Wheel:
- Target Company: National Tyre & Wheel
- Seed URL: https://ntaw.com.au/
- Workflow: JEDOX
- Target Product: Jedox
- Compares findings against historical Job #71 baseline.
- Validates offline determinism using pre-loaded benchmark fixtures.
"""

from __future__ import annotations

import os
import sys
import json
import logging
from typing import Any, Dict, List

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import database
from models import (
    CrawlJob,
    CrawlPage,
    CrawlJobStatus,
    CrawlPageStatus,
    WorkflowType,
    RoleCategory,
    RelationshipType,
    CandidateClassification,
    ContactOwnership,
)
from search_service import (
    MockSearchProvider,
    SearchResultItem,
    ExternalResearchFrontier,
    ResearchBudget,
)
from research_controller import ResearchController, ResearchStage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ntaw_benchmark")

# Benchmark fixture content for Jedox customer case study
JEDOX_NTAW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>National Tyre & Wheel Transforms FP&A | Jedox Customer Story</title>
</head>
<body>
  <header>
    <nav><a href="https://www.jedox.com/">Jedox</a> / Customers / National Tyre &amp; Wheel</nav>
  </header>
  <main>
    <h1>How National Tyre &amp; Wheel Transformed FP&amp;A with Jedox</h1>
    <p class="summary">
      National Tyre &amp; Wheel (NTAW), Australasia's largest independent tyre and wheel wholesaler, 
      selected and deployed Jedox for financial planning, management reporting, and budgeting consolidation 
      across all Australian and New Zealand operating entities.
    </p>
    <section class="quote-section">
      <blockquote>
        "Jedox has transformed our financial planning and analysis capabilities, replacing slow spreadsheets with unified, real-time reporting across all business units."
      </blockquote>
      <div class="attribution">
        <span class="person-name">Jason Lamb</span>, 
        <span class="person-title">Chief Financial Officer at National Tyre &amp; Wheel</span>
      </div>
    </section>
    <section class="results">
      <h3>Business Outcomes with Jedox</h3>
      <ul>
        <li>Monthly financial consolidation reduced from weeks to hours</li>
        <li>Automated cash flow and variance forecasting</li>
        <li>Unified multi-entity visibility across Australia and New Zealand</li>
      </ul>
    </section>
  </main>
</body>
</html>
"""

# Benchmark fixture for NTAW Contact & Fleet Forms page
NTAW_CONTACT_TEXT = """
National Tyre & Wheel (NTAW) - Contact Us
Head Office: 30 Gow Street, Moorooka QLD 4105, Australia
General Enquiries: (07) 3715 2200
Corporate Email: info@ntaw.com.au
Investor Relations: cosec@ntaw.com.au
Media Enquiries: media@ntaw.com.au
Website: https://ntaw.com.au/
"""

NTAW_FLEET_TEXT = """
National Tyre & Wheel - Fleet Servicing & Authorization Forms
For third-party fleet maintenance approval and billing authorizations,
contact AutoGuru customer support:
AutoGuru Fleet Support: 1300 655 661
Support Email: fleets@autoguru.com.au
Office of the Australian Information Commissioner: enquiries@oaic.gov.au
"""


class MockBenchmarkHTTPClient:
    """Mock HTTP client returning benchmark fixtures for offline reproducibility."""

    class MockResponse:
        def __init__(self, text: str, url: str, status_code: int = 200):
            self.text = text
            self.url = url
            self.status_code = status_code
            self.content = text.encode("utf-8")

    def __init__(self, routes: Dict[str, str]):
        self.routes = routes

    def get(self, url: str, **kwargs):
        u_norm = url.strip()
        for route_url, html in self.routes.items():
            if route_url in u_norm or u_norm in route_url:
                return self.MockResponse(text=html, url=u_norm, status_code=200)
        return self.MockResponse(text="<html><body>Not Found</body></html>", url=u_norm, status_code=404)

    def close(self):
        pass


def run_benchmark(db_path: str = "leads.db") -> Dict[str, Any]:
    """Execute the benchmark research job on NTAW and report results."""
    logger.info("=================================================================")
    logger.info("Starting National Tyre & Wheel (NTAW) Intelligent Research Benchmark")
    logger.info("=================================================================")

    # 1. Audit baseline Job #71 in leads.db
    job71 = database.get_crawl_job(71, db_path=db_path)
    if job71:
        job71_pages = database.get_crawled_pages(71, db_path=db_path)
        job71_dms = database.get_decision_makers_for_job(71, db_path=db_path)
        job71_candidates = database.get_customer_candidates(71, db_path=db_path)
        logger.info(
            "BASELINE Job #71 state: Status=%s, Pages=%d, Decision-Makers=%d, Candidate Entities=%d",
            job71.status,
            len(job71_pages),
            len(job71_dms),
            len(job71_candidates),
        )
    else:
        logger.warning("Job #71 not found in %s; proceeding with fresh benchmark creation.", db_path)

    # 2. Find or Create Company Profile for NTAW
    conn = database.get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM companies WHERE domain = ? OR normalized_name LIKE ?", ("ntaw.com.au", "%national tyre%")).fetchone()
        if row:
            ntaw_comp = database._row_to_company(row)
        else:
            ntaw_comp = database.create_company(
                CompanyProfile(
                    company_name="National Tyre & Wheel",
                    normalized_name="national tyre & wheel",
                    domain="ntaw.com.au",
                    website_url="https://ntaw.com.au/",
                    workflow=WorkflowType.JEDOX,
                ),
                db_path=db_path,
            )
    finally:
        conn.close()

    # 3. Create new CrawlJob for Benchmark
    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://ntaw.com.au/",
            company_id=ntaw_comp.id,
            company_name="National Tyre & Wheel",
            objective="find customers using Jedox",
            target_product="Jedox",
            workflow=WorkflowType.JEDOX,
            max_depth=2,
            max_pages=20,
            max_pages_per_domain=20,
            status=CrawlJobStatus.RUNNING,
        ),
        db_path=db_path,
    )
    logger.info("Created Benchmark Crawl Job #%d", job.id)

    # 4. Seed Internal Frontier Pages (NTAW website)
    # Page A: Seed Homepage
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://ntaw.com.au/",
            final_url="https://ntaw.com.au/",
            http_status=200,
            depth=0,
            title="National Tyre & Wheel | Australia's Largest Wholesaler",
            extracted_text="National Tyre & Wheel is the largest independent tyre and wheel wholesaler in Australia and New Zealand. Our leadership team drives sustainable growth across all operating subsidiaries.",
            word_count=28,
            frontier="INTERNAL",
            source_category="OFFICIAL_COMPANY",
            priority_score=85.0,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=db_path,
    )

    # Page B: Contact page
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://ntaw.com.au/contact-us",
            final_url="https://ntaw.com.au/contact-us",
            http_status=200,
            depth=1,
            title="Contact Us | National Tyre & Wheel",
            extracted_text=NTAW_CONTACT_TEXT,
            word_count=35,
            frontier="INTERNAL",
            source_category="OFFICIAL_COMPANY",
            priority_score=78.0,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=db_path,
    )

    # Page C: Fleet Forms page (contains third-party contacts: AutoGuru, OAIC)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://ntaw.com.au/fleet-forms",
            final_url="https://ntaw.com.au/fleet-forms",
            http_status=200,
            depth=1,
            title="Fleet Forms & Authorizations | National Tyre & Wheel",
            extracted_text=NTAW_FLEET_TEXT,
            word_count=42,
            frontier="INTERNAL",
            source_category="OFFICIAL_COMPANY",
            priority_score=62.0,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=db_path,
    )

    # Page D: Corporate Governance / Mission Statement page
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://ntaw.com.au/investors/governance",
            final_url="https://ntaw.com.au/investors/governance",
            http_status=200,
            depth=1,
            title="Mission Statement & Governance | National Tyre & Wheel",
            extracted_text="Mission Statement\nNational Tyre & Wheel operates with high ethical standards. Environmental Policy and modern slavery policies are published here.",
            headings_json={"h1": ["Mission Statement"], "h2": ["Environmental Policy"]},
            word_count=22,
            frontier="INTERNAL",
            source_category="OFFICIAL_COMPANY",
            priority_score=50.0,
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=db_path,
    )

    # 5. Set up Mock Search Provider with benchmark results
    mock_search = MockSearchProvider({
        '"national tyre & wheel" jedox': [
            SearchResultItem(
                url="https://www.jedox.com/en/customers/ntaw/",
                title="National Tyre & Wheel - Jedox Customer Story",
                snippet="National Tyre & Wheel transforms FP&A with Jedox. Jason Lamb, Chief Financial Officer at National Tyre & Wheel explains how Jedox streamlined consolidation.",
                engine="mock",
                priority_score=92.0,
            ),
        ],
        'site:jedox.com "national tyre & wheel"': [
            SearchResultItem(
                url="https://www.jedox.com/en/customers/ntaw/",
                title="National Tyre & Wheel - Jedox Customer Story",
                snippet="Read how National Tyre & Wheel automated budgeting across Australia and New Zealand.",
                engine="mock",
                priority_score=92.0,
            ),
        ],
        '"national tyre & wheel" cfo': [
            SearchResultItem(
                url="https://www.jedox.com/en/customers/ntaw/",
                title="Jason Lamb, CFO | National Tyre & Wheel",
                snippet="Jason Lamb, Chief Financial Officer at National Tyre & Wheel.",
                engine="mock",
                priority_score=88.0,
            ),
        ],
    })

    # Pattern fallback for any query mentioning ntaw or national tyre
    mock_search.add_pattern_rule(
        r"national\s+tyre|ntaw",
        [
            SearchResultItem(
                url="https://www.jedox.com/en/customers/ntaw/",
                title="National Tyre & Wheel - Jedox Customer Story",
                snippet="National Tyre & Wheel selected Jedox for FP&A. Jason Lamb, Chief Financial Officer at National Tyre & Wheel.",
                engine="mock",
                priority_score=92.0,
            ),
        ],
    )

    mock_http = MockBenchmarkHTTPClient({
        "https://www.jedox.com/en/customers/ntaw/": JEDOX_NTAW_HTML,
    })

    # 6. Initialize and Execute Research Controller
    controller = ResearchController(
        job_id=job.id,
        search_provider=mock_search,
        http_client=mock_http,
        budget=ResearchBudget(
            max_internal_pages=20,
            max_external_search_results=25,
            max_external_pages_retrieved=10,
            max_search_queries=6,
        ),
        db_path=db_path,
    )

    logger.info("Executing Research Controller pipeline...")
    final_metrics = controller.run()

    # 7. Query and Validate Final Output
    finished_job = database.get_crawl_job(job.id, db_path=db_path)
    all_pages = database.get_crawled_pages(job.id, db_path=db_path)
    decision_makers = database.get_decision_makers_for_job(job.id, db_path=db_path)
    contacts = database.get_public_contacts(job_id=job.id, db_path=db_path)
    candidates = database.get_customer_candidates(job.id, db_path=db_path)
    evidence = database.get_unified_evidence(job_id=job.id, db_path=db_path)

    # 8. Verify specific benchmark assertions
    logger.info("-----------------------------------------------------------------")
    logger.info("Benchmark Results Summary for Job #%d:", job.id)
    logger.info("Status: %s", finished_job.status)
    logger.info("Research Stage: %s", finished_job.research_stage)
    logger.info("Pages Crawled: %d (Internal: %d, External: %d)", len(all_pages), finished_job.internal_pages_count, finished_job.external_pages_count)
    logger.info("Decision Makers: %d", len(decision_makers))
    logger.info("Public Contacts: %d", len(contacts))
    logger.info("Candidates Discovered: %d", len(candidates))
    logger.info("Evidence Linked: %d", len(evidence))

    # Assertion A: National Tyre & Wheel confirmed customer with Jedox usage
    ntaw_cand = next((c for c in candidates if "national tyre" in c.normalized_name or "ntaw" in c.normalized_name), None)
    customer_verified = False
    if ntaw_cand:
        logger.info("Found NTAW Candidate: Classification=%s, Rel=%s, ProductUsage=%s", ntaw_cand.classification, ntaw_cand.relationship_type, ntaw_cand.product_usage_status)
        customer_verified = (
            ntaw_cand.classification in (CandidateClassification.CONFIRMED, CandidateClassification.PARTIALLY_VERIFIED)
            and ntaw_cand.product_usage_status == "CONFIRMED"
        )
    logger.info("Assertion 1 (Customer & Jedox Usage Verified): %s", "PASS" if customer_verified else "FAIL")

    # Assertion B: Jason Lamb CFO discovered with NO invented email
    jason = next((dm for dm in decision_makers if "Jason Lamb" in dm.full_name), None)
    dm_verified = False
    if jason:
        has_no_email = getattr(jason, "email", None) is None or jason.email == ""
        logger.info("Found Jason Lamb: Title='%s', Role=%s, Email='%s'", jason.published_title, jason.role_category, getattr(jason, "email", "None"))
        dm_verified = "Chief Financial Officer" in jason.published_title and has_no_email
    logger.info("Assertion 2 (Jason Lamb CFO Extracted, 0 Invented Email): %s", "PASS" if dm_verified else "FAIL")

    # Assertion C: Contact Ownership Segregation
    autoguru_ct = next((c for c in contacts if "1300 655 661" in c.contact_value or "fleets@autoguru" in c.contact_value), None)
    oaic_ct = next((c for c in contacts if "enquiries@oaic.gov.au" in c.contact_value), None)
    ntaw_ct = next((c for c in contacts if "3715 2200" in c.contact_value or "info@ntaw.com.au" in c.contact_value), None)

    contacts_segregated = True
    if autoguru_ct and autoguru_ct.contact_ownership != ContactOwnership.THIRD_PARTY:
        contacts_segregated = False
    if oaic_ct and oaic_ct.contact_ownership != ContactOwnership.REGULATOR:
        contacts_segregated = False
    if ntaw_ct and ntaw_ct.contact_ownership != ContactOwnership.TARGET_COMPANY:
        contacts_segregated = False
    logger.info("Assertion 3 (Contact Ownership Segregation): %s", "PASS" if contacts_segregated else "FAIL")

    # Assertion D: Rejection of false positive entities
    invalid_found = [c for c in candidates if c.candidate_name in ("Mission Statement", "Environmental Policy", "We have", "Fleet Forms", "4WD & Off", "Road")]
    false_positives_rejected = len(invalid_found) == 0
    logger.info("Assertion 4 (False Positives Rejected): %s (Found %d)", "PASS" if false_positives_rejected else "FAIL", len(invalid_found))

    # Assertion E: Job #71 remained untouched
    if job71:
        job71_after = database.get_crawl_job(71, db_path=db_path)
        job71_untouched = (job71_after.pages_crawled == job71.pages_crawled and job71_after.status == job71.status)
        logger.info("Assertion 5 (Job #71 Untouched): %s", "PASS" if job71_untouched else "FAIL")
    else:
        job71_untouched = True

    return {
        "job_id": job.id,
        "status": finished_job.status.value,
        "research_stage": finished_job.research_stage,
        "customer_verified": customer_verified,
        "dm_verified": dm_verified,
        "contacts_segregated": contacts_segregated,
        "false_positives_rejected": false_positives_rejected,
        "job71_untouched": job71_untouched,
        "metrics": final_metrics,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("\nBENCHMARK EXECUTION SUMMARY:")
    print(json.dumps(res, indent=2))
