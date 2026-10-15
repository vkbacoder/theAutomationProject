"""Deduplication and entity matching utilities for corporate leads.

Prevents duplicate lead records using domain normalization, corporate suffix
stripping, and RapidFuzz token matching.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse
from rapidfuzz import fuzz

# Common corporate legal entity suffixes to strip for normalized matching
CORPORATE_SUFFIXES = [
    r"\bpvt\.?\s*ltd\.?\b",
    r"\bprivate\s+limited\b",
    r"\bltd\.?\b",
    r"\blimited\b",
    r"\binc\.?\b",
    r"\bincorporated\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\bllc\b",
    r"\bllp\b",
    r"\bgmbh\b",
    r"\bplc\b",
    r"\bs\.?a\.?\b",
    r"\bco\.?\b",
    r"\bcompany\b",
    r"\bgroup\b",
    r"\bholdings?\b",
    r"\bsolutions?\b",
    r"\btechnologies\b",
    r"\btech\b",
]

SUFFIX_REGEX = re.compile(r"|".join(CORPORATE_SUFFIXES), flags=re.IGNORECASE)


def normalize_domain(url_or_domain: str) -> str:
    """Extract a canonical normalized domain from a URL or raw domain string.
    
    Examples:
        'https://WWW.Acme-Corp.COM/about?ref=1' -> 'acme-corp.com'
        'http://sub.domain.co.uk/' -> 'sub.domain.co.uk'
    """
    if not url_or_domain:
        return ""

    raw = url_or_domain.strip().lower()
    if "://" not in raw:
        raw = "http://" + raw

    try:
        parsed = urlparse(raw)
        hostname = parsed.hostname or ""
    except Exception:
        hostname = raw

    # Strip leading www.
    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname.strip().lower()


def normalize_company_name(name: str) -> str:
    """Normalize a company name for deduplication.
    
    Strips punctuation, legal suffixes, and collapses whitespace.
    Example:
        'Acme Industrial Solutions, Inc.' -> 'acme industrial'
    """
    if not name:
        return ""

    # Lowercase
    cleaned = name.lower().strip()

    # Strip legal entity suffixes
    cleaned = SUFFIX_REGEX.sub(" ", cleaned)

    # Remove non-alphanumeric characters (keep spaces)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)

    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def is_fuzzy_name_match(name1: str, name2: str, threshold: float = 85.0) -> bool:
    """Check if two company names are fuzzy matches using RapidFuzz."""
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)

    if not norm1 or not norm2:
        return False

    if norm1 == norm2:
        return True

    # Token sort ratio accounts for word order differences
    score = fuzz.token_sort_ratio(norm1, norm2)
    return score >= threshold


def infer_company_name_from_title(title: Optional[str], domain: str) -> str:
    """Infer a clean company name from the webpage title or domain."""
    if title:
        # Split by typical title delimiters: |, -, —, •, :, »
        chunks = re.split(r"[\|\-—•:»]", title)
        for chunk in chunks:
            chunk = chunk.strip()
            # Skip generic web phrases
            if not chunk or re.match(r"^(home(\s+page)?|welcome(\s+to.*)?|about(\s+us)?|official\s+site|index)$", chunk, re.I):
                continue
            if len(chunk) >= 2 and len(chunk) <= 60:
                return chunk

    # Fallback to domain name (e.g. 'acme-industrial.com' -> 'Acme Industrial')
    if domain:
        base = domain.split(".")[0]
        cleaned_domain = re.sub(r"[-_]", " ", base).title()
        if len(cleaned_domain) >= 2:
            return cleaned_domain

    return "Unnamed Organization"
