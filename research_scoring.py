"""Intelligent Best-First URL Priority Scoring Engine.

Implements the 4-component weighted scoring model:
  Priority Score = 0.35 * Research Relevance
                 + 0.25 * Keyword Relevance
                 + 0.20 * Source Authority
                 + 0.20 * Information Potential

All components are normalized to a 0–100 scale before calculating the final score.
Deterministic, fast, and does not require LLM calls for every link.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field


# Keywords indicating high customer / case study value
CUSTOMER_KEYWORDS = {
    "customer", "customers", "client", "clients", "case-study", "case_study",
    "casestudy", "case-studies", "casestudies", "success-story", "success-stories",
    "successstory", "successstories", "stories", "reference", "references",
    "testimonial", "testimonials", "portfolio", "our-work", "our_work", "users",
}

# Keywords indicating leadership, finance, and decision-makers
LEADERSHIP_KEYWORDS = {
    "leadership", "executive", "executives", "management", "board", "directors",
    "cfo", "chief-financial-officer", "finance", "controller", "fp&a", "fpa",
    "cio", "chief-information-officer", "it-director", "team", "our-team",
    "about", "about-us", "governance", "people",
}

# Keywords indicating investor relations, annual reports, corporate performance
INVESTOR_KEYWORDS = {
    "investor", "investors", "investor-relations", "annual-report", "annual-reports",
    "annualreport", "financial-results", "reports", "governance", "asx", "sec",
    "filings", "corporate", "shareholder", "shareholders",
}

# Keywords indicating contact info
CONTACT_KEYWORDS = {
    "contact", "contact-us", "contactus", "locations", "offices", "headquarters",
    "branches", "get-in-touch", "reach-us",
}

# Technology, platform, and implementation keywords
TECH_KEYWORDS = {
    "software", "platform", "technology", "solution", "solutions", "erp", "cpm",
    "epm", "bi", "analytics", "implementation", "partner", "partners", "alliance",
    "alliances", "certified", "integration", "cloud",
}

# Low-priority patterns (catalogue, terms, privacy, noise)
DEPRIORITIZED_PATTERNS = [
    r"/privacy(?:-policy)?/?",
    r"/terms(?:-and-conditions|-of-use|-of-service)?/?",
    r"/cookie(?:-policy)?/?",
    r"/login/?",
    r"/signin/?",
    r"/cart/?",
    r"/checkout/?",
    r"/shop/?",
    r"/product(?:s)?/[a-z0-9_-]+/[a-z0-9_-]+/?",  # Deep product catalog
    r"/tag/[a-z0-9_-]+/?",
    r"/category/[a-z0-9_-]+/?",
    r"/page/\d+/?",
    r"/wp-content/uploads/.*?\.(?:jpg|jpeg|png|gif|svg)$",
]


class URLPriorityScore(BaseModel):
    """Detailed breakdown of URL priority score calculation."""
    url: str
    priority_score: float = Field(..., ge=0.0, le=100.0)
    research_relevance: float = Field(..., ge=0.0, le=100.0)
    keyword_relevance: float = Field(..., ge=0.0, le=100.0)
    source_authority: float = Field(..., ge=0.0, le=100.0)
    information_potential: float = Field(..., ge=0.0, le=100.0)
    discovery_depth: int = 0
    discovery_source: Optional[str] = None
    research_objective: Optional[str] = None
    rationale: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(timezone.utc).isoformat())

    @property
    def final_score(self) -> float:
        return self.priority_score


PriorityScoreComponents = URLPriorityScore


def normalize_url_for_research(url: str) -> str:
    """Normalize a URL by lowercasing scheme and host, stripping fragments and trailing slashes."""
    if not url:
        return ""
    url = url.strip()
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{scheme}://{netloc}{path}{query}"
    except Exception:
        return url.rstrip("/")


def compute_url_priority(
    url: str,
    link_text: Optional[str] = None,
    discovery_depth: int = 0,
    discovery_source: Optional[str] = None,
    workflow: str = "GENERAL",
    target_product: Optional[str] = None,
    company_name: Optional[str] = None,
    objective: Optional[str] = None,
    is_external: bool = False,
    target_company_domain: Optional[str] = None,
) -> URLPriorityScore:
    """Calculate the 4-component normalized priority score for a candidate URL."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    netloc = parsed.netloc.lower()
    combined_text = f"{url} {link_text or ''}".lower()
    t_prod = (target_product or "").strip().lower()
    c_name = (company_name or "").strip().lower()

    # ---------------------------------------------------------
    # 1. Research Relevance (0–100)
    # ---------------------------------------------------------
    # Measures direct alignment with the active research objectives.
    rel_score = 30.0  # Baseline

    # Target product alignment (e.g. Jedox, RECOV)
    if t_prod and t_prod in combined_text:
        rel_score += 40.0

    # Company name alignment
    if c_name and c_name in combined_text:
        rel_score += 20.0

    # Workflow-specific objective signals
    wf = (workflow or "").upper()
    if wf == "JEDOX":
        if any(term in combined_text for term in ("fpa", "fp&a", "budgeting", "planning", "financial planning", "cpm", "epm")):
            rel_score += 20.0
    elif wf == "RECOV":
        if any(term in combined_text for term in ("debt", "collection", "recovery", "receivable", "npa", "overdue")):
            rel_score += 20.0

    # Specific objective text matching
    if objective:
        obj_tokens = set(re.findall(r"\b\w{4,}\b", objective.lower()))
        matched_obj = [t for t in obj_tokens if t in combined_text]
        if matched_obj:
            rel_score += min(20.0, len(matched_obj) * 5.0)

    # Deprioritize catalog/policy unless specifically requested
    for pattern in DEPRIORITIZED_PATTERNS:
        if re.search(pattern, path):
            rel_score = max(5.0, rel_score - 45.0)
            break

    research_relevance = min(100.0, max(0.0, rel_score))

    # ---------------------------------------------------------
    # 2. Keyword Relevance (0–100)
    # ---------------------------------------------------------
    # Measures the density of target business, leadership, customer, and tech keywords.
    kw_score = 20.0  # Baseline

    cust_matches = [k for k in CUSTOMER_KEYWORDS if k in combined_text]
    lead_matches = [k for k in LEADERSHIP_KEYWORDS if k in combined_text]
    inv_matches = [k for k in INVESTOR_KEYWORDS if k in combined_text]
    cont_matches = [k for k in CONTACT_KEYWORDS if k in combined_text]
    tech_matches = [k for k in TECH_KEYWORDS if k in combined_text]

    kw_score += min(30.0, len(cust_matches) * 10.0)
    kw_score += min(25.0, len(lead_matches) * 10.0)
    kw_score += min(20.0, len(inv_matches) * 10.0)
    kw_score += min(15.0, len(cont_matches) * 8.0)
    kw_score += min(15.0, len(tech_matches) * 5.0)

    keyword_relevance = min(100.0, max(0.0, kw_score))

    # ---------------------------------------------------------
    # 3. Source Authority (0–100)
    # ---------------------------------------------------------
    # Assesses domain credibility, structural depth, and document authority.
    auth_score = 60.0  # Standard authority for company website

    # Depth penalty (shallower links are generally higher-level index/landing pages)
    depth_penalty = discovery_depth * 8.0
    auth_score -= depth_penalty

    # Official vendor domain for target product
    if t_prod and f"{t_prod}.com" in netloc:
        auth_score += 35.0

    # Government / Regulatory domain
    if any(netloc.endswith(tld) for tld in (".gov", ".gov.au", ".org.au", ".edu.au", ".govt.nz")):
        auth_score += 30.0
    elif any(auth_domain in netloc for auth_domain in ("asic.gov.au", "oaic.gov.au", "asx.com.au")):
        auth_score += 35.0

    # Official corporate domain root / primary sections
    path_segments = [s for s in path.strip("/").split("/") if s]
    if len(path_segments) <= 2:
        auth_score += 15.0

    # High-value corporate sections
    if any(sec in path for sec in ("/about", "/investors", "/leadership", "/management", "/governance", "/customers", "/case-studies")):
        auth_score += 15.0

    # Query string noise penalty
    if parsed.query:
        auth_score -= 10.0

    source_authority = min(100.0, max(0.0, auth_score))

    # ---------------------------------------------------------
    # 4. Information Potential (0–100)
    # ---------------------------------------------------------
    # Likelihood of extracting novel, verifiable facts:
    # - Product usage evidence
    # - Customer relationships
    # - Decision-makers
    # - Public contacts
    info_score = 25.0  # Baseline

    if cust_matches:
        info_score += 30.0  # High chance of customer relationships & usage evidence
    if lead_matches:
        info_score += 25.0  # High chance of decision-makers
    if cont_matches:
        info_score += 20.0  # High chance of public contacts
    if inv_matches:
        info_score += 20.0  # High chance of annual reports & executive signoffs
    if path.endswith((".pdf", ".xlsx", ".docx")):
        info_score += 15.0  # Documents frequently contain formal statements & case studies

    # Deprioritize generic blogs/tags without specific keywords
    if "/tag/" in path or "/category/" in path:
        info_score = max(5.0, info_score - 20.0)

    information_potential = min(100.0, max(0.0, info_score))

    # ---------------------------------------------------------
    # Final Weighted Priority Score
    # 0.35 * Research + 0.25 * Keyword + 0.20 * Source + 0.20 * Info
    # ---------------------------------------------------------
    total = (
        0.35 * research_relevance
        + 0.25 * keyword_relevance
        + 0.20 * source_authority
        + 0.20 * information_potential
    )
    final_score = round(min(100.0, max(0.0, total)), 2)

    # Human-readable rationale
    reasons = []
    if t_prod and t_prod in combined_text:
        reasons.append(f"mentions target product '{t_prod}'")
    if cust_matches:
        reasons.append(f"customer terms: {', '.join(cust_matches[:3])}")
    if lead_matches:
        reasons.append(f"leadership terms: {', '.join(lead_matches[:3])}")
    if inv_matches:
        reasons.append("investor/report path")
    if cont_matches:
        reasons.append("contact path")
    if any(re.search(p, path) for p in DEPRIORITIZED_PATTERNS):
        reasons.append("deprioritized catalogue/policy path")

    rationale = f"Priority {final_score:.1f}: " + ("; ".join(reasons) if reasons else "general site exploration")

    return URLPriorityScore(
        url=url,
        priority_score=final_score,
        research_relevance=round(research_relevance, 2),
        keyword_relevance=round(keyword_relevance, 2),
        source_authority=round(source_authority, 2),
        information_potential=round(information_potential, 2),
        discovery_depth=discovery_depth,
        discovery_source=discovery_source,
        research_objective=objective,
        rationale=rationale,
    )
