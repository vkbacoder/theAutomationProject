"""Web scraping and extraction engine for the Lead Research System.

Includes robust SSRF protections, DNS validation, size limits,
BeautifulSoup4 HTML parsing, and Trafilatura main content extraction.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, Field, HttpUrl
import trafilatura

# Safety and performance limits
DEFAULT_TIMEOUT_SEC = 15.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 LeadResearchBot/1.0"
)


class ScrapeRequest(BaseModel):
    """Incoming request model for web scraping."""
    url: str = Field(..., description="Target website URL to scrape (HTTP/HTTPS only)")


class LinkItem(BaseModel):
    """Structured representation of an extracted link."""
    text: str
    url: str


class HeadingsGroup(BaseModel):
    """Structured representation of page headings."""
    h1: List[str] = Field(default_factory=list)
    h2: List[str] = Field(default_factory=list)
    h3: List[str] = Field(default_factory=list)


class ScrapeResponse(BaseModel):
    """Structured result returned by the scraper endpoint."""
    success: bool
    url: str
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    canonical_url: Optional[str] = None
    headings: HeadingsGroup = Field(default_factory=HeadingsGroup)
    links: List[LinkItem] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    text: str = ""
    word_count: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None


class SecurityException(Exception):
    """Raised when a request violates security or SSRF policies."""
    pass


class ExtractionException(Exception):
    """Raised when fetching or parsing fails."""
    pass


def is_ip_allowed(ip_str: str) -> bool:
    """Check if an IP address is a safe public IP (not loopback, private, link-local, etc.)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
        # Specific check for AWS/Cloud metadata (169.254.169.254 is covered by is_link_local)
        if ip_str.startswith("169.254."):
            return False
        return True
    except ValueError:
        return False


def validate_url_security(target_url: str) -> Tuple[str, str, int]:
    """Validate that the URL scheme is permitted and its hostname resolves only to safe public IPs.
    
    Returns (normalized_url, hostname, port).
    Raises SecurityException if the URL or resolved IP is forbidden.
    """
    if not target_url or not isinstance(target_url, str):
        raise SecurityException("URL must be a non-empty string.")

    target_url = target_url.strip()
    parsed = urlparse(target_url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityException(
            f"Invalid scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SecurityException("URL does not contain a valid hostname.")

    # Reject obvious local hostnames
    lowered_host = hostname.lower().strip()
    if (
        lowered_host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        or lowered_host.endswith(".local")
        or lowered_host.endswith(".internal")
        or lowered_host.endswith(".localhost")
    ):
        raise SecurityException(f"Access to local destination '{hostname}' is blocked.")

    # Determine default port
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    # Resolve hostname via DNS and check all returned IPs
    try:
        addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SecurityException(f"DNS Resolution Error: Could not resolve '{hostname}': {e}")
    except Exception as e:
        raise SecurityException(f"DNS lookup failed for '{hostname}': {e}")

    if not addr_info:
        raise SecurityException(f"No IP addresses found for hostname '{hostname}'.")

    for item in addr_info:
        sockaddr = item[4]
        ip_addr = sockaddr[0]
        if not is_ip_allowed(ip_addr):
            raise SecurityException(
                f"Security Block: Destination '{hostname}' resolves to private/restricted IP ({ip_addr}). "
                "SSRF protection prevents accessing internal or cloud metadata networks."
            )

    return target_url, hostname, port


def safe_fetch(
    target_url: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    user_agent: str = DEFAULT_USER_AGENT,
    client: Optional[httpx.Client] = None,
) -> Tuple[str, int, str, str]:
    """Fetch URL with SSRF checks on every redirect, response size limits, and content-type validation.
    
    Returns (final_url, status_code, content_type, html_content).
    """
    current_url, _, _ = validate_url_security(target_url)
    redirect_count = 0
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }

    own_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_sec, connect=timeout_sec),
        verify=True,
    )

    try:
        while True:
            # Re-validate security for every hop (including redirects)
            validate_url_security(current_url)

            try:
                response = http_client.get(current_url, headers=headers)
            except httpx.TimeoutException:
                raise ExtractionException(f"Request timed out after {timeout_sec}s connecting to {current_url}")
            except httpx.ConnectError as e:
                raise ExtractionException(f"Connection error reaching {current_url}: {e}")
            except httpx.RequestError as e:
                raise ExtractionException(f"HTTP request failed: {e}")

            # Check redirect status codes (301, 302, 303, 307, 308)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location") or response.headers.get("location")
                if not location:
                    raise ExtractionException("Redirect response missing Location header.")

                redirect_count += 1
                if redirect_count > max_redirects:
                    raise ExtractionException(f"Exceeded maximum redirect limit of {max_redirects}.")

                # Resolve relative redirect URLs against current URL
                current_url = urljoin(current_url, location)
                continue

            # Non-redirect final response reached
            final_url = str(response.url)
            status_code = response.status_code
            content_type_header = response.headers.get("content-type", "").lower()
            main_content_type = content_type_header.split(";")[0].strip()

            # Enforce content-type check
            if main_content_type and not any(
                allowed in main_content_type for allowed in ALLOWED_CONTENT_TYPES
            ):
                raise ExtractionException(
                    f"Unsupported content type '{main_content_type}'. "
                    f"Only HTML or text resources ({', '.join(ALLOWED_CONTENT_TYPES)}) can be scraped."
                )

            # Check response size limit
            content_bytes = response.content
            if len(content_bytes) > max_bytes:
                raise ExtractionException(
                    f"Response size ({len(content_bytes)} bytes) exceeds the maximum allowed limit of {max_bytes} bytes (5 MB)."
                )

            text_content = response.text
            return final_url, status_code, content_type_header, text_content

    finally:
        if own_client:
            http_client.close()


