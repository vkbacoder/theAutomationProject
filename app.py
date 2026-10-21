"""FastAPI application for the Lead Research & Qualification System.

Provides:
- POST /api/scrape: Web scraper endpoint
- GET  /api/health: Service and Vishnu LLM health status
- POST /api/chat: LLM terminal chat endpoint (preserved from chatbot.py)
- GET  /: Serves the Web Scraper Test dashboard
"""

from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
from pydantic import BaseModel, Field

import config
from scraper import (
    ScrapeRequest,
    ScrapeResponse,
    SecurityException,
    scrape_website,
    validate_url_security,
)
from dedup import normalize_domain
import database
from models import (
    AddContactRequest,
    CandidateCategory,
    CandidateClassification,
    ClaimType,
    CompanyProfile,
    ContactType,
    CrawlJob,
    CrawlJobMetrics,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    CreateCrawlJobRequest,
    CustomerCandidate,
    DecisionMaker,
    DiscoveredDocument,
    IngestLeadRequest,
    LeadRecord,
    PublicContact,
    QualificationScore,
    QualifyLeadRequest,
    RelationshipType,
    ResearchStatus,
    RoleCategory,
    ScrapeEvidence,
    UnifiedEvidence,
    WorkflowType,
)
import pipeline
from crawler_worker import (
    get_worker_status,
    start_embedded_worker,
    stop_embedded_worker,
    wake_worker,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Initialize database tables on module load
database.init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan managing background crawl worker thread."""
    start_embedded_worker()
    yield
    stop_embedded_worker()


app = FastAPI(
    title="AI-Powered Lead Research & Qualification System",
    description="Web scraping ingestion engine and Vishnu LLM integration for RECOV and Jedox.",
    version="1.1.0",
    lifespan=lifespan,
)

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Favicon endpoint returning 204 No Content to avoid browser 404 console errors."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ChatRequest(BaseModel):
    """Request payload for LLM chat generation."""
    prompt: str = Field(..., description="Prompt to send to the Vishnu LLM")


@app.get("/api/health")
def health_check():
    """Health check endpoint reporting scraper and LLM status."""
    return {
        "status": "online",
        "service": "Lead Research & Web Scraper Engine",
        "version": "1.0.0",
        "configured_llm_url": config.LLM_API_URL or "Not configured",
    }


@app.post("/api/scrape", response_model=ScrapeResponse)
def api_scrape(payload: ScrapeRequest):
    """Scrape a public website, extract structured metadata, headings, links, and readable text."""
    target_url = payload.url.strip()
    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A non-empty URL parameter is required.",
        )

    result = scrape_website(target_url)

    # Return structured JSON
    return result


@app.post("/api/chat")
def api_chat(payload: ChatRequest):
    """Preserve Vishnu LLM generation through the web backend."""
    try:
        import chatbot
        reply = chatbot.generate_response(payload.prompt)
        return {
            "success": True,
            "prompt": payload.prompt,
            "response": reply,
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "error": f"Failed to contact Vishnu LLM: {e}",
            },
        )


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serve the Web Scraper Test frontend interface."""
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Lead Research System</h1><p>Frontend static file not found.</p>",
        status_code=404,
    )


# -------------------------------------------------------------
# Lead Research & Database Endpoints
# -------------------------------------------------------------

@app.post("/api/leads/ingest", response_model=LeadRecord)
def api_ingest_lead(payload: IngestLeadRequest):
    """Ingest a target website: scrapes, deduplicates, stores evidence, and returns the lead record."""
    try:
        lead = pipeline.ingest_and_research_website(
            url=payload.url,
            workflow=payload.workflow,
            company_name=payload.company_name,
        )
        return lead
    except pipeline.PipelineException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error during ingestion: {e}",
        )


