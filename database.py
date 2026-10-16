"""SQLite persistent storage layer for the Lead Research System.

Manages schema initialization, foreign keys, transactions, and CRUD operations
for company profiles, scrape evidence, contacts, qualification scores, and audit history.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from dedup import is_fuzzy_name_match, normalize_company_name, normalize_domain
from models import (
    CompanyProfile,
    CrawlJob,
    CrawlJobMetrics,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    DecisionMaker,
    FitLevel,
    LeadRecord,
    QualificationScore,
    ResearchHistoryEntry,
    ResearchStatus,
    ScrapeEvidence,
    VerificationStatus,
    WorkflowType,
)

# Default database location in the workspace
DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "leads.db")


def get_db_path() -> str:
    """Return the database path from environment variable or default."""
    return os.getenv("LEADS_DB_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create a SQLite connection with foreign keys and Row factory enabled."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables, indexes, and constraints idempotently."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                website_url TEXT NOT NULL,
                industry TEXT,
                description TEXT,
                country TEXT,
                city TEXT,
                workflow TEXT NOT NULL DEFAULT 'GENERAL',
                research_status TEXT NOT NULL DEFAULT 'PENDING',
                verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(domain, workflow)
            );

            CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
            CREATE INDEX IF NOT EXISTS idx_companies_workflow ON companies(workflow);
            CREATE INDEX IF NOT EXISTS idx_companies_normalized ON companies(normalized_name);

            CREATE TABLE IF NOT EXISTS scrape_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                source_url TEXT NOT NULL,
                http_status INTEGER,
                title TEXT,
                meta_description TEXT,
                canonical_url TEXT,
                raw_text TEXT,
                headings_json TEXT,
                metadata_json TEXT,
                links_count INTEGER DEFAULT 0,
                word_count INTEGER DEFAULT 0,
                scraped_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_evidence_company ON scrape_evidence(company_id);

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                title TEXT,
                email TEXT,
                phone TEXT,
                linkedin_url TEXT,
                source_url TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);

            CREATE TABLE IF NOT EXISTS qualification_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                workflow TEXT NOT NULL,
                score REAL NOT NULL,
                fit_level TEXT NOT NULL,
                reasoning TEXT,
                criteria_matched TEXT,
                is_ai_generated INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scores_company ON qualification_scores(company_id);

            CREATE TABLE IF NOT EXISTS research_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_company ON research_history(company_id);

            CREATE TABLE IF NOT EXISTS crawl_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seed_url TEXT NOT NULL,
                allowed_domains_json TEXT,
                workflow TEXT NOT NULL DEFAULT 'GENERAL',
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                company_name TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                max_depth INTEGER NOT NULL DEFAULT 2,
                max_pages INTEGER NOT NULL DEFAULT 100,
                max_pages_per_domain INTEGER NOT NULL DEFAULT 30,
                pages_crawled INTEGER NOT NULL DEFAULT 0,
                pages_failed INTEGER NOT NULL DEFAULT 0,
                discovered_urls_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                worker_pid INTEGER,
                metrics_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_crawl_jobs_company ON crawl_jobs(company_id);

            CREATE TABLE IF NOT EXISTS crawl_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
                original_url TEXT NOT NULL,
                final_url TEXT,
                http_status INTEGER,
                depth INTEGER NOT NULL DEFAULT 0,
                discovery_source_url TEXT,
                title TEXT,
                extracted_text TEXT,
                headings_json TEXT,
                metadata_json TEXT,
                links_count INTEGER DEFAULT 0,
                word_count INTEGER DEFAULT 0,
                content_hash TEXT,
                status TEXT NOT NULL DEFAULT 'SUCCESS',
                error_message TEXT,
                evidence_id INTEGER REFERENCES scrape_evidence(id) ON DELETE SET NULL,
                retrieved_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_crawl_pages_job ON crawl_pages(job_id);
            CREATE INDEX IF NOT EXISTS idx_crawl_pages_url ON crawl_pages(original_url);
            """)

            # Non-destructive migration check: ensure metrics_json column exists on crawl_jobs
            cursor = conn.execute("PRAGMA table_info(crawl_jobs)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "metrics_json" not in existing_cols:
                conn.execute("ALTER TABLE crawl_jobs ADD COLUMN metrics_json TEXT")
    finally:
        conn.close()


# -------------------------------------------------------------
# Company CRUD & Deduplication
# -------------------------------------------------------------

def create_company(company: CompanyProfile, db_path: Optional[str] = None) -> CompanyProfile:
    """Insert a new company record."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO companies (
                    company_name, normalized_name, domain, website_url,
                    industry, description, country, city, workflow,
                    research_status, verification_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company.company_name,
                    company.normalized_name,
                    company.domain,
                    company.website_url,
                    company.industry,
                    company.description,
                    company.country,
                    company.city,
                    company.workflow.value,
                    company.research_status.value,
                    company.verification_status.value,
                    company.created_at,
                    company.updated_at,
                ),
            )
            company_id = cursor.lastrowid
            company.id = company_id
            return company
    finally:
        conn.close()


def get_company_by_id(company_id: int, db_path: Optional[str] = None) -> Optional[CompanyProfile]:
    """Retrieve a company by primary key."""
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return None
        return _row_to_company(row)
    finally:
        conn.close()


def find_company_by_domain(
    domain: str, workflow: WorkflowType, db_path: Optional[str] = None
) -> Optional[CompanyProfile]:
    """Lookup an existing company by canonical domain and workflow."""
    clean_domain = normalize_domain(domain)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE domain = ? AND workflow = ?",
            (clean_domain, workflow.value),
        ).fetchone()
        if row:
            return _row_to_company(row)
        return None
    finally:
        conn.close()


def find_company_by_fuzzy_name(
    name: str, workflow: WorkflowType, threshold: float = 85.0, db_path: Optional[str] = None
) -> Optional[CompanyProfile]:
    """Find an existing company within the same workflow using fuzzy name matching."""
    norm_target = normalize_company_name(name)
    if not norm_target:
        return None

    conn = get_connection(db_path)
    try:
        # Check exact normalized match first
        row = conn.execute(
            "SELECT * FROM companies WHERE normalized_name = ? AND workflow = ?",
            (norm_target, workflow.value),
        ).fetchone()
        if row:
            return _row_to_company(row)

        # Retrieve candidates in the same workflow for fuzzy evaluation
        candidates = conn.execute(
            "SELECT * FROM companies WHERE workflow = ?", (workflow.value,)
        ).fetchall()

        for cand in candidates:
            if is_fuzzy_name_match(norm_target, cand["normalized_name"], threshold=threshold):
                return _row_to_company(cand)

        return None
    finally:
        conn.close()


def list_companies(
    workflow: Optional[WorkflowType] = None,
    status: Optional[ResearchStatus] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[str] = None,
) -> List[CompanyProfile]:
    """List company profiles with optional workflow, status, and text search filters."""
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM companies WHERE 1=1"
        params: List[Any] = []

        if workflow:
            query += " AND workflow = ?"
            params.append(workflow.value)

        if status:
            query += " AND research_status = ?"
            params.append(status.value)

        if search:
            query += " AND (company_name LIKE ? OR domain LIKE ? OR description LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [_row_to_company(r) for r in rows]
    finally:
        conn.close()


def update_company_status(
    company_id: int,
    status: Optional[ResearchStatus] = None,
    verification: Optional[VerificationStatus] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update company research or verification status."""
    conn = get_connection(db_path)
    try:
        with conn:
            updates = []
            params = []
            if status:
                updates.append("research_status = ?")
                params.append(status.value)
            if verification:
                updates.append("verification_status = ?")
                params.append(verification.value)
            if not updates:
                return False

            params.append(company_id)
            query = f"UPDATE companies SET {', '.join(updates)} WHERE id = ?"
            cursor = conn.execute(query, params)
            return cursor.rowcount > 0
    finally:
        conn.close()


# -------------------------------------------------------------
# Scrape Evidence
# -------------------------------------------------------------

def add_scrape_evidence(
    evidence: ScrapeEvidence, db_path: Optional[str] = None
) -> ScrapeEvidence:
    """Store raw and parsed scrape evidence tied to a company."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO scrape_evidence (
                    company_id, source_url, http_status, title,
                    meta_description, canonical_url, raw_text,
                    headings_json, metadata_json, links_count,
                    word_count, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.company_id,
                    evidence.source_url,
                    evidence.http_status,
                    evidence.title,
                    evidence.meta_description,
                    evidence.canonical_url,
                    evidence.raw_text,
                    json.dumps(evidence.headings_json) if evidence.headings_json else None,
                    json.dumps(evidence.metadata_json) if evidence.metadata_json else None,
                    evidence.links_count,
                    evidence.word_count,
                    evidence.scraped_at,
                ),
            )
            evidence.id = cursor.lastrowid
            return evidence
    finally:
        conn.close()


def get_evidence_by_company(
    company_id: int, db_path: Optional[str] = None
) -> List[ScrapeEvidence]:
    """Retrieve all evidence records collected for a company."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM scrape_evidence WHERE company_id = ? ORDER BY id DESC",
            (company_id,),
        ).fetchall()
        return [_row_to_evidence(r) for r in rows]
    finally:
        conn.close()


