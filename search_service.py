"""External Search Service and Iterative Search Expansion Engine.

Coordinates the External Research Frontier:
1. Generates targeted query templates for JEDOX, RECOV, and GENERAL workflows.
2. Integrates with SearXNG, Web Search fallback, and Mock providers.
3. Implements Iterative Search Expansion based on discoveries (e.g. discovered executives, case studies).
4. Maintains query history, deduplication, and request budget limits.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, Field

from dedup import normalize_domain
from research_scoring import compute_url_priority
from scraper import DEFAULT_TIMEOUT_SEC, DEFAULT_USER_AGENT, validate_url_security

logger = logging.getLogger(__name__)


class SearchResultItem(BaseModel):
    """Structured search engine result item."""
    url: str
    title: str
    snippet: str = ""
    engine: str = "search"
    query: str = ""
    priority_score: float = 0.0


class ResearchBudget(BaseModel):
    """Configurable resource and retrieval limits for a research job."""
    max_internal_pages: int = 20
    max_external_search_results: int = 30
    max_external_pages_retrieved: int = 12
    max_concurrent_requests: int = 4
    max_research_depth: int = 3
    max_search_queries: int = 6
    max_depth: int = 3
    timeout_seconds: float = 300.0


class SearchProvider:
    """Base interface for search engine providers."""

    def search(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        raise NotImplementedError


class SearXNGSearchProvider(SearchProvider):
    """SearXNG JSON API search provider."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = (base_url or os.getenv("SEARXNG_URL", "http://localhost:8080")).rstrip("/")
        self.timeout = timeout

    def search(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        target_url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "engines": "google,bing,duckduckgo",
            "safesearch": "1",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(target_url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_results = data.get("results", [])
                    results: List[SearchResultItem] = []
                    for r in raw_results[:limit]:
                        url = r.get("url")
                        if url:
                            results.append(
                                SearchResultItem(
                                    url=url,
                                    title=r.get("title", ""),
                                    snippet=r.get("content", ""),
                                    engine="searxng",
                                    query=query,
                                )
                            )
                    return results
        except Exception as e:
            logger.debug("SearXNG search error for '%s': %s", query, e)
        return []


class WebSearchProvider(SearchProvider):
    """Safe HTTP search provider using public endpoints with SSRF guards."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def search(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        """Query DuckDuckGo HTML endpoint as a reliable, API-key-free web fallback."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        results: List[SearchResultItem] = []
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    for a_tag in soup.select("a.result__url, a.result__snippet, .result__body"):
                        link_elem = a_tag.find_parent("div", class_="result") or a_tag
                        title_elem = link_elem.select_one(".result__title a")
                        snippet_elem = link_elem.select_one(".result__snippet")
                        if title_elem and title_elem.get("href"):
                            raw_href = title_elem["href"]
                            # Extract actual destination from DDG redirect url (uddg parameter)
                            match = re.search(r"uddg=([^&]+)", raw_href)
                            actual_url = httpx.URL(raw_href).query.decode("utf-8") if not match else None
                            if match:
                                from urllib.parse import unquote
                                dest_url = unquote(match.group(1))
                            else:
                                dest_url = raw_href

                            if dest_url.startswith("http"):
                                results.append(
                                    SearchResultItem(
                                        url=dest_url,
                                        title=title_elem.get_text(strip=True),
                                        snippet=snippet_elem.get_text(strip=True) if snippet_elem else "",
                                        engine="duckduckgo_web",
                                        query=query,
                                    )
                                )
                                if len(results) >= limit:
                                    break
        except Exception as e:
            logger.debug("Web search provider error for '%s': %s", query, e)
        return results


class MockSearchProvider(SearchProvider):
    """Deterministic mock provider for automated testing and offline benchmark replay."""

    def __init__(self, mock_responses: Optional[Dict[str, List[SearchResultItem]]] = None):
        self.mock_responses: Dict[str, List[SearchResultItem]] = mock_responses or {}
        self.fallback_rules: List[tuple[re.Pattern, List[SearchResultItem]]] = []

    def add_mock(self, query: str, items: List[SearchResultItem]):
        self.mock_responses[query.lower().strip()] = items

    def add_pattern_rule(self, pattern: str, items: List[SearchResultItem]):
        self.fallback_rules.append((re.compile(pattern, re.IGNORECASE), items))

    def search(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        q_norm = query.lower().strip()
        if q_norm in self.mock_responses:
            return self.mock_responses[q_norm][:limit]

        # Check pattern rules
        for pattern, items in self.fallback_rules:
            if pattern.search(query):
                return items[:limit]

        return []


# -------------------------------------------------------------
# Query Template Generation
# -------------------------------------------------------------

def generate_initial_search_queries(
    company_name: str,
    target_product: Optional[str] = None,
    workflow: str = "GENERAL",
    partner_name: Optional[str] = None,
) -> List[str]:
    """Generate high-precision initial queries based on target company and workflow."""
    c_clean = company_name.strip()
    t_prod = (target_product or "").strip()
    wf = (workflow or "").upper()
    queries: List[str] = []

    if wf == "JEDOX" or (t_prod and t_prod.lower() == "jedox"):
        # Section 3B required Jedox query templates
        queries.append(f'"{c_clean}" Jedox')
        queries.append(f'"{c_clean}" Jedox customer')
        queries.append(f'"{c_clean}" case study')
        queries.append(f'"{c_clean}" customer story')
        queries.append(f'"{c_clean}" CFO')
        queries.append(f'"{c_clean}" leadership')
        queries.append(f'site:jedox.com "{c_clean}"')
        if partner_name:
            queries.append(f'"{partner_name}" "{c_clean}" Jedox')

    elif wf == "RECOV" or (t_prod and t_prod.lower() == "recov"):
        queries.append(f'"{c_clean}" RECOV')
        queries.append(f'"{c_clean}" debt recovery')
        queries.append(f'"{c_clean}" debt collection')
        queries.append(f'"{c_clean}" loan recovery')
        queries.append(f'"{c_clean}" collections platform')
        queries.append(f'"{c_clean}" NBFC lending')
        queries.append(f'"{c_clean}" recovery partner')
        queries.append(f'"{c_clean}" collections leadership')

    else:  # GENERAL
        queries.append(f'"{c_clean}" overview corporate profile')
        queries.append(f'"{c_clean}" leadership executives')
        queries.append(f'"{c_clean}" case study customer stories')
        queries.append(f'"{c_clean}" contact phone email headquarters')

    # Deduplicate while preserving order
    seen: Set[str] = set()
    deduped: List[str] = []
    for q in queries:
        q_low = q.lower().strip()
        if q_low not in seen:
            seen.add(q_low)
            deduped.append(q)
    return deduped


def generate_followup_queries(
    company_name: str,
    discovered_person_name: Optional[str] = None,
    discovered_person_title: Optional[str] = None,
    target_product: Optional[str] = None,
    need_contact_info: bool = False,
) -> List[str]:
    """Generate iterative follow-up queries based on intermediate research discoveries."""
    c_clean = company_name.strip()
    queries: List[str] = []

    if discovered_person_name:
        p_clean = discovered_person_name.strip()
        title = (discovered_person_title or "CFO").strip()
        queries.append(f'"{p_clean}" "{c_clean}" {title}')
        queries.append(f'"{p_clean}" "{c_clean}"')

    if need_contact_info:
        queries.append(f'"{c_clean}" contact email phone headquarters')
        queries.append(f'"{c_clean}" Australian office address')

    if target_product and discovered_person_name:
        queries.append(f'"{discovered_person_name}" "{target_product}"')

    return queries


generate_external_queries = generate_initial_search_queries


# -------------------------------------------------------------
# Iterative External Research Frontier Orchestrator
# -------------------------------------------------------------

class ExternalResearchFrontier:
    """Manages external search discovery, query expansion, and candidate scoring."""

    def __init__(
        self,
        provider: Optional[SearchProvider] = None,
        max_queries: int = 6,
        max_results_per_query: int = 10,
        budget: Optional[ResearchBudget] = None,
    ):
        self.provider = provider or WebSearchProvider()
        self.budget = budget or ResearchBudget()
        self.max_queries = budget.max_search_queries if budget else max_queries
        self.max_results_per_query = max_results_per_query
        self.executed_queries: List[str] = []
        self.seen_query_keys: Set[str] = set()
        self.discovered_urls: Set[str] = set()
        self.all_results: List[SearchResultItem] = []

    def is_duplicate_url(self, url: str) -> bool:
        from research_scoring import normalize_url_for_research
        norm = normalize_url_for_research(url)
        return norm in self.discovered_urls or url in self.discovered_urls

    def record_url(self, url: str) -> None:
        from research_scoring import normalize_url_for_research
        norm = normalize_url_for_research(url)
        self.discovered_urls.add(norm)
        self.discovered_urls.add(url)

    def can_execute_more_queries(self) -> bool:
        return len(self.executed_queries) < self.max_queries

    def execute_query(
        self,
        query: str,
        target_product: Optional[str] = None,
        company_name: Optional[str] = None,
        workflow: str = "GENERAL",
        objective: Optional[str] = None,
    ) -> List[SearchResultItem]:
        """Execute a single query if budget allows and not already executed."""
        q_key = query.strip().lower()
        if q_key in self.seen_query_keys:
            logger.debug("Skipping already executed query: %s", query)
            return []

        if not self.can_execute_more_queries():
            logger.info("Search query budget reached (%d/%d).", len(self.executed_queries), self.max_queries)
            return []

        self.seen_query_keys.add(q_key)
        self.executed_queries.append(query)

        raw_items = self.provider.search(query, limit=self.max_results_per_query)
        scored_items: List[SearchResultItem] = []

        for item in raw_items:
            # URL deduplication
            norm_url = item.url.strip()
            if norm_url in self.discovered_urls:
                continue
            self.discovered_urls.add(norm_url)

            # Score result priority
            score_res = compute_url_priority(
                url=norm_url,
                link_text=f"{item.title} {item.snippet}",
                discovery_depth=1,
                workflow=workflow,
                target_product=target_product,
                company_name=company_name,
                objective=objective,
                is_external=True,
            )
            item.priority_score = score_res.priority_score
            scored_items.append(item)
            self.all_results.append(item)

        # Sort items by priority score descending
        scored_items.sort(key=lambda x: x.priority_score, reverse=True)
        return scored_items

    def expand_and_execute_batch(
        self,
        queries: List[str],
        target_product: Optional[str] = None,
        company_name: Optional[str] = None,
        workflow: str = "GENERAL",
        objective: Optional[str] = None,
    ) -> List[SearchResultItem]:
        """Execute a batch of queries within the configured budget."""
        batch_results: List[SearchResultItem] = []
        for q in queries:
            if not self.can_execute_more_queries():
                break
            items = self.execute_query(
                query=q,
                target_product=target_product,
                company_name=company_name,
                workflow=workflow,
                objective=objective,
            )
            batch_results.extend(items)
        return batch_results