@app.get("/api/leads", response_model=list[CompanyProfile])
def api_list_leads(
    workflow: Optional[WorkflowType] = None,
    status: Optional[ResearchStatus] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List company profiles with optional workflow, status, and search query filters."""
    return database.list_companies(
        workflow=workflow,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@app.get("/api/leads/{company_id}", response_model=LeadRecord)
def api_get_lead(company_id: int):
    """Retrieve full lead dossier including evidence, decision makers, and qualification scores."""
    lead = database.get_lead_record(company_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with company ID {company_id} not found.",
        )
    return lead


@app.post("/api/leads/{company_id}/qualify", response_model=QualificationScore)
def api_qualify_lead(company_id: int, payload: QualifyLeadRequest):
    """Record a qualification score with explicit provenance and reasoning."""
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with company ID {company_id} not found.",
        )

    score = QualificationScore(
        company_id=company_id,
        workflow=payload.workflow,
        score=payload.score,
        fit_level=payload.fit_level,
        reasoning=payload.reasoning,
        criteria_matched=payload.criteria_matched,
        is_ai_generated=payload.is_ai_generated,
    )
    saved = database.add_qualification_score(score)
    database.add_history_entry(
        company_id,
        action="QUALIFIED",
        details=f"Score {payload.score} ({payload.fit_level.value}) for {payload.workflow.value} (AI={payload.is_ai_generated})",
    )
    return saved


@app.post("/api/leads/{company_id}/contacts", response_model=DecisionMaker)
def api_add_contact(company_id: int, payload: AddContactRequest):
    """Attach a verified decision-maker contact to a company with provenance tracking."""
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with company ID {company_id} not found.",
        )

    contact = DecisionMaker(
        company_id=company_id,
        name=payload.name,
        title=payload.title,
        email=payload.email,
        phone=payload.phone,
        linkedin_url=payload.linkedin_url,
        source_url=payload.source_url,
    )
    saved = database.add_contact(contact)
    database.add_history_entry(
        company_id,
        action="CONTACT_ADDED",
        details=f"Added {payload.name} ({payload.title or 'Unknown title'}) from {payload.source_url}",
    )
    return saved


@app.post("/api/leads/{company_id}/evaluate", response_model=QualificationScore)
def api_evaluate_lead(company_id: int, workflow: Optional[WorkflowType] = None):
    """Run automated signal evaluation against factual web evidence."""
    lead = database.get_lead_record(company_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead with company ID {company_id} not found.",
        )

    eval_workflow = workflow or lead.company.workflow
    score = pipeline.evaluate_lead_signals(lead, eval_workflow)
    return score


# -------------------------------------------------------------
# Scrapy Recursive Crawling Endpoints
# -------------------------------------------------------------

@app.post("/api/crawl/jobs", response_model=CrawlJob, status_code=status.HTTP_201_CREATED)
def api_create_crawl_job(payload: CreateCrawlJobRequest):
    """Initiate a recursive Scrapy crawl job for lead research."""
    url = payload.url.strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A non-empty seed URL is required.",
        )

    # Validate seed URL security and SSRF rules before creating job
    try:
        norm_url, hostname, port = validate_url_security(url)
    except SecurityException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security policy violation: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {e}",
        )

    domain = normalize_domain(norm_url)
    allowed_domains = payload.allowed_domains or ([domain] if domain else [])

    # Check or create company profile if company_name or lead tracking is desired
    company_id = None
    if domain:
        existing_company = database.find_company_by_domain(domain, payload.workflow)
        if existing_company:
            company_id = existing_company.id
        else:
            comp_name = payload.company_name.strip() if payload.company_name else pipeline.infer_company_name_from_title(None, domain)
            norm_name = pipeline.normalize_company_name(comp_name)
            new_comp = CompanyProfile(
                company_name=comp_name,
                normalized_name=norm_name,
                domain=domain,
                website_url=norm_url,
                workflow=payload.workflow,
                research_status=ResearchStatus.PENDING,
            )
            created_comp = database.create_company(new_comp)
            company_id = created_comp.id

    new_job = CrawlJob(
        seed_url=norm_url,
        allowed_domains=allowed_domains,
        workflow=payload.workflow,
        company_id=company_id,
        company_name=payload.company_name,
        objective=payload.objective,
        target_product=payload.target_product,
        status=CrawlJobStatus.PENDING,
        max_depth=payload.max_depth or 2,
        max_pages=payload.max_pages or 100,
        max_pages_per_domain=payload.max_pages_per_domain or 30,
    )

    created_job = database.create_crawl_job(new_job)
    wake_worker()
    return created_job


@app.get("/api/crawl/jobs", response_model=list[CrawlJob])
def api_list_crawl_jobs(
    status: Optional[CrawlJobStatus] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List crawl jobs with optional status filter."""
    return database.list_crawl_jobs(status=status, limit=limit, offset=offset)


@app.get("/api/crawl/jobs/{job_id}", response_model=CrawlJob)
def api_get_crawl_job(job_id: int):
    """Retrieve status, configuration, and progress for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return job


@app.get("/api/crawl/jobs/{job_id}/metrics", response_model=CrawlJobMetrics)
def api_get_crawl_job_metrics(job_id: int):
    """Retrieve detailed performance and extraction metrics for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return job.metrics or database.calculate_job_metrics(job_id)


@app.get("/api/crawl/jobs/{job_id}/results", response_model=list[CrawlPage])
def api_get_crawl_job_results(
    job_id: int,
    status: Optional[CrawlPageStatus] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Retrieve extracted page results and evidence for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_crawled_pages(job_id, status=status, limit=limit, offset=offset)


@app.get("/api/evidence/{evidence_id}", response_model=ScrapeEvidence)
def api_get_evidence(evidence_id: int):
    """Retrieve full scrape evidence record by its primary key ID."""
    ev = database.get_evidence_by_id(evidence_id)
    if not ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence record #{evidence_id} not found.",
        )
    return ev


@app.post("/api/crawl/jobs/{job_id}/cancel")
def api_cancel_crawl_job(job_id: int):
    """Request cooperative cancellation of a pending or running crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    if job.status in {CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED, CrawlJobStatus.CANCELLED}:
        return {
            "success": False,
            "message": f"Job is already in terminal state '{job.status.value}'.",
            "job": job,
        }

    success = database.request_cancel_crawl_job(job_id)
    return {
        "success": success,
        "job_id": job_id,
        "message": "Cancellation request submitted. The crawler will stop promptly.",
    }


@app.post("/api/crawl/jobs/{job_id}/retry", response_model=CrawlJob)
def api_retry_crawl_job(job_id: int):
    """Create a new crawl job retrying failed pages or restarting a failed job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )

    failed_pages = database.get_failed_crawled_pages(job_id)
    seed_url = job.seed_url
    if failed_pages:
        eligible = [p.original_url for p in failed_pages if p.original_url]
        if eligible:
            seed_url = eligible[0]

    retry_job = CrawlJob(
        seed_url=seed_url,
        allowed_domains=job.allowed_domains,
        workflow=job.workflow,
        company_id=job.company_id,
        company_name=job.company_name,
        objective=job.objective,
        target_product=job.target_product,
        status=CrawlJobStatus.PENDING,
        max_depth=job.max_depth,
        max_pages=job.max_pages,
        max_pages_per_domain=job.max_pages_per_domain,
    )
    created_job = database.create_crawl_job(retry_job)
    wake_worker()
    return created_job


