"""Scrapy settings for the Lead Research recursive crawler engine.

Enforces SSRF prevention, per-domain throttling, bounded concurrency,
response size limits, and robust retry backoff.
"""

from scraper import DEFAULT_USER_AGENT, MAX_RESPONSE_BYTES, DEFAULT_TIMEOUT_SEC, MAX_REDIRECTS

BOT_NAME = "LeadResearchCrawler"

# Identity & Politeness
USER_AGENT = DEFAULT_USER_AGENT
ROBOTSTXT_OBEY = True
COOKIES_ENABLED = False

# Concurrency & Throttling
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 1.0

# AutoThrottle (Adaptive delay per domain)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# Timeouts & Size limits
DOWNLOAD_TIMEOUT = int(DEFAULT_TIMEOUT_SEC)
DOWNLOAD_MAXSIZE = 25 * 1024 * 1024  # 25 MB stream cutoff for documents & pages
DOWNLOAD_WARNSIZE = 2 * 1024 * 1024     # 2 MB warning threshold
REDIRECT_MAX_TIMES = MAX_REDIRECTS      # 5 redirects max

# Retries with Backoff
RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
RETRY_PRIORITY_ADJUST = -1

# Security: Disable environment proxy bypass and force real-time DNS
HTTPPROXY_ENABLED = False
DNSCACHE_ENABLED = False
TWISTED_DNS_RESOLVER = "crawler.resolver.SafeCachingThreadedResolver"
DNS_RESOLVER = "crawler.resolver.SafeCachingThreadedResolver"


# Downloader Middlewares
DOWNLOADER_MIDDLEWARES = {
    # Custom SSRF and IP policy validation (runs first)
    "crawler.middlewares.SSRFProtectionMiddleware": 50,
    "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": 100,
    "scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware": None,
    "scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware": 350,
    "scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware": 400,
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": 500,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
    "scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware": 580,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 590,
    "scrapy.downloadermiddlewares.redirect.RedirectMiddleware": 600,
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": None,
}

# Item Pipelines
ITEM_PIPELINES = {
    "crawler.pipelines.DatabasePipeline": 300,
}

# Request fingerprinting & Duplication Filter
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"

# Logging & Terminal Output
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
