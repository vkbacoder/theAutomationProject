"""Automated tests for Lead Research models, SQLite database, and pipeline integration.

Uses isolated temporary SQLite databases and mocked scraper calls to verify
deduplication, provenance tracking, evidence storage, and API routes.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app import app
import database
from dedup import (
    infer_company_name_from_title,
    is_fuzzy_name_match,
    normalize_company_name,
    normalize_domain,
)
from models import (
    CompanyProfile,
    DecisionMaker,
    FitLevel,
    LeadRecord,
    QualificationScore,
    ResearchStatus,
    ScrapeEvidence,
    VerificationStatus,
    WorkflowType,
)
import pipeline
from scraper import HeadingsGroup, ScrapeResponse

client = TestClient(app)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for test isolation."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.init_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass


# -------------------------------------------------------------
# 1. Deduplication Engine Unit Tests
# -------------------------------------------------------------

def test_normalize_domain():
    """Test extracting clean domain strings."""
    assert normalize_domain("https://WWW.Example-Corp.COM/about?query=1") == "example-corp.com"
    assert normalize_domain("http://jedox.com/") == "jedox.com"
    assert normalize_domain("finlytyx.ai/recov") == "finlytyx.ai"


def test_normalize_company_name():
    """Test corporate suffix stripping and character normalization."""
    assert normalize_company_name("Acme Industrial Solutions, Inc.") == "acme industrial"
    assert normalize_company_name("Finlytyx AI Technologies Pvt Ltd") == "finlytyx ai"
    assert normalize_company_name("Jedox AG") == "jedox ag"
    assert normalize_company_name("Enorme Capital LLC") == "enorme capital"


def test_fuzzy_name_matching():
    """Test RapidFuzz entity matching with variations."""
    assert is_fuzzy_name_match("Acme Corp", "Acme Corporation")
    assert is_fuzzy_name_match("Finlytyx Solutions Pvt Ltd", "Finlytyx Ltd")
    assert not is_fuzzy_name_match("Acme Corp", "Comcast Cable")


def test_infer_company_name_from_title():
    """Test inferring clean company names from HTML titles."""
    assert infer_company_name_from_title("Jedox | Enterprise Performance Management", "jedox.com") == "Jedox"
    assert infer_company_name_from_title("Home - Finlytyx Recov Automation", "finlytyx.com") == "Finlytyx Recov Automation"
    assert infer_company_name_from_title("Welcome to Our Site", "acme-machining.com") == "Acme Machining"


# -------------------------------------------------------------
# 2. Database Schema & CRUD Unit Tests
# -------------------------------------------------------------

def test_init_db_idempotency(temp_db):
    """Verify schema initialization can run multiple times without error."""
    database.init_db(temp_db)
    database.init_db(temp_db)


def test_company_creation_and_retrieval(temp_db):
    """Test creating and reading a company profile."""
    company = CompanyProfile(
        company_name="Enorme Capital",
        normalized_name=normalize_company_name("Enorme Capital"),
        domain="enormecapital.com",
        website_url="https://enormecapital.com",
        workflow=WorkflowType.RECOV,
        industry="NBFC & Lending",
    )
    created = database.create_company(company, db_path=temp_db)
    assert created.id is not None

    fetched = database.get_company_by_id(created.id, db_path=temp_db)
    assert fetched is not None
    assert fetched.company_name == "Enorme Capital"
    assert fetched.workflow == WorkflowType.RECOV
    assert fetched.research_status == ResearchStatus.PENDING


def test_domain_deduplication_in_same_workflow(temp_db):
    """Verify lookup by domain prevents duplicate companies in the same workflow."""
    company1 = CompanyProfile(
        company_name="Jedox Inc",
        normalized_name="jedox",
        domain="jedox.com",
        website_url="https://jedox.com",
        workflow=WorkflowType.JEDOX,
    )
    database.create_company(company1, db_path=temp_db)

    # Lookup by domain
    found = database.find_company_by_domain("jedox.com", WorkflowType.JEDOX, db_path=temp_db)
    assert found is not None
    assert found.domain == "jedox.com"

    # Searching with www should also find it
    found_www = database.find_company_by_domain("www.jedox.com", WorkflowType.JEDOX, db_path=temp_db)
    assert found_www is not None
    assert found_www.id == found.id


def test_workflow_isolation_allows_separate_profiles(temp_db):
    """Verify a company can have separate profiles for RECOV and Jedox workflows."""
    comp_recov = CompanyProfile(
        company_name="Omni Corp",
        normalized_name="omni",
        domain="omnicorp.com",
        website_url="https://omnicorp.com",
        workflow=WorkflowType.RECOV,
    )
    comp_jedox = CompanyProfile(
        company_name="Omni Corp",
        normalized_name="omni",
        domain="omnicorp.com",
        website_url="https://omnicorp.com",
        workflow=WorkflowType.JEDOX,
    )

    c1 = database.create_company(comp_recov, db_path=temp_db)
    c2 = database.create_company(comp_jedox, db_path=temp_db)

    assert c1.id != c2.id
    assert database.find_company_by_domain("omnicorp.com", WorkflowType.RECOV, db_path=temp_db).id == c1.id
    assert database.find_company_by_domain("omnicorp.com", WorkflowType.JEDOX, db_path=temp_db).id == c2.id


def test_scrape_evidence_storage_and_linkage(temp_db):
    """Test storing scrape evidence linked to a company."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Test Bank",
            normalized_name="test bank",
            domain="testbank.com",
            website_url="https://testbank.com",
        ),
        db_path=temp_db,
    )

    evidence = ScrapeEvidence(
        company_id=comp.id,
        source_url="https://testbank.com/about",
        http_status=200,
        title="About Test Bank",
        raw_text="Providing retail loans and debt servicing across branches.",
        word_count=8,
    )
    saved_ev = database.add_scrape_evidence(evidence, db_path=temp_db)
    assert saved_ev.id is not None

    all_ev = database.get_evidence_by_company(comp.id, db_path=temp_db)
    assert len(all_ev) == 1
    assert all_ev[0].source_url == "https://testbank.com/about"
    assert "retail loans" in all_ev[0].raw_text


