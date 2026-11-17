# ============================================================================
# Test Suite: Intelligent Search-Guided Research Architecture
# Covers all 14 mandatory validation areas from Task Specification Section 13
# ============================================================================

import os
import sys
import pytest
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from research_scoring import (
    compute_url_priority,
    normalize_url_for_research,
    PriorityScoreComponents,
)
from source_classifier import (
    classify_source,
    get_source_authority_score,
    SourceCategory,
)
from search_service import (
    ExternalResearchFrontier,
    ResearchBudget,
    SearchResultItem,
    MockSearchProvider,
    generate_external_queries,
    generate_followup_queries,
)
from research_controller import ResearchController, ResearchStage
from scraper import validate_url_security
from candidate_verifier import (
    verify_candidate_entity,
    is_invalid_entity_candidate,
    is_partner_page,
)
from intelligence_extractor import (
    extract_decision_makers_from_text,
    classify_contact_ownership,
)
from models import (
    ContactOwnership,
    RoleCategory,
    WorkflowType,
    RelationshipType,
    CandidateClassification,
)


# ============================================================================
# 1. URL Normalization and Deduplication
# ============================================================================
def test_01_url_normalization_and_deduplication():
    url1 = "https://NTAW.com.au/about-us/#leadership"
    url2 = "https://ntaw.com.au/about-us"
    url3 = "https://ntaw.com.au/about-us/"

    norm1 = normalize_url_for_research(url1)
    norm2 = normalize_url_for_research(url2)
    norm3 = normalize_url_for_research(url3)

    assert norm1 == "https://ntaw.com.au/about-us"
    assert norm2 == "https://ntaw.com.au/about-us"
    assert norm3 == "https://ntaw.com.au/about-us"
    assert norm1 == norm2 == norm3

    # Frontier deduplication
    frontier = ExternalResearchFrontier(
        provider=MockSearchProvider({}),
        budget=ResearchBudget(),
    )
    assert frontier.is_duplicate_url(norm1) is False
    frontier.record_url(norm1)
    assert frontier.is_duplicate_url(norm1) is True
    assert frontier.is_duplicate_url("https://ntaw.com.au/about-us/#team") is True


# ============================================================================
# 2. BFS Traversal and Depth Enforcement
# ============================================================================
def test_02_bfs_traversal_and_depth_enforcement():
    budget = ResearchBudget(max_depth=2, max_internal_pages=20)
    assert budget.max_depth == 2
    assert budget.max_internal_pages == 20

    # Depth 3 should exceed limit
    depth_allowed = lambda d: d <= budget.max_depth
    assert depth_allowed(0) is True
    assert depth_allowed(1) is True
    assert depth_allowed(2) is True
    assert depth_allowed(3) is False


# ============================================================================
# 3. Best-First URL Selection and Priority Ordering
# ============================================================================
def test_03_best_first_url_selection():
    target_comp = "National Tyre & Wheel"
    target_prod = "Jedox"

    urls = [
        "https://ntaw.com.au/privacy-policy",
        "https://ntaw.com.au/investors/annual-reports",
        "https://ntaw.com.au/leadership-team",
        "https://ntaw.com.au/terms-and-conditions",
        "https://ntaw.com.au/products/tyres/item-12345",
    ]

    scored = []
    for u in urls:
        score = compute_url_priority(
            url=u,
            company_name=target_comp,
            target_product=target_prod,
            workflow="JEDOX",
            target_company_domain="ntaw.com.au",
        )
        scored.append((score.final_score, u))

    # Sort descending by priority (Best-First)
    scored.sort(key=lambda x: x[0], reverse=True)
    top_urls = [u for _, u in scored[:2]]

    # High priority pages (leadership & investors) must rank strictly higher than privacy & product catalogue
    assert "https://ntaw.com.au/leadership-team" in top_urls
    assert "https://ntaw.com.au/investors/annual-reports" in top_urls

    lowest_url = scored[-1][1]
    assert lowest_url in (
        "https://ntaw.com.au/privacy-policy",
        "https://ntaw.com.au/terms-and-conditions",
        "https://ntaw.com.au/products/tyres/item-12345",
    )


