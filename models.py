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