def test_contact_traceability_source_url(temp_db):
    """Verify decision-maker contacts store the exact evidence source URL."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Finlytyx",
            normalized_name="finlytyx",
            domain="finlytyx.com",
            website_url="https://finlytyx.com",
        ),
        db_path=temp_db,
    )

    contact = DecisionMaker(
        company_id=comp.id,
        name="John Doe",
        title="Head of Credit & Collections",
        email="john.doe@finlytyx.com",
        source_url="https://finlytyx.com/leadership",
    )
    saved = database.add_contact(contact, db_path=temp_db)
    assert saved.id is not None

    contacts = database.get_contacts_by_company(comp.id, db_path=temp_db)
    assert len(contacts) == 1
    assert contacts[0].source_url == "https://finlytyx.com/leadership"


def test_qualification_scoring_ai_provenance(temp_db):
    """Verify that AI-generated scores are explicitly flagged vs verified rule scores."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Auto Finance Ltd",
            normalized_name="auto finance",
            domain="autofinance.com",
            website_url="https://autofinance.com",
            workflow=WorkflowType.RECOV,
        ),
        db_path=temp_db,
    )

    # 1. Rule-based verified score
    rule_score = QualificationScore(
        company_id=comp.id,
        workflow=WorkflowType.RECOV,
        score=85.0,
        fit_level=FitLevel.HIGH,
        reasoning="Company operates active vehicle lending portfolio with NPA recovery needs.",
        criteria_matched=["lending_nbfc", "recovery_signals"],
        is_ai_generated=False,
    )
    database.add_qualification_score(rule_score, db_path=temp_db)

    # 2. AI-inferred hypothesis score
    ai_score = QualificationScore(
        company_id=comp.id,
        workflow=WorkflowType.RECOV,
        score=72.0,
        fit_level=FitLevel.MEDIUM,
        reasoning="LLM inferred possible overdue debtor bottleneck from careers page.",
        criteria_matched=["ai_sentiment_hypothesis"],
        is_ai_generated=True,
    )
    database.add_qualification_score(ai_score, db_path=temp_db)

    scores = database.get_qualifications_by_company(comp.id, db_path=temp_db)
    assert len(scores) == 2
    assert any(not s.is_ai_generated for s in scores)
    assert any(s.is_ai_generated for s in scores)