def get_evidence_by_id(
    evidence_id: int, db_path: Optional[str] = None
) -> Optional[ScrapeEvidence]:
    """Retrieve an individual scrape evidence record by ID."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scrape_evidence WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        return _row_to_evidence(row) if row else None
    finally:
        conn.close()



# -------------------------------------------------------------
# Contacts / Decision-Makers
# -------------------------------------------------------------

def add_contact(contact: DecisionMaker, db_path: Optional[str] = None) -> DecisionMaker:
    """Store contact information with explicit source evidence URL."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO contacts (
                    company_id, name, title, email, phone, linkedin_url, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.company_id,
                    contact.name,
                    contact.title,
                    contact.email,
                    contact.phone,
                    contact.linkedin_url,
                    contact.source_url,
                    contact.created_at,
                ),
            )
            contact.id = cursor.lastrowid
            return contact
    finally:
        conn.close()


def get_contacts_by_company(
    company_id: int, db_path: Optional[str] = None
) -> List[DecisionMaker]:
    """Retrieve decision-makers attached to a company."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE company_id = ? ORDER BY id ASC",
            (company_id,),
        ).fetchall()
        return [_row_to_contact(r) for r in rows]
    finally:
        conn.close()


# -------------------------------------------------------------
# Qualification Scoring
# -------------------------------------------------------------

def add_qualification_score(
    score: QualificationScore, db_path: Optional[str] = None
) -> QualificationScore:
    """Record an evaluation score, preserving the AI vs verified provenance flag."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO qualification_scores (
                    company_id, workflow, score, fit_level, reasoning,
                    criteria_matched, is_ai_generated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.company_id,
                    score.workflow.value,
                    score.score,
                    score.fit_level.value,
                    score.reasoning,
                    json.dumps(score.criteria_matched),
                    1 if score.is_ai_generated else 0,
                    score.created_at,
                ),
            )
            score.id = cursor.lastrowid
            return score
    finally:
        conn.close()


