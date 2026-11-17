"""Source Classification and Authority Engine.

Classifies discovery sources into 7 distinct authority tiers:
1. OFFICIAL_VENDOR: Official product/vendor websites (e.g. jedox.com, recov.com).
2. OFFICIAL_COMPANY: Official target company domain (e.g. ntaw.com.au).
3. GOVERNMENT_REGULATORY: Government and statutory authorities (e.g. oaic.gov.au, asic.gov.au).
4. PRESS_RELEASE: Established corporate PR distribution wires (e.g. prnewswire.com, businesswire.com).
5. PROFESSIONAL_PROFILE: Professional platforms & corporate registries (e.g. linkedin.com, bloomberg.com).
6. NEWS_PUBLICATION: Established news and industry reporting (e.g. reuters.com, afr.com).
7. THIRD_PARTY: All other external blogs, forums, and unverified websites.

Enforces source authority during relationship and product usage verification.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Optional, Set
from urllib.parse import urlparse

from dedup import normalize_domain


class SourceCategory(str, Enum):
    """Classification tiers for research source domains."""
    OFFICIAL_VENDOR = "OFFICIAL_VENDOR"
    OFFICIAL_COMPANY = "OFFICIAL_COMPANY"
    GOVERNMENT_REGULATORY = "GOVERNMENT_REGULATORY"
    PRESS_RELEASE = "PRESS_RELEASE"
    PROFESSIONAL_PROFILE = "PROFESSIONAL_PROFILE"
    NEWS_PUBLICATION = "NEWS_PUBLICATION"
    THIRD_PARTY = "THIRD_PARTY"


# Known vendor domains for active products
KNOWN_VENDOR_DOMAINS: Set[str] = {
    "jedox.com", "jedox.de", "recov.com", "recov.co", "recov.in",
    "microsoft.com", "sap.com", "oracle.com", "salesforce.com",
    "anaplan.com", "onestream.com", "tagetik.com",
}

# Known regulatory & government domains
GOVERNMENT_REGULATORY_DOMAINS: Set[str] = {
    "oaic.gov.au", "asic.gov.au", "asx.com.au", "sec.gov", "ato.gov.au",
    "accc.gov.au", "justice.gov", "companieshouse.gov.uk",
}

# Major press release distribution wires
PRESS_RELEASE_DOMAINS: Set[str] = {
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "marketwatch.com", "accesswire.com", "prweb.com",
}

# Professional profile & executive registry domains
PROFESSIONAL_PROFILE_DOMAINS: Set[str] = {
    "linkedin.com", "bloomberg.com", "crunchbase.com", "zoominfo.com",
    "pitchbook.com",
}

# Established financial and business news outlets
NEWS_DOMAINS: Set[str] = {
    "reuters.com", "bloomberg.com", "afr.com", "smh.com.au",
    "theaustralian.com.au", "forbes.com", "wsj.com", "ft.com",
    "itnews.com.au", "crn.com.au", "businessnewsaustralia.com",
}


def classify_source(
    url: str,
    target_company_domain: Optional[str] = None,
    target_product: Optional[str] = None,
) -> SourceCategory:
    """Classify the source URL into an authority category."""
    if not url:
        return SourceCategory.THIRD_PARTY

    domain = normalize_domain(url)
    if not domain:
        return SourceCategory.THIRD_PARTY

    # 1. Target company's official domain
    if target_company_domain:
        norm_target = normalize_domain(target_company_domain)
        if norm_target and (domain == norm_target or domain.endswith("." + norm_target)):
            return SourceCategory.OFFICIAL_COMPANY

    # 2. Official product / vendor website
    t_prod = (target_product or "").strip().lower()
    if t_prod:
        # e.g. jedox -> jedox.com
        if domain == f"{t_prod}.com" or domain.endswith(f".{t_prod}.com"):
            return SourceCategory.OFFICIAL_VENDOR
        if t_prod in KNOWN_VENDOR_DOMAINS and any(domain == vd or domain.endswith("." + vd) for vd in KNOWN_VENDOR_DOMAINS):
            return SourceCategory.OFFICIAL_VENDOR
    if any(domain == vd or domain.endswith("." + vd) for vd in KNOWN_VENDOR_DOMAINS):
        return SourceCategory.OFFICIAL_VENDOR

    # 3. Government and regulatory authority
    if (
        domain in GOVERNMENT_REGULATORY_DOMAINS
        or any(domain.endswith("." + grd) for grd in GOVERNMENT_REGULATORY_DOMAINS)
        or domain.endswith(".gov")
        or domain.endswith(".gov.au")
        or domain.endswith(".govt.nz")
        or domain.endswith(".parliament.uk")
    ):
        return SourceCategory.GOVERNMENT_REGULATORY

    # 4. Press release wire
    if any(domain == prd or domain.endswith("." + prd) for prd in PRESS_RELEASE_DOMAINS):
        return SourceCategory.PRESS_RELEASE

    # 5. Professional profiles
    if any(domain == ppd or domain.endswith("." + ppd) for ppd in PROFESSIONAL_PROFILE_DOMAINS):
        return SourceCategory.PROFESSIONAL_PROFILE

    # 6. Established news publication
    if any(domain == nd or domain.endswith("." + nd) for nd in NEWS_DOMAINS):
        return SourceCategory.NEWS_PUBLICATION

    # 7. Other third party
    return SourceCategory.THIRD_PARTY


def get_source_authority_weight(category: SourceCategory) -> float:
    """Return an authority multiplier between 0.0 and 1.0 for evidence verification."""
    weights = {
        SourceCategory.OFFICIAL_VENDOR: 1.0,         # Definitive customer case studies
        SourceCategory.OFFICIAL_COMPANY: 0.95,       # Self-disclosed annual reports / releases
        SourceCategory.GOVERNMENT_REGULATORY: 0.95,  # Statutory filings
        SourceCategory.PRESS_RELEASE: 0.85,          # Formal corporate announcements
        SourceCategory.NEWS_PUBLICATION: 0.80,       # Journalistic reporting
        SourceCategory.PROFESSIONAL_PROFILE: 0.75,   # Executive self-published positions
        SourceCategory.THIRD_PARTY: 0.40,            # General blogs, forums, resale directories
    }
    return weights.get(category, 0.40)


def get_source_authority_score(category: SourceCategory) -> float:
    """Return an authority score between 0.0 and 100.0 for priority scoring."""
    return round(get_source_authority_weight(category) * 100.0, 1)