def test_research_history_audit_trail(temp_db):
    """Test chronological logging of research events."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Alpha Corp",
            normalized_name="alpha",
            domain="alpha.com",
            website_url="https://alpha.com",
        ),
        db_path=temp_db,
    )

    database.add_history_entry(comp.id, "INGESTED", "Created lead record", db_path=temp_db)
    database.add_history_entry(comp.id, "STATUS_CHANGE", "Moved to QUALIFIED", db_path=temp_db)

    history = database.get_history_by_company(comp.id, db_path=temp_db)
    assert len(history) == 2
    assert history[0].action == "INGESTED"
    assert history[1].action == "STATUS_CHANGE"


# -------------------------------------------------------------
# 3. Pipeline Ingestion & Heuristic Scoring Tests
# -------------------------------------------------------------

def test_pipeline_ingest_and_research(temp_db):
    """Test full pipeline ingestion with mocked scraper response."""
    mock_response = ScrapeResponse(
        success=True,
        url="https://target-nbfc.com",
        final_url="https://target-nbfc.com/home",
        status_code=200,
        content_type="text/html",
        title="Fast Loans NBFC - Microfinance & Credit",
        description="Affordable loans and microcredit across 200 branches.",
        canonical_url="https://target-nbfc.com/",
        headings=HeadingsGroup(h1=["Microfinance Solutions"], h2=["Customer Loans"], h3=[]),
        links=[],
        metadata={"og:title": "Fast Loans NBFC"},
        text="Fast Loans NBFC provides microfinance, personal loans, and debt management services.",
        word_count=12,
    )

    with patch("pipeline.scrape_website", return_value=mock_response):
        lead = pipeline.ingest_and_research_website(
            url="https://target-nbfc.com",
            workflow=WorkflowType.RECOV,
            db_path=temp_db,
        )

        assert lead.company.id is not None
        assert lead.company.domain == "target-nbfc.com"
        assert lead.company.workflow == WorkflowType.RECOV
        assert len(lead.evidence) == 1
        assert lead.evidence[0].http_status == 200
        assert len(lead.history) == 1
        assert lead.history[0].action == "INGESTED"


def test_pipeline_heuristic_signals_recov(temp_db):
    """Test RECOV signal detection on a financial lending lead."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Apex Capital",
            normalized_name="apex capital",
            domain="apexcap.com",
            website_url="https://apexcap.com",
            workflow=WorkflowType.RECOV,
            description="NBFC specializing in consumer credit, lending portfolios, and debt recovery.",
        ),
        db_path=temp_db,
    )
    database.add_scrape_evidence(
        ScrapeEvidence(
            company_id=comp.id,
            source_url="https://apexcap.com",
            raw_text="Managing overdue loans, NPA accounts, and delinquent receivables across branches.",
        ),
        db_path=temp_db,
    )

    lead = database.get_lead_record(comp.id, db_path=temp_db)
    score = pipeline.evaluate_lead_signals(lead, WorkflowType.RECOV, db_path=temp_db)

    assert score.score >= 80.0
    assert score.fit_level == FitLevel.HIGH
    assert not score.is_ai_generated
    assert "financial_lending_sector" in score.criteria_matched
    assert "collections_receivables_exposure" in score.criteria_matched