def get_qualifications_by_company(
    company_id: int, db_path: Optional[str] = None
) -> List[QualificationScore]:
    """Retrieve all qualification records for a company."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM qualification_scores WHERE company_id = ? ORDER BY id DESC",
            (company_id,),
        ).fetchall()
        return [_row_to_qualification(r) for r in rows]
    finally:
        conn.close()


# -------------------------------------------------------------
# Research History Audit Trail
# -------------------------------------------------------------

def add_history_entry(
    company_id: int, action: str, details: Optional[str] = None, db_path: Optional[str] = None
) -> ResearchHistoryEntry:
    """Append an event to the immutable research audit trail."""
    conn = get_connection(db_path)
    entry = ResearchHistoryEntry(company_id=company_id, action=action, details=details)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO research_history (company_id, action, details, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (company_id, entry.action, entry.details, entry.timestamp),
            )
            entry.id = cursor.lastrowid
            return entry
    finally:
        conn.close()


def get_history_by_company(
    company_id: int, db_path: Optional[str] = None
) -> List[ResearchHistoryEntry]:
    """Retrieve audit history for a lead."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM research_history WHERE company_id = ? ORDER BY id ASC",
            (company_id,),
        ).fetchall()
        return [_row_to_history(r) for r in rows]
    finally:
        conn.close()


