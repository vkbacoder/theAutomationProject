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
            """)
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
