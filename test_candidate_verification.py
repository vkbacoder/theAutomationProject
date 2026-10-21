"""Automated tests for Customer Candidate Discovery, Verification, and Checklist.

Tests:
- Candidate discovery from case study titles, logos, testimonials, and customer text patterns
- Multi-page evidence citation and deduplication
- Verification of customer relationship vs. incidental mention
- Verification of target product usage vs. missing product evidence
- 6-item verification checklist accuracy
- Candidate classification (CONFIRMED, PARTIALLY_VERIFIED, UNVERIFIED, RESEARCH_INCOMPLETE)
- Unverified candidates are NEVER marked CONFIRMED
- SQLite database persistence and retrieval
- FastAPI endpoints for candidate queries and verification
"""

from __future__ import annotations

import tempfile
import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app import app
from candidate_verifier import (
    clean_candidate_name,
    extract_candidates_from_html,
    extract_candidates_from_text_block,
    verify_all_candidates_for_job,
    verify_customer_candidate,
)
import database
from models import (
    CandidateClassification,
    CompanyProfile,
    CrawlJob,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    CustomerCandidate,
    EvidenceReference,
    RelationshipType,
    WorkflowType,
)

client = TestClient(app)


@pytest.fixture
def temp_db():
    """Create isolated SQLite database for candidate testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.init_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass


# -------------------------------------------------------------
# 1. Candidate Extraction & Cleaning Tests
# -------------------------------------------------------------

def test_clean_candidate_name():
    """Verify name sanitization and exclusion of web UI noise."""
    assert clean_candidate_name("  \"Acme Corp\"  ") == "Acme Corp"
    assert clean_candidate_name("Siemens AG logo") == "Siemens AG"
    assert clean_candidate_name("Logo of Henkel") == "Henkel"
    assert clean_candidate_name("Privacy Policy") is None
    assert clean_candidate_name("Contact Us") is None
    assert clean_candidate_name("Case Studies") is None
    assert clean_candidate_name("12345") is None
    assert clean_candidate_name("") is None


def test_extract_from_story_heading_and_testimonial():
    """Test extracting candidate companies from case study titles and testimonial signatures."""
    text = (
        "Customer Story: Henkel AG\n"
        "How Henkel transformed their enterprise financial planning with automated solutions.\n"
        "“This platform reduced our budget cycle by 50%.”\n"
        "— Marcus Weber, CFO at Schaeffler Group\n"
    )
    results = extract_candidates_from_text_block(
        text=text,
        page_url="https://jedox.com/en/customers/henkel",
        page_title="Henkel Customer Story",
        target_company_name="Jedox",
        target_product="Jedox",
    )

    names = {r["candidate_name"] for r in results}
    assert "Henkel AG" in names or "Henkel" in names
    assert "Schaeffler Group" in names

    # Target company itself must never be extracted as its own customer
    assert "Jedox" not in names


def test_extract_from_logo_alt_tags_in_html():
    """Test extracting customer candidate from logo images and alt text."""
    html = """
    <html>
      <body>
        <section class="customer-logos">
          <h2>Trusted by Industry Leaders</h2>
          <img src="/logos/daimler.png" alt="Daimler AG customer logo" />
          <img src="/logos/bayer.png" alt="Bayer logo" />
          <img src="/icons/arrow.svg" alt="Next page" />
        </section>
      </body>
    </html>
    """
    results = extract_candidates_from_html(
        html_content=html,
        page_url="https://vendor.com/customers",
        page_title="Our Customers",
        target_company_name="Vendor Inc",
        target_product="Jedox",
    )
    names = {r["candidate_name"] for r in results}
    assert "Daimler AG" in names
    assert "Bayer" in names
    assert "Next page" not in names


# -------------------------------------------------------------
# 2. Candidate Verification & Checklist Tests
# -------------------------------------------------------------

def test_verify_candidate_confirmed():
    """Verify that a candidate with both customer relationship and explicit product usage is CONFIRMED."""
    sources = [
        EvidenceReference(
            source_url="https://vendor.com/customers/acme",
            page_title="Acme Corp Case Study",
            supporting_text="Case Study: Acme Corp. Acme Corp selected Jedox to modernize financial consolidation.",
            relationship_claim="CASE_STUDY",
            product_claim="Mentioned with Jedox",
        )
    ]
    all_pages = [
        ("https://vendor.com/customers/acme", "Acme Corp Case Study", "Case Study: Acme Corp. Acme Corp uses Jedox for budgeting and corporate performance management.")
    ]

    candidate = verify_customer_candidate(
        candidate_name="Acme Corp",
        candidate_sources=sources,
        all_page_texts=all_pages,
        target_product="Jedox",
        is_crawl_complete=True,
    )

    assert candidate.classification == CandidateClassification.CONFIRMED
    assert candidate.relationship_type in (RelationshipType.CASE_STUDY, RelationshipType.CUSTOMER)
    assert candidate.checklist.company_discovered is True
    assert candidate.checklist.customer_relationship_supported is True
    assert candidate.checklist.product_usage_supported is True
    assert candidate.checklist.source_url_recorded is True
    assert candidate.checklist.supporting_text_recorded is True
    assert candidate.checklist.verification_completed is True
    assert candidate.product_usage_status == "CONFIRMED"
    assert "verified" in candidate.missing_evidence_reason.lower()


def test_verify_candidate_partially_verified_customer_no_product():
    """Verify candidate identified as customer but without explicit product usage is PARTIALLY_VERIFIED."""
    sources = [
        EvidenceReference(
            source_url="https://vendor.com/customers",
            page_title="Our Customers",
            supporting_text="Our customer, Beta Logistics, trusts our team for operational efficiency.",
            relationship_claim="CUSTOMER",
        )
    ]
    all_pages = [
        ("https://vendor.com/customers", "Our Customers", "Our customer, Beta Logistics, trusts our team for operational efficiency.")
    ]

    candidate = verify_customer_candidate(
        candidate_name="Beta Logistics",
        candidate_sources=sources,
        all_page_texts=all_pages,
        target_product="Jedox",
        is_crawl_complete=True,
    )

    assert candidate.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert candidate.checklist.customer_relationship_supported is True
    assert candidate.checklist.product_usage_supported is False
    assert candidate.product_usage_status == "UNVERIFIED"
    assert "explicit usage of jedox was not found" in candidate.missing_evidence_reason.lower()


def test_verify_candidate_partially_verified_partner():
    """Verify candidate mentioned with product but as partner/vendor is PARTIALLY_VERIFIED, not customer."""
    sources = [
        EvidenceReference(
            source_url="https://vendor.com/partners",
            page_title="Alliances",
            supporting_text="Gamma Consulting is our certified implementation partner using Jedox to serve clients.",
            relationship_claim="PARTNER",
        )
    ]
    all_pages = [
        ("https://vendor.com/partners", "Alliances", "Gamma Consulting is our certified implementation partner using Jedox to serve clients.")
    ]

    candidate = verify_customer_candidate(
        candidate_name="Gamma Consulting",
        candidate_sources=sources,
        all_page_texts=all_pages,
        target_product="Jedox",
        is_crawl_complete=True,
    )

    assert candidate.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert candidate.relationship_type == RelationshipType.PARTNER
    assert candidate.checklist.customer_relationship_supported is False
    assert candidate.checklist.product_usage_supported is True
    assert "partner" in candidate.missing_evidence_reason.lower()


def test_verify_candidate_unverified_incidental_mention():
    """Verify incidental mention without customer or product evidence remains UNVERIFIED."""
    sources = [
        EvidenceReference(
            source_url="https://vendor.com/blog/trends",
            page_title="Market Trends",
            supporting_text="According to a public survey by Delta Analytics, data volumes grew 30%.",
            relationship_claim="MENTION",
        )
    ]
    all_pages = [
        ("https://vendor.com/blog/trends", "Market Trends", "According to a public survey by Delta Analytics, data volumes grew 30%.")
    ]

    candidate = verify_customer_candidate(
        candidate_name="Delta Analytics",
        candidate_sources=sources,
        all_page_texts=all_pages,
        target_product="Jedox",
        is_crawl_complete=True,
    )

    # Must NEVER be marked as CONFIRMED from a mere mention
    assert candidate.classification == CandidateClassification.UNVERIFIED
    assert candidate.checklist.customer_relationship_supported is False
    assert candidate.checklist.product_usage_supported is False
    assert candidate.product_usage_status == "UNVERIFIED"


def test_verify_candidate_research_incomplete():
    """Verify candidate during interrupted crawl is marked RESEARCH_INCOMPLETE."""
    sources = [
        EvidenceReference(
            source_url="https://vendor.com/customers/omega",
            page_title="Omega Case Study",
            supporting_text="Customer Story: Omega Corp",
            relationship_claim="CASE_STUDY",
        )
    ]

    candidate = verify_customer_candidate(
        candidate_name="Omega Corp",
        candidate_sources=sources,
        all_page_texts=[],
        target_product="Jedox",
        is_crawl_complete=False,
    )

    assert candidate.classification == CandidateClassification.RESEARCH_INCOMPLETE
    assert candidate.checklist.verification_completed is False


# -------------------------------------------------------------
# 3. Database Persistence Tests
# -------------------------------------------------------------

def test_database_persistence_and_retrieval(temp_db):
    """Test saving and querying candidates with checklist and sources in SQLite."""
    # 1. Create target company and job
    comp = database.create_company(
        CompanyProfile(
            company_name="Enterprise BI AG",
            normalized_name="enterprise bi ag",
            domain="enterprisebi.com",
            website_url="https://enterprisebi.com",
        ),
        db_path=temp_db,
    )

    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://enterprisebi.com",
            company_id=comp.id,
            company_name=comp.company_name,
            objective="find customers using Jedox",
            target_product="Jedox",
            status=CrawlJobStatus.COMPLETED,
        ),
        db_path=temp_db,
    )

    # 2. Create Candidate
    sources = [
        EvidenceReference(
            source_url="https://enterprisebi.com/customers/bmw",
            page_title="BMW Success Story",
            supporting_text="Case Study: BMW Group. BMW Group implemented Jedox for enterprise planning.",
            relationship_claim="CASE_STUDY",
        )
    ]
    candidate = CustomerCandidate(
        job_id=job.id,
        target_company_id=comp.id,
        candidate_name="BMW Group",
        normalized_name="bmw group",
        target_product="Jedox",
        relationship_type=RelationshipType.CASE_STUDY,
        classification=CandidateClassification.CONFIRMED,
        checklist=database.VerificationChecklist(
            company_discovered=True,
            customer_relationship_supported=True,
            product_usage_supported=True,
            source_url_recorded=True,
            supporting_text_recorded=True,
            verification_completed=True,
        ),
        product_usage_status="CONFIRMED",
        sources=sources,
        missing_evidence_reason="Verified via case study.",
    )

    saved = database.save_customer_candidate(candidate, db_path=temp_db)
    assert saved.id is not None

    # 3. Query candidates by job
    results = database.get_customer_candidates(job_id=job.id, db_path=temp_db)
    assert len(results) == 1
    retrieved = results[0]
    assert retrieved.candidate_name == "BMW Group"
    assert retrieved.classification == CandidateClassification.CONFIRMED
    assert retrieved.checklist.customer_relationship_supported is True
    assert retrieved.checklist.product_usage_supported is True
    assert len(retrieved.sources) == 1
    assert "BMW Success Story" in retrieved.sources[0].page_title

    # 4. Filter by classification
    confirmed_only = database.get_customer_candidates(
        job_id=job.id, classification=CandidateClassification.CONFIRMED, db_path=temp_db
    )
    assert len(confirmed_only) == 1

    unverified_only = database.get_customer_candidates(
        job_id=job.id, classification=CandidateClassification.UNVERIFIED, db_path=temp_db
    )
    assert len(unverified_only) == 0


def test_verify_all_candidates_for_job_integration(temp_db):
    """Test full integration of verify_all_candidates_for_job against simulated crawl pages."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Cloud Solutions Inc",
            normalized_name="cloud solutions inc",
            domain="cloudsolutions.com",
            website_url="https://cloudsolutions.com",
        ),
        db_path=temp_db,
    )

    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://cloudsolutions.com",
            company_id=comp.id,
            company_name=comp.company_name,
            objective="find customers using Jedox",
            target_product="Jedox",
            status=CrawlJobStatus.COMPLETED,
        ),
        db_path=temp_db,
    )

    # Page 1: Customer story with product usage
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://cloudsolutions.com/customers/zalando",
            title="Customer Story: Zalando SE",
            extracted_text="Customer Story: Zalando SE. Zalando SE implemented Jedox to automate multi-entity budgeting.",
            headings_json={"h1": ["Customer Story: Zalando SE"]},
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Page 2: Customer mention without product usage
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://cloudsolutions.com/clients",
            title="Our Clients",
            extracted_text="Our client: Spotify. We provide Spotify with 24/7 technical infrastructure advisory.",
            headings_json={"h2": ["Our Clients"]},
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    candidates = verify_all_candidates_for_job(job.id, db_path=temp_db)
    assert len(candidates) >= 2

    zalando = next((c for c in candidates if "zalando" in c.normalized_name), None)
    assert zalando is not None
    assert zalando.classification == CandidateClassification.CONFIRMED
    assert zalando.checklist.customer_relationship_supported is True
    assert zalando.checklist.product_usage_supported is True

    spotify = next((c for c in candidates if "spotify" in c.normalized_name), None)
    assert spotify is not None
    assert spotify.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert spotify.checklist.customer_relationship_supported is True
    assert spotify.checklist.product_usage_supported is False


