"""Data models for the AI-Powered Lead Research & Qualification System.

Supports RECOV (debt recovery & credit intelligence) and Jedox (FP&A & EPM solutions),
tracking provenance, verification status, decision-makers, and audit history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """Supported lead research workflows."""
    RECOV = "RECOV"        # Debt collection, recovery automation, overdue receivables
    JEDOX = "JEDOX"        # FP&A, financial planning, consolidation, business intelligence
    GENERAL = "GENERAL"    # General business intelligence and lead discovery


class ResearchStatus(str, Enum):
    """Lifecycle status of lead research."""
    PENDING = "PENDING"
    SCRAPED = "SCRAPED"
    RESEARCHING = "RESEARCHING"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    FLAGGED = "FLAGGED"
    ARCHIVED = "ARCHIVED"


class VerificationStatus(str, Enum):
    """Confidence/truth status of extracted claims."""
    UNVERIFIED = "UNVERIFIED"  # Extracted or AI-generated without human/third-party proof
    VERIFIED = "VERIFIED"      # Confirmed via source evidence or official register
    DISPUTED = "DISPUTED"      # Inconsistent or contradictory data found


class FitLevel(str, Enum):
    """Qualification fit level for the target workflow."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNQUALIFIED = "UNQUALIFIED"


# -------------------------------------------------------------
# Component Models
# -------------------------------------------------------------

