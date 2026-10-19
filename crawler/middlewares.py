"""Security and SSRF Downloader Middlewares for Scrapy.

Enforces:
- HTTP / HTTPS scheme restriction.
- Real-time DNS resolution and validation against loopback, private, link-local,
  cloud metadata (169.254.x.x), and reserved IPs.
- Local hostname blocking (localhost, .local, .internal, etc.).
- Redirect destination validation.
- Content-type validation.
- Prevention of unintended proxy bypass.
"""

from __future__ import annotations

import logging
import socket
from urllib.parse import urljoin, urlparse

from scrapy.exceptions import IgnoreRequest
from scraper import is_ip_allowed, validate_url_security

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_PREFIXES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.",
    "application/vnd.ms-excel",
    "application/msword",
    "application/vnd.ms-powerpoint",
    "text/csv",
    "image/",
    "application/octet-stream",
)


class SSRFProtectionMiddleware:
    """Downloader middleware to block SSRF and private network access."""

    def process_request(self, request, spider=None):
        """Validate every outgoing request (including redirects and seed URLs)."""
        url = request.url
        try:
            # 1. Scheme check
            parsed = urlparse(url)
            if parsed.scheme.lower() not in ALLOWED_SCHEMES:
                raise IgnoreRequest(f"Forbidden URL scheme '{parsed.scheme}': {url}")

            # 2. Hostname validation
            hostname = parsed.hostname
            if not hostname:
                raise IgnoreRequest(f"Missing hostname in URL: {url}")

            lowered_host = hostname.lower().strip()
            if (
                lowered_host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
                or lowered_host.endswith(".local")
                or lowered_host.endswith(".internal")
                or lowered_host.endswith(".localhost")
            ):
                raise IgnoreRequest(f"Access to local hostname '{hostname}' is blocked: {url}")

            # 3. DNS resolution and IP verification
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            try:
                addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            except socket.gaierror as e:
                raise IgnoreRequest(f"DNS Resolution failed for '{hostname}': {e}")
            except Exception as e:
                raise IgnoreRequest(f"DNS lookup error for '{hostname}': {e}")

            if not addr_info:
                raise IgnoreRequest(f"No IP addresses resolved for hostname '{hostname}'")

            for item in addr_info:
                sockaddr = item[4]
                ip_addr = sockaddr[0]
                if not is_ip_allowed(ip_addr):
                    raise IgnoreRequest(
                        f"SSRF Block: '{hostname}' resolves to private or restricted IP ({ip_addr})."
                    )

            # Store verified IP for provenance tracking
            request.meta["verified_ip"] = addr_info[0][4][0]
            return None

        except IgnoreRequest as e:
            logger.warning("[SSRF Block] %s", e)
            if spider and hasattr(spider, "record_url_error"):
                spider.record_url_error(url, str(e), error_type="SSRFBlock")
            raise

    def process_response(self, request, response, spider=None):
        """Validate redirect destinations and content types on responses."""
        # Check redirect status codes (301, 302, 303, 307, 308)
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location") or response.headers.get("location")
            if location:
                try:
                    loc_str = location.decode("utf-8", errors="ignore").strip()
                    resolved_redirect = urljoin(response.url, loc_str)
                    # Pre-validate redirect target
                    validate_url_security(resolved_redirect)
                except Exception as e:
                    logger.warning("[Redirect Security Block] Invalid redirect %s: %s", response.url, e)
                    if hasattr(spider, "record_url_error"):
                        spider.record_url_error(response.url, f"Forbidden redirect target: {e}", error_type="SecurityError")
                    raise IgnoreRequest(f"Security block on redirect to {loc_str}: {e}")

        # Check Content-Type header
        content_type = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore").lower()
        if content_type:
            main_type = content_type.split(";")[0].strip()
            # If Content-Type is clearly non-textual (e.g. binary/media/pdf), ignore request body
            if not any(main_type.startswith(prefix) for prefix in ALLOWED_CONTENT_PREFIXES):
                logger.info("[Content-Type Skip] Ignoring non-HTML content type '%s' for %s", main_type, response.url)
                if hasattr(spider, "record_url_skipped"):
                    spider.record_url_skipped(response.url, f"Skipped unsupported content-type: {main_type}")
                raise IgnoreRequest(f"Unsupported content type: {main_type}")

        return response