# -------------------------------------------------------------
# 4. API Endpoints Tests
# -------------------------------------------------------------

def test_api_candidates_endpoints(temp_db):
    """Test GET and POST candidate endpoints on FastAPI."""
    with patch("database.get_db_path", return_value=temp_db), \
         patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        # 1. Create Crawl Job with objective
        create_resp = client.post("/api/crawl/jobs", json={
            "url": "https://example.com",
            "company_name": "Example Corp",
            "objective": "find customers using Jedox",
            "target_product": "Jedox",
            "max_depth": 2,
            "max_pages": 5,
        })
        assert create_resp.status_code == 201
        job_data = create_resp.json()
        job_id = job_data["id"]
        assert job_data["objective"] == "find customers using Jedox"
        assert job_data["target_product"] == "Jedox"

        # 2. Add Crawl Page
        database.save_crawled_page(
            CrawlPage(
                job_id=job_id,
                original_url="https://example.com/customers/lufthansa",
                title="Case Study: Lufthansa Group",
                extracted_text="Case Study: Lufthansa Group. Lufthansa Group deployed Jedox across European hubs.",
                headings_json={"h1": ["Case Study: Lufthansa Group"]},
                status=CrawlPageStatus.SUCCESS,
            ),
            db_path=temp_db,
        )

        # 3. Trigger verification endpoint
        verify_resp = client.post(f"/api/crawl/jobs/{job_id}/verify-candidates")
        assert verify_resp.status_code == 200
        candidates = verify_resp.json()
        assert len(candidates) >= 1
        lufthansa = candidates[0]
        assert "Lufthansa Group" in lufthansa["candidate_name"]
        assert lufthansa["classification"] == "CONFIRMED"
        assert lufthansa["checklist"]["customer_relationship_supported"] is True
        assert lufthansa["checklist"]["product_usage_supported"] is True

        cand_id = lufthansa["id"]

        # 4. Query candidate by ID
        get_cand = client.get(f"/api/candidates/{cand_id}")
        assert get_cand.status_code == 200
        cand_detail = get_cand.json()
        assert cand_detail["id"] == cand_id
        assert cand_detail["candidate_name"] == lufthansa["candidate_name"]

        # 5. Query candidates for job with filter
        query_resp = client.get(f"/api/crawl/jobs/{job_id}/candidates?classification=CONFIRMED")
        assert query_resp.status_code == 200
        assert len(query_resp.json()) >= 1