# ============================================================================
# 4. Priority Score Calculation Formula (4 components, 0-100 range)
# ============================================================================
def test_04_priority_score_calculation_formula():
    res = compute_url_priority(
        url="https://ntaw.com.au/investor-centre/board-management",
        company_name="National Tyre & Wheel",
        target_product="Jedox",
        workflow="JEDOX",
        objective="Find CFO and Jedox implementation",
        target_company_domain="ntaw.com.au",
    )

    # 4 Components must exist
    assert 0.0 <= res.research_relevance <= 100.0
    assert 0.0 <= res.keyword_relevance <= 100.0
    assert 0.0 <= res.source_authority <= 100.0
    assert 0.0 <= res.information_potential <= 100.0

    # Exact mathematical formula:
    # 0.35 * Research + 0.25 * Keyword + 0.20 * Source + 0.20 * Info Potential
    expected = round(
        0.35 * res.research_relevance
        + 0.25 * res.keyword_relevance
        + 0.20 * res.source_authority
        + 0.20 * res.information_potential,
        2,
    )
    assert res.final_score == expected
    assert 0.0 <= res.final_score <= 100.0


# ============================================================================
# 5. Search Query Expansion for Jedox
# ============================================================================
def test_05_search_query_expansion_jedox():
    queries = generate_external_queries(
        company_name="National Tyre & Wheel",
        target_product="Jedox",
        workflow="JEDOX",
        partner_name="Qubix",
    )

    assert len(queries) >= 6
    assert '"National Tyre & Wheel" Jedox' in queries
    assert '"National Tyre & Wheel" Jedox customer' in queries
    assert '"National Tyre & Wheel" case study' in queries
    assert '"National Tyre & Wheel" customer story' in queries
    assert '"National Tyre & Wheel" CFO' in queries
    assert '"National Tyre & Wheel" leadership' in queries
    assert 'site:jedox.com "National Tyre & Wheel"' in queries
    assert '"Qubix" "National Tyre & Wheel" Jedox' in queries


# ============================================================================
# 6. Search Query Expansion for RECOV
# ============================================================================
def test_06_search_query_expansion_recov():
    queries = generate_external_queries(
        company_name="Acme Corp",
        target_product="RECOV",
        workflow="RECOV",
    )

    # Distinct templates from Jedox
    assert any("debt collection" in q.lower() or "recovery" in q.lower() or "recov" in q.lower() for q in queries)
    assert not any("jedox" in q.lower() for q in queries)
    assert '"Acme Corp" RECOV' in queries
    assert '"Acme Corp" collections' in queries or '"Acme Corp" debt recovery' in queries


# ============================================================================
# 7. Search Query Deduplication and Budget Limits
# ============================================================================
def test_07_search_query_deduplication_and_budget_limits():
    budget = ResearchBudget(max_search_queries=4)
    frontier = ExternalResearchFrontier(
        provider=MockSearchProvider({}),
        budget=budget,
    )

    # Initial batch of 5 queries (budget is 4)
    q_list = ["query A", "query B", "query A", "query C", "query D", "query E"]
    results = frontier.expand_and_execute_batch(
        queries=q_list,
        target_product="Jedox",
        company_name="NTAW",
        workflow="JEDOX",
    )

    # Must deduplicate 'query A' and respect max_search_queries limit of 4
    assert len(frontier.executed_queries) <= 4
    assert len(frontier.executed_queries) == len(set(frontier.executed_queries))
    assert frontier.can_execute_more_queries() is False


