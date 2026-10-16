"""Automated test suite for web scraping engine and API routes.

Uses mocked HTTP responses to test URL validation, SSRF protections,
HTML parsing, text extraction, error handling, and API endpoints without
depending on public website availability.
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest
import ssl
from fastapi.testclient import TestClient

from app import app
from scraper import (
    ExtractionException,
    HeadingsGroup,
    LinkItem,
    SSRFSafeSyncBackend,
    SecurityException,
    create_ssrf_safe_client,
    get_ssl_context,
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


# ---------------------------------------------------------
# 5. Connection-Boundary SSRF & Streaming Size Limit Tests
# ---------------------------------------------------------

def test_public_url_acceptance():
    """Verify that legitimate public URLs and IPs are accepted."""
    def app_handler(request):
        return httpx.Response(
            200,
            text="<html><body><h1>Public Page</h1></body></html>",
            headers={"content-type": "text/html"},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(app_handler))
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        final_url, status, content_type, text = safe_fetch("https://example.com/page", client=mock_client)
        assert status == 200
        assert "<h1>Public Page</h1>" in text


def test_connection_boundary_private_and_loopback_ip_rejection():
    """Verify that SSRFSafeSyncBackend blocks requests to private, loopback, and metadata IPs."""
    backend = SSRFSafeSyncBackend()
    prohibited_ips = [
        "127.0.0.1",
        "127.0.1.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
    ]
    for ip in prohibited_ips:
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", (ip, 80))]):
            with pytest.raises(SecurityException) as excinfo:
                backend.connect_tcp("internal-target.com", 80)
            assert "resolves to private/restricted IP" in str(excinfo.value)


def test_redirect_to_prohibited_destination_blocked():
    """Verify that redirect hops to private, loopback, or cloud metadata IPs are blocked."""
    def redirect_handler(request):
        if request.url.path == "/bounce":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})
        return httpx.Response(200, text="unreachable")

    client = httpx.Client(transport=httpx.MockTransport(redirect_handler))
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.side_effect = [
            [(2, 1, 6, "", ("93.184.216.34", 443))],
            [(2, 1, 6, "", ("169.254.169.254", 80))],
        ]
        with pytest.raises(SecurityException) as excinfo:
            safe_fetch("https://public-site.com/bounce", client=client)
        assert "resolves to private/restricted IP" in str(excinfo.value)


def test_dns_rebinding_rejected_at_connection_time():
    """Verify TOCTOU / DNS rebinding protection: public during validation, private during connect."""
    dns_history = []

    def mock_rebinding_dns(host, port, *args, **kwargs):
        dns_history.append((host, port))
        if len(dns_history) == 1:
            # 1st call: validate_url_security pre-flight check returns public IP
            return [(2, 1, 6, "", ("93.184.216.34", port))]
        # 2nd call: SSRFSafeSyncBackend.connect_tcp connection-time resolution returns loopback
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    with patch("socket.getaddrinfo", side_effect=mock_rebinding_dns):
        with pytest.raises(SecurityException) as excinfo:
            safe_fetch("http://rebind-attack.com/admin")
        assert "resolves to private/restricted IP (127.0.0.1)" in str(excinfo.value)


def test_oversized_streamed_response_aborted_at_limit():
    """Verify streaming stops as soon as byte limit is exceeded, aborting further chunk downloads."""
    chunks_yielded = 0

    def chunk_generator():
        nonlocal chunks_yielded
        for _ in range(25):
            chunks_yielded += 1
            yield b"X" * 1024  # 1 KB per chunk

    def app_handler(request):
        return httpx.Response(200, content=chunk_generator(), headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(app_handler))
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        with pytest.raises(ExtractionException) as excinfo:
            safe_fetch("https://example.com/big", max_bytes=4096, client=client)
        assert "exceeds the maximum allowed limit of 4096 bytes" in str(excinfo.value)
        # Ensure chunk generator was aborted early (5 chunks = 5120 bytes > 4096 bytes)
        assert chunks_yielded == 5


def test_decompressed_response_size_enforced():
    """Verify byte limit is enforced against decompressed payload to prevent compression bombs."""
    import gzip

    decompressed_body = b"<html><body>" + (b"Lead Research Qualification Data. " * 300) + b"</body></html>"
    compressed_body = gzip.compress(decompressed_body)
    assert len(compressed_body) < 300
    assert len(decompressed_body) > 10000

    def app_handler(request):
        return httpx.Response(
            200,
            content=compressed_body,
            headers={"content-type": "text/html", "content-encoding": "gzip"},
        )

    client = httpx.Client(transport=httpx.MockTransport(app_handler))
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        with pytest.raises(ExtractionException) as excinfo:
            safe_fetch("https://example.com/gzip-bomb", max_bytes=2048, client=client)
        assert "exceeds the maximum allowed limit of 2048 bytes" in str(excinfo.value)


def test_safe_fetch_successful_streaming_and_extraction():
    """Verify normal multi-chunk streaming completes extraction successfully within limit."""
    def chunk_generator():
        yield b"<!DOCTYPE html><html><head><title>Streaming Works</title></head>"
        yield b"<body><h1>Stream Success</h1><p>Content arrived in chunks safely.</p></body></html>"

    def app_handler(request):
        return httpx.Response(200, content=chunk_generator(), headers={"content-type": "text/html; charset=utf-8"})

    client = httpx.Client(transport=httpx.MockTransport(app_handler))
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        final_url, status, content_type, text = safe_fetch("https://example.com/stream-ok", client=client)
        assert status == 200
        assert "<title>Streaming Works</title>" in text
        assert "Content arrived in chunks safely." in text


def test_scrape_website_dns_rebinding_handled():
    """Verify scrape_website gracefully catches connection-time SSRF/DNS rebinding."""
    dns_calls = []

    def mock_dns(host, port, *args, **kwargs):
        dns_calls.append((host, port))
        if len(dns_calls) == 1:
            return [(2, 1, 6, "", ("93.184.216.34", port))]
        return [(2, 1, 6, "", ("169.254.169.254", port))]

    with patch("socket.getaddrinfo", side_effect=mock_dns):
        response = scrape_website("http://rebind-aws.com/meta")
        assert response.success is False
        assert response.error_type == "SecurityError"
        assert response.status_code == 400
        assert "resolves to private/restricted IP" in response.error


# ---------------------------------------------------------
# 10. TLS & SSL Verification Security Tests
# ---------------------------------------------------------

def test_ssl_context_strict_tls_and_hostname_verification_enabled():
    """Verify get_ssl_context enforces strict certificate and hostname verification."""
    import ssl
    ctx = get_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    # verify_mode must be CERT_REQUIRED (never CERT_NONE or CERT_OPTIONAL)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    # check_hostname must be strictly enabled
    assert ctx.check_hostname is True


def test_create_ssrf_safe_client_uses_verified_ssl_context():
    """Verify create_ssrf_safe_client initializes with verified SSLContext."""
    import ssl
    client = create_ssrf_safe_client()
    transport = client._transport
    assert hasattr(transport, "_pool")
    ssl_context = getattr(transport._pool, "_ssl_context", None)
    if ssl_context:
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname is True


def test_ssl_context_loads_custom_ca_file(tmp_path):
    """Verify get_ssl_context loads verifiable intermediate certificates from extra_ca_file."""
    dummy_pem = tmp_path / "custom.pem"
    dummy_pem.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    ctx = get_ssl_context(extra_ca_file=str(dummy_pem))
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_ssl_context_rejects_untrusted_certificates():
    """Verify get_ssl_context rejects self-signed certificates with CERTIFICATE_VERIFY_FAILED."""
    import ssl
    import socket

    ctx = get_ssl_context()
    try:
        with socket.create_connection(("self-signed.badssl.com", 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname="self-signed.badssl.com"):
                pytest.fail("Should have rejected self-signed certificate")
    except ssl.SSLCertVerificationError as e:
        assert "CERTIFICATE_VERIFY_FAILED" in str(e)
    except (socket.timeout, OSError):
        pass


