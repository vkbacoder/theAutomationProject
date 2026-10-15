"""Automated test suite for web scraping engine and API routes.

Uses mocked HTTP responses to test URL validation, SSRF protections,
HTML parsing, text extraction, error handling, and API endpoints without
depending on public website availability.
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app import app
from scraper import (
    ExtractionException,
    HeadingsGroup,
    LinkItem,
    SecurityException,
    is_ip_allowed,
    parse_html_data,
    safe_fetch,
    scrape_website,
    validate_url_security,
)

client = TestClient(app)


# ---------------------------------------------------------
# 1. URL Validation & SSRF Security Tests
# ---------------------------------------------------------

def test_url_validation_valid_schemes():
    """Verify HTTP and HTTPS schemes pass validation."""
    with patch("socket.getaddrinfo") as mock_dns:
        # Mock safe public IP (93.184.216.34)
        mock_dns.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443))
        ]
        url, host, port = validate_url_security("https://example.com/test")
        assert url == "https://example.com/test"
        assert host == "example.com"
        assert port == 443


def test_url_validation_invalid_schemes():
    """Verify non-HTTP schemes are rejected."""
    invalid_urls = [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com",
        "data:text/html,hello",
        "javascript:alert(1)",
        "",
        None,
    ]
    for bad_url in invalid_urls:
        with pytest.raises(SecurityException):
            validate_url_security(bad_url)


def test_is_ip_allowed():
    """Test private, loopback, link-local, and reserved IP blocking."""
    # Forbidden IPs
    assert not is_ip_allowed("127.0.0.1")
    assert not is_ip_allowed("127.0.1.1")
    assert not is_ip_allowed("10.0.0.1")
    assert not is_ip_allowed("172.16.0.1")
    assert not is_ip_allowed("192.168.1.1")
    assert not is_ip_allowed("169.254.169.254")  # AWS/Cloud metadata
    assert not is_ip_allowed("0.0.0.0")
    assert not is_ip_allowed("::1")
    assert not is_ip_allowed("invalid-ip")

    # Allowed Public IPs
    assert is_ip_allowed("93.184.216.34")   # example.com
    assert is_ip_allowed("8.8.8.8")         # Google DNS
    assert is_ip_allowed("1.1.1.1")         # Cloudflare DNS


def test_ssrf_blocking_local_hostnames():
    """Test rejection of localhost, internal, and link-local destinations."""
    blocked_hosts = [
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://0.0.0.0/",
        "http://server.local/",
        "http://corp.internal/",
    ]
    for url in blocked_hosts:
        with pytest.raises(SecurityException):
            validate_url_security(url)


def test_ssrf_blocking_dns_resolving_to_private_ip():
    """Test that a public-looking domain resolving to an internal IP is blocked."""
    with patch("socket.getaddrinfo") as mock_dns:
        # Mock DNS resolving malicious-site.com to 169.254.169.254 (Cloud metadata)
        mock_dns.return_value = [
            (2, 1, 6, "", ("169.254.169.254", 80))
        ]
        with pytest.raises(SecurityException) as excinfo:
            validate_url_security("http://malicious-site.com/latest/meta-data")
        assert "resolves to private/restricted IP" in str(excinfo.value)


# ---------------------------------------------------------
# 2. HTML Parsing & Extraction Tests
# ---------------------------------------------------------

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Acme Industrial Solutions - Precision Manufacturing</title>
  <meta name="description" content="Leading provider of high-precision CNC machinery and automated components.">
  <link rel="canonical" href="https://acme.com/industrial">
  <meta property="og:title" content="Acme Solutions">
  <meta property="og:description" content="Leading provider of high-precision CNC machinery.">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
  <nav>
    <a href="/home">Home</a>
    <a href="/about">About Us</a>
  </nav>

  <header>
    <h1>Precision CNC Machining</h1>
  </header>

  <main>
    <h2>Aerospace Grade Components</h2>
    <p>Acme delivers tight-tolerance components designed for high-stress aerospace environments.</p>
    
    <h2>Medical Technology</h2>
    <p>Our clean-room production line guarantees particulate-free titanium implants.</p>
    
    <h3>Certification Standards</h3>
    <p>ISO 9001 and AS9100 certified facilities across North America.</p>
    
    <a href="https://acme.com/contact">Request a Quote</a>
    <a href="/catalog.pdf">Download Catalog</a>
    <a href="javascript:void(0)">Skip Navigation</a>
    <a href="#top">Back to top</a>
  </main>

  <footer>
    <p>&copy; 2026 Acme Corp. All rights reserved.</p>
  </footer>
</body>
</html>
"""


def test_html_title_and_description_extraction():
    """Test extraction of title, meta description, and canonical URL."""
    data = parse_html_data(SAMPLE_HTML, base_url="https://acme.com/industrial")
    assert data["title"] == "Acme Industrial Solutions - Precision Manufacturing"
    assert "Leading provider of high-precision CNC machinery" in data["description"]
    assert data["canonical_url"] == "https://acme.com/industrial"