class DecisionMaker(BaseModel):
    """Contact information for a corporate decision-maker."""
    id: Optional[int] = None
    company_id: Optional[int] = None
    name: str = Field(..., description="Full name of decision maker")
    title: Optional[str] = Field(None, description="Executive title or job role")
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: str = Field(..., description="Source URL where this contact was extracted from")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ScrapeEvidence(BaseModel):
    """Raw and structured web evidence linked to a company."""
    id: Optional[int] = None
    company_id: Optional[int] = None
    source_url: str
    http_status: Optional[int] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    raw_text: Optional[str] = None
    headings_json: Optional[Dict[str, List[str]]] = None
    metadata_json: Optional[Dict[str, str]] = None
    links_count: int = 0
    word_count: int = 0
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class QualificationScore(BaseModel):
    """Structured evaluation score for RECOV or Jedox fit."""
    id: Optional[int] = None
    company_id: Optional[int] = None
    workflow: WorkflowType
    score: float = Field(..., ge=0.0, le=100.0, description="Qualification score from 0 to 100")
    fit_level: FitLevel
    reasoning: Optional[str] = None
    criteria_matched: List[str] = Field(default_factory=list)
    is_ai_generated: bool = Field(
        default=False,
        description="True if score was inferred by LLM; False if based on verified data rules"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ResearchHistoryEntry(BaseModel):
    """Audit log tracking changes and research events."""
    id: Optional[int] = None
    company_id: Optional[int] = None
    action: str = Field(..., description="e.g. INGESTED, SCRAPED, SCORED, CONTACT_ADDED")
    details: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# -------------------------------------------------------------
# Main Aggregate Lead Record
# -------------------------------------------------------------

class CompanyProfile(BaseModel):
    """Core company record."""
    id: Optional[int] = None
    company_name: str
    normalized_name: str
    domain: str
    website_url: str
    industry: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    workflow: WorkflowType = WorkflowType.GENERAL
    research_status: ResearchStatus = ResearchStatus.PENDING
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LeadRecord(BaseModel):
    """Complete aggregated lead record with all evidence, contacts, and audit history."""
    company: CompanyProfile
    evidence: List[ScrapeEvidence] = Field(default_factory=list)
    contacts: List[DecisionMaker] = Field(default_factory=list)
    qualifications: List[QualificationScore] = Field(default_factory=list)
    history: List[ResearchHistoryEntry] = Field(default_factory=list)


# -------------------------------------------------------------
# API Request / Response Models
# -------------------------------------------------------------

class IngestLeadRequest(BaseModel):
    """Request to ingest and scrape a target website for a specific workflow."""
    url: str = Field(..., description="Target corporate website URL")
    workflow: WorkflowType = Field(
        default=WorkflowType.GENERAL,
        description="Workflow context: 'RECOV', 'JEDOX', or 'GENERAL'"
    )
    company_name: Optional[str] = Field(
        None,
        description="Optional company name override. If omitted, will be inferred from title."
    )


class AddContactRequest(BaseModel):
    """Request to attach a verified decision-maker to a lead."""
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: str = Field(..., description="Evidence URL where contact info was found")


class QualifyLeadRequest(BaseModel):
    """Request to record a qualification score."""
    workflow: WorkflowType
    score: float = Field(..., ge=0.0, le=100.0)
    fit_level: FitLevel
    reasoning: Optional[str] = None
    criteria_matched: List[str] = Field(default_factory=list)
    is_ai_generated: bool = False


# -------------------------------------------------------------
# Scrapy Crawl Job Models
# -------------------------------------------------------------

class CrawlJobStatus(str, Enum):
    """Execution status of a recursive crawl job."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CrawlPageStatus(str, Enum):
    """Result status of an individual crawled page."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CrawlJobMetrics(BaseModel):
    """Detailed performance and extraction metrics for a recursive crawl job."""
    requests_attempted: int = Field(default=0, description="Total HTTP requests attempted by crawler")
    responses_downloaded: int = Field(default=0, description="Successfully downloaded HTTP responses")
    unique_pages_saved: int = Field(default=0, description="Unique pages persisted in database")
    useful_pages: int = Field(default=0, description="Pages with non-empty extracted text")
    empty_or_thin_pages: int = Field(default=0, description="Pages with empty or thin content")
    duplicate_requests_filtered: int = Field(default=0, description="Duplicate requests filtered by dupefilter")
    failed_requests: int = Field(default=0, description="Failed requests, timeouts, and HTTP errors")
    total_response_bytes: Optional[int] = Field(default=0, description="Total downloaded response wire bytes")
    total_decompressed_bytes: Optional[int] = Field(default=0, description="Total decompressed response bytes")
    crawl_duration_sec: Optional[float] = Field(default=0.0, description="Total crawl duration in seconds")
    evidence_records_created: int = Field(default=0, description="Evidence records created and linked")
    final_outcome: str = Field(default="COMPLETED", description="Final job status: COMPLETED, CANCELLED, or FAILED")
    stop_reason: Optional[str] = Field(default=None, description="Engine stop reason (e.g. finished, max_pages_reached, cancelled)")


class CrawlJob(BaseModel):
    """Record of a recursive Scrapy crawl job."""
    id: Optional[int] = None
    seed_url: str
    allowed_domains: List[str] = Field(default_factory=list)
    workflow: WorkflowType = WorkflowType.GENERAL
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    status: CrawlJobStatus = CrawlJobStatus.PENDING
    cancellation_requested: bool = False
    max_depth: int = 2
    max_pages: int = 100
    max_pages_per_domain: int = 30
    pages_crawled: int = 0
    pages_failed: int = 0
    discovered_urls_count: int = 0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    worker_pid: Optional[int] = None
    metrics_json: Optional[str] = None
    metrics: Optional[CrawlJobMetrics] = None


class CrawlPage(BaseModel):
    """A single page crawled and extracted during a crawl job."""
    id: Optional[int] = None
    job_id: int
    original_url: str
    final_url: Optional[str] = None
    http_status: Optional[int] = None
    depth: int = 0
    discovery_source_url: Optional[str] = None
    title: Optional[str] = None
    extracted_text: Optional[str] = None
    headings_json: Optional[Dict[str, List[str]]] = None
    metadata_json: Optional[Dict[str, str]] = None
    links_count: int = 0
    word_count: int = 0
    content_hash: Optional[str] = None
    status: CrawlPageStatus = CrawlPageStatus.SUCCESS
    error_message: Optional[str] = None
    evidence_id: Optional[int] = None
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CreateCrawlJobRequest(BaseModel):
    """Request payload to initiate a recursive crawl job."""
    url: str = Field(..., description="Seed URL for recursive crawling")
    workflow: WorkflowType = Field(
        default=WorkflowType.GENERAL,
        description="Workflow context: 'RECOV', 'JEDOX', or 'GENERAL'"
    )
    company_name: Optional[str] = None
    max_depth: Optional[int] = Field(default=2, ge=0, le=10)
    max_pages: Optional[int] = Field(default=100, ge=1, le=500)
    max_pages_per_domain: Optional[int] = Field(default=30, ge=1, le=200)
    allowed_domains: Optional[List[str]] = None

