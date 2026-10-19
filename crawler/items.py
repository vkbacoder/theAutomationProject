"""Scrapy Item definitions for crawled page evidence."""

import scrapy


class CrawledPageItem(scrapy.Item):
    """Structured evidence item yielded by the recursive crawler."""
    job_id = scrapy.Field()
    original_url = scrapy.Field()
    final_url = scrapy.Field()
    http_status = scrapy.Field()
    depth = scrapy.Field()
    discovery_source_url = scrapy.Field()
    title = scrapy.Field()
    extracted_text = scrapy.Field()
    headings_json = scrapy.Field()
    metadata_json = scrapy.Field()
    links_count = scrapy.Field()
    word_count = scrapy.Field()
    content_hash = scrapy.Field()
    status = scrapy.Field()
    error_message = scrapy.Field()
    retrieved_at = scrapy.Field()


class DiscoveredDocumentItem(scrapy.Item):
    """Structured document resource yielded by the crawler."""
    job_id = scrapy.Field()
    source_page_url = scrapy.Field()
    document_url = scrapy.Field()
    file_name = scrapy.Field()
    file_format = scrapy.Field()
    content_type = scrapy.Field()
    file_size_bytes = scrapy.Field()
    download_status = scrapy.Field()
    extraction_status = scrapy.Field()
    error_message = scrapy.Field()
    extracted_text = scrapy.Field()
    metadata_json = scrapy.Field()
    sections_json = scrapy.Field()
    retrieved_at = scrapy.Field()
