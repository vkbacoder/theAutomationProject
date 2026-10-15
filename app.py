"""FastAPI application for the Lead Research & Qualification System.

Provides:
- POST /api/scrape: Web scraper endpoint
- GET  /api/health: Service and Vishnu LLM health status
- POST /api/chat: LLM terminal chat endpoint (preserved from chatbot.py)
- GET  /: Serves the Web Scraper Test dashboard
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from scraper import ScrapeRequest, ScrapeResponse, scrape_website
import database
from models import (
    AddContactRequest,
    CompanyProfile,
    DecisionMaker,
    IngestLeadRequest,
    LeadRecord,
    QualificationScore,
    QualifyLeadRequest,
    ResearchStatus,
    WorkflowType,
)
import pipeline

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Initialize database tables on module load
database.init_db()

app = FastAPI(
    title="AI-Powered Lead Research & Qualification System",
    description="Web scraping ingestion engine and Vishnu LLM integration for RECOV and Jedox.",
    version="1.1.0",
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