# -------------------------------------------------------------
# 5. Regression Tests for 3rd Rock Issue
# -------------------------------------------------------------

def test_regression_first_ordinal_false_positive_rejected():
    """Ensure generic ordinal words and UI fragments do not become customer candidates."""
    assert clean_candidate_name("First") is None
    assert clean_candidate_name("First Cases") is None
    assert clean_candidate_name("Second") is None
    assert clean_candidate_name("Initially") is None
    assert clean_candidate_name("Customer Profile") is None
    assert clean_candidate_name("The Solution") is None


def test_regression_thirdrock_intelligence_and_candidate_verification(temp_db):
    """Deterministic regression test verifying complete entity extraction, candidate classification,
    stakeholder identification, and public contact segregation on 3rd Rock case studies.
    """
    import sqlite3

    # 1. Setup Target Company
    target_comp = database.create_company(
        CompanyProfile(
            company_name="3rd Rock Business Solutions",
            normalized_name="3rd rock business solutions",
            domain="thirdrock.com.au",
            website_url="https://www.thirdrock.com.au/",
            workflow=WorkflowType.JEDOX,
        ),
        db_path=temp_db,
    )

    # 2. Setup Crawl Job
    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://www.thirdrock.com.au/",
            company_id=target_comp.id,
            company_name=target_comp.company_name,
            objective="Identify named customers",
            target_product="Jedox",
            workflow=WorkflowType.JEDOX,
            status=CrawlJobStatus.COMPLETED,
        ),
        db_path=temp_db,
    )

    # 3. Add Deterministic Mocked Pages matching 3rd Rock content
    # Page A: Starlight Children's Foundation (Jedox case study + Anna Schell quote with unicode quotes)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/starlight",
            title="Starlight Foundation | 3rd Rock Business Solutions",
            extracted_text=(
                "Enhanced decision-making for national nonprofit\n"
                "Starlight Children\u2019s Foundation unleashes the potential of FP&A to drive innovation.\n"
                "Customer Profile\n"
                "Starlight Children\u2019s Foundation is a nonprofit in Australia operating nationally with a mission to deliver happiness.\n"
                "3rd Rock worked with the customer in re-deploying Jedox to unlock the overall functionality.\n"
                "First implemented to replicate their existing legacy planning and reporting, users realized a clear lack of details.\n"
                "Results & Outcomes\n"
                "\"This solution is great for cross functional relationships and collaboration.\"\n"
                "- Anna Schell ( FP&A Starlight)\n"
                "Starlight engaged 3rd Rock to look into how best to utilize Jedox functionality with the fresh set of eyes.\n"
                "3rd Rock re-implemented Jedox to support the business analysis, board reporting, planning, budgeting, and forecasting."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Page B: Ball & Doggett (Customer case study without Jedox)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/ball-and-doggett",
            title="Ball & Doggett | 3rd Rock Business Solutions",
            extracted_text=(
                "Performance Management Transformation\n"
                "Budgeting & Reporting transformation of paper & print material supplier\n"
                "Customer Profile\n"
                "The Ball & Doggett is Australia\u2019s largest distributor of printable materials and consumables.\n"
                "3rd Rock engaged with B&D to identify, design, and implement a solution that met the Customer requirements.\n"
                "The Customer used Microsoft ERP and were familiar with Azure platform, so 3rd Rock used combination of Microsoft based technologies."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Page C: Steadfast Group Limited (Case study without Jedox)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/steadfast",
            title="Steadfast Group Limited | 3rd Rock",
            extracted_text=(
                "Steadfast Group Limited\n"
                "Introduction\n"
                "Steadfast is Australia\u2019s largest Insurance Broker Network and is owned by its broker-shareholders.\n"
                "Executive Summary\n"
                "The Challenge: Manual Complexity\n"
                "Prior to the implementation, Steadfast faced significant hurdles in managing their distributed planning and consolidation:\n"
                "Time-Intensive Processes: During their IPO, consolidation required 3-4 months of work."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Page D: Jedox Partner page (Partner relationship, not a customer)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/jedox-partner",
            title="Jedox | 3rd Rock",
            extracted_text=(
                "Jedox\n"
                "3rd Rock is a dedicated Jedox Partner specializing in delivering robust, effective Enterprise Performance Management (EPM) and Business Intelligence (BI) solutions.\n"
                "We focus on transforming the Office of Finance by implementing and supporting Jedox."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # Page E: Contact Us page (Host company address)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/contact",
            title="Contact | 3rd Rock",
            extracted_text=(
                "Contact Us\n"
                "Reach out to us with your questions, comments or feedback.\n"
                "55, Pyrmont Bridge Road, Pyrmont Sydney 2009\n"
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=temp_db,
    )

    # 4. Execute Candidate Verification
    verified = verify_all_candidates_for_job(job.id, db_path=temp_db)
    cand_names = [c.candidate_name for c in verified]

    # Verification Assertion: Generic "First" must NOT be extracted
    assert "First" not in cand_names
    assert "First Cases" not in cand_names

    # Verification Assertion: Starlight Children's Foundation must be CONFIRMED with Jedox
    starlight = next((c for c in verified if "starlight" in c.normalized_name), None)
    assert starlight is not None, "Starlight Children's Foundation must be discovered"
    assert starlight.classification == CandidateClassification.CONFIRMED
    assert starlight.checklist.customer_relationship_supported is True
    assert starlight.checklist.product_usage_supported is True
    assert starlight.product_usage_status == "CONFIRMED"

    # Verification Assertion: Ball & Doggett must be PARTIALLY_VERIFIED (customer without Jedox)
    bd = next((c for c in verified if "ball" in c.normalized_name), None)
    assert bd is not None, "Ball & Doggett must be discovered"
    assert bd.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert bd.checklist.customer_relationship_supported is True
    assert bd.checklist.product_usage_supported is False

    # Verification Assertion: Steadfast Group Limited must be PARTIALLY_VERIFIED (case study without Jedox)
    steadfast = next((c for c in verified if "steadfast" in c.normalized_name), None)
    assert steadfast is not None, "Steadfast Group Limited must be discovered"
    assert steadfast.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert steadfast.checklist.customer_relationship_supported is True
    assert steadfast.checklist.product_usage_supported is False

    # Verification Assertion: Jedox is a PARTNER, NOT treated as customer-level usage
    jedox_cand = next((c for c in verified if c.normalized_name == "jedox"), None)
    assert jedox_cand is not None, "Jedox must be discovered"
    assert jedox_cand.relationship_type == RelationshipType.PARTNER
    assert jedox_cand.classification == CandidateClassification.PARTIALLY_VERIFIED

    # 5. Database Consistency & Foreign-Key Integrity Verification
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Decision Maker: Anna Schell must be associated with Starlight candidate ID, NOT company_id
    cursor.execute(
        "SELECT id, name, title, department, associated_company, candidate_company_id, company_id, professional_relevance, email, phone "
        "FROM decision_makers WHERE job_id = ?",
        (job.id,),
    )
    dms = cursor.fetchall()
    assert len(dms) == 1, f"Expected 1 decision maker, found {len(dms)}"
    dm_id, name, title, dept, assoc_co, cand_co_id, comp_id, relevance, email, phone = dms[0]
    assert name == "Anna Schell"
    assert title == "FP&A"
    assert cand_co_id == starlight.id, "Candidate company ID must match Starlight candidate table ID"
    assert comp_id is None, "Company ID must be None since Starlight is a candidate, not a parent company"
    assert "customer case study" in relevance.lower()
    assert email is None, "Must not fabricate email"
    assert phone is None, "Must not fabricate phone"

    # Public Contact: Pyrmont Address must belong to 3rd Rock (target company), NOT a customer
    cursor.execute(
        "SELECT id, contact_type, contact_value, associated_job_title, associated_company, candidate_company_id, company_id "
        "FROM public_contacts WHERE job_id = ?",
        (job.id,),
    )
    contacts = cursor.fetchall()
    assert len(contacts) == 1, f"Expected 1 contact, found {len(contacts)}"
    c_id, c_type, c_val, c_title, c_assoc, c_cand_id, c_comp_id = contacts[0]
    assert "Pyrmont" in c_val
    assert c_assoc == "3rd Rock Business Solutions"
    assert c_cand_id is None, "3rd Rock contact must not be assigned to a candidate"
    assert c_comp_id == target_comp.id, "Must be linked to target company"

    # Unified Evidence: all rows must have valid foreign keys
    cursor.execute("SELECT count(*) FROM unified_evidence WHERE job_id = ?", (job.id,))
    ev_count = cursor.fetchone()[0]
    assert ev_count > 0, "Unified evidence records must be generated and persisted"

    conn.close()

