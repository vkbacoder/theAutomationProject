"""Data models for the AI-Powered Lead Research & Qualification System.

Supports RECOV (debt recovery & credit intelligence) and Jedox (FP&A & EPM solutions),
tracking provenance, verification status, decision-makers, and audit history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


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

class RoleCategory(str, Enum):
    """Broad professional role categories for decision makers."""
    TECHNOLOGY_IT = "TECHNOLOGY_IT"
    FINANCE_BUSINESS = "FINANCE_BUSINESS"
    EXECUTIVE = "EXECUTIVE"
    OPERATIONS = "OPERATIONS"
    OTHER = "OTHER"


class ContactType(str, Enum):
    """Types of extracted public professional contacts."""
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    OFFICE_PHONE = "OFFICE_PHONE"
    LINKEDIN = "LINKEDIN"
    PROFILE_URL = "PROFILE_URL"
    OTHER = "OTHER"


class ContactVerificationStatus(str, Enum):
    """Verification classification for public contacts."""
    VERIFIED_PUBLIC = "VERIFIED_PUBLIC"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ClaimType(str, Enum):
    """Types of verifiable business claims."""
    CUSTOMER_RELATIONSHIP = "CUSTOMER_RELATIONSHIP"
    RELATIONSHIP = "CUSTOMER_RELATIONSHIP"
    PRODUCT_USAGE = "PRODUCT_USAGE"
    PARTNERSHIP = "PARTNERSHIP"
    DECISION_MAKER = "DECISION_MAKER"
    CONTACT_INFO = "CONTACT_INFO"
    CONTACT = "CONTACT_INFO"
    VENDOR_SUPPLIER = "VENDOR_SUPPLIER"
    TESTIMONIAL = "TESTIMONIAL"
    OTHER = "OTHER"


class CandidateCategory(str, Enum):
    """Quality-control categorization of extracted candidate entities."""
    NAMED_COMPANY = "NAMED_COMPANY"
    ANONYMOUS_CLIENT_DESCRIPTION = "ANONYMOUS_CLIENT_DESCRIPTION"
    PERSON = "PERSON"
    PRODUCT_OR_TECHNOLOGY = "PRODUCT_OR_TECHNOLOGY"
    PROJECT_TITLE = "PROJECT_TITLE"
    OTHER_ENTITY = "OTHER_ENTITY"


class DocumentFormat(str, Enum):
    """Supported document and media formats."""
    HTML = "HTML"
    PDF = "PDF"
    XLSX = "XLSX"
    XLS = "XLS"
    CSV = "CSV"
    DOCX = "DOCX"
    DOC = "DOC"
    PPTX = "PPTX"
    PPT = "PPT"
    PNG = "PNG"
    JPG = "JPG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    TIFF = "TIFF"
    OTHER = "OTHER"


class DownloadStatus(str, Enum):
    """Document download status."""
    PENDING = "PENDING"
    DOWNLOADED = "DOWNLOADED"
    SKIPPED_SIZE = "SKIPPED_SIZE"
    SKIPPED_DOMAIN = "SKIPPED_DOMAIN"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class ExtractionStatus(str, Enum):
    """Document extraction and OCR status."""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    ENCRYPTED = "ENCRYPTED"
    OCR_FAILED = "OCR_FAILED"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


class DecisionMaker(BaseModel):
    """Contact information for a corporate decision-maker."""
    id: Optional[int] = None
    job_id: Optional[int] = None
    company_id: Optional[int] = None
    target_company_id: Optional[int] = None
    candidate_company_id: Optional[int] = None
    name: Optional[str] = None
    full_name: Optional[str] = None
    normalized_name: Optional[str] = None
    title: Optional[str] = None
    published_title: Optional[str] = None
    department: Optional[str] = None
    role_category: RoleCategory = RoleCategory.OTHER
    associated_company: Optional[str] = None
    professional_relevance: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: str = Field(..., description="Source URL where this contact was extracted from")
    source_type: str = "HTML"
    supporting_quote: Optional[str] = None
    verification_status: str = "UNVERIFIED"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_name_and_title(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "full_name" in data and not data.get("name"):
                data["name"] = data["full_name"]
            elif "name" in data and not data.get("full_name"):
                data["full_name"] = data["name"]
            if "published_title" in data and not data.get("title"):
                data["title"] = data["published_title"]
            elif "title" in data and not data.get("published_title"):
                data["published_title"] = data["title"]
        return data


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
    objective: Optional[str] = None
    target_product: Optional[str] = None
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
    objective: Optional[str] = Field(
        default=None,
        description="Research objective (e.g., 'find customers using Jedox')"
    )
    target_product: Optional[str] = Field(
        default=None,
        description="Target software or product to verify usage of (e.g. 'Jedox')"
    )
    max_depth: Optional[int] = Field(default=2, ge=0, le=10)
    max_pages: Optional[int] = Field(default=100, ge=1, le=500)
    max_pages_per_domain: Optional[int] = Field(default=30, ge=1, le=200)
    allowed_domains: Optional[List[str]] = None


# -------------------------------------------------------------
# Customer Candidate & Verification Checklist Models
# -------------------------------------------------------------

class CandidateClassification(str, Enum):
    """Verification classification for discovered customer candidates."""
    CONFIRMED = "CONFIRMED"                      # Both customer relationship and product usage supported
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"    # Exactly one is supported
    UNVERIFIED = "UNVERIFIED"                    # Neither is sufficiently supported
    RESEARCH_INCOMPLETE = "RESEARCH_INCOMPLETE"  # Crawl failed or limits prevented completion


class RelationshipType(str, Enum):
    """Documented relationship between candidate and target company."""
    CUSTOMER = "CUSTOMER"
    CASE_STUDY = "CASE_STUDY"
    TESTIMONIAL = "TESTIMONIAL"
    PARTNER = "PARTNER"
    IMPLEMENTATION_PARTNER = "IMPLEMENTATION_PARTNER"
    TECHNOLOGY_PLATFORM = "TECHNOLOGY_PLATFORM"
    TARGET_VENDOR = "TARGET_VENDOR"
    VENDOR = "VENDOR"
    PROSPECT = "PROSPECT"
    MENTION = "MENTION"
    UNKNOWN = "UNKNOWN"


class VerificationChecklist(BaseModel):
    """Granular verification checklist statuses."""
    company_discovered: bool = False
    customer_relationship_supported: bool = False
    product_usage_supported: bool = False
    source_url_recorded: bool = False
    supporting_text_recorded: bool = False
    verification_completed: bool = False


class EvidenceReference(BaseModel):
    """Source URL and supporting text citation for candidate verification."""
    source_url: str
    page_title: Optional[str] = None
    supporting_text: str
    relationship_claim: Optional[str] = None
    product_claim: Optional[str] = None
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CustomerCandidate(BaseModel):
    """A discovered potential customer candidate and its verification status."""
    id: Optional[int] = None
    job_id: Optional[int] = None
    target_company_id: Optional[int] = None
    candidate_name: str
    normalized_name: str
    target_product: str = "Jedox"
    relationship_type: RelationshipType = RelationshipType.UNKNOWN
    classification: CandidateClassification = CandidateClassification.UNVERIFIED
    candidate_category: CandidateCategory = CandidateCategory.NAMED_COMPANY
    checklist: VerificationChecklist = Field(default_factory=VerificationChecklist)
    product_usage_status: str = "UNVERIFIED"
    sources: List[EvidenceReference] = Field(default_factory=list)
    missing_evidence_reason: Optional[str] = None
    research_status: str = "PENDING"
    relationship_verification_status: str = "UNVERIFIED"
    relationship_evidence: Optional[str] = None
    product_usage_evidence: Optional[str] = None
    supporting_source_url: Optional[str] = None
    exact_supporting_quote: Optional[str] = None
    confidence_score: Optional[float] = None
    verification_rationale: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DiscoveredDocument(BaseModel):
    """A discovered resource file (PDF, Office, media) and its extraction outcome."""
    id: Optional[int] = None
    job_id: int
    source_page_url: str
    document_url: str
    file_name: str
    file_format: str
    content_type: Optional[str] = None
    file_size_bytes: int = 0
    download_status: str = "PENDING"
    extraction_status: str = "PENDING"
    error_message: Optional[str] = None
    extracted_text: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    sections_json: Optional[List[Dict[str, Any]]] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PublicContact(BaseModel):
    """Publicly published business contact information."""
    id: Optional[int] = None
    job_id: int
    person_id: Optional[int] = None
    company_id: Optional[int] = None
    candidate_company_id: Optional[int] = None
    contact_type: ContactType
    contact_value: str
    associated_person_name: Optional[str] = None
    person_name: Optional[str] = None
    associated_job_title: Optional[str] = None
    job_title: Optional[str] = None
    associated_company: Optional[str] = None
    source_url: str
    source_type: str = "HTML"
    file_name: Optional[str] = None
    supporting_quote: str = ""
    source_location: Optional[str] = None
    verification_status: ContactVerificationStatus = ContactVerificationStatus.UNVERIFIED
    is_public: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def sync_contact_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "person_name" in data and not data.get("associated_person_name"):
                data["associated_person_name"] = data["person_name"]
            elif "associated_person_name" in data and not data.get("person_name"):
                data["person_name"] = data["associated_person_name"]
            if "job_title" in data and not data.get("associated_job_title"):
                data["associated_job_title"] = data["job_title"]
            elif "associated_job_title" in data and not data.get("job_title"):
                data["job_title"] = data["associated_job_title"]
            if "file_type" in data and not data.get("source_type"):
                data["source_type"] = data["file_type"]
            if "supporting_quote" not in data or data.get("supporting_quote") is None:
                data["supporting_quote"] = ""
        return data

    @property
    def file_type(self) -> str:
        return self.source_type


class UnifiedEvidence(BaseModel):
    """Unified traceable evidence record linking claims to fine-grained source locations."""
    id: Optional[int] = None
    job_id: int
    company_id: Optional[int] = None
    candidate_id: Optional[int] = None
    person_id: Optional[int] = None
    claim_type: ClaimType
    claim_text: str
    source_url: str
    original_file_url: Optional[str] = None
    source_format: str = "HTML"
    file_name: Optional[str] = None
    supporting_quote: str
    source_location: Optional[str] = None
    extraction_status: str = "SUCCESS"
    verification_status: str = "UNVERIFIED"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def discovery_timestamp(self) -> str:
        return self.created_at