def test_pipeline_heuristic_signals_jedox(temp_db):
    """Test Jedox signal detection on an enterprise FP&A lead."""
    comp = database.create_company(
        CompanyProfile(
            company_name="Global Retail Holdings",
            normalized_name="global retail",
            domain="globalretail.com",
            website_url="https://globalretail.com",
            workflow=WorkflowType.JEDOX,
            description="Multinational retail corporation with multiple subsidiaries.",
        ),
        db_path=temp_db,
    )
    database.add_scrape_evidence(
        ScrapeEvidence(
            company_id=comp.id,
            source_url="https://globalretail.com",
            raw_text="Complex financial planning, budgeting, forecasting, and consolidation integrated with SAP ERP and Power BI.",
        ),
        db_path=temp_db,
    )

    lead = database.get_lead_record(comp.id, db_path=temp_db)
    score = pipeline.evaluate_lead_signals(lead, WorkflowType.JEDOX, db_path=temp_db)

    assert score.score >= 80.0
    assert score.fit_level == FitLevel.HIGH
    assert "fpa_budgeting_requirements" in score.criteria_matched
    assert "compatible_erp_bi_stack" in score.criteria_matched


# -------------------------------------------------------------
# 4. API End-to-End Route Tests
# -------------------------------------------------------------

def test_api_lead_ingest_and_get():
    """Test POST /api/leads/ingest and GET /api/leads/{id}."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    test_url = f"https://client-{uid}.com"

    mock_response = ScrapeResponse(
        success=True,
        url=test_url,
        final_url=test_url,
        status_code=200,
        content_type="text/html",
        title=f"Acme Global Finance {uid}",
        description="Global financial planning services.",
        canonical_url=test_url,
        headings=HeadingsGroup(),
        links=[],
        metadata={},
        text="Enterprise financial planning and reporting systems.",
        word_count=8,
    )

    with patch("pipeline.scrape_website", return_value=mock_response):
        ingest_res = client.post(
            "/api/leads/ingest",
            json={
                "url": test_url,
                "workflow": "JEDOX",
                "company_name": f"Acme Global {uid}",
            },
        )
        assert ingest_res.status_code == 200
        data = ingest_res.json()
        assert data["company"]["company_name"] == f"Acme Global {uid}"
        assert data["company"]["workflow"] == "JEDOX"
        company_id = data["company"]["id"]

        # Fetch lead
        get_res = client.get(f"/api/leads/{company_id}")
        assert get_res.status_code == 200
        lead_data = get_res.json()
        assert lead_data["company"]["id"] == company_id
        assert len(lead_data["evidence"]) >= 1


def test_api_add_contact_and_qualify():
    """Test adding contacts and qualification scores via REST API."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    domain = f"capital-{uid}.com"

    comp = database.create_company(
        CompanyProfile(
            company_name=f"Capital Partners {uid}",
            normalized_name=f"capital partners {uid}",
            domain=domain,
            website_url=f"https://{domain}",
            workflow=WorkflowType.RECOV,
        )
    )

    # 1. Add contact
    contact_res = client.post(
        f"/api/leads/{comp.id}/contacts",
        json={
            "name": "Sarah Connor",
            "title": "VP of Collections",
            "email": "sarah@cappartners.com",
            "source_url": f"https://{domain}/team",
        },
    )
    assert contact_res.status_code == 200
    contact_data = contact_res.json()
    assert contact_data["name"] == "Sarah Connor"
    assert contact_data["source_url"] == f"https://{domain}/team"

    # 2. Add qualification score
    qual_res = client.post(
        f"/api/leads/{comp.id}/qualify",
        json={
            "workflow": "RECOV",
            "score": 88.0,
            "fit_level": "HIGH",
            "reasoning": "High recovery volume confirmed.",
            "criteria_matched": ["collections_volume"],
            "is_ai_generated": False,
        },
    )
    assert qual_res.status_code == 200
    qual_data = qual_res.json()
    assert qual_data["score"] == 88.0
    assert qual_data["fit_level"] == "HIGH"