# -------------------------------------------------------------
# Aggregate Lead Record
# -------------------------------------------------------------

def get_lead_record(company_id: int, db_path: Optional[str] = None) -> Optional[LeadRecord]:
    """Retrieve the full aggregated lead dossier."""
    company = get_company_by_id(company_id, db_path=db_path)
    if not company:
        return None

    evidence = get_evidence_by_company(company_id, db_path=db_path)
    contacts = get_contacts_by_company(company_id, db_path=db_path)
    scores = get_qualifications_by_company(company_id, db_path=db_path)
    history = get_history_by_company(company_id, db_path=db_path)

    return LeadRecord(
        company=company,
        evidence=evidence,
        contacts=contacts,
        qualifications=scores,
        history=history,
    )


# -------------------------------------------------------------
# Internal Row Deserializers
# -------------------------------------------------------------

def _row_to_company(row: sqlite3.Row) -> CompanyProfile:
    return CompanyProfile(
        id=row["id"],
        company_name=row["company_name"],
        normalized_name=row["normalized_name"],
        domain=row["domain"],
        website_url=row["website_url"],
        industry=row["industry"],
        description=row["description"],
        country=row["country"],
        city=row["city"],
        workflow=WorkflowType(row["workflow"]),
        research_status=ResearchStatus(row["research_status"]),
        verification_status=VerificationStatus(row["verification_status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_evidence(row: sqlite3.Row) -> ScrapeEvidence:
    headings = None
    if row["headings_json"]:
        try:
            headings = json.loads(row["headings_json"])
        except Exception:
            pass

    metadata = None
    if row["metadata_json"]:
        try:
            metadata = json.loads(row["metadata_json"])
        except Exception:
            pass

    return ScrapeEvidence(
        id=row["id"],
        company_id=row["company_id"],
        source_url=row["source_url"],
        http_status=row["http_status"],
        title=row["title"],
        meta_description=row["meta_description"],
        canonical_url=row["canonical_url"],
        raw_text=row["raw_text"],
        headings_json=headings,
        metadata_json=metadata,
        links_count=row["links_count"] or 0,
        word_count=row["word_count"] or 0,
        scraped_at=row["scraped_at"],
    )


def _row_to_contact(row: sqlite3.Row) -> DecisionMaker:
    return DecisionMaker(
        id=row["id"],
        company_id=row["company_id"],
        name=row["name"],
        title=row["title"],
        email=row["email"],
        phone=row["phone"],
        linkedin_url=row["linkedin_url"],
        source_url=row["source_url"],
        created_at=row["created_at"],
    )


def _row_to_qualification(row: sqlite3.Row) -> QualificationScore:
    criteria = []
    if row["criteria_matched"]:
        try:
            criteria = json.loads(row["criteria_matched"])
        except Exception:
            pass

    return QualificationScore(
        id=row["id"],
        company_id=row["company_id"],
        workflow=WorkflowType(row["workflow"]),
        score=row["score"],
        fit_level=FitLevel(row["fit_level"]),
        reasoning=row["reasoning"],
        criteria_matched=criteria,
        is_ai_generated=bool(row["is_ai_generated"]),
        created_at=row["created_at"],
    )


def _row_to_history(row: sqlite3.Row) -> ResearchHistoryEntry:
    return ResearchHistoryEntry(
        id=row["id"],
        company_id=row["company_id"],
        action=row["action"],
        details=row["details"],
        timestamp=row["timestamp"],
    )


# -------------------------------------------------------------
# Scrapy Crawl Jobs & Pages Persistence
# -------------------------------------------------------------

def create_crawl_job(job: CrawlJob, db_path: Optional[str] = None) -> CrawlJob:
    """Insert a new crawl job record."""
    conn = get_connection(db_path)
    try:
        metrics_raw = job.metrics_json or (job.metrics.model_dump_json() if job.metrics else None)
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO crawl_jobs (
                    seed_url, allowed_domains_json, workflow, company_id,
                    company_name, status, cancellation_requested, max_depth,
                    max_pages, max_pages_per_domain, pages_crawled, pages_failed,
                    discovered_urls_count, created_at, started_at, finished_at,
                    error_message, worker_pid, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.seed_url,
                    json.dumps(job.allowed_domains),
                    job.workflow.value,
                    job.company_id,
                    job.company_name,
                    job.status.value,
                    1 if job.cancellation_requested else 0,
                    job.max_depth,
                    job.max_pages,
                    job.max_pages_per_domain,
                    job.pages_crawled,
                    job.pages_failed,
                    job.discovered_urls_count,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    job.error_message,
                    job.worker_pid,
                    metrics_raw,
                ),
            )
            job.id = cursor.lastrowid
            return job
    finally:
        conn.close()


def get_crawl_job(
    job_id: int,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[CrawlJob]:
    """Retrieve a crawl job by ID, ensuring performance metrics are loaded."""
    own_conn = conn is None
    c = conn or get_connection(db_path)
    try:
        row = c.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = _row_to_crawl_job(row)
        if job.metrics is None:
            job.metrics = calculate_job_metrics(job_id, conn=c)
        return job
    finally:
        if own_conn:
            c.close()


def list_crawl_jobs(
    status: Optional[CrawlJobStatus] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[CrawlJob]:
    """List crawl jobs with optional status filter."""
    own_conn = conn is None
    c = conn or get_connection(db_path)
    try:
        query = "SELECT * FROM crawl_jobs WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = c.execute(query, params).fetchall()
        jobs = []
        for r in rows:
            job = _row_to_crawl_job(r)
            if job.metrics is None:
                job.metrics = calculate_job_metrics(job.id, conn=c)
            jobs.append(job)
        return jobs
    finally:
        if own_conn:
            c.close()


def claim_next_pending_job(worker_pid: int, db_path: Optional[str] = None) -> Optional[CrawlJob]:
    """Atomically find and claim the oldest pending crawl job."""
    from datetime import datetime, timezone
    conn = get_connection(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT * FROM crawl_jobs WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job_id = row["id"]
            now_str = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'RUNNING', started_at = ?, worker_pid = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                (now_str, worker_pid, job_id),
            )
            if cursor.rowcount > 0:
                claimed = conn.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
                return _row_to_crawl_job(claimed)
            return None
    finally:
        conn.close()


def update_crawl_job_status(
    job_id: int,
    status: CrawlJobStatus,
    error_message: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update crawl job status and completion time."""
    from datetime import datetime, timezone
    conn = get_connection(db_path)
    try:
        with conn:
            finished_at = None
            if status in {CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED, CrawlJobStatus.CANCELLED}:
                finished_at = datetime.now(timezone.utc).isoformat()

            cursor = conn.execute(
                """
                UPDATE crawl_jobs
                SET status = ?,
                    finished_at = COALESCE(?, finished_at),
                    error_message = COALESCE(?, error_message)
                WHERE id = ?
                """,
                (status.value, finished_at, error_message, job_id),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def increment_crawl_job_progress(
    job_id: int,
    pages_crawled_inc: int = 0,
    pages_failed_inc: int = 0,
    discovered_inc: int = 0,
    db_path: Optional[str] = None,
) -> None:
    """Increment progress counters for a running crawl job."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE crawl_jobs
                SET pages_crawled = pages_crawled + ?,
                    pages_failed = pages_failed + ?,
                    discovered_urls_count = discovered_urls_count + ?
                WHERE id = ?
                """,
                (pages_crawled_inc, pages_failed_inc, discovered_inc, job_id),
            )
    finally:
        conn.close()


def request_cancel_crawl_job(job_id: int, db_path: Optional[str] = None) -> bool:
    """Flag a crawl job for cancellation."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE crawl_jobs
                SET cancellation_requested = 1
                WHERE id = ? AND status IN ('PENDING', 'RUNNING')
                """,
                (job_id,),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def is_cancellation_requested(job_id: int, db_path: Optional[str] = None) -> bool:
    """Check if cancellation has been requested for a job."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT cancellation_requested, status FROM crawl_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return False
        return bool(row["cancellation_requested"]) or row["status"] == CrawlJobStatus.CANCELLED.value
    finally:
        conn.close()


def recover_interrupted_jobs(db_path: Optional[str] = None) -> int:
    """Recover jobs left in RUNNING status after a process restart or crash.
    
    Marks them as FAILED with a clear interruption message and finalizes their metrics.
    """
    from datetime import datetime, timezone
    conn = get_connection(db_path)
    try:
        with conn:
            running_jobs = conn.execute("SELECT id FROM crawl_jobs WHERE status = 'RUNNING'").fetchall()
            if not running_jobs:
                return 0
            job_ids = [r["id"] for r in running_jobs]
            now_str = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'FAILED',
                    finished_at = ?,
                    error_message = 'Interrupted: Worker process terminated before job completion.'
                WHERE status = 'RUNNING'
                """,
                (now_str,),
            )
            for jid in job_ids:
                calculate_and_save = calculate_job_metrics(
                    jid,
                    stop_reason="interrupted",
                    final_outcome="FAILED",
                    conn=conn,
                )
                save_crawl_job_metrics(jid, calculate_and_save, conn=conn)
            return cursor.rowcount
    finally:
        conn.close()


def save_crawled_page(page: CrawlPage, db_path: Optional[str] = None) -> CrawlPage:
    """Persist an extracted crawl page result."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO crawl_pages (
                    job_id, original_url, final_url, http_status, depth,
                    discovery_source_url, title, extracted_text, headings_json,
                    metadata_json, links_count, word_count, content_hash,
                    status, error_message, evidence_id, retrieved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page.job_id,
                    page.original_url,
                    page.final_url,
                    page.http_status,
                    page.depth,
                    page.discovery_source_url,
                    page.title,
                    page.extracted_text,
                    json.dumps(page.headings_json) if page.headings_json else None,
                    json.dumps(page.metadata_json) if page.metadata_json else None,
                    page.links_count,
                    page.word_count,
                    page.content_hash,
                    page.status.value,
                    page.error_message,
                    page.evidence_id,
                    page.retrieved_at,
                ),
            )
            page.id = cursor.lastrowid
            return page
    finally:
        conn.close()


def get_crawled_pages(
    job_id: int,
    status: Optional[CrawlPageStatus] = None,
    limit: int = 200,
    offset: int = 0,
    db_path: Optional[str] = None,
) -> List[CrawlPage]:
    """Retrieve crawled pages for a specific job."""
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM crawl_pages WHERE job_id = ?"
        params: List[Any] = [job_id]
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [_row_to_crawl_page(r) for r in rows]
    finally:
        conn.close()


def get_failed_crawled_pages(job_id: int, db_path: Optional[str] = None) -> List[CrawlPage]:
    """Retrieve failed pages for a job to support retry analysis."""
    return get_crawled_pages(job_id, status=CrawlPageStatus.FAILED, db_path=db_path)


def _row_to_crawl_job(row: sqlite3.Row) -> CrawlJob:
    domains = []
    if row["allowed_domains_json"]:
        try:
            domains = json.loads(row["allowed_domains_json"])
        except Exception:
            pass

    metrics_json_str = None
    metrics_obj = None
    if "metrics_json" in row.keys() and row["metrics_json"]:
        metrics_json_str = row["metrics_json"]
        try:
            metrics_obj = CrawlJobMetrics.model_validate_json(metrics_json_str)
        except Exception:
            pass

    return CrawlJob(
        id=row["id"],
        seed_url=row["seed_url"],
        allowed_domains=domains,
        workflow=WorkflowType(row["workflow"]),
        company_id=row["company_id"],
        company_name=row["company_name"],
        status=CrawlJobStatus(row["status"]),
        cancellation_requested=bool(row["cancellation_requested"]),
        max_depth=row["max_depth"],
        max_pages=row["max_pages"],
        max_pages_per_domain=row["max_pages_per_domain"],
        pages_crawled=row["pages_crawled"],
        pages_failed=row["pages_failed"],
        discovered_urls_count=row["discovered_urls_count"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_message=row["error_message"],
        worker_pid=row["worker_pid"],
        metrics_json=metrics_json_str,
        metrics=metrics_obj,
    )


def calculate_job_metrics(
    job_id: int,
    scrapy_stats: Optional[Dict[str, Any]] = None,
    stop_reason: Optional[str] = None,
    final_outcome: Optional[str] = None,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> CrawlJobMetrics:
    """Calculate and aggregate performance metrics for a crawl job from database records and Scrapy statistics."""
    own_conn = conn is None
    c = conn or get_connection(db_path)
    try:
        # 1. Aggregate metrics from crawl_pages
        page_stats = c.execute(
            """
            SELECT 
                COUNT(*) as total_pages,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as unique_pages_saved,
                SUM(CASE WHEN status = 'SUCCESS' AND word_count > 0 AND length(trim(coalesce(extracted_text, ''))) > 0 THEN 1 ELSE 0 END) as useful_pages,
                SUM(CASE WHEN status = 'SUCCESS' AND (word_count = 0 OR extracted_text IS NULL OR length(trim(extracted_text)) = 0) THEN 1 ELSE 0 END) as empty_or_thin_pages,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_pages,
                SUM(CASE WHEN evidence_id IS NOT NULL THEN 1 ELSE 0 END) as evidence_linked
            FROM crawl_pages WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

        unique_pages = int(page_stats["unique_pages_saved"] or 0)
        useful_pages = int(page_stats["useful_pages"] or 0)
        empty_thin_pages = int(page_stats["empty_or_thin_pages"] or 0)
        failed_pages = int(page_stats["failed_pages"] or 0)
        evidence_linked = int(page_stats["evidence_linked"] or 0)

        # 2. Fetch job record
        job_row = c.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
        outcome = final_outcome or (job_row["status"] if job_row else "COMPLETED")

        # 3. Compute duration from timestamps if available
        duration_sec = 0.0
        if job_row and job_row["started_at"]:
            try:
                from datetime import datetime, timezone
                started = datetime.fromisoformat(job_row["started_at"])
                ended = datetime.fromisoformat(job_row["finished_at"]) if job_row["finished_at"] else datetime.now(timezone.utc)
                duration_sec = max(0.0, (ended - started).total_seconds())
            except Exception:
                pass

        # 4. Integrate Scrapy stats if provided
        stats = scrapy_stats or {}
        req_attempted = max(0, int(stats.get("downloader/request_count", 0)))
        resp_downloaded = max(0, int(stats.get("response_received_count", 0) or stats.get("downloader/response_count", 0)))
        dupe_filtered = max(0, int(stats.get("dupefilter/filtered", 0)))
        wire_bytes = max(0, int(stats.get("downloader/response_bytes", 0)))
        decompressed_bytes = max(0, int(stats.get("httpcompression/response_bytes", 0)))

        # Fallback for Scrapy stats if job was finished or stats omitted
        if req_attempted == 0 and (unique_pages > 0 or failed_pages > 0):
            req_attempted = unique_pages + failed_pages
        if resp_downloaded == 0 and unique_pages > 0:
            resp_downloaded = unique_pages

        elapsed_stats = stats.get("elapsed_time_seconds")
        if elapsed_stats is not None:
            try:
                duration_sec = max(0.0, float(elapsed_stats))
            except Exception:
                pass

        # Failed requests: combine downloader exceptions, HTTP errors, and DB failed pages
        status_errors = sum(
            val for key, val in stats.items()
            if key.startswith("downloader/response_status_count/") and int(key.split("/")[-1]) >= 400
        ) if stats else 0
        exceptions_count = int(stats.get("downloader/exception_count", 0)) if stats else 0
        failed_requests = max(failed_pages, exceptions_count + status_errors)

        reason = stop_reason or stats.get("finish_reason") or outcome.lower()

        return CrawlJobMetrics(
            requests_attempted=req_attempted,
            responses_downloaded=resp_downloaded,
            unique_pages_saved=unique_pages,
            useful_pages=useful_pages,
            empty_or_thin_pages=empty_thin_pages,
            duplicate_requests_filtered=dupe_filtered,
            failed_requests=failed_requests,
            total_response_bytes=wire_bytes,
            total_decompressed_bytes=decompressed_bytes,
            crawl_duration_sec=round(duration_sec, 2),
            evidence_records_created=evidence_linked,
            final_outcome=outcome,
            stop_reason=str(reason) if reason else None,
        )
    finally:
        if own_conn:
            c.close()


def save_crawl_job_metrics(
    job_id: int,
    metrics: CrawlJobMetrics,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Persist structured crawl metrics JSON into the crawl_jobs record."""
    own_conn = conn is None
    c = conn or get_connection(db_path)
    try:
        cursor = c.execute(
            "UPDATE crawl_jobs SET metrics_json = ? WHERE id = ?",
            (metrics.model_dump_json(), job_id),
        )
        if own_conn:
            c.commit()
        return cursor.rowcount > 0
    finally:
        if own_conn:
            c.close()


def finalize_crawl_job_metrics(
    job_id: int,
    scrapy_stats: Optional[Dict[str, Any]] = None,
    stop_reason: Optional[str] = None,
    final_outcome: Optional[str] = None,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> CrawlJobMetrics:
    """Calculate and persist final metrics for a completed, cancelled, or failed crawl job."""
    own_conn = conn is None
    c = conn or get_connection(db_path)
    try:
        metrics = calculate_job_metrics(
            job_id=job_id,
            scrapy_stats=scrapy_stats,
            stop_reason=stop_reason,
            final_outcome=final_outcome,
            conn=c,
        )
        save_crawl_job_metrics(job_id, metrics, conn=c)
        if own_conn:
            c.commit()
        return metrics
    finally:
        if own_conn:
            c.close()


def _row_to_crawl_page(row: sqlite3.Row) -> CrawlPage:
    headings = None
    if row["headings_json"]:
        try:
            headings = json.loads(row["headings_json"])
        except Exception:
            pass

    metadata = None
    if row["metadata_json"]:
        try:
            metadata = json.loads(row["metadata_json"])
        except Exception:
            pass

    return CrawlPage(
        id=row["id"],
        job_id=row["job_id"],
        original_url=row["original_url"],
        final_url=row["final_url"],
        http_status=row["http_status"],
        depth=row["depth"],
        discovery_source_url=row["discovery_source_url"],
        title=row["title"],
        extracted_text=row["extracted_text"],
        headings_json=headings,
        metadata_json=metadata,
        links_count=row["links_count"] or 0,
        word_count=row["word_count"] or 0,
        content_hash=row["content_hash"],
        status=CrawlPageStatus(row["status"]),
        error_message=row["error_message"],
        evidence_id=row["evidence_id"],
        retrieved_at=row["retrieved_at"],
    )

