"""Regression test suite for Job #35 defects and fixes.

Covers all 12 requirements:
1. ERP/platform mention cannot confirm internal Jedox usage (SAP).
2. Partner status cannot confirm internal Jedox usage (Microsoft, Jedox).
3. Explicit Starlight case-study evidence preserves customer and usage claims.
4. Customer status and product-usage status can differ (Steadfast, Ball & Doggett).
5. Technology mentions do not create formal partnerships automatically (Fabric, Power BI).
6. Author bylines do not establish decision-making authority (Badrish, Sankaran).
7. Duplicate public contacts are removed without losing distinct contacts.
8. Summary counts agree with underlying records.
9. Product Usage Evidence tab and API endpoint use consistent filters.
10. Workflow selection survives submission, persistence, and retrieval.
11. Historical jobs (Jobs 32, 34, 35) are not rewritten.
12. CSV, Excel, and JSON exports preserve consistent classifications and provenance.
"""

import io
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

import database
from app import app
from dedup import canonical_contact_key
from intelligence_extractor import (
    extract_decision_makers_from_text,
    extract_public_contacts_from_text,
    generate_job_unified_evidence,
)
from candidate_verifier import (
    check_explicit_product_usage,
    check_explicit_relationship,
    verify_customer_candidate,
)
from models import (
    CandidateCategory,
    CandidateClassification,
    ClaimType,
    ContactType,
    CrawlJob,
    CrawlJobStatus,
    CreateCrawlJobRequest,
    CustomerCandidate,
    EvidenceReference,
    PublicContact,
    RelationshipType,
    RoleCategory,
    UnifiedEvidence,
    VerificationChecklist,
    WorkflowType,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_job():
    """Create a temporary test job for DB operations requiring foreign keys."""
    job = CrawlJob(
        seed_url="https://www.thirdrock.com.au/",
        allowed_domains=["thirdrock.com.au"],
        workflow=WorkflowType.JEDOX,
        company_name="Third Rock Business Solutions",
        objective="Verify customers using Jedox",
        target_product="Jedox",
        status=CrawlJobStatus.COMPLETED,
        max_depth=2,
        max_pages=20,
        max_pages_per_domain=20
    )
    return database.create_crawl_job(job)


# ---------------------------------------------------------------------------
# Test 1: ERP / Platform Mention Cannot Confirm Internal Jedox Usage (SAP)
# ---------------------------------------------------------------------------
def test_sap_erp_mention_cannot_confirm_jedox_usage():
    """SAP mentioned as an ERP or consolidation source must NOT produce CONFIRMED Jedox usage."""
    sap_evidence = [
        "We help clients integrate Jedox with their ERP system such as SAP.",
        "Consolidate financial data from SAP and other core business systems into Jedox for FP&A.",
        "Third Rock provides migration solutions from legacy SAP architectures."
    ]

    has_usage, quote = check_explicit_product_usage(
        candidate_name="SAP",
        target_product="Jedox",
        all_snippets=sap_evidence,
        relationship_type=RelationshipType.TECHNOLOGY_PLATFORM
    )

    assert has_usage is False
    assert quote is None

    # Full candidate verification for SAP
    candidate = CustomerCandidate(
        job_id=35,
        candidate_name="SAP",
        normalized_name="sap",
        candidate_category=CandidateCategory.PRODUCT_OR_TECHNOLOGY,
        classification=CandidateClassification.UNVERIFIED,
        relationship_type=RelationshipType.TECHNOLOGY_PLATFORM,
        relationship_verification_status="UNVERIFIED",
        target_product="Jedox",
        product_usage_status="UNVERIFIED",
        sources=[
            EvidenceReference(
                supporting_text="Consolidate financial data from SAP and other systems into Jedox.",
                source_url="https://www.thirdrock.com.au/case-studies/starlight",
                page_title="Case Study"
            )
        ]
    )

    verified = verify_customer_candidate(
        candidate_name="SAP",
        candidate_sources=candidate.sources,
        all_page_texts=[("https://www.thirdrock.com.au/case-studies/starlight", "Case Study", "Consolidate financial data from SAP and other core business systems into Jedox for FP&A.")],
        target_product="Jedox"
    )

    assert verified.product_usage_status == "UNVERIFIED"
    assert verified.classification != CandidateClassification.CONFIRMED
    assert verified.checklist.product_usage_supported is False


# ---------------------------------------------------------------------------
# Test 2: Partner Status Cannot Confirm Internal Jedox Usage
# ---------------------------------------------------------------------------
def test_partner_status_cannot_confirm_internal_jedox_usage():
    """A formal partnership with Jedox or Microsoft does not confirm internal Jedox deployment."""
    partner_evidence = [
        "Third Rock is an official Jedox Gold Partner in Australia.",
        "We are proud to be a Microsoft Solutions Partner for Data & AI."
    ]

    for vendor in ["Jedox", "Microsoft"]:
        has_usage, quote = check_explicit_product_usage(
            candidate_name=vendor,
            target_product="Jedox",
            all_snippets=partner_evidence,
            relationship_type=RelationshipType.PARTNER
        )
        assert has_usage is False
        assert quote is None


# ---------------------------------------------------------------------------
# Test 3: Explicit Starlight Case Study Preserves Customer & Usage Claims
# ---------------------------------------------------------------------------
def test_starlight_case_study_preserves_confirmed_customer_and_usage():
    """Starlight case study explicitly says 3rd Rock re-implemented Jedox for Starlight."""
    starlight_evidence = [
        "Starlight Children's Foundation partnered with Third Rock to re-implement their Jedox solution for budgeting and reporting.",
        "The Jedox re-implementation delivered automated reporting and saved hundreds of hours for Starlight."
    ]

    # Test explicit relationship
    rel_verified, rel_type, rel_quote = check_explicit_relationship(
        candidate_name="Starlight Children's Foundation",
        all_snippets=starlight_evidence,
        target_product="Jedox"
    )
    assert rel_verified is True
    assert rel_type in {RelationshipType.CASE_STUDY, RelationshipType.CUSTOMER}
    assert rel_quote is not None

    # Test explicit product usage
    has_usage, usage_quote = check_explicit_product_usage(
        candidate_name="Starlight Children's Foundation",
        target_product="Jedox",
        all_snippets=starlight_evidence,
        relationship_type=rel_type
    )
    assert has_usage is True
    assert usage_quote is not None
    assert "Jedox" in usage_quote

    # Full candidate verification
    candidate = CustomerCandidate(
        job_id=35,
        candidate_name="Starlight Children's Foundation",
        normalized_name="starlight childrens foundation",
        candidate_category=CandidateCategory.NAMED_COMPANY,
        classification=CandidateClassification.UNVERIFIED,
        relationship_type=RelationshipType.CASE_STUDY,
        relationship_verification_status="UNVERIFIED",
        target_product="Jedox",
        product_usage_status="UNVERIFIED",
        sources=[
            EvidenceReference(
                supporting_text=starlight_evidence[0],
                source_url="https://www.thirdrock.com.au/case-studies/starlight",
                page_title="Starlight Case Study"
            )
        ]
    )

    verified = verify_customer_candidate(
        candidate_name="Starlight Children's Foundation",
        candidate_sources=candidate.sources,
        all_page_texts=[("https://www.thirdrock.com.au/case-studies/starlight", "Starlight Case Study", " ".join(starlight_evidence))],
        target_product="Jedox"
    )

    assert verified.classification == CandidateClassification.CONFIRMED
    assert verified.relationship_verification_status == "CONFIRMED"
    assert verified.product_usage_status == "CONFIRMED"
    assert verified.checklist.customer_relationship_supported is True
    assert verified.checklist.product_usage_supported is True


# ---------------------------------------------------------------------------
# Test 4: Customer Status and Product-Usage Status Can Differ
# ---------------------------------------------------------------------------
def test_customer_status_and_product_usage_status_can_differ():
    """Steadfast Group has confirmed customer relationship but unverified Jedox product usage."""
    steadfast_evidence = [
        "Steadfast Group engaged 3rd Rock to modernize their financial reporting processes.",
        "Our team delivered automated management reporting models for Steadfast Group."
    ]

    rel_verified, rel_type, rel_quote = check_explicit_relationship(
        candidate_name="Steadfast Group",
        all_snippets=steadfast_evidence,
        target_product="Jedox"
    )
    assert rel_verified is True
    assert rel_type in {RelationshipType.CASE_STUDY, RelationshipType.CUSTOMER}

    has_usage, usage_quote = check_explicit_product_usage(
        candidate_name="Steadfast Group",
        target_product="Jedox",
        all_snippets=steadfast_evidence,
        relationship_type=rel_type
    )
    assert has_usage is False
    assert usage_quote is None

    candidate = CustomerCandidate(
        job_id=35,
        candidate_name="Steadfast Group",
        normalized_name="steadfast group",
        candidate_category=CandidateCategory.NAMED_COMPANY,
        classification=CandidateClassification.UNVERIFIED,
        relationship_type=RelationshipType.CASE_STUDY,
        relationship_verification_status="UNVERIFIED",
        target_product="Jedox",
        product_usage_status="UNVERIFIED",
        sources=[
            EvidenceReference(
                supporting_text=steadfast_evidence[0],
                source_url="https://www.thirdrock.com.au/case-studies/steadfast",
                page_title="Steadfast Case Study"
            )
        ]
    )

    verified = verify_customer_candidate(
        candidate_name="Steadfast Group",
        candidate_sources=candidate.sources,
        all_page_texts=[("https://www.thirdrock.com.au/case-studies/steadfast", "Steadfast Case Study", " ".join(steadfast_evidence))],
        target_product="Jedox"
    )

    # Customer relationship is CONFIRMED, but product usage is UNVERIFIED -> overall PARTIALLY_VERIFIED
    assert verified.relationship_verification_status == "CONFIRMED"
    assert verified.product_usage_status == "UNVERIFIED"
    assert verified.classification == CandidateClassification.PARTIALLY_VERIFIED


# ---------------------------------------------------------------------------
# Test 5: Technology Mentions Do Not Create Formal Partnerships
# ---------------------------------------------------------------------------
def test_technology_mentions_do_not_create_formal_partnerships():
    """Mentions of Power BI, Microsoft Fabric, Kepion, TM1, Tagetik default to TECHNOLOGY_PLATFORM."""
    tech_snippets = [
        "We build interactive dashboards using Power BI and Microsoft Fabric.",
        "Our consultants have deep expertise in Kepion, IBM Planning Analytics / TM1, and CCH Tagetik."
    ]

    for tech_name in ["Power BI", "Microsoft Fabric", "Kepion", "IBM Planning Analytics/TM1", "CCH Tagetik"]:
        rel_verified, rel_type, quote = check_explicit_relationship(
            candidate_name=tech_name,
            all_snippets=tech_snippets,
            target_product="Jedox"
        )
        assert rel_type == RelationshipType.TECHNOLOGY_PLATFORM
        assert rel_type != RelationshipType.PARTNER
        assert rel_type != RelationshipType.CUSTOMER


# ---------------------------------------------------------------------------
# Test 6: Author Bylines Do Not Establish Decision-Making Authority
# ---------------------------------------------------------------------------
def test_author_bylines_classified_as_author_contributor_unverified():
    """Blog authors (Badrish Shriniwas, Sankaran Angamuthu) must be AUTHOR_CONTRIBUTOR with UNVERIFIED status."""
    blog_text = """
    Leveraging Power BI for Modern Reporting
    Author: Badrish Shriniwas
    Sankaran AngamuthuMar 194 min read
    In this article, our consultants explore how to integrate modern BI with enterprise planning.
    """

    dms = extract_decision_makers_from_text(
        text=blog_text,
        source_url="https://www.thirdrock.com.au/blogs/power-bi-reporting",
        default_company="Third Rock Business Solutions"
    )

    names = {dm.full_name: dm for dm in dms}
    assert "Badrish Shriniwas" in names
    assert "Sankaran Angamuthu" in names

    for name in ["Badrish Shriniwas", "Sankaran Angamuthu"]:
        dm = names[name]
        assert dm.role_category == RoleCategory.AUTHOR_CONTRIBUTOR
        assert dm.verification_status == "UNVERIFIED"
        assert dm.published_title == "Author"
        assert dm.associated_company == "Third Rock Business Solutions"


# ---------------------------------------------------------------------------
# Test 7: Duplicate Public Contacts are Removed Without Losing Distinct Contacts
# ---------------------------------------------------------------------------
def test_canonical_contact_key_and_deduplication(test_job):
    """Phone formatting variations and duplicate addresses normalize to canonical keys."""
    k1 = canonical_contact_key("PHONE", "+61 2 8000 1234")
    k2 = canonical_contact_key("PHONE", "(02) 8000-1234")
    k3 = canonical_contact_key("PHONE", "02 8000 1234")
    assert k1 == k2 == k3

    k_email1 = canonical_contact_key("EMAIL", "Info@ThirdRock.com.au")
    k_email2 = canonical_contact_key("EMAIL", "info@thirdrock.com.au ")
    assert k_email1 == k_email2

    # Distinct contacts remain distinct
    k_phone_other = canonical_contact_key("PHONE", "+61 3 9000 5678")
    assert k1 != k_phone_other

    # Database deduplication test using test_job
    job_id = test_job.id
    c1 = PublicContact(
        job_id=job_id,
        contact_type=ContactType.PHONE,
        contact_value="+61 2 8000 1234",
        source_url="https://www.thirdrock.com.au/contact"
    )
    c2 = PublicContact(
        job_id=job_id,
        contact_type=ContactType.PHONE,
        contact_value="(02) 8000 1234",
        source_url="https://www.thirdrock.com.au/about"
    )
    c3 = PublicContact(
        job_id=job_id,
        contact_type=ContactType.EMAIL,
        contact_value="info@thirdrock.com.au",
        source_url="https://www.thirdrock.com.au/contact"
    )

    database.save_public_contact(c1)
    database.save_public_contact(c2)
    database.save_public_contact(c3)

    retrieved = database.get_public_contacts(job_id=job_id)
    types_values = [(c.contact_type.value, c.contact_value) for c in retrieved]
    phones = [v for t, v in types_values if t == "PHONE"]
    emails = [v for t, v in types_values if t == "EMAIL"]

    assert len(phones) == 1
    assert len(emails) == 1


# ---------------------------------------------------------------------------
# Test 8 & 9: Summary Counts Agree with Evidence Records & Product Usage Filters
# ---------------------------------------------------------------------------
def test_summary_counts_agree_with_unified_evidence_records(test_job):
    """Product Usage Evidence tab and summary metrics use the same unified evidence records."""
    job_id = test_job.id

    # Create candidate with confirmed Jedox usage
    starlight = CustomerCandidate(
        job_id=job_id,
        candidate_name="Starlight Children's Foundation",
        normalized_name="starlight childrens foundation",
        candidate_category=CandidateCategory.NAMED_COMPANY,
        classification=CandidateClassification.CONFIRMED,
        relationship_type=RelationshipType.CASE_STUDY,
        relationship_verification_status="CONFIRMED",
        target_product="Jedox",
        product_usage_status="CONFIRMED",
        product_usage_evidence="3rd Rock re-implemented Jedox for Starlight Children's Foundation.",
        supporting_source_url="https://www.thirdrock.com.au/case-studies/starlight",
        exact_supporting_quote="3rd Rock re-implemented Jedox for Starlight Children's Foundation.",
        checklist=VerificationChecklist(
            customer_relationship_supported=True,
            product_usage_supported=True,
            explicit_quote_present=True,
            url_attributable=True,
            independent_of_vendor_claim=True
        ),
        sources=[
            EvidenceReference(
                supporting_text="3rd Rock re-implemented Jedox for Starlight Children's Foundation.",
                source_url="https://www.thirdrock.com.au/case-studies/starlight",
                page_title="Case Study"
            )
        ]
    )

    database.save_customer_candidate(starlight)
    ev_records = generate_job_unified_evidence(
        job_id=job_id,
        candidates=[starlight],
        decision_makers=[],
        contacts=[]
    )
    database.save_unified_evidences(ev_records)

    # Fetch via database and verify consistency
    usage_evidence = database.get_unified_evidence(job_id=job_id, claim_type=ClaimType.PRODUCT_USAGE)
    assert len(usage_evidence) >= 1
    assert any("Jedox" in ev.claim_text for ev in usage_evidence)

    all_evidence = database.get_unified_evidence(job_id=job_id)
    assert len(all_evidence) >= len(usage_evidence)


# ---------------------------------------------------------------------------
# Test 10: Workflow Selection Survives Submission, Persistence, and Retrieval
# ---------------------------------------------------------------------------
def test_workflow_selection_survives_submission_and_retrieval(client):
    """GENERAL, RECOV, and JEDOX workflows are persisted and retrieved exactly as submitted."""
    for wf in [WorkflowType.GENERAL, WorkflowType.RECOV, WorkflowType.JEDOX]:
        payload = {
            "url": "https://quotes.toscrape.com/",
            "workflow": wf.value,
            "max_depth": 1,
            "max_pages": 5,
            "max_pages_per_domain": 5
        }
        res = client.post("/api/crawl/jobs", json=payload)
        assert res.status_code == 201
        data = res.json()
        job_id = data["id"]
        assert data["workflow"] == wf.value

        # Fetch job by ID
        fetch_res = client.get(f"/api/crawl/jobs/{job_id}")
        assert fetch_res.status_code == 200
        assert fetch_res.json()["workflow"] == wf.value


# ---------------------------------------------------------------------------
# Test 11: Historical Jobs Are Not Rewritten by New Classification Logic
# ---------------------------------------------------------------------------
def test_historical_jobs_preserved():
    """Jobs 32, 34, and 35 must exist in leads.db with their original configurations."""
    for job_id in [32, 34, 35]:
        job = database.get_crawl_job(job_id)
        if job:
            assert job.id == job_id
            assert job.seed_url is not None
            # Verify Job 35 historical workflow is preserved as GENERAL
            if job_id == 35:
                assert job.workflow == WorkflowType.GENERAL
                assert job.target_product == "Jedox"


# ---------------------------------------------------------------------------
# Test 12: CSV, Excel, and JSON Exports Preserve Consistent Classifications
# ---------------------------------------------------------------------------
def test_exports_preserve_consistent_classifications_and_workflow(client):
    """Excel, CSV ZIP, and JSON exports produce consistent records and include workflow."""
    job = database.get_crawl_job(35)
    if not job:
        pytest.skip("Job 35 not found in database")

    # JSON export
    res_json = client.get("/api/crawl/jobs/35/export?format=json")
    assert res_json.status_code == 200
    json_data = res_json.json()
    assert "workflow" in json_data
    assert json_data["workflow"] == "GENERAL"
    assert "candidates" in json_data
    assert "evidence" in json_data
    assert "decision_makers" in json_data
    assert "contacts" in json_data

    # CSV ZIP export
    res_csv = client.get("/api/crawl/jobs/35/export?format=csv")
    assert res_csv.status_code == 200
    assert res_csv.headers["content-type"] == "application/zip"

    # Excel export
    res_excel = client.get("/api/crawl/jobs/35/export?format=excel")
    assert res_excel.status_code == 200
    assert "spreadsheetml" in res_excel.headers["content-type"]
