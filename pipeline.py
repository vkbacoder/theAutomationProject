"""Lead Research Pipeline integrating scraping, deduplication, and persistence.

Handles ingestion, company resolution, evidence linking, and workflow-specific
heuristic qualification for RECOV and Jedox.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
import httpx

from database import (
    add_contact,
    add_history_entry,
    add_qualification_score,
    add_scrape_evidence,
    create_company,
    find_company_by_domain,
    find_company_by_fuzzy_name,
    get_lead_record,
    init_db,
    update_company_status,
)
from dedup import (
    infer_company_name_from_title,
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
from scraper import ScrapeResponse, scrape_website

# -------------------------------------------------------------
# Workflow Keywords for Heuristic Signal Detection
# -------------------------------------------------------------

RECOV_SIGNALS = {
    "lending_nbfc": [
        r"\bnbfc\b", r"\blending\b", r"\bmicrofinance\b", r"\bfintech\b",
        r"\bloan\b", r"\bcredit\b", r"\bbank\b", r"\bfinancial\s+services\b"
    ],
    "collections_recovery": [
        r"\brecovery\b", r"\bcollections?\b", r"\boverdue\b", r"\bdelinquen",
        r"\breceivables?\b", r"\bdebt\b", r"\bdefault\b", r"\bnpa\b"
    ],
    "enterprise_scale": [
        r"\bbranches\b", r"\bcustomers?\b", r"\bportfolio\b", r"\bassets\b"
    ]
}

JEDOX_SIGNALS = {
    "fpa_planning": [
        r"\bfp&a\b", r"\bfinancial\s+planning\b", r"\bbudgeting\b",
        r"\bforecasting\b", r"\bconsolidation\b", r"\bcorporate\s+performance\b"
    ],
    "erp_bi_stack": [
        r"\bsap\b", r"\berp\b", r"\bpower\s*bi\b", r"\boracle\b",
        r"\bmicrosoft\s+dynamics\b", r"\bnetsuite\b", r"\bsalesforce\b"
    ],
    "multi_entity": [
        r"\bglobal\b", r"\bsubsidiaries\b", r"\bmultinational\b",
        r"\bdivisions?\b", r"\bgroup\s+of\s+companies\b"
    ]
}


class PipelineException(Exception):
    """Raised when lead ingestion or processing encounters an error."""
    pass


def ingest_and_research_website(
    url: str,
    workflow: WorkflowType = WorkflowType.GENERAL,
    company_name: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    db_path: Optional[str] = None,
) -> LeadRecord:
    """Ingest a target website, execute scraping, deduplicate company, and record evidence."""
    # Ensure database tables exist
    init_db(db_path)

    # 1. Scrape target website using the existing scraper
    scrape_result: ScrapeResponse = scrape_website(url, client=client)
    if not scrape_result.success:
        raise PipelineException(
            f"Failed to ingest URL '{url}': {scrape_result.error or 'Scraping failed'} "
            f"[{scrape_result.error_type or 'ScraperError'}]"
        )

    # 2. Extract and resolve domain
    final_url = scrape_result.final_url or url
    domain = normalize_domain(final_url)
    if not domain:
        raise PipelineException(f"Could not extract a valid domain from '{final_url}'.")

    # 3. Determine company name
    inferred_name = company_name
    if not inferred_name:
        inferred_name = infer_company_name_from_title(scrape_result.title, domain)
    clean_name = inferred_name.strip()
    norm_name = normalize_company_name(clean_name)

    # 4. Check for existing company (Deduplication)
    # Step 4a: Check exact domain match within workflow
    existing_company = find_company_by_domain(domain, workflow, db_path=db_path)

    # Step 4b: If no domain match, check fuzzy company name match
    if not existing_company and clean_name:
        existing_company = find_company_by_fuzzy_name(
            clean_name, workflow, threshold=88.0, db_path=db_path
        )

    if existing_company:
        company = existing_company
        # Update description if it was previously empty
        if not company.description and scrape_result.description:
            company.description = scrape_result.description
        add_history_entry(
            company.id,  # type: ignore
            action="RE_SCRAPED",
            details=f"Re-scraped evidence from {final_url} (HTTP {scrape_result.status_code})",
            db_path=db_path,
        )
    else:
        # Create new company record
        new_company = CompanyProfile(
            company_name=clean_name,
            normalized_name=norm_name,
            domain=domain,
            website_url=final_url,
            industry=None,
            description=scrape_result.description or None,
            country=None,
            city=None,
            workflow=workflow,
            research_status=ResearchStatus.SCRAPED,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        company = create_company(new_company, db_path=db_path)
        add_history_entry(
            company.id,  # type: ignore
            action="INGESTED",
            details=f"Created new {workflow.value} lead profile from {final_url}",
            db_path=db_path,
        )

    # 5. Store Scrape Evidence with strict provenance tracking
    evidence = ScrapeEvidence(
        company_id=company.id,
        source_url=final_url,
        http_status=scrape_result.status_code,
        title=scrape_result.title,
        meta_description=scrape_result.description,
        canonical_url=scrape_result.canonical_url,
        raw_text=scrape_result.text,
        headings_json=scrape_result.headings.model_dump(),
        metadata_json=scrape_result.metadata,
        links_count=len(scrape_result.links),
        word_count=scrape_result.word_count,
    )
    add_scrape_evidence(evidence, db_path=db_path)

    # 6. Retrieve and return the complete aggregated record
    lead_record = get_lead_record(company.id, db_path=db_path)  # type: ignore
    if not lead_record:
        raise PipelineException(f"Failed to load lead record for company id {company.id}")

    return lead_record


# -------------------------------------------------------------
# Rule-Based Heuristic Lead Qualification
# -------------------------------------------------------------

def evaluate_lead_signals(
    lead: LeadRecord, workflow: WorkflowType, db_path: Optional[str] = None
) -> QualificationScore:
    """Evaluate lead against factual signals extracted from web evidence.
    
    Produces a rule-based qualification score with traceable criteria.
    Marks is_ai_generated=False to maintain truth boundaries.
    """
    corpus_parts = [
        lead.company.company_name,
        lead.company.description or "",
    ]
    for ev in lead.evidence:
        if ev.title:
            corpus_parts.append(ev.title)
        if ev.meta_description:
            corpus_parts.append(ev.meta_description)
        if ev.raw_text:
            corpus_parts.append(ev.raw_text[:10000])

    corpus = " ".join(corpus_parts).lower()
    criteria_matched: List[str] = []
    points = 0.0

    if workflow == WorkflowType.RECOV:
        # Check RECOV signals: lending/nbfc (40 pts), collections/receivables (40 pts), scale (20 pts)
        for category, patterns in RECOV_SIGNALS.items():
            matched_terms = [p for p in patterns if re.search(p, corpus)]
            if matched_terms:
                if category == "lending_nbfc":
                    points += 40.0
                    criteria_matched.append("financial_lending_sector")
                elif category == "collections_recovery":
                    points += 40.0
                    criteria_matched.append("collections_receivables_exposure")
                elif category == "enterprise_scale":
                    points += 20.0
                    criteria_matched.append("multi_branch_scale")

    elif workflow == WorkflowType.JEDOX:
        # Check Jedox signals: FP&A planning (45 pts), ERP/BI stack (35 pts), multi-entity (20 pts)
        for category, patterns in JEDOX_SIGNALS.items():
            matched_terms = [p for p in patterns if re.search(p, corpus)]
            if matched_terms:
                if category == "fpa_planning":
                    points += 45.0
                    criteria_matched.append("fpa_budgeting_requirements")
                elif category == "erp_bi_stack":
                    points += 35.0
                    criteria_matched.append("compatible_erp_bi_stack")
                elif category == "multi_entity":
                    points += 20.0
                    criteria_matched.append("multi_entity_complexity")

    else:  # GENERAL
        if len(corpus) > 300:
            points += 50.0
            criteria_matched.append("active_online_presence")
        if len(lead.evidence) > 0 and lead.evidence[0].http_status == 200:
            points += 50.0
            criteria_matched.append("verified_web_endpoint")

    # Determine Fit Level
    score_val = min(100.0, max(0.0, points))
    if score_val >= 70.0:
        fit = FitLevel.HIGH
    elif score_val >= 40.0:
        fit = FitLevel.MEDIUM
    elif score_val >= 20.0:
        fit = FitLevel.LOW
    else:
        fit = FitLevel.UNQUALIFIED

    reasoning = (
        f"Rule-based evaluation for {workflow.value} identified {len(criteria_matched)} signals: "
        f"{', '.join(criteria_matched) if criteria_matched else 'no distinct target signals found'}."
    )

    score_obj = QualificationScore(
        company_id=lead.company.id,
        workflow=workflow,
        score=score_val,
        fit_level=fit,
        reasoning=reasoning,
        criteria_matched=criteria_matched,
        is_ai_generated=False,  # Factual rule-based evaluation
    )

    saved_score = add_qualification_score(score_obj, db_path=db_path)

    # Update company status to QUALIFIED
    if lead.company.id:
        update_company_status(
            lead.company.id,
            status=ResearchStatus.QUALIFIED if fit in (FitLevel.HIGH, FitLevel.MEDIUM) else ResearchStatus.SCRAPED,
            db_path=db_path,
        )
        add_history_entry(
            lead.company.id,
            action="SCORED",
            details=f"Evaluated fit for {workflow.value}: Score={score_val}, Fit={fit.value}",
            db_path=db_path,
        )

    return saved_score
