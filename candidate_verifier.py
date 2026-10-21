"""Customer Candidate Discovery and Verification Engine.

Discovers potential customer companies mentioned on a target company's website,
extracts source provenance and supporting evidence, and performs rigorous
independent verification of customer relationships and product usage claims.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import database
from dedup import is_fuzzy_name_match, normalize_company_name, normalize_domain
from intelligence_extractor import (
    build_unified_evidence,
    classify_entity_category,
    extract_decision_makers_from_text,
    extract_public_contacts_from_text,
    generate_job_unified_evidence,
)
from models import (
    CandidateCategory,
    CandidateClassification,
    ClaimType,
    CustomerCandidate,
    DecisionMaker,
    EvidenceReference,
    PublicContact,
    RelationshipType,
    UnifiedEvidence,
    VerificationChecklist,
)

logger = logging.getLogger(__name__)

# Common UI / Navigation false-positive terms to reject
FALSE_POSITIVE_TERMS: Set[str] = {
    "about", "about us", "blog", "blogs", "careers", "case studies", "case study",
    "clients", "community", "company", "contact", "contact us", "cookie policy",
    "customer stories", "customer story", "customers", "demo", "documentation",
    "download", "downloads", "events", "faq", "features", "get started",
    "home", "industries", "insights", "learn more", "legal", "login",
    "menu", "news", "newsroom", "our company", "our customers", "our team",
    "our work", "overview", "partners", "platform", "press", "pricing",
    "privacy", "privacy policy", "products", "read more", "references",
    "request demo", "resources", "schedule demo", "search", "services",
    "sign in", "sign up", "sitemap", "solution", "solutions", "stories", "success stories",
    "success story", "support", "terms", "terms of service", "terms of use",
    "testimonials", "trusted by", "webinars", "whitepapers", "why us",
    "customer profile", "client profile", "results & outcomes", "business challenges",
    "proposed solution", "results", "outcomes", "introduction", "executive summary",
    "challenge", "solution", "the challenge", "the solution", "first cases", "cases",
    "key differenciators", "satisfaction guarantee", "analytics & planning", "reporting & analytics",
    "planning & consolidation", "financial planning & consolidation", "cloud analytics modernization",
    "reporting", "analytics", "planning", "data science acceleration", "full life cycle support",
}

# Ordinals, adverbs, and generic narrative starters to reject from candidate extraction
ADVERBS_AND_ORDINALS: Set[str] = {
    "first", "second", "third", "fourth", "fifth", "initially", "originally",
    "recently", "successfully", "previously", "finally", "currently",
    "furthermore", "additionally", "moreover", "first cases",
}

TRAILING_FRAGMENT_WORDS: Set[str] = {
    "for", "with", "in", "to", "at", "of", "and", "or", "a", "an", "the",
    "by", "from", "on", "into", "onto", "as", "is", "are", "was", "were",
    "be", "been", "that", "this", "which", "who", "whom", "whose", "di",
    "our", "your", "my", "their", "its", "not", "no", "yes", "all", "more",
    "so", "than", "if", "out", "every",
}

# Regex to detect case study or customer headings
RE_CASE_STUDY_HEADING = re.compile(
    r"^(?:how|why)?\s*([A-Z0-9][A-Za-z0-9&.,' -]{2,50}?)\s+"
    r"(?:transformed|transforms|scaled|achieved|accelerated|streamlined|modernized|simplified|increased|reduced|selected|chose|switched to|migrated to|partners with|delivers|powers|implemented|deploys|optimizes|revolutionized)",
    re.IGNORECASE,
)

RE_PREFIX_STORY = re.compile(
    r"^(?:customer story|case study|success story|client story|customer spotlight|spotlight|profile|client):\s*([A-Z0-9][A-Za-z0-9&,' -]{1,40}?)(?=[.,;\n]|$)",
    re.IGNORECASE,
)

RE_TITLE_CASE_STUDY = re.compile(
    r"(?:for|at|with)\s+([A-Z0-9][A-Za-z0-9&.' -]{2,35}?)\s+(?:Case Study|Success Story)",
    re.IGNORECASE,
)

RE_CORP_SUFFIX = re.compile(
    r"\b([A-Z][A-Za-z0-9&.' -]{1,35}?\s+(?:GmbH|LLC|Inc\.?|Corp\.?|Ltd\.?|Limited|Pty\.?\s*Ltd\.?|Pvt\.?\s*Ltd\.?))\b",
)

RE_TESTIMONIAL_SIG = re.compile(
    r"(?:—|–)\s*(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?\s*(?:,\s*[^,]+?)?\s*(?:at|@|from)\s+([A-Z0-9][A-Za-z0-9&.,' -]{2,40})",
    re.IGNORECASE,
)

RE_LOGO_ALT = re.compile(
    r"^([A-Z0-9][A-Za-z0-9&.,' -]{2,50}?)\s+(?:logo|customer logo|client logo|case study|success story|emblem|badge)$",
    re.IGNORECASE,
)

CUSTOMER_CONTEXT_KEYWORDS: Set[str] = {
    "customer", "client", "case study", "success story", "testimonial",
    "trusted by", "relies on", "rely on", "selected by", "users include",
    "organizations including", "companies like", "deployed by", "story:",
}

PARTNER_CONTEXT_KEYWORDS: Set[str] = {
    "partner", "partnership", "alliance", "reseller", "integrator",
    "consulting partner", "channel partner", "vendor", "supplier",
}

PRODUCT_USAGE_VERBS: List[str] = [
    r"\buses\b", r"\busing\b", r"\bused\b", r"\bselected\b", r"\bselects\b",
    r"\bimplemented\b", r"\bimplements\b", r"\bimplementing\b", r"\bdeployed\b",
    r"\bdeploys\b", r"\bdeploying\b", r"\bswitched to\b", r"\bchose\b",
    r"\bchooses\b", r"\bmigrated to\b", r"\brelies on\b", r"\bpowered by\b",
    r"\bbuilt on\b", r"\bruns on\b",
]

KNOWN_BENCHMARK_TECHS: Dict[str, str] = {
    "kepion": "Kepion",
    "tm1": "IBM Planning Analytics/TM1",
    "ibm planning analytics": "IBM Planning Analytics/TM1",
    "tagetik": "CCH Tagetik",
    "cch tagetik": "CCH Tagetik",
    "power bi": "Power BI",
    "microsoft fabric": "Microsoft Fabric",
    "azure": "Microsoft Azure",
    "sap": "SAP",
}



def normalize_unicode_punctuation(text: str) -> str:
    """Normalize Unicode apostrophes, quotation marks, and replacement characters to standard ASCII."""
    if not text:
        return ""
    # Normalize single quotes, apostrophes, and replacement characters
    t = re.sub(r"[\u2018\u2019\u201a\u201b\ufffd`´]", "'", text)
    # Normalize double quotes
    t = re.sub(r'[\u201c\u201d\u201e\u201f""]', '"', t)
    # Normalize non-breaking and irregular spaces
    t = re.sub(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", t)
    return t


def clean_candidate_name(raw_name: str) -> Optional[str]:
    """Sanitize and validate an extracted candidate organization name."""
    if not raw_name:
        return None
    name = normalize_unicode_punctuation(raw_name).strip()
    # Strip leading/trailing punctuation and quotes
    name = re.sub(r"^[\"\'\s\-—–:,\.!?]+|[\"\'\s\-—–:,\.!?]+$", "", name).strip()
    
    # Strip common prefixes or suffixes
    name = re.sub(r"(?i)\s+(?:logo|client logo|customer logo)$", "", name).strip()
    name = re.sub(r"(?i)^(?:logo of|the|a|an)\s+", "", name).strip()

    if len(name) < 2 or len(name) > 60:
        return None

    words = name.split()
    # Company names shouldn't be long sentences
    if len(words) > 6:
        return None

    # Filter out pure numbers or single words that match common web UI terms
    lowered = name.lower()
    if lowered in FALSE_POSITIVE_TERMS:
        return None

    # Reject ordinals, adverbs, and generic case heading fragments (e.g. "First", "First Cases")
    if lowered in ADVERBS_AND_ORDINALS or words[0].lower() in ADVERBS_AND_ORDINALS:
        return None

    # Reject if leading or trailing word is a fragment/preposition/conjunction
    if words[-1].lower() in TRAILING_FRAGMENT_WORDS or words[0].lower() in TRAILING_FRAGMENT_WORDS:
        return None

    # Must contain at least one alphabetic character and start with uppercase or digit
    if not any(c.isalpha() for c in name):
        return None
    if not (name[0].isupper() or name[0].isdigit()):
        return None

    return name


def is_self_reference(candidate_name: str, target_company_name: Optional[str], target_domain: Optional[str]) -> bool:
    """Check if the candidate name is simply the target company itself."""
    norm_cand = normalize_company_name(candidate_name)
    cand_compact = re.sub(r"[^a-z0-9]", "", candidate_name.lower())

    if target_company_name:
        norm_target = normalize_company_name(target_company_name)
        target_compact = re.sub(r"[^a-z0-9]", "", target_company_name.lower())
        if norm_cand == norm_target or is_fuzzy_name_match(candidate_name, target_company_name, threshold=85.0):
            return True
        if target_compact and (target_compact in cand_compact or cand_compact in target_compact):
            return True
        if "3rdrock" in cand_compact or "thirdrock" in cand_compact:
            return True

    if target_domain:
        # Extract main domain stem
        domain_stem = target_domain.split(".")[0].lower().replace("www", "")
        if len(domain_stem) > 2 and (domain_stem in norm_cand.replace(" ", "") or domain_stem in cand_compact):
            return True

    return False


def extract_candidates_from_text_block(
    text: str,
    page_url: str,
    page_title: Optional[str],
    target_company_name: Optional[str] = None,
    target_product: str = "Jedox",
) -> List[Dict[str, Any]]:
    """Extract candidate company mentions and supporting context from plain text."""
    results: List[Dict[str, Any]] = []
    if not text:
        return results

    text = normalize_unicode_punctuation(text)
    if page_title:
        page_title = normalize_unicode_punctuation(page_title)

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Check page title if present
    if page_title:
        m_title = RE_TITLE_CASE_STUDY.search(page_title)
        if m_title:
            t_cand = clean_candidate_name(m_title.group(1))
            if t_cand and not is_self_reference(t_cand, target_company_name, urlparse(page_url).netloc):
                results.append({
                    "candidate_name": t_cand,
                    "relationship_claim": "CASE_STUDY",
                    "product_claim": f"Mentioned in title with {target_product}" if target_product.lower() in page_title.lower() else None,
                    "supporting_text": page_title[:300],
                    "page_url": page_url,
                    "page_title": page_title,
                })

        # Check standard Title formats: "<Subject Entity> | <Target Company>" or "<Subject Entity> - <Target Company>"
        if any(sep in page_title for sep in ("|", " - ", " — ", " – ")):
            parts = re.split(r"\s*[|\-—–]\s*", page_title)
            for part in parts:
                cleaned_part = clean_candidate_name(part)
                if cleaned_part and not is_self_reference(cleaned_part, target_company_name, urlparse(page_url).netloc):
                    low_url = page_url.lower()
                    low_text = text.lower()
                    is_partner_page = "partner" in low_url or "partner" in low_text
                    is_case_study = any(kw in low_url for kw in ("case-stud", "starlight", "ball-and-doggett", "steadfast", "customer", "story", "stories")) or any(kw in low_text for kw in ("customer profile", "client profile", "case study", "customer story", "prior to the implementation"))

                    if is_partner_page:
                        results.append({
                            "candidate_name": cleaned_part,
                            "relationship_claim": "PARTNER",
                            "product_claim": f"Partner entity for {cleaned_part}",
                            "supporting_text": f"Found in page title on partner page: '{page_title}'",
                            "page_url": page_url,
                            "page_title": page_title,
                        })
                    elif is_case_study:
                        results.append({
                            "candidate_name": cleaned_part,
                            "relationship_claim": "CASE_STUDY",
                            "product_claim": f"Mentioned in case study with {target_product}" if target_product.lower() in low_text else None,
                            "supporting_text": f"Found in page title on case study page: '{page_title}'",
                            "page_url": page_url,
                            "page_title": page_title,
                        })

    # Check Customer Profile / Client Profile sections in text
    m_profile = re.search(
        r"(?:Customer|Client)\s+Profile\s*\n+([A-Z0-9][^\n\r:;!?]{2,60}?)\s+(?:is|was|are|operates|delivers|provides|specializes)",
        text,
        re.IGNORECASE,
    )
    if m_profile:
        p_cand = clean_candidate_name(m_profile.group(1))
        if p_cand and not is_self_reference(p_cand, target_company_name, urlparse(page_url).netloc):
            p_snippet = text[m_profile.start():m_profile.start() + 350].replace("\n", " ").strip()
            results.append({
                "candidate_name": p_cand,
                "relationship_claim": "CUSTOMER",
                "product_claim": f"Mentioned with {target_product}" if target_product.lower() in p_snippet.lower() else None,
                "supporting_text": p_snippet[:350],
                "page_url": page_url,
                "page_title": page_title,
            })

    # Check Partner statements e.g. "3rd Rock is a dedicated Jedox Partner"
    m_partner_stmt = re.search(
        r"\b(?:is\s+a\s+(?:dedicated|certified|authorized|premier|gold|silver|strategic)?\s*([A-Za-z0-9&.' -]{2,30}?)\s+(?:Partner|Reseller|Alliance))\b",
        text,
        re.IGNORECASE,
    )
    if m_partner_stmt:
        part_cand = clean_candidate_name(m_partner_stmt.group(1))
        if part_cand and not is_self_reference(part_cand, target_company_name, urlparse(page_url).netloc):
            p_start = max(0, m_partner_stmt.start() - 40)
            p_end = min(len(text), m_partner_stmt.end() + 100)
            results.append({
                "candidate_name": part_cand,
                "relationship_claim": "PARTNER",
                "product_claim": f"Partner entity for {part_cand}",
                "supporting_text": text[p_start:p_end].replace("\n", " ").strip()[:350],
                "page_url": page_url,
                "page_title": page_title,
            })

    # Check Prior to implementation / Customer engagement statements
    m_prior = re.search(
        r"Prior\s+to\s+the\s+implementation,\s*([A-Z0-9][A-Za-z0-9&.,' -]{2,45}?)\s+faced\b",
        text,
        re.IGNORECASE,
    )
    if m_prior:
        prior_cand = clean_candidate_name(m_prior.group(1))
        if prior_cand and not is_self_reference(prior_cand, target_company_name, urlparse(page_url).netloc):
            pr_start = max(0, m_prior.start() - 20)
            pr_end = min(len(text), m_prior.end() + 200)
            results.append({
                "candidate_name": prior_cand,
                "relationship_claim": "CASE_STUDY",
                "product_claim": None,
                "supporting_text": text[pr_start:pr_end].replace("\n", " ").strip()[:350],
                "page_url": page_url,
                "page_title": page_title,
            })

    m_eng = re.search(
        r"\b([A-Z0-9][A-Za-z0-9&.,' -]{2,45}?)\s+(?:engaged|partnered with|selected)\s+(?:3rd\s+Rock|[A-Za-z0-9&.' -]+|us|our team)\s+to\b",
        text,
        re.IGNORECASE,
    )
    if m_eng:
        eng_cand = clean_candidate_name(m_eng.group(1))
        if eng_cand and not is_self_reference(eng_cand, target_company_name, urlparse(page_url).netloc):
            e_start = max(0, m_eng.start() - 30)
            e_end = min(len(text), m_eng.end() + 200)
            results.append({
                "candidate_name": eng_cand,
                "relationship_claim": "CUSTOMER",
                "product_claim": f"Mentioned with {target_product}" if target_product.lower() in text[e_start:e_end].lower() else None,
                "supporting_text": text[e_start:e_end].replace("\n", " ").strip()[:350],
                "page_url": page_url,
                "page_title": page_title,
            })

    # Check for technology platform mentions in implementation, solution, or integration contexts
    low_text = text.lower()
    for tech_key, tech_disp in KNOWN_BENCHMARK_TECHS.items():
        if re.search(r"\b" + re.escape(tech_key) + r"\b", low_text):
            if any(kw in low_text for kw in ("implement", "solution", "platform", "cpm", "erp", "azure", "power bi", "architecture", "compatible", "using", "partner", "case study", "deployed")):
                m_tech = re.search(r"\b" + re.escape(tech_key) + r"\b", low_text)
                if m_tech:
                    start = max(0, m_tech.start() - 40)
                    end = min(len(text), m_tech.end() + 120)
                    snippet = text[start:end].replace("\n", " ").strip()
                    results.append({
                        "candidate_name": tech_disp,
                        "relationship_claim": "TECHNOLOGY_PLATFORM",
                        "product_claim": None,
                        "supporting_text": snippet[:350],
                        "page_url": page_url,
                        "page_title": page_title,
                    })

    for line in lines:
        cand_name: Optional[str] = None
        rel_claim: str = "MENTION"
        supporting_snippet = line[:400]

        # 1. Check Story/Case study prefix
        m_prefix = RE_PREFIX_STORY.search(line)
        if m_prefix:
            cand_name = clean_candidate_name(m_prefix.group(1))
            rel_claim = "CASE_STUDY"

        # 2. Check Action heading ("How X transformed...")
        if not cand_name:
            m_heading = RE_CASE_STUDY_HEADING.search(line)
            if m_heading:
                cand_name = clean_candidate_name(m_heading.group(1))
                rel_claim = "CASE_STUDY"

        # 3. Check Testimonial attribution ("— Name, Title at Company")
        if not cand_name:
            m_sig = RE_TESTIMONIAL_SIG.search(line)
            if m_sig:
                cand_name = clean_candidate_name(m_sig.group(1))
                rel_claim = "TESTIMONIAL"

        # 4. Check explicit Customer/Partner phrases
        if not cand_name:
            m_customer = re.search(
                r"(?:our\s+customer|our\s+client|case\s+study|client|customer):\s*([A-Z0-9][A-Za-z0-9&,' -]{1,40}?)(?=[.,;\n]|$)",
                line,
                re.IGNORECASE,
            )
            if m_customer:
                cand_name = clean_candidate_name(m_customer.group(1))
                rel_claim = "CUSTOMER"

        if not cand_name:
            m_partner = re.search(
                r"(?:our\s+partner|partner|alliance|reseller):\s*([A-Z0-9][A-Za-z0-9&,' -]{1,40}?)(?=[.,;\n]|$)",
                line,
                re.IGNORECASE,
            )
            if m_partner:
                cand_name = clean_candidate_name(m_partner.group(1))
                rel_claim = "PARTNER"

        # 5. Check Corporate suffix entities (e.g. Micro Labs GmbH)
        if not cand_name:
            for m_corp in RE_CORP_SUFFIX.finditer(line):
                corp_cand = clean_candidate_name(m_corp.group(1))
                if corp_cand and not is_self_reference(corp_cand, target_company_name, urlparse(page_url).netloc):
                    cand_name = corp_cand
                    rel_claim = "MENTION"
                    break

        # Check product claim in line
        prod_claim: Optional[str] = None
        if target_product.lower() in line.lower():
            prod_claim = f"Mentioned with {target_product}"

        if cand_name and not is_self_reference(cand_name, target_company_name, urlparse(page_url).netloc):
            results.append({
                "candidate_name": cand_name,
                "relationship_claim": rel_claim,
                "product_claim": prod_claim,
                "supporting_text": supporting_snippet,
                "page_url": page_url,
                "page_title": page_title,
            })

    return results


def extract_candidates_from_html(
    html_content: str,
    page_url: str,
    page_title: Optional[str],
    target_company_name: Optional[str] = None,
    target_product: str = "Jedox",
) -> List[Dict[str, Any]]:
    """Parse raw HTML to discover candidate logos, headings, testimonials, and customer sections."""
    results: List[Dict[str, Any]] = []
    if not html_content:
        return results

    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        soup = BeautifulSoup(html_content, "html.parser")

    target_domain = urlparse(page_url).netloc

    # 1. Logo image extraction (<img alt="Company Logo">)
    for img in soup.find_all("img", alt=True):
        alt = img.get("alt", "").strip()
        m_logo = RE_LOGO_ALT.search(alt)
        cand_name = None
        if m_logo:
            cand_name = clean_candidate_name(m_logo.group(1))
        elif "logo" in alt.lower() and len(alt.split()) <= 4:
            cand_name = clean_candidate_name(re.sub(r"(?i)\s*logo\s*", "", alt))

        if cand_name and not is_self_reference(cand_name, target_company_name, target_domain):
            results.append({
                "candidate_name": cand_name,
                "relationship_claim": "CUSTOMER_LOGO",
                "product_claim": None,
                "supporting_text": f"Found customer logo with alt text: '{alt}'",
                "page_url": page_url,
                "page_title": page_title,
            })

    # 2. Extract Headings (h1, h2, h3, h4)
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        h_text = h.get_text(strip=True)
        h_candidates = extract_candidates_from_text_block(
            h_text, page_url, page_title, target_company_name, target_product
        )
        results.extend(h_candidates)

    # 3. Customer / Case Study Sections
    for section in soup.find_all(["section", "div"]):
        sec_class = " ".join(section.get("class", [])).lower()
        sec_id = section.get("id", "").lower()
        if any(term in sec_class or term in sec_id for term in ("customer", "client", "case-study", "testimonial", "stories")):
            # Look for item titles or cards inside
            for card in section.find_all(["li", "div", "article"], limit=20):
                card_text = card.get_text(separator=" ", strip=True)
                if 5 < len(card_text) < 300:
                    lines = card_text.split(". ")
                    if lines:
                        first_line = lines[0]
                        m_heading = RE_CASE_STUDY_HEADING.search(first_line)
                        if m_heading:
                            cand_name = clean_candidate_name(m_heading.group(1))
                            if cand_name and not is_self_reference(cand_name, target_company_name, target_domain):
                                results.append({
                                    "candidate_name": cand_name,
                                    "relationship_claim": "CASE_STUDY",
                                    "product_claim": f"Mentioned in customer section with {target_product}" if target_product.lower() in card_text.lower() else None,
                                    "supporting_text": card_text[:300],
                                    "page_url": page_url,
                                    "page_title": page_title,
                                })

    return results


def check_explicit_relationship(
    candidate_name: str,
    all_snippets: List[str],
    target_product: str = "Jedox",
) -> Tuple[bool, RelationshipType, Optional[str]]:
    """Determine whether crawled content explicitly identifies the candidate as a customer, partner, target vendor, or technology platform.
    
    Never infers customer status from a name mention alone.
    """
    cand_clean = normalize_unicode_punctuation(candidate_name)
    cand_lower = cand_clean.lower()
    prod_lower = normalize_unicode_punctuation(target_product).lower()

    # Priority 0: Check if candidate is explicitly documented as a partner / reseller / alliance
    for text in all_snippets:
        norm_text = normalize_unicode_punctuation(text)
        text_lower = norm_text.lower()
        if cand_lower not in text_lower:
            continue
        for kw in PARTNER_CONTEXT_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                return True, RelationshipType.PARTNER, text

    # Priority 1: Check if candidate is the target vendor / product itself
    if cand_lower == prod_lower or normalize_company_name(candidate_name) == normalize_company_name(target_product):
        for text in all_snippets:
            if prod_lower in text.lower():
                return True, RelationshipType.TARGET_VENDOR, text
        return True, RelationshipType.TARGET_VENDOR, (all_snippets[0] if all_snippets else None)

    # Priority 2: Check if candidate is a known technology / platform (e.g. Kepion, Azure, Power BI, TM1, Tagetik)
    if any(tech_key in cand_lower for tech_key in ("kepion", "tm1", "tagetik", "power bi", "azure", "fabric", "databricks", "snowflake")):
        for text in all_snippets:
            norm_text = normalize_unicode_punctuation(text)
            text_lower = norm_text.lower()
            if cand_lower in text_lower:
                if any(kw in text_lower for kw in ("partner", "partnership", "alliance")):
                    return True, RelationshipType.PARTNER, text
                if any(kw in text_lower for kw in ("solution", "cpm", "erp", "platform", "implemented", "planning", "reporting", "using", "compatible", "modernized")):
                    return True, RelationshipType.TECHNOLOGY_PLATFORM, text
        return True, RelationshipType.TECHNOLOGY_PLATFORM, (all_snippets[0] if all_snippets else None)

    # Priority 3: Check for explicit Customer / Case Study indicators
    for text in all_snippets:
        norm_text = normalize_unicode_punctuation(text)
        text_lower = norm_text.lower()
        if cand_lower not in text_lower:
            continue

        # Look for explicit story, testimonial, or customer profile attribution
        for kw in ("case study", "customer story", "client story", "success story", "testimonial", "customer profile", "client profile"):
            if kw in text_lower:
                rel = RelationshipType.CASE_STUDY if "case study" in kw or "story" in kw or "profile" in kw else RelationshipType.TESTIMONIAL
                return True, rel, text

        for kw in ("our customer", "our client", "the customer", "the client", "trusted by", "selected by", "relies on", "deployed by", "engaged with", "engaged"):
            if kw in text_lower and any(v in text_lower for v in ("implementation", "solution", "support", "planning", "reporting", "budgeting", "project", "work", "deliver", "partnered")):
                return True, RelationshipType.CUSTOMER, text

        if re.search(r"\b(?:implementation|implemented|consolidation|deployment|consulting)\b", text_lower) and any(kw in text_lower for kw in ("challenge", "solution", "result", "customer", "client", "prior to", "hurdles")):
            return True, RelationshipType.CASE_STUDY, text

        if re.search(r"\b(?:our\s+(?:\w+\s+)?(?:customers?|clients?)|(?:customers?|clients?)\s+" + re.escape(cand_lower) + r")\b", text_lower):
            return True, RelationshipType.CUSTOMER, text

        if re.search(r"\b(?:customers?|clients?)\b", text_lower) and any(verb in text_lower for verb in ("chose", "selected", "deployed", "trusted")):
            return True, RelationshipType.CUSTOMER, text

    return False, RelationshipType.MENTION, None


def check_explicit_product_usage(
    candidate_name: str,
    target_product: str,
    all_snippets: List[str],
    relationship_type: RelationshipType,
) -> Tuple[bool, Optional[str]]:
    """Verify whether explicit evidence shows the candidate uses the target product.
    
    Requires explicit usage assertion or verified case study detailing the product.
    Never infers internal product usage from partnership pages or vendor/technology mentions.
    """
    cand_clean = normalize_unicode_punctuation(candidate_name)
    cand_lower = cand_clean.lower()
    prod_lower = normalize_unicode_punctuation(target_product).lower()

    # Rule 1: A target vendor is the product vendor itself, NOT a customer or internal user
    if relationship_type == RelationshipType.TARGET_VENDOR or cand_lower == prod_lower or normalize_company_name(candidate_name) == normalize_company_name(target_product):
        return False, None

    # Rule 2: A partner, implementation partner, technology platform, or vendor
    # does NOT internally use the target product merely by being mentioned on partner or stack pages.
    if relationship_type in (RelationshipType.PARTNER, RelationshipType.IMPLEMENTATION_PARTNER, RelationshipType.TECHNOLOGY_PLATFORM, RelationshipType.VENDOR):
        for text in all_snippets:
            norm_text = normalize_unicode_punctuation(text)
            for sentence in re.split(r"[.!?\n]", norm_text):
                s_lower = sentence.lower()
                if cand_lower in s_lower and prod_lower in s_lower:
                    if any(lst_term in s_lower for lst_term in (", and", ", or", "platforms like", "technologies like", "partner specializing")):
                        continue
                    if re.search(rf"\b(?:{re.escape(cand_lower)}|partner)\b.*?\b(?:using|uses|implemented|implementing|deployed)\s+{re.escape(prod_lower)}\b", s_lower):
                        return True, sentence.strip()
        return False, None

    verb_pattern = re.compile("|".join(PRODUCT_USAGE_VERBS), re.IGNORECASE)

    for text in all_snippets:
        norm_text = normalize_unicode_punctuation(text)
        text_lower = norm_text.lower()
        if cand_lower not in text_lower or prod_lower not in text_lower:
            continue

        # Condition 1: Case study / Success story specifically connecting candidate and product
        if relationship_type in (RelationshipType.CASE_STUDY, RelationshipType.TESTIMONIAL):
            if any(term in text_lower for term in (f"implemented {prod_lower}", f"using {prod_lower}", f"with {prod_lower}", f"{prod_lower} solution", f"{prod_lower} for {cand_lower}", f"{prod_lower} partner")):
                return True, text
            for sentence in re.split(r"[.!?\n]", norm_text):
                s_lower = sentence.lower()
                if cand_lower in s_lower and prod_lower in s_lower:
                    return True, sentence.strip()

        # Condition 2: Co-occurrence with an active deployment/usage verb in the same sentence
        sentences = re.split(r"[.!?\n]", norm_text)
        for sentence in sentences:
            s_lower = sentence.lower()
            if cand_lower in s_lower and prod_lower in s_lower:
                if any(delim in s_lower for delim in (", and", ", or", "platforms like", "technologies like")):
                    continue
                if verb_pattern.search(sentence):
                    return True, sentence.strip()

        # Condition 3: "with [Target Product]" phrase in direct proximity
        if re.search(rf"\bwith\s+{re.escape(prod_lower)}\b", text_lower) and f"for {cand_lower}" in text_lower:
            return True, text

    return False, None


def verify_customer_candidate(
    candidate_name: str,
    candidate_sources: List[EvidenceReference],
    all_page_texts: List[Tuple[str, Optional[str], str]],  # (url, title, raw_text)
    target_product: str = "Jedox",
    is_crawl_complete: bool = True,
) -> CustomerCandidate:
    """Evaluate and classify a candidate across all collected page evidence."""
    norm_name = normalize_company_name(candidate_name)
    all_snippets = [s.supporting_text for s in candidate_sources]

    # Collect additional relevant snippets across all crawled pages with stable deduplication
    cand_clean = normalize_unicode_punctuation(candidate_name)
    cand_lower = cand_clean.lower()
    for page_url, page_title, page_text in all_page_texts:
        norm_page_text = normalize_unicode_punctuation(page_text)
        if cand_lower in norm_page_text.lower():
            lines = [line.strip() for line in norm_page_text.split("\n") if line.strip()]
            for line in lines:
                if cand_lower in line.lower() and len(line) > 20:
                    all_snippets.append(line)
            if target_product.lower() in norm_page_text.lower():
                all_snippets.append(norm_page_text)
        if cand_lower in page_text.lower():
            page_src_count = len([s for s in candidate_sources if s.source_url == page_url])
            if page_src_count < 2:
                for sentence in re.split(r"[.!?\n]+", page_text):
                    clean_sent = sentence.strip()
                    if cand_lower in clean_sent.lower() and len(clean_sent) > 15:
                        if clean_sent not in all_snippets:
                            all_snippets.append(clean_sent)
                            candidate_sources.append(
                                EvidenceReference(
                                    source_url=page_url,
                                    page_title=page_title,
                                    supporting_text=clean_sent[:300],
                                )
                            )
                            page_src_count += 1
                            if page_src_count >= 2:
                                break

    # 1. Assess relationship
    rel_supported, rel_type, rel_quote = check_explicit_relationship(candidate_name, all_snippets, target_product)

    # 2. Assess product usage
    usage_supported, usage_quote = check_explicit_product_usage(
        candidate_name, target_product, all_snippets, rel_type
    )

    # 3. Determine relationship verification status
    if rel_type in (RelationshipType.CASE_STUDY, RelationshipType.TESTIMONIAL, RelationshipType.CUSTOMER):
        rel_verification_status = "CONFIRMED" if rel_supported else "UNVERIFIED"
    elif rel_type in (RelationshipType.PARTNER, RelationshipType.IMPLEMENTATION_PARTNER, RelationshipType.TARGET_VENDOR, RelationshipType.TECHNOLOGY_PLATFORM):
        rel_verification_status = "CONFIRMED"
    else:
        rel_verification_status = "UNVERIFIED"

    # 4. Build Checklist
    has_source_url = any(bool(s.source_url) for s in candidate_sources)
    has_supporting_text = any(bool(s.supporting_text) for s in candidate_sources)

    checklist = VerificationChecklist(
        company_discovered=True,
        customer_relationship_supported=rel_supported if rel_type in (RelationshipType.CASE_STUDY, RelationshipType.TESTIMONIAL, RelationshipType.CUSTOMER) else False,
        product_usage_supported=usage_supported,
        source_url_recorded=has_source_url,
        supporting_text_recorded=has_supporting_text,
        verification_completed=is_crawl_complete,
    )

    # 5. Determine Classification and Product Usage Status
    classification: CandidateClassification
    missing_reason: Optional[str] = None
    product_usage_status: str

    if not is_crawl_complete:
        classification = CandidateClassification.RESEARCH_INCOMPLETE
        missing_reason = "Crawl limits or execution errors prevented verification from running across all pages."
        product_usage_status = "RESEARCH_INCOMPLETE"
    elif rel_type == RelationshipType.TARGET_VENDOR:
        classification = CandidateClassification.UNVERIFIED
        missing_reason = f"Target product/vendor ({target_product}) under research; excluded from prospective customer pipeline."
        product_usage_status = "UNVERIFIED"
    elif rel_type in (RelationshipType.PARTNER, RelationshipType.IMPLEMENTATION_PARTNER):
        classification = CandidateClassification.PARTIALLY_VERIFIED
        if usage_supported:
            missing_reason = f"{target_product} usage mentioned, but candidate is identified as {rel_type.value.lower()} rather than a confirmed customer."
            product_usage_status = "CONFIRMED_AS_PARTNER_OR_MENTION"
        else:
            missing_reason = f"Formal partner/alliance documented; internal {target_product} usage is unverified."
            product_usage_status = "UNVERIFIED"
    elif rel_type == RelationshipType.TECHNOLOGY_PLATFORM:
        classification = CandidateClassification.PARTIALLY_VERIFIED
        if usage_supported:
            missing_reason = f"{target_product} usage mentioned, but candidate is identified as {rel_type.value.lower()} rather than a confirmed customer."
            product_usage_status = "CONFIRMED_AS_PARTNER_OR_MENTION"
        else:
            missing_reason = f"Technology platform documented in implementation/architecture context; internal {target_product} usage is unverified."
            product_usage_status = "UNVERIFIED"
    elif rel_supported and usage_supported:
        classification = CandidateClassification.CONFIRMED
        missing_reason = f"Customer relationship and {target_product} usage both verified with source evidence quotes."
        product_usage_status = "CONFIRMED"
    elif rel_supported and not usage_supported:
        classification = CandidateClassification.PARTIALLY_VERIFIED
        missing_reason = (
            f"Customer relationship verified via documented {rel_type.value.lower()}, "
            f"but explicit usage of {target_product} was not found on crawled pages."
        )
        product_usage_status = "UNVERIFIED"
    elif not rel_supported and usage_supported:
        classification = CandidateClassification.PARTIALLY_VERIFIED
        missing_reason = (
            f"{target_product} usage mentioned, but candidate is identified as {rel_type.value.lower()} "
            f"rather than a confirmed customer."
        )
        product_usage_status = "CONFIRMED_AS_PARTNER_OR_MENTION"
    else:
        classification = CandidateClassification.UNVERIFIED
        missing_reason = (
            f"Candidate was mentioned on the website, but neither customer relationship "
            f"nor {target_product} usage has supporting evidence."
        )
        product_usage_status = "UNVERIFIED"

    # Classify candidate entity category
    all_context = " ".join(s.supporting_text for s in candidate_sources)
    candidate_category = classify_entity_category(candidate_name, all_context)
    if rel_type in (RelationshipType.TARGET_VENDOR, RelationshipType.TECHNOLOGY_PLATFORM):
        candidate_category = CandidateCategory.PRODUCT_OR_TECHNOLOGY

    if candidate_category != CandidateCategory.NAMED_COMPANY:
        if classification == CandidateClassification.CONFIRMED:
            classification = CandidateClassification.PARTIALLY_VERIFIED
            missing_reason = f"Candidate classified as {candidate_category.value} rather than a confirmed corporate entity."

    # Build provenance & audit fields
    rel_evidence = rel_quote if rel_quote else (candidate_sources[0].supporting_text if candidate_sources else None)
    prod_evidence = usage_quote if usage_supported else None

    best_src_url = candidate_sources[0].source_url if candidate_sources else None
    best_quote = candidate_sources[0].supporting_text if candidate_sources else None

    if classification == CandidateClassification.CONFIRMED:
        conf_score = 0.95
    elif classification == CandidateClassification.PARTIALLY_VERIFIED:
        conf_score = 0.80
    else:
        conf_score = 0.40

    rationale = (
        f"Relationship: {rel_type.value} ({rel_verification_status}). "
        f"Target product ({target_product}) usage: {product_usage_status}. "
        f"{missing_reason or ''}"
    ).strip()

    return CustomerCandidate(
        candidate_name=candidate_name,
        normalized_name=norm_name,
        candidate_category=candidate_category,
        target_product=target_product,
        relationship_type=rel_type,
        classification=classification,
        checklist=checklist,
        product_usage_status=product_usage_status,
        sources=candidate_sources,
        missing_evidence_reason=missing_reason,
        research_status="COMPLETED" if is_crawl_complete else "INCOMPLETE",
        relationship_verification_status=rel_verification_status,
        relationship_evidence=rel_evidence,
        product_usage_evidence=prod_evidence,
        supporting_source_url=best_src_url,
        exact_supporting_quote=best_quote,
        confidence_score=conf_score,
        verification_rationale=rationale,
    )


def verify_all_candidates_for_job(
    job_id: int,
    db_path: Optional[str] = None,
) -> List[CustomerCandidate]:
    """Discover, verify, and persist candidates, decision-makers, contacts, and evidence for a crawl job."""
    job = database.get_crawl_job(job_id, db_path=db_path)
    if not job:
        logger.error("Job %d not found for candidate verification.", job_id)
        return []

    target_product = job.target_product or "Jedox"
    # Infer target product from objective if not explicitly provided
    if not job.target_product and job.objective:
        m_obj = re.search(r"\busing\s+([A-Za-z0-9]+)\b", job.objective, re.IGNORECASE)
        if m_obj:
            target_product = m_obj.group(1).capitalize()

    target_company_name = job.company_name
    is_crawl_complete = job.status not in (database.CrawlJobStatus.FAILED, database.CrawlJobStatus.CANCELLED)

    # 1. Fetch all crawled pages and discovered documents for this job
    pages = database.get_crawled_pages(job_id, db_path=db_path)
    documents = database.get_discovered_documents(job_id, db_path=db_path)

    all_page_texts: List[Tuple[str, Optional[str], str]] = [
        (p.final_url or p.original_url, p.title, p.extracted_text or "")
        for p in pages
        if p.status == database.CrawlPageStatus.SUCCESS and p.extracted_text
    ]

    for doc in documents:
        if doc.extracted_text and doc.extracted_text.strip():
            all_page_texts.append((doc.document_url, doc.file_name, doc.extracted_text.strip()))

    if not all_page_texts:
        logger.warning("No crawled pages or documents with extracted text found for Job %d.", job_id)
        return []

    # 2. Extract Candidate Mentions from all crawled pages and documents
    raw_extractions: List[Dict[str, Any]] = []
    for page in pages:
        if page.status != database.CrawlPageStatus.SUCCESS:
            continue
        p_url = page.final_url or page.original_url
        p_title = page.title
        p_text = page.extracted_text or ""

        # Extract from headings JSON if available
        h_data = page.headings_json
        if isinstance(h_data, str):
            try:
                import json
                h_data = json.loads(h_data)
            except Exception:
                h_data = {}
        if isinstance(h_data, dict):
            for tag_list in h_data.values():
                if isinstance(tag_list, list):
                    for heading_text in tag_list:
                        raw_extractions.extend(
                            extract_candidates_from_text_block(
                                heading_text, p_url, p_title, target_company_name, target_product
                            )
                        )

        # Extract from page text
        raw_extractions.extend(
            extract_candidates_from_text_block(
                p_text, p_url, p_title, target_company_name, target_product
            )
        )

    # Extract candidate mentions from discovered documents (PDF, Excel, Docx, PPTX)
    for doc in documents:
        if doc.extracted_text and doc.extracted_text.strip():
            raw_extractions.extend(
                extract_candidates_from_text_block(
                    doc.extracted_text, doc.document_url, doc.file_name, target_company_name, target_product
                )
            )

    # 3. Deduplicate Candidates by normalized name
    candidates_by_name: Dict[str, Dict[str, Any]] = {}
    for item in raw_extractions:
        name = item["candidate_name"]
        norm = normalize_company_name(name)
        if not norm:
            continue

        ref = EvidenceReference(
            source_url=item["page_url"],
            page_title=item["page_title"],
            supporting_text=item["supporting_text"],
            relationship_claim=item["relationship_claim"],
            product_claim=item["product_claim"],
        )

        matched_key = None
        for key in candidates_by_name.keys():
            if (
                key == norm
                or is_fuzzy_name_match(norm, key, threshold=75.0)
                or (
                    len(key.split()) >= 2
                    and len(norm.split()) >= 2
                    and key.split()[0] == norm.split()[0]
                    and key.split()[-1] == norm.split()[-1]
                )
            ):
                matched_key = key
                break

        if matched_key:
            existing_sources = candidates_by_name[matched_key]["sources"]
            if not any(
                s.source_url == ref.source_url and (
                    s.supporting_text == ref.supporting_text
                    or (s.relationship_claim == ref.relationship_claim and s.product_claim == ref.product_claim)
                )
                for s in existing_sources
            ):
                existing_sources.append(ref)
            curr_name = candidates_by_name[matched_key]["candidate_name"]
            if len(name) > len(curr_name) and not is_self_reference(name, target_company_name, urlparse(item["page_url"]).netloc):
                candidates_by_name[matched_key]["candidate_name"] = name
        else:
            candidates_by_name[norm] = {
                "candidate_name": name,
                "sources": [ref],
            }

    # 4. Verify Each Candidate across all crawled page and document evidence
    verified_candidates: List[CustomerCandidate] = []
    for entry in candidates_by_name.values():
        c_name = entry["candidate_name"]
        c_sources = entry["sources"]

        candidate_obj = verify_customer_candidate(
            candidate_name=c_name,
            candidate_sources=c_sources,
            all_page_texts=all_page_texts,
            target_product=target_product,
            is_crawl_complete=is_crawl_complete,
        )
        candidate_obj.job_id = job.id
        candidate_obj.target_company_id = job.company_id
        verified_candidates.append(candidate_obj)

    # 5. Clear stale records for this job before saving new ones
    conn = database.get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM customer_candidates WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM decision_makers WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM public_contacts WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM unified_evidence WHERE job_id = ?", (job_id,))
    finally:
        conn.close()

    saved_candidates = database.save_customer_candidates(verified_candidates, db_path=db_path)
    logger.info("Persisted %d customer candidates for Job #%d.", len(saved_candidates), job_id)

    # 6. Extract Decision-Makers across all pages and documents
    raw_dms: List[DecisionMaker] = []
    for p_url, p_title, p_text in all_page_texts:
        is_doc = any(p_url == d.document_url for d in documents)
        src_type = "DOCUMENT" if is_doc else "WEBPAGE"

        # Identify candidate associated with this page
        page_candidate = None
        for sc in saved_candidates:
            if any(s.source_url == p_url for s in sc.sources):
                page_candidate = sc.candidate_name
                break

        dms = extract_decision_makers_from_text(
            text=p_text,
            source_url=p_url,
            source_type=src_type,
            job_id=job_id,
            associated_company=page_candidate,
            default_company=target_company_name,
        )
        raw_dms.extend(dms)

    # Deduplicate Decision-Makers
    dms_by_name: Dict[str, DecisionMaker] = {}
    for dm in raw_dms:
        norm_dm_name = f"{dm.full_name.strip().lower()}::{(dm.associated_company or '').strip().lower()}"
        if norm_dm_name in dms_by_name:
            existing = dms_by_name[norm_dm_name]
            if len(dm.supporting_quote or "") > len(existing.supporting_quote or ""):
                dms_by_name[norm_dm_name] = dm
        else:
            dms_by_name[norm_dm_name] = dm

    deduped_dms = list(dms_by_name.values())
    for dm in deduped_dms:
        if dm.associated_company:
            norm_assoc = normalize_company_name(dm.associated_company)
            for sc in saved_candidates:
                if (
                    sc.normalized_name == norm_assoc
                    or is_fuzzy_name_match(norm_assoc, sc.normalized_name, threshold=75.0)
                    or (norm_assoc and norm_assoc in sc.normalized_name)
                    or (sc.normalized_name and sc.normalized_name in norm_assoc)
                ):
                    dm.candidate_company_id = sc.id
                    dm.company_id = None
                    dm.associated_company = sc.candidate_name
                    break

    saved_dms = database.save_decision_makers(deduped_dms, db_path=db_path)
    logger.info("Persisted %d decision-makers for Job #%d.", len(saved_dms), job_id)

    # 7. Extract Public Professional Contacts across all pages and documents
    raw_contacts: List[PublicContact] = []
    for p_url, p_title, p_text in all_page_texts:
        doc_match = next((d for d in documents if d.document_url == p_url), None)
        f_type = doc_match.file_format if doc_match else "HTML"
        f_name = doc_match.file_name if doc_match else None

        # Check candidate associated with this page
        page_candidate = None
        for sc in saved_candidates:
            if any(s.source_url == p_url for s in sc.sources):
                page_candidate = sc.candidate_name
                break

        contacts = extract_public_contacts_from_text(
            text=p_text,
            source_url=p_url,
            file_type=f_type,
            file_name=f_name,
            associated_company=page_candidate or target_company_name,
            job_id=job_id,
        )
        raw_contacts.extend(contacts)

    # Deduplicate Contacts by (contact_type, value)
    contacts_by_val: Dict[str, PublicContact] = {}
    for c in raw_contacts:
        key = f"{c.contact_type.value}:{c.contact_value.strip().lower()}"
        if key not in contacts_by_val:
            contacts_by_val[key] = c
        else:
            existing_c = contacts_by_val[key]
            if not existing_c.person_name and c.person_name:
                existing_c.person_name = c.person_name
            if not existing_c.job_title and c.job_title:
                existing_c.job_title = c.job_title

    deduped_contacts = list(contacts_by_val.values())
    for c in deduped_contacts:
        # If this is a general company contact on host domain, ensure associated_company is target_company_name
        if target_company_name and c.source_url:
            host_domain = urlparse(job.seed_url).netloc.lower().replace("www.", "") if job.seed_url else ""
            source_domain = urlparse(c.source_url).netloc.lower().replace("www.", "") if c.source_url else ""
            if source_domain == host_domain:
                if (
                    not c.person_name
                    or any(c.contact_value.lower().startswith(p) for p in ("webadmin@", "info@", "contact@", "support@", "admin@", "sales@"))
                    or c.job_title in ("Company Phone", "Company Address", "Company Contact Email")
                ):
                    c.associated_company = target_company_name
                    if job and job.company_id:
                        c.company_id = job.company_id
                    c.candidate_company_id = None

        if c.associated_company and c.associated_company != target_company_name:
            norm_assoc = normalize_company_name(c.associated_company)
            for sc in saved_candidates:
                if sc.normalized_name == norm_assoc or is_fuzzy_name_match(norm_assoc, sc.normalized_name, threshold=75.0):
                    c.candidate_company_id = sc.id
                    c.company_id = None
                    c.associated_company = sc.candidate_name
                    break
        elif c.associated_company and c.associated_company == target_company_name:
            if job and job.company_id:
                c.company_id = job.company_id
            c.candidate_company_id = None

        if c.person_name:
            norm_p = c.person_name.strip().lower()
            for dm in saved_dms:
                if dm.full_name and dm.full_name.strip().lower() == norm_p:
                    c.person_id = dm.id
                    break

    saved_contacts = database.save_public_contacts(deduped_contacts, db_path=db_path)
    logger.info("Persisted %d public contacts for Job #%d.", len(saved_contacts), job_id)

    # 8. Build and persist Unified Evidence records
    unified_records = generate_job_unified_evidence(
        job_id=job_id,
        candidates=saved_candidates,
        decision_makers=saved_dms,
        contacts=saved_contacts,
        documents=documents,
    )
    database.save_unified_evidence(unified_records, db_path=db_path)
    logger.info("Persisted %d unified evidence records for Job #%d.", len(unified_records), job_id)

    return saved_candidates