def clean_text(raw_text: str) -> str:
    """Normalize whitespace and clean text."""
    if not raw_text:
        return ""
    # Normalize multiple line breaks and trailing whitespace
    lines = [line.strip() for line in raw_text.splitlines()]
    # Remove excessive blank lines
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned_lines.append("")
                prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False
    return "\n".join(cleaned_lines).strip()


def parse_html_data(html_content: str, base_url: str) -> Dict[str, Any]:
    """Parse HTML and extract metadata, title, headings, links, and main body text."""
    soup = BeautifulSoup(html_content, "lxml")

    # 1. Title Extraction
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("meta", property="og:title"):
        title = soup.find("meta", property="og:title").get("content", "").strip()

    # 2. Meta Description Extraction
    description = ""
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if desc_tag and desc_tag.get("content"):
        description = desc_tag.get("content").strip()
    else:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            description = og_desc.get("content").strip()

    # 3. Canonical URL
    canonical_url = None
    canonical_tag = soup.find("link", rel=re.compile(r"^canonical$", re.I))
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = urljoin(base_url, canonical_tag.get("href").strip())

    # 4. Headings Extraction (H1, H2, H3)
    headings = {
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)],
        "h3": [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)],
    }

    # 5. Metadata dictionary (OpenGraph, Twitter, common meta)
    metadata: Dict[str, str] = {}
    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property") or meta.get("http-equiv")
        content = meta.get("content")
        if key and content:
            key_clean = key.strip()
            # Only keep informative metadata
            if any(
                prefix in key_clean.lower()
                for prefix in ("og:", "twitter:", "description", "keywords", "author", "viewport", "robots")
            ):
                metadata[key_clean] = content.strip()

    # 6. Links Extraction with Absolute URL resolution
    extracted_links: List[LinkItem] = []
    seen_urls: Set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        raw_href = a_tag.get("href", "").strip()
        if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        resolved_url = urljoin(base_url, raw_href)
        if resolved_url in seen_urls:
            continue

        seen_urls.add(resolved_url)
        link_text = a_tag.get_text(strip=True) or a_tag.get("title") or resolved_url
        extracted_links.append(LinkItem(text=link_text[:120], url=resolved_url))

    # 7. Main Text Extraction via Trafilatura with BeautifulSoup fallback
    main_text = ""
    try:
        extracted = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if extracted and len(extracted.strip()) > 30:
            main_text = extracted.strip()
    except Exception:
        main_text = ""

    # Fallback to BeautifulSoup if Trafilatura extracted nothing (e.g. sparse pages)
    if not main_text:
        # Create a copy of the soup for text stripping
        clean_soup = BeautifulSoup(html_content, "lxml")
        for tag in clean_soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe", "button"]):
            tag.decompose()
        main_text = clean_soup.get_text(separator="\n")

    main_text = clean_text(main_text)
    word_count = len(main_text.split()) if main_text else 0

    return {
        "title": title,
        "description": description,
        "canonical_url": canonical_url,
        "headings": headings,
        "links": extracted_links,
        "metadata": metadata,
        "text": main_text,
        "word_count": word_count,
    }


def scrape_website(url: str, client: Optional[httpx.Client] = None) -> ScrapeResponse:
    """Orchestrate URL validation, fetching, parsing, and structured response creation."""
    try:
        # Step 1 & 2: Validate security and fetch page
        final_url, status_code, content_type, html_content = safe_fetch(url, client=client)

        # Step 3: Parse and extract structured data
        parsed = parse_html_data(html_content, base_url=final_url)

        return ScrapeResponse(
            success=True,
            url=url,
            final_url=final_url,
            status_code=status_code,
            content_type=content_type,
            title=parsed["title"],
            description=parsed["description"],
            canonical_url=parsed["canonical_url"],
            headings=HeadingsGroup(**parsed["headings"]),
            links=parsed["links"],
            metadata=parsed["metadata"],
            text=parsed["text"],
            word_count=parsed["word_count"],
        )

    except SecurityException as e:
        return ScrapeResponse(
            success=False,
            url=url,
            error=str(e),
            error_type="SecurityError",
            status_code=400,
        )
    except ExtractionException as e:
        return ScrapeResponse(
            success=False,
            url=url,
            error=str(e),
            error_type="ExtractionError",
            status_code=502,
        )
    except Exception as e:
        return ScrapeResponse(
            success=False,
            url=url,
            error=f"Unexpected error while processing page: {e}",
            error_type="InternalError",
            status_code=500,
        )
