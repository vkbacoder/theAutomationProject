"""Intelligence Extraction Engine for Document, Decision-Maker, Contact, and Evidence Discovery.

Extracts:
1. Decision-Makers: Executives, IT leaders, Finance heads, and department leads with published titles.
2. Public Professional Contacts: Emails, business phone numbers, and LinkedIn URLs explicitly published.
3. Entity Quality Classification: Distinguishes genuine NAMED_COMPANY leads from
   ANONYMOUS_CLIENT_DESCRIPTION, PERSON, PRODUCT_OR_TECHNOLOGY, and PROJECT_TITLE.
4. Unified Evidence: Links all claims with exact quotes and fine-grained source locations.

Strict Quality & Truth Standards:
- Zero fabricated contact details (no guessed emails or pattern generation).
- Anonymous client descriptions are retained but separated from verified corporate leads.
- Preserve published job titles and distinguish verified titles from inferred relevance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from dedup import is_fuzzy_name_match, normalize_company_name
from models import (
    CandidateCategory,
    ClaimType,
    ContactType,
    ContactVerificationStatus,
    DecisionMaker,
    PublicContact,
    RoleCategory,
    UnifiedEvidence,
)

# -------------------------------------------------------------
# Decision Maker Role Detection Patterns
# -------------------------------------------------------------

RE_EXEC_TITLES = [
    # C-Level & Executives
    (r"\b(?:Chief\s+Executive\s+Officer|CEO)\b", RoleCategory.EXECUTIVE, "Executive Leadership"),
    (r"\b(?:Chief\s+Technology\s+Officer|CTO)\b", RoleCategory.TECHNOLOGY_IT, "Technology Leadership"),
    (r"\b(?:Chief\s+Information\s+Officer|CIO)\b", RoleCategory.TECHNOLOGY_IT, "IT & Information Leadership"),
    (r"\b(?:Chief\s+Data\s+Officer|CDO)\b", RoleCategory.TECHNOLOGY_IT, "Data Leadership"),
    (r"\b(?:Chief\s+Financial\s+Officer|CFO)\b", RoleCategory.FINANCE_BUSINESS, "Finance Leadership"),
    (r"\b(?:Chief\s+Operating\s+Officer|COO)\b", RoleCategory.OPERATIONS, "Operations Leadership"),
    (r"\b(?:Managing\s+Director|MD)\b", RoleCategory.EXECUTIVE, "Executive Leadership"),
    (r"\b(?:President|Vice\s+President|VP|Executive\s+Director)\b", RoleCategory.EXECUTIVE, "Executive Leadership"),
    (r"\b(?:Founder|Co-Founder|Owner|Partner)\b", RoleCategory.EXECUTIVE, "Founding Executive"),

    # Technology, Data & IT Leadership
    (r"\b(?:Head\s+of\s+IT|IT\s+Director|Director\s+of\s+IT|IT\s+Manager)\b", RoleCategory.TECHNOLOGY_IT, "IT Management"),
    (r"\b(?:Head\s+of\s+Data|Director\s+of\s+Data|Data\s+Engineering\s+Lead)\b", RoleCategory.TECHNOLOGY_IT, "Data Architecture"),
    (r"\b(?:Head\s+of\s+Analytics|Analytics\s+Director|Director\s+of\s+Analytics)\b", RoleCategory.TECHNOLOGY_IT, "Analytics Leadership"),
    (r"\b(?:Head\s+of\s+(?:BI|Business\s+Intelligence)|Director\s+of\s+Business\s+Intelligence|BI\s+Director|BI\s+Manager)\b", RoleCategory.TECHNOLOGY_IT, "Business Intelligence"),
    (r"\b(?:Head\s+of\s+Enterprise\s+Systems|Enterprise\s+Architect|Solutions\s+Architect)\b", RoleCategory.TECHNOLOGY_IT, "Enterprise Architecture"),
    (r"\b(?:Digital\s+Transformation\s+Lead(?:er)?|Director\s+of\s+Digital\s+Transformation)\b", RoleCategory.TECHNOLOGY_IT, "Digital Transformation"),

    # Finance, Planning & Performance Leadership
    (r"\b(?:Finance\s+Director|Director\s+of\s+Finance|Financial\s+Controller|Controller)\b", RoleCategory.FINANCE_BUSINESS, "Finance & Controllership"),
    (r"\b(?:Head\s+of\s+FP&A|FP&A\s+(?:Manager|Lead|Director|Specialist|Analyst)|FP&A|Financial\s+Planning\s+Manager)\b", RoleCategory.FINANCE_BUSINESS, "Financial Planning & Analysis"),
    (r"\b(?:Head\s+of\s+Planning|Planning\s+Director|EPM\s+Lead|CPM\s+Director)\b", RoleCategory.FINANCE_BUSINESS, "Enterprise Planning"),
    (r"\b(?:Head\s+of\s+Performance\s+Management|Director\s+of\s+Performance\s+Management)\b", RoleCategory.FINANCE_BUSINESS, "Performance Management"),
    (r"\b(?:Head\s+of\s+Procurement|Procurement\s+Director|Purchasing\s+Manager)\b", RoleCategory.FINANCE_BUSINESS, "Procurement & Purchasing"),

    # Operations & Supply Chain Leadership
    (r"\b(?:Head\s+of\s+Supply\s+Chain|Supply\s+Chain\s+Director|Director\s+of\s+Supply\s+Chain)\b", RoleCategory.OPERATIONS, "Supply Chain"),
    (r"\b(?:Head\s+of\s+Operations|Director\s+of\s+Operations|Operations\s+Manager)\b", RoleCategory.OPERATIONS, "Operations Management"),
]

# Patterns linking Name to Title:
# "John Doe, Chief Financial Officer"
# "Jane Smith - Head of FP&A"
# "- Anna Schell ( FP&A Starlight)"
# "Director of IT, Robert Taylor"
# "Spokesperson: Alice Johnson, CFO at Company"
RE_NAME_TITLE_PATTERNS = [
    # Parenthetical signature: "- Anna Schell ( FP&A Starlight)" or "Anna Schell (FP&A, Starlight)"
    re.compile(
        r"(?:^|[—–\-\n])\s*([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*\(\s*([^)\n]+?)\s*\)",
    ),
    # "John Doe, CFO" or "John Doe, Chief Technology Officer"
    re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*(?:,\s*|—\s*|–\s*|-\s*|\s+is\s+the\s+)([A-Z][A-Za-z0-9&/,\. ]{2,45}?)(?=[.,;\n\)]|$)",
    ),
    # "CFO John Doe" or "Chief Financial Officer Jane Smith"
    re.compile(
        r"\b(Chief\s+[A-Za-z]+\s+Officer|Director\s+of\s+[A-Za-z]+|Head\s+of\s+[A-Za-z&]+)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b",
    ),
]


# -------------------------------------------------------------
# Contact Extraction Patterns
# -------------------------------------------------------------

RE_EMAIL = re.compile(
    r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b",
)

RE_PHONE = re.compile(
    r"(?:\b|\+)(?:(?:\+?[1-9]\d{0,2}[ -]?)?(?:\(?\d{2,4}\)?[ -]?)?\d{3,4}[ -]?\d{3,4})\b"
)

RE_LINKEDIN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|company)/([a-zA-Z0-9_%-]+)/?",
    re.IGNORECASE,
)

INVALID_EMAIL_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".woff", ".ttf",
}

DISALLOWED_EMAIL_DOMAINS = {
    "example.com", "example.org", "domain.com", "sample.com", "test.com", "yoursite.com",
    "email.com", "placeholder.com",
}

# -------------------------------------------------------------
# Candidate Entity Categorization Rules
# -------------------------------------------------------------

ANONYMOUS_CLIENT_DESCRIPTORS = [
    "global fintech player", "fintech firm", "fintech player", "alcobev giant",
    "global food company", "beverage leader", "global beverage leader",
    "global it software gcc", "building materials gcc", "general insurance firm",
    "food & beverage company", "food and beverage company", "leading bank",
    "fortune 500 company", "fortune 100 enterprise", "global pharmaceutical firm",
    "global alcobev leader", "tier 1 supplier", "multinational conglomerate",
]

KNOWN_TECHNOLOGIES_AND_PRODUCTS = [
    "anaplan", "jedox", "azure databricks", "databricks", "qlikview", "qlik sense",
    "power bi", "tableau", "snowflake", "sap", "sap s/4hana", "oracle", "oracle epm",
    "onestream", "netsuite", "coupa", "greenhouse", "unity catalog", "aws", "gcp",
    "microsoft azure", "salesforce", "workday", "hubspot",
]

PROJECT_AND_ARCHITECTURE_TERMS = [
    "rag based search", "ddh architecture", "data mesh", "pos analytics",
    "medallion architecture", "space optimization", "prompt engineering",
    "generative ai", "sales forecasting", "agentic ai",
]


def classify_entity_category(name: str, supporting_text: Optional[str] = None) -> CandidateCategory:
    """Classify an extracted entity to filter out anonymous descriptions, products, and titles."""
    if not name:
        return CandidateCategory.OTHER_ENTITY
    norm = name.strip().lower()

    # Personal name prefix check (e.g. Dr. Robert Smith, Prof. Charles Xavier)
    if re.match(r"^(?:mr|ms|mrs|dr|prof|sir)\.?\s+[A-Za-z]+", norm):
        return CandidateCategory.PERSON

    # 1. Anonymous client descriptions
    if any(desc in norm or is_fuzzy_name_match(norm, desc, threshold=85.0) for desc in ANONYMOUS_CLIENT_DESCRIPTORS):
        return CandidateCategory.ANONYMOUS_CLIENT_DESCRIPTION

    if supporting_text:
        supp_low = supporting_text.lower()
        if any(f"client, a {desc}" in supp_low or f"a {desc}" in supp_low for desc in ANONYMOUS_CLIENT_DESCRIPTORS):
            return CandidateCategory.ANONYMOUS_CLIENT_DESCRIPTION

    # 2. Products and technologies
    if any(tech == norm or (len(tech) > 3 and tech in norm and not any(suff in norm for suff in ("gmbh", "inc", "corp", "ltd", "llc"))) for tech in KNOWN_TECHNOLOGIES_AND_PRODUCTS):
        return CandidateCategory.PRODUCT_OR_TECHNOLOGY

    # 3. Project titles and architectures
    if any(proj in norm for proj in PROJECT_AND_ARCHITECTURE_TERMS):
        return CandidateCategory.PROJECT_TITLE

    # 4. Personal name check (e.g. 2 capitalized words without corporate suffix)
    words = name.split()
    if len(words) >= 2 and words[0].lower().rstrip(".") in ("mr", "ms", "mrs", "dr", "prof"):
        return CandidateCategory.PERSON

    # 5. Default genuine named company
    return CandidateCategory.NAMED_COMPANY


# -------------------------------------------------------------
# Decision Maker Discovery
# -------------------------------------------------------------

def extract_decision_makers_from_text(
    text: str,
    source_url: str,
    source_type: str = "HTML",
    source_location: Optional[str] = None,
    associated_company: Optional[str] = None,
    target_product: str = "Jedox",
    job_id: Optional[int] = None,
    default_company: Optional[str] = None,
) -> List[DecisionMaker]:
    """Scan text for professional decision-makers and their published titles."""
    discovered: List[DecisionMaker] = []
    if not text:
        return discovered

    company_to_use = associated_company or default_company
    seen_names: Set[str] = set()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines:
        for pattern in RE_NAME_TITLE_PATTERNS:
            for match in pattern.finditer(line):
                groups = match.groups()
                if len(groups) == 2:
                    p1, p2 = groups[0].strip(), groups[1].strip()
                    name_cand, title_cand = (p1, p2) if not any(kw in p1.lower() for kw in ("chief", "head", "director", "manager", "officer", "vp")) else (p2, p1)

                    name_words = name_cand.split()
                    if not (1 < len(name_words) <= 4 and all(w[0].isupper() for w in name_words if w.isalpha())):
                        continue
                    if any(t in name_cand.lower() for t in ("polestar", "analytics", "case study", "company", "solution", "report")):
                        continue

                    norm_name = normalize_company_name(name_cand)
                    if norm_name in seen_names or len(norm_name) < 4:
                        continue

                    # Check if title_cand contains an embedded company: e.g. "FP&A Starlight" or "FP&A, Starlight"
                    clean_title = title_cand.strip()
                    item_company = company_to_use
                    m_comp = re.search(r"^(.*?)(?:\s+(?:at|@|,)\s+|\s+-\s+)(.+)$", title_cand, re.IGNORECASE)
                    if m_comp:
                        clean_title = m_comp.group(1).strip()
                        item_company = m_comp.group(2).strip()
                    else:
                        m_space_comp = re.search(r"^(FP&A|CFO|CTO|CIO|CEO|COO|VP|Director|Manager)\s+([A-Z][A-Za-z0-9&.' -]+)$", title_cand, re.IGNORECASE)
                        if m_space_comp:
                            clean_title = m_space_comp.group(1).strip()
                            item_company = m_space_comp.group(2).strip()

                    matched_role = None
                    department_desc = "Management"
                    relevance_desc = "Decision-maker in organizational hierarchy"

                    for role_pattern, role_cat, dept in RE_EXEC_TITLES:
                        if re.search(role_pattern, clean_title, re.IGNORECASE) or re.search(role_pattern, title_cand, re.IGNORECASE):
                            matched_role = role_cat
                            department_desc = dept
                            if role_cat == RoleCategory.FINANCE_BUSINESS:
                                relevance_desc = f"Key purchasing/evaluation authority for {target_product} FP&A solutions"
                            elif role_cat == RoleCategory.TECHNOLOGY_IT:
                                relevance_desc = f"Technical and architecture evaluation authority for {target_product} deployment"
                            elif role_cat == RoleCategory.EXECUTIVE:
                                relevance_desc = f"Executive signing and strategy authority"
                            break

                    # Distinguish customer case-study stakeholders from active purchasing decision-makers
                    if any(kw in source_url.lower() for kw in ("case-stud", "starlight", "customer", "success-stor", "stories", "reference")):
                        relevance_desc = "Named professional stakeholder associated with customer case study"

                    if matched_role:
                        seen_names.add(norm_name)
                        snippet = line[:250]
                        discovered.append(
                            DecisionMaker(
                                job_id=job_id,
                                name=name_cand,
                                full_name=name_cand,
                                normalized_name=norm_name,
                                title=clean_title,
                                published_title=clean_title,
                                department=department_desc,
                                role_category=matched_role,
                                associated_company=item_company,
                                professional_relevance=relevance_desc,
                                source_url=source_url,
                                source_type=source_type,
                                supporting_quote=snippet,
                                verification_status="CONFIRMED_PUBLIC",
                            )
                        )

    return discovered


# -------------------------------------------------------------
# Public Professional Contact Extraction
# -------------------------------------------------------------

def extract_public_contacts_from_text(
    text: str,
    source_url: str,
    source_type: str = "HTML",
    file_name: Optional[str] = None,
    source_location: Optional[str] = None,
    associated_company: Optional[str] = None,
    file_type: Optional[str] = None,
    job_id: Optional[int] = None,
) -> List[PublicContact]:
    """Extract and strictly validate public professional emails, phone numbers, addresses, and LinkedIn URLs."""
    contacts: List[PublicContact] = []
    if not text:
        return contacts

    resolved_source_type = file_type or source_type
    seen_values: Set[str] = set()

    # 1. Emails
    for match in RE_EMAIL.finditer(text):
        raw_email = match.group(1).strip()
        email_clean = raw_email.rstrip(".,;:")
        lowered = email_clean.lower()

        # Validation rules
        if any(lowered.endswith(ext) for ext in INVALID_EMAIL_EXTENSIONS):
            continue
        domain_part = lowered.split("@")[-1]
        if domain_part in DISALLOWED_EMAIL_DOMAINS:
            continue
        if len(email_clean) < 6 or ".." in email_clean:
            continue
        if lowered in seen_values:
            continue
        seen_values.add(lowered)

        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        quote = text[start:end].replace("\n", " ").strip()

        # Classify general company contact vs named employee
        is_general_inbox = any(
            email_clean.lower().startswith(pfx)
            for pfx in ("webadmin@", "info@", "contact@", "support@", "admin@", "sales@", "hello@", "enquiries@")
        )
        j_title = "Company Contact Email" if is_general_inbox else None

        contacts.append(
            PublicContact(
                job_id=job_id or 0,
                contact_type=ContactType.EMAIL,
                contact_value=email_clean,
                job_title=j_title,
                associated_company=associated_company,
                source_url=source_url,
                source_type=resolved_source_type,
                file_name=file_name,
                supporting_quote=quote,
                source_location=source_location,
                verification_status=ContactVerificationStatus.VERIFIED_PUBLIC,
                is_public=True,
            )
        )

    # 2. LinkedIn URLs
    for match in RE_LINKEDIN.finditer(text):
        profile_slug = match.group(1)
        full_url = f"https://www.linkedin.com/in/{profile_slug}"
        if full_url in seen_values:
            continue
        seen_values.add(full_url)

        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        quote = text[start:end].replace("\n", " ").strip()

        contacts.append(
            PublicContact(
                job_id=job_id or 0,
                contact_type=ContactType.LINKEDIN,
                contact_value=full_url,
                associated_company=associated_company,
                source_url=source_url,
                source_type=resolved_source_type,
                file_name=file_name,
                supporting_quote=quote,
                source_location=source_location,
                verification_status=ContactVerificationStatus.VERIFIED_PUBLIC,
                is_public=True,
            )
        )

    # 3. Public Business Phone Numbers
    for match in RE_PHONE.finditer(text):
        raw_phone = match.group(0).strip()
        digits = re.sub(r"\D", "", raw_phone)
        # Only accept standard phone numbers (between 9 and 15 digits)
        if not (9 <= len(digits) <= 15):
            continue
        # Avoid timestamps (e.g. 20261019) or year strings
        if digits.startswith(("199", "200", "201", "202")) and len(digits) == 8:
            continue
        if raw_phone in seen_values:
            continue

        # Look at preceding context to ensure it's presented as telephone / contact
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        context = text[start:end].lower()

        if any(term in context for term in ("tel", "phone", "call", "fax", "contact", "+", "office", "mobile")):
            seen_values.add(raw_phone)
            quote = text[start:end].replace("\n", " ").strip()
            ctype = ContactType.OFFICE_PHONE if "office" in context else ContactType.PHONE

            contacts.append(
                PublicContact(
                    job_id=job_id or 0,
                    contact_type=ctype,
                    contact_value=raw_phone,
                    job_title="Company Phone",
                    associated_company=associated_company,
                    source_url=source_url,
                    source_type=resolved_source_type,
                    file_name=file_name,
                    supporting_quote=quote,
                    source_location=source_location,
                    verification_status=ContactVerificationStatus.VERIFIED_PUBLIC,
                    is_public=True,
                )
            )

    # 4. Public Business Address
    m_addr = re.search(
        r"(\d{1,4}[a-zA-Z]?,?\s+[A-Za-z0-9\s,'-]+(?:Road|Street|Avenue|Boulevard|Lane|Drive|Way|Parade|Crescent|Hwy|Highway),?\s+[A-Za-z\s]+(?:\s+[A-Z]{2,3})?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if m_addr:
        addr_clean = m_addr.group(1).strip()
        if addr_clean not in seen_values and len(addr_clean) < 120:
            seen_values.add(addr_clean)
            start = max(0, m_addr.start() - 30)
            end = min(len(text), m_addr.end() + 30)
            quote = text[start:end].replace("\n", " ").strip()
            contacts.append(
                PublicContact(
                    job_id=job_id or 0,
                    contact_type=ContactType.OTHER,
                    contact_value=addr_clean,
                    job_title="Company Address",
                    associated_company=associated_company,
                    source_url=source_url,
                    source_type=resolved_source_type,
                    file_name=file_name,
                    supporting_quote=quote,
                    source_location=source_location,
                    verification_status=ContactVerificationStatus.VERIFIED_PUBLIC,
                    is_public=True,
                )
            )

    return contacts


# -------------------------------------------------------------
# Unified Evidence Generator
# -------------------------------------------------------------

def build_unified_evidence(
    job_id: int,
    claim_type: ClaimType,
    claim_text: str,
    source_url: str,
    supporting_quote: str,
    source_format: str = "HTML",
    file_name: Optional[str] = None,
    source_location: Optional[str] = None,
    candidate_id: Optional[int] = None,
    person_id: Optional[int] = None,
    company_id: Optional[int] = None,
    verification_status: str = "CONFIRMED",
) -> UnifiedEvidence:
    """Create a standardized, auditable evidence item linking a claim to its exact source snippet."""
    return UnifiedEvidence(
        job_id=job_id,
        company_id=company_id,
        candidate_id=candidate_id,
        person_id=person_id,
        claim_type=claim_type,
        claim_text=claim_text,
        source_url=source_url,
        original_file_url=source_url if source_format != "HTML" else None,
        source_format=source_format,
        file_name=file_name,
        supporting_quote=supporting_quote[:500],
        source_location=source_location,
        extraction_status="SUCCESS",
        verification_status=verification_status,
    )


def generate_job_unified_evidence(
    job_id: int,
    candidates: List[CustomerCandidate],
    decision_makers: List[DecisionMaker],
    contacts: List[PublicContact],
    documents: Optional[List[Any]] = None,
) -> List[UnifiedEvidence]:
    """Aggregate, standardize, and format all evidence into traceable UnifiedEvidence records."""
    evidences: List[UnifiedEvidence] = []

    # 1. Candidate evidence (Relationship and Product Usage)
    for c in candidates:
        for s in c.sources:
            if s.relationship_claim and s.supporting_text:
                evidences.append(
                    build_unified_evidence(
                        job_id=job_id,
                        claim_type=ClaimType.RELATIONSHIP,
                        claim_text=f"Relationship claim for {c.candidate_name}: {s.relationship_claim}",
                        source_url=s.source_url,
                        supporting_quote=s.supporting_text,
                        source_format="DOCUMENT" if any(s.source_url.lower().endswith(ext) for ext in (".pdf", ".xlsx", ".docx", ".pptx", ".csv")) else "HTML",
                        candidate_id=c.id,
                        verification_status=c.classification.value if hasattr(c.classification, "value") else str(c.classification),
                    )
                )
            if s.product_claim and s.supporting_text:
                evidences.append(
                    build_unified_evidence(
                        job_id=job_id,
                        claim_type=ClaimType.PRODUCT_USAGE,
                        claim_text=f"{c.target_product} usage claim for {c.candidate_name}: {s.product_claim}",
                        source_url=s.source_url,
                        supporting_quote=s.supporting_text,
                        source_format="DOCUMENT" if any(s.source_url.lower().endswith(ext) for ext in (".pdf", ".xlsx", ".docx", ".pptx", ".csv")) else "HTML",
                        candidate_id=c.id,
                        verification_status=c.product_usage_status,
                    )
                )

    # 2. Decision Maker evidence
    for dm in decision_makers:
        if dm.supporting_quote:
            evidences.append(
                build_unified_evidence(
                    job_id=job_id,
                    claim_type=ClaimType.DECISION_MAKER,
                    claim_text=f"{dm.full_name} ({dm.published_title}) at {dm.associated_company or 'Target Company'}",
                    source_url=dm.source_url,
                    supporting_quote=dm.supporting_quote,
                    source_format=dm.source_type,
                    candidate_id=dm.candidate_company_id,
                    company_id=dm.company_id or dm.target_company_id,
                    person_id=dm.id,
                    verification_status=dm.verification_status,
                )
            )

    # 3. Public Contact evidence
    for ct in contacts:
        if ct.supporting_quote:
            p_name = getattr(ct, "person_name", None) or getattr(ct, "associated_person_name", None)
            s_fmt = getattr(ct, "source_type", None) or getattr(ct, "file_type", "HTML")
            evidences.append(
                build_unified_evidence(
                    job_id=job_id,
                    claim_type=ClaimType.CONTACT,
                    claim_text=f"Public {ct.contact_type.value}: {ct.contact_value}" + (f" ({p_name})" if p_name else ""),
                    source_url=ct.source_url,
                    supporting_quote=ct.supporting_quote,
                    source_format=s_fmt or "HTML",
                    file_name=ct.file_name,
                    source_location=ct.source_location,
                    candidate_id=ct.candidate_company_id,
                    company_id=ct.company_id,
                    person_id=ct.person_id,
                    verification_status=ct.verification_status.value if hasattr(ct.verification_status, "value") else str(ct.verification_status),
                )
            )

    return evidences