def test_headings_extraction():
    """Test grouping of H1, H2, and H3 headings."""
    data = parse_html_data(SAMPLE_HTML, base_url="https://acme.com/industrial")
    headings = data["headings"]
    assert headings["h1"] == ["Precision CNC Machining"]
    assert headings["h2"] == ["Aerospace Grade Components", "Medical Technology"]
    assert headings["h3"] == ["Certification Standards"]


def test_links_extraction_and_resolution():
    """Test absolute URL resolution and anchor text extraction."""
    data = parse_html_data(SAMPLE_HTML, base_url="https://acme.com/industrial")
    links = data["links"]
    urls = [link.url for link in links]

    assert "https://acme.com/contact" in urls
    assert "https://acme.com/catalog.pdf" in urls
    assert "https://acme.com/home" in urls
    assert "https://acme.com/about" in urls

    # Anchors and javascript pseudo-links must be excluded
    for url in urls:
        assert not url.startswith("javascript:")
        assert not url.endswith("#top")


def test_metadata_extraction():
    """Test extraction of OpenGraph and viewport metadata tags."""
    data = parse_html_data(SAMPLE_HTML, base_url="https://acme.com/industrial")
    meta = data["metadata"]
    assert "viewport" in meta
    assert meta["og:title"] == "Acme Solutions"


def test_main_text_and_word_count():
    """Test clean body text extraction and word counting."""
    data = parse_html_data(SAMPLE_HTML, base_url="https://acme.com/industrial")
    assert "Acme delivers tight-tolerance components" in data["text"]
    assert data["word_count"] > 20


def test_empty_and_malformed_html():
    """Verify that empty or broken HTML does not crash the parser."""
    empty_data = parse_html_data("", base_url="https://example.com")
    assert empty_data["title"] == ""
    assert empty_data["word_count"] == 0
    assert empty_data["headings"]["h1"] == []

    malformed_html = "<html><body><div><p>Unclosed paragraph<h1>Heading without close"
    malformed_data = parse_html_data(malformed_html, base_url="https://example.com")
    assert malformed_data["headings"]["h1"] == ["Heading without close"]


# ---------------------------------------------------------
# 3. HTTP Client, Redirect & Error Handling Tests
# ---------------------------------------------------------

def test_safe_fetch_unsupported_content_type():
    """Test rejection of non-HTML content (e.g. PDF or images)."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/pdf"}
    mock_response.url = httpx.URL("https://example.com/doc.pdf")

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response

    with patch("scraper.validate_url_security") as mock_sec:
        mock_sec.return_value = ("https://example.com/doc.pdf", "example.com", 443)
        with pytest.raises(ExtractionException) as excinfo:
            safe_fetch("https://example.com/doc.pdf", client=mock_client)
        assert "Unsupported content type 'application/pdf'" in str(excinfo.value)


def test_safe_fetch_redirect_limit():
    """Test that infinite redirect loops trigger maximum redirect limits."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 302
    mock_response.headers = httpx.Headers({"Location": "https://example.com/loop"})
    mock_response.url = httpx.URL("https://example.com/loop")

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response

    with patch("scraper.validate_url_security") as mock_sec:
        mock_sec.return_value = ("https://example.com/loop", "example.com", 443)
        with pytest.raises(ExtractionException) as excinfo:
            safe_fetch("https://example.com/loop", max_redirects=3, client=mock_client)
        assert "Exceeded maximum redirect limit" in str(excinfo.value)


# ---------------------------------------------------------
# 4. FastAPI Endpoint Integration Tests
# ---------------------------------------------------------

def test_api_health():
    """Test health check route."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "service" in data


def test_api_scrape_success_mocked():
    """Test POST /api/scrape returns structured response matching schema."""
    with patch("scraper.safe_fetch") as mock_fetch:
        mock_fetch.return_value = (
            "https://mocked-site.com/",
            200,
            "text/html; charset=UTF-8",
            SAMPLE_HTML,
        )
        response = client.post("/api/scrape", json={"url": "https://mocked-site.com/"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["title"] == "Acme Industrial Solutions - Precision Manufacturing"
        assert len(data["headings"]["h1"]) == 1
        assert len(data["headings"]["h2"]) == 2
        assert len(data["links"]) >= 4
        assert data["word_count"] > 10


def test_api_scrape_ssrf_blocked():
    """Test POST /api/scrape safely rejects private IP destinations."""
    response = client.post("/api/scrape", json={"url": "http://127.0.0.1:8000/admin"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error_type"] == "SecurityError"
    assert "blocked" in data["error"].lower() or "forbidden" in data["error"].lower()


def test_api_scrape_empty_url():
    """Test POST /api/scrape rejects empty URLs."""
    response = client.post("/api/scrape", json={"url": "   "})
    assert response.status_code == 400


def test_frontend_index_route():
    """Verify GET / returns the Web Scraper Test HTML dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Web Scraper Test" in response.text
    assert "Scrape Website" in response.text
    assert "id=\"url-input\"" in response.text