@app.get("/api/crawl/worker/status")
def api_get_worker_status():
    """Retrieve status of the crawl worker, mutual exclusion lock, and queue depth."""
    status_info = get_worker_status()
    status_info["pending_jobs_count"] = database.count_pending_crawl_jobs()
    status_info["active_running_job"] = database.get_current_running_crawl_job()
    return status_info


# -------------------------------------------------------------
# Customer Candidate Discovery & Verification Endpoints
# -------------------------------------------------------------

@app.get("/api/crawl/jobs/{job_id}/candidates", response_model=list[CustomerCandidate])
def api_get_job_candidates(
    job_id: int,
    classification: Optional[CandidateClassification] = None,
    relationship: Optional[RelationshipType] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Retrieve all discovered and verified customer candidates for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_customer_candidates(
        job_id=job_id,
        classification=classification,
        relationship_type=relationship,
        limit=limit,
        offset=offset,
    )


@app.post("/api/crawl/jobs/{job_id}/verify-candidates", response_model=list[CustomerCandidate])
def api_verify_job_candidates(job_id: int):
    """Execute customer candidate extraction and verification across all crawled pages for a job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    from candidate_verifier import verify_all_candidates_for_job
    return verify_all_candidates_for_job(job_id)


@app.get("/api/candidates/{candidate_id}", response_model=CustomerCandidate)
def api_get_candidate(candidate_id: int):
    """Retrieve details, evidence citations, and checklist for a customer candidate."""
    cand = database.get_candidate_by_id(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate #{candidate_id} not found.",
        )
    return cand


# -------------------------------------------------------------
# Multi-Format Document, Decision-Maker, and Evidence Endpoints
# -------------------------------------------------------------

@app.get("/api/crawl/jobs/{job_id}/documents", response_model=list[DiscoveredDocument])
def api_get_job_documents(
    job_id: int,
    download_status: Optional[str] = None,
    extraction_status: Optional[str] = None,
    file_format: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Retrieve discovered documents and media resources for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_discovered_documents(
        job_id=job_id,
        download_status=download_status,
        extraction_status=extraction_status,
        file_format=file_format,
        limit=limit,
        offset=offset,
    )


@app.get("/api/crawl/jobs/{job_id}/decision-makers", response_model=list[DecisionMaker])
def api_get_job_decision_makers(
    job_id: int,
    role_category: Optional[RoleCategory] = None,
    company: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Retrieve discovered decision-makers and published roles for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_decision_makers(
        job_id=job_id,
        role_category=role_category,
        company=company,
        limit=limit,
        offset=offset,
    )


@app.get("/api/crawl/jobs/{job_id}/contacts", response_model=list[PublicContact])
def api_get_job_public_contacts(
    job_id: int,
    contact_type: Optional[ContactType] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Retrieve public professional contacts (emails, phones, LinkedIn) for a crawl job."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_public_contacts(
        job_id=job_id,
        contact_type=contact_type,
        limit=limit,
        offset=offset,
    )


@app.get("/api/crawl/jobs/{job_id}/evidence", response_model=list[UnifiedEvidence])
def api_get_job_unified_evidence(
    job_id: int,
    claim_type: Optional[ClaimType] = None,
    limit: int = 300,
    offset: int = 0,
):
    """Retrieve unified evidence records linking claims to source citations for auditability."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )
    return database.get_unified_evidence(
        job_id=job_id,
        claim_type=claim_type,
        limit=limit,
        offset=offset,
    )


@app.get("/api/crawl/jobs/{job_id}/export")
def api_export_job_data(job_id: int, format: str = "excel"):
    """Export all research findings (candidates, evidence, decision-makers, contacts, documents) to Excel or CSV."""
    job = database.get_crawl_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job #{job_id} not found.",
        )

    candidates = database.get_customer_candidates(job_id, limit=1000)
    decision_makers = database.get_decision_makers(job_id, limit=1000)
    contacts = database.get_public_contacts(job_id, limit=1000)
    evidence = database.get_unified_evidence(job_id, limit=2000)
    documents = database.get_discovered_documents(job_id, limit=1000)

    df_candidates = pd.DataFrame([
        {
            "Candidate Name": c.candidate_name,
            "Normalized Name": c.normalized_name,
            "Category": c.candidate_category.value if hasattr(c.candidate_category, "value") else str(c.candidate_category),
            "Classification": c.classification.value if hasattr(c.classification, "value") else str(c.classification),
            "Relationship Type": c.relationship_type.value if hasattr(c.relationship_type, "value") else str(c.relationship_type),
            "Relationship Status": getattr(c, "relationship_verification_status", "UNVERIFIED"),
            "Target Product": c.target_product,
            "Product Usage Status": c.product_usage_status,
            "Relationship Evidence": getattr(c, "relationship_evidence", "") or "",
            "Product Usage Evidence": getattr(c, "product_usage_evidence", "") or "",
            "Supporting Source URL": getattr(c, "supporting_source_url", "") or "",
            "Exact Supporting Quote": getattr(c, "exact_supporting_quote", "") or "",
            "Confidence Score": getattr(c, "confidence_score", None),
            "Verification Rationale": getattr(c, "verification_rationale", "") or "",
            "Missing Evidence Reason": c.missing_evidence_reason,
            "Sources Count": len(c.sources),
        }
        for c in candidates
    ])

    df_evidence = pd.DataFrame([
        {
            "Claim Type": ev.claim_type.value if hasattr(ev.claim_type, "value") else str(ev.claim_type),
            "Claim Text": ev.claim_text,
            "Supporting Quote": ev.supporting_quote,
            "Source URL": ev.source_url,
            "Source Format": ev.source_format,
            "Source Location": ev.source_location,
            "Verification Status": ev.verification_status,
            "Discovery Timestamp": getattr(ev, "discovery_timestamp", getattr(ev, "created_at", "")),
        }
        for ev in evidence
    ])

    df_decision_makers = pd.DataFrame([
        {
            "Full Name": dm.full_name,
            "Published Title": dm.published_title,
            "Role Category": dm.role_category.value if hasattr(dm.role_category, "value") else str(dm.role_category),
            "Department": dm.department,
            "Associated Company": dm.associated_company,
            "Professional Relevance": dm.professional_relevance,
            "Verification Status": dm.verification_status,
            "Supporting Quote": dm.supporting_quote,
            "Source URL": dm.source_url,
            "Source Type": dm.source_type,
        }
        for dm in decision_makers
    ])

    df_contacts = pd.DataFrame([
        {
            "Contact Type": ct.contact_type.value if hasattr(ct.contact_type, "value") else str(ct.contact_type),
            "Contact Value": ct.contact_value,
            "Contact Level": "PERSON" if (ct.person_id or ct.person_name) else "COMPANY",
            "Person Name": ct.person_name,
            "Job Title": ct.job_title,
            "Associated Company": ct.associated_company,
            "Verification Status": ct.verification_status.value if hasattr(ct.verification_status, "value") else str(ct.verification_status),
            "Supporting Quote": ct.supporting_quote,
            "Source URL": ct.source_url,
            "File Type": ct.file_type,
        }
        for ct in contacts
    ])

    df_documents = pd.DataFrame([
        {
            "File Name": d.file_name,
            "Format": d.file_format,
            "Content Type": d.content_type,
            "File Size (Bytes)": d.file_size_bytes,
            "Download Status": d.download_status,
            "Extraction Status": d.extraction_status,
            "Error Message": d.error_message,
            "Document URL": d.document_url,
            "Discovery Source Page": d.source_page_url,
        }
        for d in documents
    ])

    if format.lower() == "json":
        return JSONResponse(
            content={
                "job_id": job_id,
                "company_name": job.company_name,
                "target_product": job.target_product,
                "candidates": df_candidates.to_dict(orient="records"),
                "evidence": df_evidence.to_dict(orient="records"),
                "decision_makers": df_decision_makers.to_dict(orient="records"),
                "contacts": df_contacts.to_dict(orient="records"),
                "documents": df_documents.to_dict(orient="records"),
            }
        )

    if format.lower() == "csv":
        import zipfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("candidates.csv", df_candidates.to_csv(index=False))
            zf.writestr("evidence.csv", df_evidence.to_csv(index=False))
            zf.writestr("decision_makers.csv", df_decision_makers.to_csv(index=False))
            zf.writestr("public_contacts.csv", df_contacts.to_csv(index=False))
            zf.writestr("documents.csv", df_documents.to_csv(index=False))
        zip_buf.seek(0)
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=job_{job_id}_research_data.zip"},
        )

    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_candidates.to_excel(writer, sheet_name="Candidates", index=False)
        df_evidence.to_excel(writer, sheet_name="Evidence", index=False)
        df_decision_makers.to_excel(writer, sheet_name="Decision Makers", index=False)
        df_contacts.to_excel(writer, sheet_name="Public Contacts", index=False)
        df_documents.to_excel(writer, sheet_name="Documents & Media", index=False)
    excel_buf.seek(0)
    return StreamingResponse(
        excel_buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=job_{job_id}_research_data.xlsx"},
    )



