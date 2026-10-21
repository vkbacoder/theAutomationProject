"""Benchmark and Regression Test Suite for 3rd Rock Lead Research & Qualification.

Target website: https://www.thirdrock.com.au/
Workflow: JEDOX
Target Product: Jedox

Validates:
1. Starlight Children's Foundation: Confirmed customer and confirmed Jedox usage.
2. Ball & Doggett: Confirmed customer; Jedox usage remains unverified.
3. Steadfast Group Limited: Confirmed case study; Jedox usage remains unverified.
4. Jedox: Dedicated partner / target vendor, excluded from customer lead pipeline.
5. Microsoft: Partner/technology relationship; does not infer internal Jedox usage.
6. Kepion: Extracted as technology platform from Ball & Doggett implementation context; no partnership assumed.
7. Anna Schell: Preserved exact published title ("FP&A") and candidate linkage; no invented details.
8. Badrish Shriniwas: Discovered author/director from blog bylines; no invented contact details.
9. Public company contacts: Segregated company vs person contacts, normalized without loss.
10. Evidence Deduplication: Repeated processing produces stable record counts without row multiplication.
11. Multi-format export: CSV, Excel, and JSON export validation.
"""

import io
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

import database
from app import app
from candidate_verifier import (
    check_explicit_product_usage,
    check_explicit_relationship,
    verify_all_candidates_for_job,
    verify_customer_candidate,
)
from intelligence_extractor import (
    extract_decision_makers_from_text,
    extract_public_contacts_from_text,
    generate_job_unified_evidence,
)
from models import (
    CandidateCategory,
    CandidateClassification,
    ClaimType,
    CompanyProfile,
    ContactType,
    CrawlJob,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    CustomerCandidate,
    DecisionMaker,
    EvidenceReference,
    PublicContact,
    RelationshipType,
    RoleCategory,
    UnifiedEvidence,
)


@pytest.fixture
def benchmark_db(tmp_path):
    """Create a temporary SQLite database initialized with fresh schema."""
    db_file = str(tmp_path / "benchmark_leads.db")
    database.init_db(db_file)
    return db_file