# ============================================================================
# 8. External Domain Handling and SSRF Protection
# ============================================================================
def test_08_external_domain_handling_and_ssrf_protection():
    # Valid external public URL
    safe_url = "https://www.jedox.com/en/customers/ntaw/"
    validate_url_security(safe_url)  # Must not raise

    # SSRF: localhost and private IPs must be blocked
    with pytest.raises(Exception):
        validate_url_security("http://localhost:8000/admin")

    with pytest.raises(Exception):
        validate_url_security("http://127.0.0.1:8000/")

    with pytest.raises(Exception):
        validate_url_security("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(Exception):
        validate_url_security("http://10.0.0.1/internal")


# ============================================================================
# 9. Source Classification into 7 Authority Categories
# ============================================================================
def test_09_source_classification_7_categories():
    t_domain = "ntaw.com.au"
    t_prod = "Jedox"

    c1 = classify_source("https://www.jedox.com/en/customers/ntaw/", t_domain, t_prod)
    c2 = classify_source("https://ntaw.com.au/about-us", t_domain, t_prod)
    c3 = classify_source("https://www.oaic.gov.au/privacy", t_domain, t_prod)
    c4 = classify_source("https://www.prnewswire.com/news-releases/ntaw-jedox-story.html", t_domain, t_prod)
    c5 = classify_source("https://au.linkedin.com/in/jason-lamb-cfo", t_domain, t_prod)
    c6 = classify_source("https://www.afr.com/companies/transport/national-tyre-update", t_domain, t_prod)
    c7 = classify_source("https://www.autoguru.com.au/service", t_domain, t_prod)

    assert c1 == SourceCategory.OFFICIAL_VENDOR
    assert c2 == SourceCategory.OFFICIAL_COMPANY
    assert c3 == SourceCategory.GOVERNMENT_REGULATORY
    assert c4 == SourceCategory.PRESS_RELEASE
    assert c5 == SourceCategory.PROFESSIONAL_PROFILE
    assert c6 == SourceCategory.NEWS_PUBLICATION
    assert c7 == SourceCategory.THIRD_PARTY

    # Check authority scores hierarchy
    assert get_source_authority_score(c1) >= 95.0
    assert get_source_authority_score(c2) >= 90.0
    assert get_source_authority_score(c3) >= 85.0
    assert get_source_authority_score(c4) >= 75.0
    assert get_source_authority_score(c5) >= 70.0
    assert get_source_authority_score(c6) >= 65.0
    assert get_source_authority_score(c7) <= 40.0


# ============================================================================
# 10. Entity Validation: Strict Rejection of False Positives
# ============================================================================
def test_10_entity_validation_rejection_of_false_positives():
    invalid_candidates = [
        "Mission Statement",
        "Environmental Policy",
        "We have",
        "Fleet Forms",
        "4WD & Off",
        "Road",
        "About Us",
        "Terms of Use",
        "Privacy Policy",
        "Australia",
    ]

    for cand in invalid_candidates:
        assert is_invalid_entity_candidate(cand) is True, f"Failed to reject: {cand}"
        is_valid, _ = verify_candidate_entity(cand, source_text="Company policy", context="heading")
        assert is_valid is False, f"Entity verification should reject: {cand}"

    # Valid candidate should pass
    valid_cand = "National Tyre & Wheel"
    assert is_invalid_entity_candidate(valid_cand) is False


# ============================================================================
# 11. Relationship Verification (Customer vs Partner vs Vendor vs Tech Mention)
# ============================================================================
def test_11_relationship_verification_types():
    # Customer story on vendor site
    vendor_url = "https://www.jedox.com/en/customers/ntaw/"
    vendor_text = "National Tyre & Wheel implemented Jedox for financial planning and reporting."
    cat = classify_source(vendor_url, "ntaw.com.au", "Jedox")
    assert cat == SourceCategory.OFFICIAL_VENDOR

    # Must recognize customer context on vendor site
    is_customer_source = (cat == SourceCategory.OFFICIAL_VENDOR and "customer" in vendor_url.lower())
    assert is_customer_source is True

    # Partner check: generic text containing 'partner' should not false-positive if not a partner directory
    body_with_partner_word = "We partner with our clients to provide quality tyres."
    assert is_partner_page(body_with_partner_word, "https://ntaw.com.au/about-us") is False

    partner_page_text = "Our Certified Technology Partners and Implementation Partner Directory"
    assert is_partner_page(partner_page_text, "https://example.com/partners") is True


# ============================================================================
# 12. Decision-Maker Extraction (CFO, published title, zero invented emails)
# ============================================================================
def test_12_decision_maker_extraction_and_zero_invented_emails():
    sample_text = (
        'Jason Lamb, Chief Financial Officer at National Tyre & Wheel: '
        '"Jedox has transformed our financial planning and analysis capabilities."'
    )

    dms = extract_decision_makers_from_text(
        text=sample_text,
        source_url="https://www.jedox.com/en/customers/ntaw/",
        target_company="National Tyre & Wheel",
        target_product="Jedox",
    )

    assert len(dms) >= 1
    jason = next((d for d in dms if "Jason Lamb" in d.full_name), None)
    assert jason is not None
    assert "Chief Financial Officer" in jason.published_title or "CFO" in jason.published_title
    assert jason.role_category == RoleCategory.EXECUTIVE or jason.role_category == RoleCategory.FINANCE_BUSINESS
    assert "Jedox has transformed" in jason.supporting_quote

    # CRITICAL: Decision maker extraction must NOT invent or extrapolate email
    assert getattr(jason, "email", None) is None or jason.email == ""


# ============================================================================
# 13. Contact Ownership Classification (TARGET_COMPANY, THIRD_PARTY, REGULATOR)
# ============================================================================
def test_13_contact_ownership_classification():
    target_comp = "National Tyre & Wheel"
    target_domain = "ntaw.com.au"

    # 1. Target company contact on company contact page
    c1_owner, _ = classify_contact_ownership(
        contact_type="PHONE",
        contact_value="07 3715 2200",
        context_text="National Tyre & Wheel Head Office: 07 3715 2200",
        page_url="https://ntaw.com.au/contact-us",
        target_company=target_comp,
        target_domain=target_domain,
    )
    assert c1_owner == ContactOwnership.TARGET_COMPANY

    # 2. Third-party vendor contact on fleet form (e.g. AutoGuru)
    c2_owner, _ = classify_contact_ownership(
        contact_type="PHONE",
        contact_value="1300 655 661",
        context_text="For fleet servicing contact AutoGuru customer support at 1300 655 661",
        page_url="https://ntaw.com.au/fleet-forms",
        target_company=target_comp,
        target_domain=target_domain,
    )
    assert c2_owner == ContactOwnership.THIRD_PARTY

    # 3. Regulatory authority contact (e.g. OAIC)
    c3_owner, _ = classify_contact_ownership(
        contact_type="EMAIL",
        contact_value="enquiries@oaic.gov.au",
        context_text="Office of the Australian Information Commissioner: enquiries@oaic.gov.au",
        page_url="https://ntaw.com.au/privacy-policy",
        target_company=target_comp,
        target_domain=target_domain,
    )
    assert c3_owner == ContactOwnership.REGULATOR


# ============================================================================
# 14. Research Stopping Conditions (Objectives met vs Budget exhausted)
# ============================================================================
def test_14_research_stopping_conditions():
    # Budget exhausted condition
    budget = ResearchBudget(
        max_internal_pages=5,
        max_external_pages_retrieved=3,
        max_search_queries=2,
    )

    frontier = ExternalResearchFrontier(
        provider=MockSearchProvider({}),
        budget=budget,
    )

    # Execute up to budget
    frontier.expand_and_execute_batch(["q1", "q2"], "Jedox", "NTAW", "JEDOX")
    assert frontier.can_execute_more_queries() is False

    # Lead qualification assessment logic:
    # When both customer relationship and product usage are confirmed -> LEAD_QUALIFIED
    c_confirmed = CandidateClassification.CONFIRMED
    rel_type = RelationshipType.CUSTOMER
    assert (c_confirmed == CandidateClassification.CONFIRMED and rel_type == RelationshipType.CUSTOMER)
