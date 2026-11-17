"""Intelligent Search-Guided Research Controller.

Coordinates the Internal and External Research Frontiers, manages Best-First
URL prioritization, executes iterative query expansion, enforces research budgets,
and evaluates multi-objective stopping conditions.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

import database
from dedup import normalize_company_name, normalize_domain
from models import (
    CrawlJob,
    CrawlJobMetrics,
    CrawlJobStatus,
    CrawlPage,
    CrawlPageStatus,
    CustomerCandidate,
    DecisionMaker,
    PublicContact,
    RelationshipType,
    RoleCategory,
    UnifiedEvidence,
    WorkflowType,
)
from research_scoring import compute_url_priority
from scraper import (
    DEFAULT_TIMEOUT_SEC,
    DEFAULT_USER_AGENT,
    MAX_RESPONSE_BYTES,
    clean_text,
    parse_html_data,
    validate_url_security,
)
from search_service import (
    ExternalResearchFrontier,
    ResearchBudget,
    SearchResultItem,
    SearchProvider,
    WebSearchProvider,
    generate_followup_queries,
    generate_initial_search_queries,
)
from source_classifier import SourceCategory, classify_source, get_source_authority_weight

logger = logging.getLogger(__name__)


class ResearchStage(str):
    INITIALIZED = "INITIALIZED"
    INTERNAL_RESEARCH = "INTERNAL_RESEARCH"
    INTERNAL_COMPLETED = "INTERNAL_COMPLETED"
    EXTERNAL_RESEARCH = "EXTERNAL_RESEARCH"
    EXTERNAL_COMPLETED = "EXTERNAL_COMPLETED"
    EXTRACTION = "EXTRACTION"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    VERIFICATION = "VERIFICATION"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    RESEARCH_INCOMPLETE = "RESEARCH_INCOMPLETE"


class ResearchController:
    """Central orchestrator for search-guided lead intelligence research."""

    def __init__(
        self,
        job_id: int,
        db_path: Optional[str] = None,
        budget: Optional[ResearchBudget] = None,
        search_provider: Optional[SearchProvider] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self.job_id = job_id
        self.db_path = db_path
        self.budget = budget or ResearchBudget()
        self.search_provider = search_provider or WebSearchProvider()
        self.frontier = ExternalResearchFrontier(
            provider=self.search_provider,
            max_queries=self.budget.max_search_queries,
            max_results_per_query=10,
        )
        self.http_client = http_client
        self.start_time = time.time()
        self.stage = ResearchStage.INITIALIZED

        # Counters & State Tracking
        self.internal_pages_count = 0
        self.external_pages_count = 0
        self.duplicate_urls_count = 0
        self.failed_requests_count = 0
        self.discovered_urls: Set[str] = set()

    def _get_job(self) -> CrawlJob:
        job = database.get_crawl_job(self.job_id, db_path=self.db_path)
        if not job:
            raise ValueError(f"Job #{self.job_id} not found in database.")
        return job

    def is_cancelled(self) -> bool:
        return database.is_cancellation_requested(self.job_id, db_path=self.db_path)

    def run(self) -> Dict[str, Any]:
        return self.execute_research_cycle()

    def execute_research_cycle(self) -> Dict[str, Any]:
        """Execute the complete multi-frontier research workflow."""
        job = self._get_job()
        company_name = job.company_name or "Target Company"
        target_product = getattr(job, "target_product", None) or ("Jedox" if job.workflow == WorkflowType.JEDOX else None)
        workflow_str = job.workflow.value if hasattr(job.workflow, "value") else str(job.workflow)
        objective = getattr(job, "objective", None)
        target_domain = normalize_domain(job.seed_url)

        logger.info(
            "Starting Intelligent Research Controller for Job #%d [%s, Product: %s, WF: %s]",
            self.job_id,
            company_name,
            target_product,
            workflow_str,
        )

        # -------------------------------------------------------------
        # Frontier 1: Internal Exploration Progress Sync
        # -------------------------------------------------------------
        self.stage = ResearchStage.INTERNAL_RESEARCH
        database.update_crawl_job_status(self.job_id, CrawlJobStatus.RUNNING, db_path=self.db_path)

        # Read any already crawled internal pages
        existing_pages = database.get_crawled_pages(self.job_id, limit=200, db_path=self.db_path)
        for p in existing_pages:
            self.discovered_urls.add(p.original_url)
            if p.final_url:
                self.discovered_urls.add(p.final_url)
            if getattr(p, "frontier", "INTERNAL") == "INTERNAL":
                self.internal_pages_count += 1

        self.stage = ResearchStage.INTERNAL_COMPLETED

        if self.is_cancelled():
            return self._terminate_job("cancelled")

        # -------------------------------------------------------------
        # Frontier 2: External Web Discovery & Search Expansion
        # -------------------------------------------------------------
        self.stage = ResearchStage.EXTERNAL_RESEARCH
        queries = generate_initial_search_queries(
            company_name=company_name,
            target_product=target_product,
            workflow=workflow_str,
        )

        logger.info("Executing initial external search queries for Job #%d: %s", self.job_id, queries)
        search_results = self.frontier.expand_and_execute_batch(
            queries=queries,
            target_product=target_product,
            company_name=company_name,
            workflow=workflow_str,
            objective=objective,
        )

        # Select top authoritative external pages within retrieval budget
        external_urls_to_fetch: List[SearchResultItem] = []
        for res in search_results:
            if len(external_urls_to_fetch) >= self.budget.max_external_pages_retrieved:
                break
            # Do not re-fetch target company internal domain via external frontier
            res_domain = normalize_domain(res.url)
            if res_domain and res_domain == target_domain:
                continue
            external_urls_to_fetch.append(res)

        logger.info(
            "Retrieved %d search results. Fetching top %d external authority pages.",
            len(search_results),
            len(external_urls_to_fetch),
        )

        # Fetch external authority pages safely
        self._fetch_external_pages(
            items=external_urls_to_fetch,
            target_company_domain=target_domain,
            target_product=target_product,
            workflow=workflow_str,
        )

        self.stage = ResearchStage.EXTERNAL_COMPLETED

        if self.is_cancelled():
            return self._terminate_job("cancelled")

        # -------------------------------------------------------------
        # Shared Extraction & Verification Pipeline (Pass 1)
        # -------------------------------------------------------------
        self.stage = ResearchStage.EXTRACTION
        from candidate_verifier import verify_all_candidates_for_job

        verified_candidates = verify_all_candidates_for_job(self.job_id, db_path=self.db_path)
        self.stage = ResearchStage.EXTRACTION_COMPLETED

        # Check discovered Decision Makers & Customers
        decision_makers = database.get_decision_makers_for_job(self.job_id, db_path=self.db_path)
        contacts = database.get_public_contacts(job_id=self.job_id, db_path=self.db_path)

        # -------------------------------------------------------------
        # Iterative Search Expansion (Pass 2 based on discoveries)
        # -------------------------------------------------------------
        has_exec_dm = any(dm.role_category in (RoleCategory.EXECUTIVE, RoleCategory.FINANCE_BUSINESS) for dm in decision_makers)
        has_contacts = len(contacts) > 0

        if self.frontier.can_execute_more_queries() and (not has_exec_dm or not has_contacts):
            followup_queries = generate_followup_queries(
                company_name=company_name,
                discovered_person_name=decision_makers[0].full_name if decision_makers else None,
                discovered_person_title=decision_makers[0].published_title if decision_makers else None,
                target_product=target_product,
                need_contact_info=not has_contacts,
            )
            if followup_queries:
                logger.info("Executing iterative follow-up queries: %s", followup_queries)
                more_results = self.frontier.expand_and_execute_batch(
                    queries=followup_queries,
                    target_product=target_product,
                    company_name=company_name,
                    workflow=workflow_str,
                    objective=objective,
                )
                extra_fetch = [
                    r for r in more_results
                    if normalize_domain(r.url) != target_domain
                    and r.url not in self.discovered_urls
                ][:3]
                if extra_fetch:
                    self._fetch_external_pages(
                        items=extra_fetch,
                        target_company_domain=target_domain,
                        target_product=target_product,
                        workflow=workflow_str,
                    )
                    # Re-run verification to incorporate iterative discoveries
                    verified_candidates = verify_all_candidates_for_job(self.job_id, db_path=self.db_path)
                    decision_makers = database.get_decision_makers_for_job(self.job_id, db_path=self.db_path)
                    contacts = database.get_public_contacts(job_id=self.job_id, db_path=self.db_path)

        # -------------------------------------------------------------
        # Stopping Conditions & Lead Qualification Assessment
        # -------------------------------------------------------------
        self.stage = ResearchStage.VERIFICATION
        has_confirmed_customer = any(
            c.relationship_type in (RelationshipType.CUSTOMER, RelationshipType.CASE_STUDY)
            and c.classification.value in ("CONFIRMED", "PARTIALLY_VERIFIED")
            for c in verified_candidates
        )
        has_confirmed_product_usage = any(
            c.product_usage_status == "CONFIRMED"
            for c in verified_candidates
        )
        has_verified_dm = any(
            dm.role_category in (RoleCategory.EXECUTIVE, RoleCategory.FINANCE_BUSINESS, RoleCategory.TECHNOLOGY_IT)
            for dm in decision_makers
        )

        final_outcome = "COMPLETED"
        if has_confirmed_customer and has_confirmed_product_usage:
            final_outcome = "LEAD_QUALIFIED"
            self.stage = ResearchStage.LEAD_QUALIFIED
        elif verified_candidates:
            self.stage = ResearchStage.VERIFICATION_COMPLETED
        else:
            self.stage = ResearchStage.RESEARCH_INCOMPLETE

        return self._terminate_job(
            stop_reason="research_objectives_evaluated",
            final_outcome=final_outcome,
        )

    def _fetch_external_pages(
        self,
        items: List[SearchResultItem],
        target_company_domain: str,
        target_product: Optional[str],
        workflow: str,
    ):
        """Fetch and extract content from external authority search results."""
        client = self.http_client or httpx.Client(
            timeout=DEFAULT_TIMEOUT_SEC,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
        should_close = self.http_client is None

        try:
            for item in items:
                url = item.url
                if url in self.discovered_urls:
                    self.duplicate_urls_count += 1
                    continue
                self.discovered_urls.add(url)

                try:
                    validate_url_security(url)
                except Exception as e:
                    logger.debug("Skipping unsafe external URL '%s': %s", url, e)
                    self.failed_requests_count += 1
                    continue

                try:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        parsed = parse_html_data(resp.text, base_url=str(resp.url))
                        source_cat = classify_source(
                            url=str(resp.url),
                            target_company_domain=target_company_domain,
                            target_product=target_product,
                        )
                        content_hash = hashlib.sha256(parsed["text"].encode("utf-8")).hexdigest()

                        now_str = datetime.datetime.now(timezone.utc).isoformat()
                        page = CrawlPage(
                            job_id=self.job_id,
                            original_url=url,
                            final_url=str(resp.url),
                            http_status=resp.status_code,
                            depth=1,
                            discovery_source_url=item.query,
                            title=parsed["title"] or item.title,
                            extracted_text=parsed["text"],
                            headings_json=parsed["headings"],
                            metadata_json=parsed["metadata"],
                            links_count=len(parsed["links"]),
                            word_count=parsed["word_count"],
                            content_hash=content_hash,
                            status=CrawlPageStatus.SUCCESS,
                            retrieved_at=now_str,
                        )
                        # Attach frontier and source_category attributes
                        page.frontier = "EXTERNAL"  # type: ignore
                        page.source_category = source_cat.value  # type: ignore
                        page.priority_score = item.priority_score  # type: ignore

                        database.save_crawled_page(page, db_path=self.db_path)
                        self.external_pages_count += 1
                        database.increment_crawl_job_progress(
                            job_id=self.job_id,
                            pages_crawled_inc=1,
                            db_path=self.db_path,
                        )
                    else:
                        self.failed_requests_count += 1
                except Exception as e:
                    logger.debug("Error fetching external URL '%s': %s", url, e)
                    self.failed_requests_count += 1
        finally:
            if should_close:
                client.close()

    def _terminate_job(self, stop_reason: str, final_outcome: str = "COMPLETED") -> Dict[str, Any]:
        """Finalize job metrics and persist execution status."""
        job_status = CrawlJobStatus.CANCELLED if stop_reason == "cancelled" else CrawlJobStatus.COMPLETED
        database.update_crawl_job_status(self.job_id, job_status, db_path=self.db_path)

        metrics = {
            "internal_pages_retrieved": self.internal_pages_count,
            "external_queries_executed": len(self.frontier.executed_queries),
            "external_urls_discovered": len(self.frontier.all_results),
            "external_pages_retrieved": self.external_pages_count,
            "duplicate_urls_filtered": self.duplicate_urls_count,
            "failed_requests": self.failed_requests_count,
            "research_stage": self.stage,
            "final_outcome": final_outcome,
            "stop_reason": stop_reason,
            "duration_seconds": round(time.time() - self.start_time, 2),
        }

        database.finalize_crawl_job_metrics(
            job_id=self.job_id,
            stop_reason=stop_reason,
            final_outcome=final_outcome,
            db_path=self.db_path,
        )

        # Save extra research metrics to crawl_jobs table
        conn = database.get_connection(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE crawl_jobs
                    SET research_stage = ?,
                        internal_pages_count = ?,
                        external_pages_count = ?,
                        queries_executed_count = ?,
                        external_urls_count = ?,
                        duplicate_urls_count = ?
                    WHERE id = ?
                    """,
                    (
                        self.stage,
                        self.internal_pages_count,
                        self.external_pages_count,
                        len(self.frontier.executed_queries),
                        len(self.frontier.all_results),
                        self.duplicate_urls_count,
                        self.job_id,
                    ),
                )
        except Exception as e:
            logger.debug("Non-fatal metric update error: %s", e)
        finally:
            conn.close()

        logger.info(
            "Research Controller completed Job #%d: Outcome=%s, Stage=%s, Internal=%d, External=%d",
            self.job_id,
            final_outcome,
            self.stage,
            self.internal_pages_count,
            self.external_pages_count,
        )
        return metrics