@pytest.fixture
def benchmark_fixture(benchmark_db):
    """Seed the benchmark database with realistic 3rd Rock pages and return job."""
    comp = database.create_company(
        CompanyProfile(
            company_name="3rd Rock Business Solutions",
            normalized_name="3rd rock business solutions",
            domain="thirdrock.com.au",
            website_url="https://www.thirdrock.com.au/",
        ),
        db_path=benchmark_db,
    )

    job = database.create_crawl_job(
        CrawlJob(
            seed_url="https://www.thirdrock.com.au/",
            company_id=comp.id,
            company_name=comp.company_name,
            objective="find customers using Jedox",
            target_product="Jedox",
            status=CrawlJobStatus.COMPLETED,
        ),
        db_path=benchmark_db,
    )

    # Page 1: Starlight Foundation case study (Explicit Jedox implementation)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/starlight",
            title="Starlight Foundation | 3rd Rock Business Solutions",
            extracted_text=(
                "Enhanced decision-making for national nonprofit\n"
                "Starlight Children's Foundation unleashes the potential of FP&A to drive innovation.\n"
                "Customer Profile\n"
                "Starlight Children's Foundation is a nonprofit in Australia operating nationally with a mission to deliver happiness.\n"
                "3rd Rock worked with the customer in re-deploying Jedox to unlock the overall functionality.\n"
                "Results & Outcomes\n"
                "\"This solution is great for cross functional relationships and collaboration.\"\n"
                "- Anna Schell ( FP&A Starlight)\n"
                "3rd Rock re-implemented Jedox to support the business analysis, board reporting, planning, budgeting, and forecasting."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 2: Ball & Doggett case study (Uses Microsoft ERP & Azure; compatible CPM like Kepion)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/ball-and-doggett",
            title="Ball & Doggett | 3rd Rock Business Solutions",
            extracted_text=(
                "Performance Management Transformation\n"
                "Customer Profile\n"
                "The Ball & Doggett is Australia's largest distributor of printable materials and consumables.\n"
                "The Customer used Microsoft ERP and were familiar with Azure platform, so 3rd Rock used combination of Microsoft based technologies for building a Planning and Reporting solution.\n"
                "Being agnostic to the technology, 3rd Rock proposed to build a planning and reporting solution using Microsoft and compatible CPM solution like Kepion."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 3: Steadfast Group Limited case study (Case study without Jedox)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/steadfast",
            title="Steadfast Group Limited | 3rd Rock",
            extracted_text=(
                "Steadfast Group Limited\n"
                "Customer Profile\n"
                "Steadfast is Australia's largest Insurance Broker Network and is owned by its broker-shareholders.\n"
                "Prior to the implementation, Steadfast faced significant hurdles in managing their distributed planning and consolidation."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 4: Jedox Partner page (Partner relationship, not customer usage)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/jedox-partner",
            title="Jedox Partner | 3rd Rock",
            extracted_text=(
                "Jedox\n"
                "3rd Rock is a dedicated Jedox Partner specializing in delivering robust, effective Enterprise Performance Management (EPM) and Business Intelligence (BI) solutions.\n"
                "We focus on transforming the Office of Finance by implementing and supporting Jedox."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 5: Microsoft Solutions & Platform page (Technology/Partner, not internal Jedox user)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/microsoft-partner",
            title="Microsoft Solutions | 3rd Rock",
            extracted_text=(
                "Microsoft\n"
                "3rd Rock is an official Microsoft Partner delivering cloud analytics and modern data architectures.\n"
                "We leverage platforms like Microsoft Fabric, Power BI, Azure, and Databricks for enterprise planning and reporting solutions."
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 6: Blog page with author bylines (Badrish Shriniwas)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/blogs",
            title="Insights & Blog | 3rd Rock",
            extracted_text=(
                "Data Modelling in Power BI with LLM\n"
                "This protocol allows you to connect AI agents directly to your Power BI semantic models.\n"
                "Badrish ShriniwasFeb 123 min read\n"
                "Beyond Insight: Mastering Write-Back and Action in Power BI\n"
                "Badrish ShriniwasFeb 23 min read\n"
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    # Page 7: Contact Us page (Company-level contacts)
    database.save_crawled_page(
        CrawlPage(
            job_id=job.id,
            original_url="https://www.thirdrock.com.au/contact",
            title="Contact Us | 3rd Rock",
            extracted_text=(
                "Contact Us\n"
                "Reach out to our Sydney team:\n"
                "Email: webadmin@thirdrock.com.au\n"
                "Phone: +61 (02) 8007 3621\n"
                "55, Pyrmont Bridge Road, Pyrmont Sydney 2009\n"
            ),
            status=CrawlPageStatus.SUCCESS,
        ),
        db_path=benchmark_db,
    )

    return job, benchmark_db


def test_benchmark_candidate_classifications(benchmark_fixture):
    """Validate candidate classifications and product-usage verification across 3rd Rock benchmark cases."""
    job, db_path = benchmark_fixture
    verified = verify_all_candidates_for_job(job.id, db_path=db_path)

    # 1. Starlight Children's Foundation: Confirmed customer AND confirmed Jedox usage
    starlight = next((c for c in verified if "starlight" in c.normalized_name), None)
    assert starlight is not None, "Starlight must be discovered"
    assert starlight.classification == CandidateClassification.CONFIRMED
    assert starlight.relationship_type == RelationshipType.CUSTOMER or starlight.relationship_type == RelationshipType.CASE_STUDY
    assert starlight.relationship_verification_status == "CONFIRMED"
    assert starlight.product_usage_status == "CONFIRMED"
    assert starlight.confidence_score >= 0.90
    assert "jedox" in (starlight.product_usage_evidence or "").lower()

    # 2. Ball & Doggett: Confirmed customer; Jedox usage remains unverified
    bd = next((c for c in verified if "ball" in c.normalized_name), None)
    assert bd is not None, "Ball & Doggett must be discovered"
    assert bd.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert bd.relationship_verification_status == "CONFIRMED"
    assert bd.product_usage_status == "UNVERIFIED"
    assert bd.checklist.customer_relationship_supported is True
    assert bd.checklist.product_usage_supported is False

    # 3. Steadfast Group Limited: Confirmed case study; Jedox usage remains unverified
    steadfast = next((c for c in verified if "steadfast" in c.normalized_name), None)
    assert steadfast is not None, "Steadfast Group Limited must be discovered"
    assert steadfast.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert steadfast.relationship_verification_status == "CONFIRMED"
    assert steadfast.product_usage_status == "UNVERIFIED"

    # 4. Jedox: Partner / target vendor; NOT a customer lead, product usage unverified
    jedox_cand = next((c for c in verified if c.normalized_name == "jedox"), None)
    assert jedox_cand is not None, "Jedox must be extracted"
    assert jedox_cand.relationship_type in (RelationshipType.PARTNER, RelationshipType.TARGET_VENDOR)
    assert jedox_cand.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert jedox_cand.product_usage_status == "UNVERIFIED"
    assert jedox_cand.checklist.customer_relationship_supported is False

    # 5. Microsoft: Partner; does NOT infer internal Jedox usage
    msft = next((c for c in verified if "microsoft" in c.normalized_name), None)
    assert msft is not None, "Microsoft must be extracted"
    assert msft.relationship_type == RelationshipType.PARTNER
    assert msft.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert msft.product_usage_status == "UNVERIFIED"
    assert msft.checklist.customer_relationship_supported is False
    assert msft.checklist.product_usage_supported is False

    # 6. Kepion: Extracted as technology platform; no partner/customer status assumed
    kepion = next((c for c in verified if "kepion" in c.normalized_name), None)
    assert kepion is not None, "Kepion must be extracted as a technology platform"
    assert kepion.relationship_type == RelationshipType.TECHNOLOGY_PLATFORM
    assert kepion.classification == CandidateClassification.PARTIALLY_VERIFIED
    assert kepion.product_usage_status == "UNVERIFIED"
    assert kepion.checklist.customer_relationship_supported is False


def test_benchmark_decision_makers_and_published_roles(benchmark_fixture):
    """Validate Anna Schell published title preservation and Badrish Shriniwas discovery without invented data."""
    job, db_path = benchmark_fixture
    verify_all_candidates_for_job(job.id, db_path=db_path)

    dms = database.get_decision_makers(job.id, db_path=db_path)

    # 1. Anna Schell: Exact published title "FP&A", linked to Starlight, no invented email/phone
    anna = next((d for d in dms if "anna" in d.full_name.lower()), None)
    assert anna is not None, "Anna Schell must be discovered"
    assert anna.published_title == "FP&A"
    assert anna.title == "FP&A"
    assert anna.role_category == RoleCategory.FINANCE_BUSINESS
    assert "starlight" in (anna.associated_company or "").lower()
    assert anna.candidate_company_id is not None
    assert anna.company_id is None
    assert anna.email is None, "Must not invent email"
    assert anna.phone is None, "Must not invent phone"

    # 2. Badrish Shriniwas: Discovered from blog byline, no invented email/phone
    badrish = next((d for d in dms if "badrish" in d.full_name.lower()), None)
    assert badrish is not None, "Badrish Shriniwas must be discovered from technical blog bylines"
    assert badrish.full_name == "Badrish Shriniwas"
    assert badrish.published_title in ("Author", "Director", "Author / Contributor")
    assert badrish.role_category in (RoleCategory.TECHNOLOGY_IT, RoleCategory.EXECUTIVE)
    assert badrish.email is None, "Must not invent email"
    assert badrish.phone is None, "Must not invent phone"


def test_benchmark_public_contacts_segregation(benchmark_fixture):
    """Validate public contact extraction and company-level vs person-level distinction."""
    job, db_path = benchmark_fixture
    verify_all_candidates_for_job(job.id, db_path=db_path)

    contacts = database.get_public_contacts(job.id, db_path=db_path)
    assert len(contacts) >= 3

    email_ct = next((c for c in contacts if c.contact_type == ContactType.EMAIL), None)
    assert email_ct is not None
    assert email_ct.contact_value == "webadmin@thirdrock.com.au"
    assert email_ct.job_title == "Company Contact Email"
    assert email_ct.person_id is None
    assert email_ct.company_id == job.company_id

    phone_ct = next((c for c in contacts if c.contact_type in (ContactType.PHONE, ContactType.OFFICE_PHONE)), None)
    assert phone_ct is not None
    assert "8007" in phone_ct.contact_value
    assert phone_ct.person_id is None


def test_benchmark_evidence_deduplication_and_idempotence(benchmark_fixture):
    """Validate that evidence records are strictly deduplicated and repeated processing is idempotent."""
    job, db_path = benchmark_fixture

    # First verification pass
    verify_all_candidates_for_job(job.id, db_path=db_path)
    evidences_pass1 = database.get_unified_evidence(job.id, limit=1000, db_path=db_path)
    count_pass1 = len(evidences_pass1)

    # Check unique (claim_type, source_url, supporting_quote) combinations
    unique_tuples = {(e.claim_type, e.source_url, e.supporting_quote) for e in evidences_pass1}
    assert len(unique_tuples) == count_pass1, "Every persisted evidence record must represent a unique claim/source combination"

    # Repeated persistence must be strictly idempotent
    database.save_unified_evidence(evidences_pass1, db_path=db_path)
    evidences_after_save = database.get_unified_evidence(job.id, limit=1000, db_path=db_path)
    assert len(evidences_after_save) == count_pass1, "Repeated save_unified_evidence calls must not multiply records"

    # Second full verification pass
    verify_all_candidates_for_job(job.id, db_path=db_path)
    evidences_pass2 = database.get_unified_evidence(job.id, limit=1000, db_path=db_path)
    assert len(evidences_pass2) == count_pass1, "Repeated verify_all_candidates_for_job must maintain stable record count"


def test_benchmark_exports_and_provenance_fields(benchmark_fixture):
    """Validate that exports (JSON, CSV, Excel) include the new provenance fields and contact level."""
    job, db_path = benchmark_fixture
    verify_all_candidates_for_job(job.id, db_path=db_path)

    # Temporarily point database to benchmark_db for test client
    original_get_db = database.get_db_path
    database.get_db_path = lambda: db_path

    try:
        client = TestClient(app)

        # 1. JSON Export
        resp_json = client.get(f"/api/crawl/jobs/{job.id}/export?format=json")
        assert resp_json.status_code == 200
        data = resp_json.json()
        assert "candidates" in data
        assert "evidence" in data
        assert "decision_makers" in data
        assert "contacts" in data

        cands = data["candidates"]
        assert len(cands) >= 5
        starlight_entry = next(c for c in cands if "starlight" in c["Normalized Name"])
        assert "Relationship Status" in starlight_entry
        assert starlight_entry["Relationship Status"] == "CONFIRMED"
        assert starlight_entry["Product Usage Status"] == "CONFIRMED"
        assert "Confidence Score" in starlight_entry
        assert starlight_entry["Confidence Score"] >= 0.90

        contacts = data["contacts"]
        for ct in contacts:
            assert "Contact Level" in ct
            assert ct["Contact Level"] in ("COMPANY", "PERSON")

        # 2. CSV Export (ZIP archive containing separate CSVs)
        resp_csv = client.get(f"/api/crawl/jobs/{job.id}/export?format=csv")
        assert resp_csv.status_code == 200
        assert resp_csv.headers["content-type"] == "application/zip"

        # 3. Excel Export
        resp_excel = client.get(f"/api/crawl/jobs/{job.id}/export?format=excel")
        assert resp_excel.status_code == 200
        assert "spreadsheetml" in resp_excel.headers["content-type"]

    finally:
        database.get_db_path = original_get_db
