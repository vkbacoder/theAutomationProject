// AI Web Research & Data Extraction - Unified Platform Controller
// Integrates Single-Page Scraper (HTTPX) & Recursive Scrapy Crawler into one cohesive frontend

document.addEventListener("DOMContentLoaded", () => {
  // ==========================================
  // DOM ELEMENT REFERENCES
  // ==========================================
  // Unified Control Form & Inputs
  const form = document.getElementById("unified-research-form");
  const crawlParamsPanel = document.getElementById("crawl-params-panel");
  const urlInput = document.getElementById("url-input") || document.getElementById("research-url-input");
  const urlInputLabel = document.getElementById("url-input-label");
  const btnClearUrl = document.getElementById("btn-clear-url");
  const btnStartResearch = document.getElementById("btn-start-research");
  const researchSpinner = document.getElementById("research-spinner");
  const researchBtnText = document.getElementById("research-btn-text");

  // Crawl Parameter Inputs
  const crawlWorkflow = document.getElementById("crawl-workflow");
  const crawlCompanyName = document.getElementById("crawl-company-name");
  const crawlMaxDepth = document.getElementById("crawl-max-depth");
  const crawlMaxPages = document.getElementById("crawl-max-pages");
  const crawlMaxDomain = document.getElementById("crawl-max-domain");

  // Alerts & Notifications
  const errorBanner = document.getElementById("error-banner");
  const errorTitle = document.getElementById("error-title");
  const errorMessage = document.getElementById("error-message");
  const btnDismissError = document.getElementById("btn-dismiss-error");

  // Live Job Monitor & Progress
  const liveJobCard = document.getElementById("live-job-card");
  const jobTitleText = document.getElementById("job-title-text");
  const jobDisplayId = document.getElementById("job-display-id");
  const jobStatusBadge = document.getElementById("job-status-badge");
  const btnCancelCrawl = document.getElementById("btn-cancel-crawl");
  const btnRetryCrawl = document.getElementById("btn-retry-crawl");
  const btnRefreshJob = document.getElementById("btn-refresh-job");
  const btnViewResults = document.getElementById("btn-view-results");
  const jobDisplaySeedUrl = document.getElementById("job-display-seed-url");
  const jobTimingInfo = document.getElementById("job-timing-info");
  const jobLastUpdated = document.getElementById("job-last-updated");
  const jobOutcomeBanner = document.getElementById("job-outcome-banner");
  const jobOutcomeIcon = document.getElementById("job-outcome-icon");
  const jobOutcomeTitle = document.getElementById("job-outcome-title");
  const jobOutcomeMessage = document.getElementById("job-outcome-message");
  const crawlProgressWrapper = document.getElementById("crawl-progress-wrapper");
  const crawlProgressFill = document.getElementById("crawl-progress-fill");
  const crawlProgressText = document.getElementById("crawl-progress-text");

  // Recent Jobs Selector
  const selectRecentJobs = document.getElementById("select-recent-jobs");
  const btnLoadRecentJob = document.getElementById("btn-load-recent-job");

  // Overview Tab References
  const ovJobId = document.getElementById("ov-job-id");
  const ovSeedUrl = document.getElementById("ov-seed-url");
  const ovWorkflow = document.getElementById("ov-workflow");
  const ovCompanyName = document.getElementById("ov-company-name");
  const ovObjective = document.getElementById("ov-objective");
  const ovTargetProduct = document.getElementById("ov-target-product");
  const ovBoundaries = document.getElementById("ov-boundaries");
  const ovStatus = document.getElementById("ov-status");
  const ovStopReason = document.getElementById("ov-stop-reason");
  const ovCountCompanies = document.getElementById("ov-count-companies");
  const ovCountRelVerified = document.getElementById("ov-count-rel-verified");
  const ovCountUsageVerified = document.getElementById("ov-count-usage-verified");
  const ovCountDms = document.getElementById("ov-count-dms");
  const ovCountContacts = document.getElementById("ov-count-contacts");
  const ovCountDocs = document.getElementById("ov-count-docs");
  const ovCountPages = document.getElementById("ov-count-pages");
  const ovCountEvidence = document.getElementById("ov-count-evidence");

  // Top Metric Summary Boxes
  const jobPagesCrawled = document.getElementById("job-pages-crawled");
  const jobDiscoveredUrls = document.getElementById("job-discovered-urls");
  const jobPagesFailed = document.getElementById("job-pages-failed");
  const jobMaxDepth = document.getElementById("job-max-depth");

  // 11 Detailed Metrics Grid
  const metricsOutcomeBadge = document.getElementById("metrics-outcome-badge");
  const metricRequestsAttempted = document.getElementById("metric-requests-attempted");
  const metricResponsesDownloaded = document.getElementById("metric-responses-downloaded");
  const metricUniqueSaved = document.getElementById("metric-unique-saved");
  const metricUsefulPages = document.getElementById("metric-useful-pages");
  const metricThinPages = document.getElementById("metric-thin-pages");
  const metricDupesFiltered = document.getElementById("metric-dupes-filtered");
  const metricFailedRequests = document.getElementById("metric-failed-requests");
  const metricDownloadBytes = document.getElementById("metric-download-bytes");
  const metricDuration = document.getElementById("metric-duration");
  const metricEvidenceLinked = document.getElementById("metric-evidence-linked");
  const metricStopReason = document.getElementById("metric-stop-reason");

  // Cooperative Intelligence Callout
  const coopIntelligenceSection = document.getElementById("coop-intelligence-section");
  const coopDetectedChips = document.getElementById("coop-detected-chips");

  // Workspace Results Table & Filters
  const workspaceSection = document.getElementById("intel-workspace-section") || document.getElementById("workspace-section");
  const workspaceResultsCount = document.getElementById("workspace-results-count");
  const workspaceSearchInput = document.getElementById("workspace-search-input");
  const workspaceStatusFilter = document.getElementById("workspace-status-filter");
  const workspaceSortSelect = document.getElementById("workspace-sort-select");
  const workspaceTbody = document.getElementById("workspace-tbody");
  const btnExportCsv = document.getElementById("btn-export-csv");
  const btnExportJson = document.getElementById("btn-export-json");

  // Record Inspection Modal & Tabs
  const recordModal = document.getElementById("record-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const modalPageTitle = document.getElementById("modal-page-title");
  const modalDepthBadge = document.getElementById("modal-depth-badge");
  const modalStatusBadge = document.getElementById("modal-status-badge");
  const modalPageUrl = document.getElementById("modal-page-url");
  const modalHttpStatus = document.getElementById("modal-http-status");
  const modalWordCount = document.getElementById("modal-word-count");
  const modalEvidenceTag = document.getElementById("modal-evidence-tag");

  // Modal Content Tabs
  const modalTabBtns = document.querySelectorAll(".modal-tab-btn");
  const modalTabContents = document.querySelectorAll(".modal-tab-content");
  const modalTextStats = document.getElementById("modal-text-stats");
  const modalTextBody = document.getElementById("modal-text-body");
  const btnModalCopyText = document.getElementById("btn-modal-copy-text");

  const modalCountH1 = document.getElementById("modal-count-h1");
  const modalCountH2 = document.getElementById("modal-count-h2");
  const modalCountH3 = document.getElementById("modal-count-h3");
  const modalListH1 = document.getElementById("modal-list-h1");
  const modalListH2 = document.getElementById("modal-list-h2");
  const modalListH3 = document.getElementById("modal-list-h3");

  const modalMetaTbody = document.getElementById("modal-meta-tbody");
  const modalEvidenceDetails = document.getElementById("modal-evidence-details");
  const modalJsonBody = document.getElementById("modal-json-body");
  const btnModalCopyJson = document.getElementById("btn-modal-copy-json");

  // Preset Chips
  const presetChips = document.querySelectorAll(".preset-chip");

  // ==========================================
  // APPLICATION STATE
  // ==========================================
  let activeCrawlJobId = null;
  let crawlPollTimer = null;
  let workspaceRecords = []; // Normalized records array
  let currentInspectedRecord = null;
  let currentJobData = null;

  // Cooperative Topics Dictionary for Keyword Scanning
  const COOP_TOPICS = [
    { label: "PACS (Primary Agricultural Credit)", key: "pacs", pattern: /\bpacs\b|primary agricultural/i },
    { label: "Dairy Cooperatives", key: "dairy", pattern: /\bdairy\b|\bmilk\b/i },
    { label: "Fisheries Cooperatives", key: "fisheries", pattern: /\bfisher(y|ies)\b|\bmatsya\b/i },
    { label: "Multi-State Cooperatives (MSCS)", key: "mscs", pattern: /\bmulti-state\b|\bmscs\b/i },
    { label: "National Database (NCD)", key: "ncd", pattern: /\bncd\b|national cooperative database/i },
    { label: "Credit & Banking Societies", key: "credit", pattern: /\bcredit societ(y|ies)\b|\bcooperative bank\b/i },
    { label: "Model Bye-Laws & Rules", key: "byelaws", pattern: /\bbye[- ]?laws\b|\brules\b|\bguidelines\b/i },
    { label: "Ministry Initiatives", key: "ministry", pattern: /\bministry of cooperation\b|\bsahakar se samriddhi\b/i }
  ];

  // ==========================================
  // INITIALIZATION & EVENT HANDLERS
  // ==========================================

  // Presets
  if (presetChips) {
    presetChips.forEach(chip => {
      chip.addEventListener("click", () => {
        const url = chip.getAttribute("data-url");
        if (url && urlInput) {
          urlInput.value = url;
          urlInput.focus();
        }
      });
    });
  }

  // Clear URL button
  if (btnClearUrl) {
    btnClearUrl.addEventListener("click", () => {
      if (urlInput) {
        urlInput.value = "";
        urlInput.focus();
      }
      hideError();
    });
  }

  // Dismiss error
  if (btnDismissError) btnDismissError.addEventListener("click", hideError);

  // Start Research Button Click & Form Submission Handlers
  if (btnStartResearch) {
    btnStartResearch.addEventListener("click", (e) => {
      e.preventDefault();
      startResearch();
    });
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      startResearch();
    });
  }

  if (urlInput) {
    urlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        startResearch();
      }
    });
  }

  // Cancel Job
  if (btnCancelCrawl) btnCancelCrawl.addEventListener("click", cancelActiveCrawlJob);

  // Retry Failed
  if (btnRetryCrawl) btnRetryCrawl.addEventListener("click", retryActiveCrawlJob);

  // Manual Refresh
  if (btnRefreshJob) {
    btnRefreshJob.addEventListener("click", () => {
      if (activeCrawlJobId) {
        pollJobDetails(activeCrawlJobId);
        pollJobMetrics(activeCrawlJobId);
        pollJobResults(activeCrawlJobId);
      }
    });
  }

  // View Results Button (Scroll to results workspace)
  if (btnViewResults) {
    btnViewResults.addEventListener("click", () => {
      if (workspaceSection) {
        workspaceSection.classList.remove("hidden");
        workspaceSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      if (activeCrawlJobId && intelCandidates.length === 0) {
        runCandidateVerificationAndFetchIntel(activeCrawlJobId);
      }
    });
  }

  // Recent Jobs Selector Handlers
  if (selectRecentJobs) {
    selectRecentJobs.addEventListener("change", () => {
      const val = selectRecentJobs.value;
      if (val) loadJobById(parseInt(val, 10));
    });
  }
  if (btnLoadRecentJob) {
    btnLoadRecentJob.addEventListener("click", () => {
      if (selectRecentJobs && selectRecentJobs.value) {
        loadJobById(parseInt(selectRecentJobs.value, 10));
      }
    });
  }

  // Table Search and Filtering
  if (workspaceSearchInput) workspaceSearchInput.addEventListener("input", renderWorkspaceTable);
  if (workspaceStatusFilter) workspaceStatusFilter.addEventListener("change", renderWorkspaceTable);
  if (workspaceSortSelect) workspaceSortSelect.addEventListener("change", renderWorkspaceTable);

  // CSV & JSON Exports
  if (btnExportCsv) btnExportCsv.addEventListener("click", exportAsCsv);
  if (btnExportJson) btnExportJson.addEventListener("click", exportAsJson);

  // Modal Close Handlers
  if (btnCloseModal) btnCloseModal.addEventListener("click", closeRecordModal);
  if (recordModal) {
    recordModal.addEventListener("click", (e) => {
      if (e.target === recordModal) closeRecordModal();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && recordModal && !recordModal.classList.contains("hidden")) {
      closeRecordModal();
    }
  });

  // Modal Copy Buttons
  if (btnModalCopyText) {
    btnModalCopyText.addEventListener("click", () => {
      if (modalTextBody) copyToClipboard(modalTextBody.textContent, btnModalCopyText, "📋 Copy Full Text");
    });
  }
  if (btnModalCopyJson) {
    btnModalCopyJson.addEventListener("click", () => {
      if (modalJsonBody) copyToClipboard(modalJsonBody.textContent, btnModalCopyJson, "📋 Copy JSON");
    });
  }

  // Modal Tab Switching
  if (modalTabBtns) {
    modalTabBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-target");
        modalTabBtns.forEach(b => b.classList.remove("active"));
        if (modalTabContents) modalTabContents.forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        const targetContent = document.getElementById(targetId);
        if (targetContent) targetContent.classList.add("active");
      });
    });
  }

  // ==========================================
  // CORE RESEARCH WORKFLOW
  // ==========================================
  async function startResearch() {
    hideError();
    const rawUrl = urlInput ? urlInput.value.trim() : "";

    // Validation
    if (!rawUrl) {
      showError("URL Required", "Please enter a valid HTTP or HTTPS destination URL to proceed.");
      if (urlInput) urlInput.focus();
      return;
    }

    let targetUrl = rawUrl;
    if (!targetUrl.startsWith("http://") && !targetUrl.startsWith("https://")) {
      targetUrl = "https://" + targetUrl;
      if (urlInput) urlInput.value = targetUrl;
    }

    // Primary Research Workflow: Recursive Website Crawl
    await executeWebsiteCrawl(targetUrl);
  }

  // ------------------------------------------
  // MODE A: SINGLE-PAGE EXTRACTION
  // ------------------------------------------
  async function executeSinglePageScrape(url) {
    setLoading(true, "Scraping Target Page...");
    if (crawlPollTimer) {
      clearInterval(crawlPollTimer);
      crawlPollTimer = null;
    }
    activeCrawlJobId = null;

    // Show live monitor card in Single-Page mode
    if (liveJobCard) liveJobCard.classList.remove("hidden");
    if (jobTitleText) jobTitleText.textContent = "Single-Page Ingestion";
    if (jobDisplayId) jobDisplayId.textContent = "DIRECT";
    if (jobStatusBadge) {
      jobStatusBadge.textContent = "INGESTING";
      jobStatusBadge.className = "badge badge-running";
    }
    if (btnCancelCrawl) btnCancelCrawl.disabled = true;
    if (btnRetryCrawl) btnRetryCrawl.classList.add("hidden");
    if (btnRefreshJob) btnRefreshJob.classList.add("hidden");

    if (crawlProgressFill) crawlProgressFill.style.width = "40%";
    if (crawlProgressText) crawlProgressText.textContent = "Connecting with SSRF & TLS verification...";
    if (jobPagesCrawled) jobPagesCrawled.textContent = "0";
    if (jobDiscoveredUrls) jobDiscoveredUrls.textContent = "0";
    if (jobPagesFailed) jobPagesFailed.textContent = "0";
    if (jobMaxDepth) jobMaxDepth.textContent = "0";

    try {
      const startTime = performance.now();
      const response = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url })
      });

      const elapsedSec = ((performance.now() - startTime) / 1000).toFixed(2);
      const data = await response.json();

      // Clear loading UI
      setLoading(false);

      if (!response.ok && !data.title && !data.error) {
        showError("Scrape Failed (HTTP " + response.status + ")", data.detail || "Server returned an error.");
        jobStatusBadge.textContent = "FAILED";
        jobStatusBadge.className = "badge badge-danger";
        crawlProgressFill.style.width = "100%";
        crawlProgressText.textContent = "Request Failed";
        return;
      }

      // Check extraction outcome vs transport
      const isExtractionSuccess = Boolean(data.success);
      const httpCode = data.status_code || (isExtractionSuccess ? 200 : 0);

      // Normalize into a workspace page record
      const normalizedRecord = {
        id: "single-1",
        depth: 0,
        title: data.title || (isExtractionSuccess ? "Webpage Content" : "Extraction Error"),
        original_url: data.url || url,
        final_url: data.final_url || data.url || url,
        http_status: httpCode,
        extraction_status: isExtractionSuccess ? "SUCCESS" : "FAILED",
        word_count: data.word_count || 0,
        evidence_id: null,
        extracted_text: data.text || "",
        headings_json: data.headings || { h1: [], h2: [], h3: [] },
        metadata_json: data.metadata || { description: data.description, canonical: data.canonical_url, content_type: data.content_type },
        error_message: data.error || (isExtractionSuccess ? null : "Extraction flagged false by engine"),
        source_mode: "single",
        raw_record: data
      };

      workspaceRecords = [normalizedRecord];

      // Update Live Card
      jobStatusBadge.textContent = isExtractionSuccess ? "COMPLETED" : "FAILED";
      jobStatusBadge.className = isExtractionSuccess ? "badge badge-success" : "badge badge-danger";
      crawlProgressFill.style.width = "100%";
      crawlProgressText.textContent = isExtractionSuccess ? "Single-Page Ingestion Complete (1/1)" : "Extraction Failed";
      jobPagesCrawled.textContent = isExtractionSuccess ? "1" : "0";
      jobDiscoveredUrls.textContent = (data.links && data.links.length) ? String(data.links.length) : "0";
      jobPagesFailed.textContent = isExtractionSuccess ? "0" : "1";
      jobMaxDepth.textContent = "0";

      // Update 11 Metrics Grid (Distinguish single-page N/A from zeros)
      metricsOutcomeBadge.textContent = isExtractionSuccess ? "Outcome: Success (Single-Page)" : "Outcome: Extraction Error";
      metricsOutcomeBadge.style.background = isExtractionSuccess ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)";
      metricsOutcomeBadge.style.color = isExtractionSuccess ? "var(--accent-success)" : "var(--accent-danger)";

      metricRequestsAttempted.textContent = "1";
      metricResponsesDownloaded.textContent = isExtractionSuccess ? "1" : "0";
      metricUniqueSaved.textContent = isExtractionSuccess ? "1" : "0";
      metricUsefulPages.textContent = (isExtractionSuccess && (data.word_count || 0) > 20) ? "1" : "0";
      metricThinPages.textContent = (isExtractionSuccess && (data.word_count || 0) <= 20) ? "1" : "0";
      metricDupesFiltered.textContent = "N/A"; // Distinct from zero for single-page
      metricFailedRequests.textContent = isExtractionSuccess ? "0" : "1";
      
      const byteLen = data.text ? new Blob([data.text]).size : 0;
      metricDownloadBytes.textContent = byteLen > 0 ? formatBytes(byteLen) : "N/A";
      metricDuration.textContent = `${elapsedSec}s`;
      metricEvidenceLinked.textContent = "N/A"; // Evidence records are created during company crawl jobs
      metricStopReason.textContent = isExtractionSuccess ? "HTTP_200_OK" : (data.error || "FAILED");

      // Show sections
      if (workspaceSection) workspaceSection.classList.remove("hidden");
      renderWorkspaceTable();
      updateCooperativeIntelligence(workspaceRecords);

      if (!isExtractionSuccess && data.error) {
        showError("Extraction Completed with Error", data.error);
      }

    } catch (err) {
      setLoading(false);
      showError("Network / API Error", err.message || "Failed to communicate with /api/scrape");
      jobStatusBadge.textContent = "ERROR";
      jobStatusBadge.className = "badge badge-danger";
    }
  }

  // ------------------------------------------
  // MODE B: RECURSIVE WEBSITE CRAWL
  // ------------------------------------------
  async function executeWebsiteCrawl(url) {
    setLoading(true, "Submitting Crawl Job...");
    if (crawlPollTimer) {
      clearInterval(crawlPollTimer);
      crawlPollTimer = null;
    }
    workspaceRecords = [];

    const crawlObjective = document.getElementById("crawl-objective");
    const crawlTargetProduct = document.getElementById("crawl-target-product");

    const payload = {
      url: url,
      workflow: crawlWorkflow.value || "GENERAL",
      company_name: crawlCompanyName.value.trim() || undefined,
      objective: (crawlObjective && crawlObjective.value.trim()) || undefined,
      target_product: (crawlTargetProduct && crawlTargetProduct.value.trim()) || undefined,
      max_depth: parseInt(crawlMaxDepth.value, 10) || 2,
      max_pages: parseInt(crawlMaxPages.value, 10) || 20,
      max_pages_per_domain: parseInt(crawlMaxDomain.value, 10) || 20
    };

    let job = null;
    try {
      const resp = await fetch("/api/crawl/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      job = await resp.json();

      if (!resp.ok) {
        setLoading(false);
        console.error("Crawl dispatch rejected by API:", resp.status, job);
        showError("Failed to Start Crawl Job", job.detail || `Crawl job submission rejected with HTTP ${resp.status}`);
        return;
      }
    } catch (netErr) {
      setLoading(false);
      console.error("Crawl Dispatch Network Exception:", netErr);
      showError("Crawl Dispatch Error", `${netErr.message || "Unable to reach /api/crawl/jobs"}\n${netErr.stack || ""}`);
      return;
    }

    // Keep button in crawling progress state during background execution
    setLoading(true, `🕷️ Crawling... (Job #${job.id})`);
    console.info("Crawl job successfully created on server. Job ID:", job.id, "Status:", job.status);
    activeCrawlJobId = job.id;
    currentJobData = job;

    // Refresh recent jobs list so the new job appears
    fetchRecentJobs();

    // Perform UI updates with dedicated error handling so a cosmetic issue never masks successful creation
    try {
      displayCrawlJobHeader(job);
      if (liveJobCard) {
        liveJobCard.classList.remove("hidden");
        liveJobCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      if (workspaceSection) workspaceSection.classList.remove("hidden");
    } catch (uiErr) {
      console.error("Diagnostic: Error updating UI header for job #" + job.id + ":", uiErr);
    }

    // Always initiate polling for the created job
    try {
      startJobPolling(job.id);
    } catch (pollErr) {
      console.error("Diagnostic: Error starting polling for job #" + job.id + ":", pollErr);
    }
  }

  // ------------------------------------------
  // CRAWL JOB POLLING & MONITORING
  // ------------------------------------------
  function startJobPolling(jobId) {
    if (crawlPollTimer) clearInterval(crawlPollTimer);

    // Initial immediate fetch
    pollJobDetails(jobId);
    pollJobMetrics(jobId);
    pollJobResults(jobId);

    crawlPollTimer = setInterval(async () => {
      const isJobDone = await pollJobDetails(jobId);
      await pollJobMetrics(jobId);
      await pollJobResults(jobId);

      if (isJobDone) {
        clearInterval(crawlPollTimer);
        crawlPollTimer = null;
        setLoading(false);
        if (btnRefreshJob) btnRefreshJob.classList.remove("hidden");
        fetchRecentJobs();
        await runCandidateVerificationAndFetchIntel(jobId);
      }
    }, 2000);
  }

  async function pollJobDetails(jobId) {
    try {
      const resp = await fetch(`/api/crawl/jobs/${jobId}`);
      if (!resp.ok) {
        console.warn(`Poll job details returned HTTP ${resp.status}`);
        return false;
      }
      const job = await resp.json();
      currentJobData = job;
      displayCrawlJobHeader(job);
      return (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED");
    } catch (err) {
      console.warn("Poll job details error:", err);
      if (jobLastUpdated) jobLastUpdated.textContent = "Reconnecting...";
      return false;
    }
  }

  async function pollJobMetrics(jobId) {
    try {
      const resp = await fetch(`/api/crawl/jobs/${jobId}/metrics`);
      if (!resp.ok) return;
      const metrics = await resp.json();
      displayMetricsGrid(metrics);
    } catch (err) {
      console.warn("Poll metrics error:", err);
    }
  }

  async function pollJobResults(jobId) {
    try {
      const resp = await fetch(`/api/crawl/jobs/${jobId}/results?limit=300`);
      if (!resp.ok) return;
      const pages = await resp.json();

      // Normalize records
      workspaceRecords = pages.map(p => ({
        id: p.id,
        depth: p.depth !== undefined ? p.depth : 0,
        title: p.title || p.original_url,
        original_url: p.original_url,
        final_url: p.final_url || p.original_url,
        http_status: p.http_status || (p.status === "SUCCESS" ? 200 : null),
        extraction_status: p.status || "UNKNOWN",
        word_count: p.word_count || 0,
        evidence_id: p.evidence_id || null,
        extracted_text: p.extracted_text || "",
        headings_json: p.headings_json || { h1: [], h2: [], h3: [] },
        metadata_json: p.metadata_json || {},
        error_message: p.error_message || null,
        source_mode: "crawl",
        raw_record: p
      }));

      renderWorkspaceTable();
      updateCooperativeIntelligence(workspaceRecords);

    } catch (err) {
      console.warn("Poll results error:", err);
    }
  }

  function formatDuration(seconds) {
    if (isNaN(seconds) || seconds < 0) return "0s";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function displayCrawlJobHeader(job) {
    if (!job) return;
    if (liveJobCard) liveJobCard.classList.remove("hidden");
    if (jobTitleText) jobTitleText.textContent = "Recursive Crawl Job #";
    if (jobDisplayId) jobDisplayId.textContent = job.id ? String(job.id) : "-";

    // Explicit Status Badge
    if (jobStatusBadge) {
      const s = (job.status || "PENDING").toUpperCase();
      if (s === "COMPLETED") {
        jobStatusBadge.textContent = "COMPLETED";
        jobStatusBadge.className = "badge badge-completed";
      } else if (s === "RUNNING") {
        jobStatusBadge.textContent = "RUNNING";
        jobStatusBadge.className = "badge badge-running";
      } else if (s === "FAILED") {
        jobStatusBadge.textContent = "FAILED";
        jobStatusBadge.className = "badge badge-failed";
      } else if (s === "CANCELLED") {
        jobStatusBadge.textContent = "CANCELLED";
        jobStatusBadge.className = "badge badge-cancelled";
      } else {
        jobStatusBadge.textContent = "QUEUED / PENDING";
        jobStatusBadge.className = "badge badge-pending";
      }
    }

    // Seed URL
    if (jobDisplaySeedUrl) {
      jobDisplaySeedUrl.textContent = job.seed_url || "Not available";
      jobDisplaySeedUrl.href = job.seed_url || "#";
    }

    // Timing Information
    if (jobTimingInfo) {
      const startTimeStr = job.created_at ? new Date(job.created_at).toLocaleTimeString() : "-";
      let elapsedSec = 0;
      if (job.created_at) {
        const startMs = new Date(job.created_at).getTime();
        const endMs = (job.status === "COMPLETED" || job.status === "FAILED" || job.status === "CANCELLED") && job.updated_at
          ? new Date(job.updated_at).getTime()
          : Date.now();
        elapsedSec = Math.max(0, Math.floor((endMs - startMs) / 1000));
      }
      jobTimingInfo.textContent = `Started: ${startTimeStr} • Elapsed: ${formatDuration(elapsedSec)}`;
    }

    // Last Status Update Time
    if (jobLastUpdated) {
      jobLastUpdated.textContent = new Date().toLocaleTimeString();
    }

    // Meaningful Progress Bar
    const maxP = job.max_pages || 20;
    const crawled = job.pages_crawled || 0;
    const pct = Math.min(100, Math.round((crawled / maxP) * 100));
    if (crawlProgressFill) crawlProgressFill.style.width = `${pct}%`;
    if (crawlProgressText) {
      if (job.status === "RUNNING" && crawled === 0) {
        crawlProgressFill.style.width = "20%";
        crawlProgressText.textContent = `0 / ${maxP} Pages Crawled (Connecting & discovering pages...)`;
      } else {
        crawlProgressText.textContent = `${crawled} / ${maxP} Pages Crawled (${pct}% of page limit)`;
      }
    }

    // Counters
    if (jobPagesCrawled) jobPagesCrawled.textContent = crawled.toLocaleString();
    if (jobDiscoveredUrls) jobDiscoveredUrls.textContent = (job.discovered_urls_count || 0).toLocaleString();
    if (jobPagesFailed) jobPagesFailed.textContent = (job.pages_failed || 0).toLocaleString();
    if (jobMaxDepth) {
      const curDepth = (job.metrics && job.metrics.request_depth_max !== undefined) ? job.metrics.request_depth_max : (job.depth_reached !== undefined ? job.depth_reached : 0);
      jobMaxDepth.textContent = `${curDepth} / ${job.max_depth || 2}`;
    }

    // Outcome Message Banner
    if (jobOutcomeBanner) {
      const reason = (job.metrics && job.metrics.stop_reason) ? job.metrics.stop_reason : "";
      if (job.status === "COMPLETED") {
        jobOutcomeBanner.className = "job-outcome-banner banner-success";
        if (jobOutcomeIcon) jobOutcomeIcon.textContent = "✅";
        if (jobOutcomeTitle) jobOutcomeTitle.textContent = "Crawl Finished Successfully";
        if (jobOutcomeMessage) jobOutcomeMessage.textContent = `Ingested ${crawled} page(s). Stop reason: ${reason || "Reached configured limits"}. Research findings verified below.`;
        jobOutcomeBanner.classList.remove("hidden");
      } else if (job.status === "FAILED") {
        jobOutcomeBanner.className = "job-outcome-banner banner-danger";
        if (jobOutcomeIcon) jobOutcomeIcon.textContent = "❌";
        if (jobOutcomeTitle) jobOutcomeTitle.textContent = "Crawl Job Failed";
        if (jobOutcomeMessage) jobOutcomeMessage.textContent = reason || job.error_message || "The crawl terminated prematurely with errors.";
        jobOutcomeBanner.classList.remove("hidden");
      } else if (job.status === "CANCELLED") {
        jobOutcomeBanner.className = "job-outcome-banner banner-warning";
        if (jobOutcomeIcon) jobOutcomeIcon.textContent = "⏹️";
        if (jobOutcomeTitle) jobOutcomeTitle.textContent = "Crawl Job Cancelled";
        if (jobOutcomeMessage) jobOutcomeMessage.textContent = "Crawl execution was cancelled by user.";
        jobOutcomeBanner.classList.remove("hidden");
      } else {
        jobOutcomeBanner.classList.add("hidden");
      }
    }

    // Button states
    if (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED") {
      setLoading(false);
    }
    if (btnCancelCrawl) {
      btnCancelCrawl.disabled = (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED");
    }
    if (btnRetryCrawl) {
      if (job.status === "FAILED" || (job.pages_failed > 0 && job.status === "COMPLETED")) {
        btnRetryCrawl.classList.remove("hidden");
      } else {
        btnRetryCrawl.classList.add("hidden");
      }
    }

    // Update Overview Tab Configuration
    updateOverviewTab(job);
  }

  function updateOverviewTab(job) {
    if (!job) return;
    if (ovJobId) ovJobId.textContent = `#${job.id}`;
    if (ovSeedUrl) {
      ovSeedUrl.textContent = job.seed_url || "Not available";
      ovSeedUrl.href = job.seed_url || "#";
    }
    if (ovWorkflow) ovWorkflow.textContent = job.workflow || "GENERAL";
    if (ovCompanyName) ovCompanyName.textContent = job.company_name || "None specified";
    if (ovObjective) ovObjective.textContent = job.objective || "Standard Business Intelligence";
    if (ovTargetProduct) ovTargetProduct.textContent = job.target_product || "None specified";
    if (ovBoundaries) {
      ovBoundaries.textContent = `Max Depth: ${job.max_depth || 2} • Max Pages: ${job.max_pages || 20} • Max/Domain: ${job.max_pages_per_domain || 20}`;
    }
    if (ovStatus) {
      ovStatus.textContent = job.status || "UNKNOWN";
      if (job.status === "COMPLETED") ovStatus.className = "badge badge-completed";
      else if (job.status === "RUNNING") ovStatus.className = "badge badge-running";
      else if (job.status === "FAILED") ovStatus.className = "badge badge-failed";
      else if (job.status === "CANCELLED") ovStatus.className = "badge badge-cancelled";
      else ovStatus.className = "badge badge-pending";
    }
    if (ovStopReason) {
      const reason = (job.metrics && job.metrics.stop_reason) ? job.metrics.stop_reason : (job.status === "RUNNING" ? "Active / In Progress" : "Not available");
      ovStopReason.textContent = `Stop Reason: ${reason}`;
    }

    // Findings count from real data
    if (ovCountCompanies) ovCountCompanies.textContent = intelCandidates.length;
    if (ovCountRelVerified) ovCountRelVerified.textContent = intelCandidates.filter(c => (c.checklist && c.checklist.relationship_verified) || c.relationship_verified || c.relationship_type === "CUSTOMER" || c.relationship_type === "CLIENT").length;
    if (ovCountUsageVerified) ovCountUsageVerified.textContent = intelCandidates.filter(c => (c.checklist && c.checklist.product_usage_verified) || c.product_usage_verified || c.product_usage_status === "CONFIRMED").length;
    if (ovCountDms) ovCountDms.textContent = intelDecisionMakers.length;
    if (ovCountContacts) ovCountContacts.textContent = intelContacts.length;
    if (ovCountDocs) ovCountDocs.textContent = intelDocuments.length;
    if (ovCountPages) ovCountPages.textContent = (job.pages_crawled || workspaceRecords.length || 0);
    if (ovCountEvidence) ovCountEvidence.textContent = intelEvidence.length;
  }

  function displayMetricsGrid(metrics) {
    if (!metrics) return;
    const m = metrics.metrics || metrics;

    metricsOutcomeBadge.textContent = `Outcome: ${m.final_outcome || "In Progress"}`;
    if (m.final_outcome === "COMPLETED") {
      metricsOutcomeBadge.style.background = "rgba(16, 185, 129, 0.2)";
      metricsOutcomeBadge.style.color = "var(--accent-success)";
    } else if (m.final_outcome === "FAILED") {
      metricsOutcomeBadge.style.background = "rgba(239, 68, 68, 0.2)";
      metricsOutcomeBadge.style.color = "var(--accent-danger)";
    } else {
      metricsOutcomeBadge.style.background = "rgba(245, 158, 11, 0.2)";
      metricsOutcomeBadge.style.color = "var(--accent-warning)";
    }

    metricRequestsAttempted.textContent = (m.requests_attempted || 0).toLocaleString();
    metricResponsesDownloaded.textContent = (m.responses_downloaded || 0).toLocaleString();
    metricUniqueSaved.textContent = (m.unique_pages_saved || 0).toLocaleString();
    metricUsefulPages.textContent = (m.useful_pages || 0).toLocaleString();
    metricThinPages.textContent = (m.empty_thin_pages || 0).toLocaleString();
    metricDupesFiltered.textContent = (m.dupes_filtered || 0).toLocaleString();
    metricFailedRequests.textContent = (m.failed_requests || 0).toLocaleString();
    
    const bytes = m.total_response_bytes || 0;
    metricDownloadBytes.textContent = formatBytes(bytes);

    metricDuration.textContent = m.crawl_duration_sec ? `${m.crawl_duration_sec.toFixed(1)}s` : "-";
    metricEvidenceLinked.textContent = (m.evidence_records_created || 0).toLocaleString();
    metricStopReason.textContent = m.stop_reason || "Not available";
  }

  // ------------------------------------------
  // RECENT JOBS MANAGEMENT
  // ------------------------------------------
  async function fetchRecentJobs() {
    if (!selectRecentJobs) return;
    try {
      const resp = await fetch("/api/crawl/jobs?limit=25");
      if (!resp.ok) return;
      const jobs = await resp.json();
      selectRecentJobs.innerHTML = '<option value="">-- Load a Previous Job --</option>';
      jobs.forEach(j => {
        const opt = document.createElement("option");
        opt.value = j.id;
        opt.textContent = `Job #${j.id} - ${j.seed_url} [${j.status}] (${j.pages_crawled || 0} pages)`;
        selectRecentJobs.appendChild(opt);
      });
    } catch (err) {
      console.warn("Failed to load recent jobs:", err);
    }
  }

  async function loadJobById(jobId) {
    if (!jobId) return;
    activeCrawlJobId = jobId;
    if (crawlPollTimer) {
      clearInterval(crawlPollTimer);
      crawlPollTimer = null;
    }
    try {
      const resp = await fetch(`/api/crawl/jobs/${jobId}`);
      if (!resp.ok) {
        showError("Job Not Found", `Could not retrieve crawl job #${jobId}`);
        return;
      }
      const job = await resp.json();
      currentJobData = job;
      displayCrawlJobHeader(job);
      if (liveJobCard) {
        liveJobCard.classList.remove("hidden");
        liveJobCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      if (workspaceSection) workspaceSection.classList.remove("hidden");

      await pollJobMetrics(jobId);
      await pollJobResults(jobId);

      const isTerminal = (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED");
      if (isTerminal) {
        await runCandidateVerificationAndFetchIntel(jobId);
      } else {
        startJobPolling(jobId);
      }
    } catch (e) {
      console.error("Failed to load job:", e);
      showError("Error Loading Job", e.message || "Failed to communicate with API");
    }
  }

  // ------------------------------------------
  // CRAWL ACTIONS: CANCEL & RETRY
  // ------------------------------------------
  async function cancelActiveCrawlJob() {
    if (!activeCrawlJobId) return;
    btnCancelCrawl.disabled = true;
    try {
      const resp = await fetch(`/api/crawl/jobs/${activeCrawlJobId}/cancel`, { method: "POST" });
      const res = await resp.json();
      if (res.success) {
        jobStatusBadge.textContent = "CANCELLED";
        jobStatusBadge.className = "badge badge-cancelled";
        crawlProgressText.textContent = "Crawl cancelled by user";
      }
    } catch (err) {
      showError("Cancel Failed", err.message);
    }
  }

  async function retryActiveCrawlJob() {
    if (!activeCrawlJobId) return;
    btnRetryCrawl.disabled = true;
    try {
      const resp = await fetch(`/api/crawl/jobs/${activeCrawlJobId}/retry`, { method: "POST" });
      const newJob = await resp.json();
      btnRetryCrawl.disabled = false;
      if (resp.ok) {
        activeCrawlJobId = newJob.id;
        displayCrawlJobHeader(newJob);
        startJobPolling(newJob.id);
      } else {
        showError("Retry Failed", newJob.detail || "Unable to retry crawl job.");
      }
    } catch (err) {
      btnRetryCrawl.disabled = false;
      showError("Retry Error", err.message);
    }
  }

  // ==========================================
  // COOPERATIVE INTELLIGENCE DISCOVERY SCAN
  // ==========================================
  function updateCooperativeIntelligence(records) {
    if (!coopIntelligenceSection || !coopDetectedChips) return;
    if (!records || records.length === 0) {
      coopIntelligenceSection.classList.add("hidden");
      return;
    }

    // Combine extracted text across all records
    const detectedCounts = {};
    let totalMentions = 0;

    COOP_TOPICS.forEach(topic => {
      detectedCounts[topic.key] = { label: topic.label, count: 0 };
    });

    records.forEach(r => {
      const content = `${r.title || ""} ${r.extracted_text || ""}`;
      COOP_TOPICS.forEach(topic => {
        const matches = content.match(new RegExp(topic.pattern, "gi"));
        if (matches) {
          detectedCounts[topic.key].count += matches.length;
          totalMentions += matches.length;
        }
      });
    });

    coopDetectedChips.innerHTML = "";

    // Always render section if research has occurred
    coopIntelligenceSection.classList.remove("hidden");

    let hasAnyChip = false;
    Object.keys(detectedCounts).forEach(key => {
      const item = detectedCounts[key];
      if (item.count > 0) {
        hasAnyChip = true;
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "coop-chip";
        chip.innerHTML = `<strong>${escapeHtml(item.label)}</strong> <span class="badge" style="background:var(--bg-main); font-size:0.75rem;">${item.count} mentions</span>`;
        chip.title = `Click to filter workspace table for ${item.label}`;
        chip.addEventListener("click", () => {
          workspaceSearchInput.value = item.label.split(" ")[0]; // Search by first keyword
          renderWorkspaceTable();
          workspaceSearchInput.focus();
        });
        coopDetectedChips.appendChild(chip);
      }
    });

    if (!hasAnyChip) {
      const notice = document.createElement("span");
      notice.className = "text-muted";
      notice.style.fontSize = "0.85rem";
      notice.textContent = "General web content detected; no specialized cooperative registry sectors found in current pages.";
      coopDetectedChips.appendChild(notice);
    }
  }

  // ==========================================
  // RESULTS WORKSPACE: SEARCH, SORT & TABLE
  // ==========================================
  function getFilteredAndSortedRecords() {
    const searchTerm = workspaceSearchInput.value.trim().toLowerCase();
    const statusFilter = workspaceStatusFilter.value;
    const sortBy = workspaceSortSelect.value;

    let filtered = workspaceRecords.filter(r => {
      // Status filter
      if (statusFilter === "SUCCESS" && r.extraction_status !== "SUCCESS") return false;
      if (statusFilter === "FAILED" && r.extraction_status === "SUCCESS") return false;

      // Text search
      if (searchTerm) {
        const titleMatch = (r.title || "").toLowerCase().includes(searchTerm);
        const urlMatch = (r.original_url || "").toLowerCase().includes(searchTerm) || (r.final_url || "").toLowerCase().includes(searchTerm);
        const textMatch = (r.extracted_text || "").toLowerCase().includes(searchTerm);
        if (!titleMatch && !urlMatch && !textMatch) return false;
      }

      return true;
    });

    // Sorting
    filtered.sort((a, b) => {
      if (sortBy === "WORDS_DESC") {
        return (b.word_count || 0) - (a.word_count || 0);
      } else if (sortBy === "DEPTH_ASC") {
        return (a.depth || 0) - (b.depth || 0);
      } else if (sortBy === "TITLE_ASC") {
        return (a.title || "").localeCompare(b.title || "");
      }
      return 0; // Default order
    });

    return filtered;
  }

  function renderWorkspaceTable() {
    const records = getFilteredAndSortedRecords();
    if (workspaceResultsCount) {
      workspaceResultsCount.textContent = `Showing ${records.length} of ${workspaceRecords.length} pages`;
    }

    if (records.length === 0) {
      workspaceTbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state">
            ${workspaceRecords.length === 0 
              ? "No research data available yet. Start research above to populate this workspace." 
              : "No pages match the active search or filter criteria."}
          </td>
        </tr>
      `;
      return;
    }

    workspaceTbody.innerHTML = "";
    records.forEach(page => {
      const tr = document.createElement("tr");

      // Col 1: Depth
      const tdDepth = document.createElement("td");
      tdDepth.style.fontFamily = "var(--font-code)";
      tdDepth.style.fontWeight = "600";
      tdDepth.textContent = `d:${page.depth}`;

      // Col 2: Title & Source URL
      const tdTitle = document.createElement("td");
      const titleDiv = document.createElement("div");
      titleDiv.style.fontWeight = "600";
      titleDiv.style.color = "var(--text-main)";
      titleDiv.style.lineHeight = "1.3";
      titleDiv.textContent = page.title || "Untitled Webpage";

      const urlLink = document.createElement("a");
      urlLink.href = page.final_url || page.original_url;
      urlLink.target = "_blank";
      urlLink.rel = "noopener noreferrer";
      urlLink.style.fontSize = "0.78rem";
      urlLink.style.color = "var(--accent-primary)";
      urlLink.style.wordBreak = "break-all";
      urlLink.textContent = page.final_url || page.original_url;

      tdTitle.appendChild(titleDiv);
      tdTitle.appendChild(urlLink);

      // Col 3: HTTP Status
      const tdHttp = document.createElement("td");
      const httpBadge = document.createElement("span");
      const statusCode = page.http_status;
      if (statusCode && statusCode >= 200 && statusCode < 300) {
        httpBadge.className = "badge badge-success";
      } else if (statusCode && statusCode >= 300 && statusCode < 400) {
        httpBadge.className = "badge badge-pending";
      } else {
        httpBadge.className = "badge badge-danger";
      }
      httpBadge.textContent = statusCode ? `HTTP ${statusCode}` : "ERR";
      tdHttp.appendChild(httpBadge);

      // Col 4: Extraction Status
      const tdExt = document.createElement("td");
      const extBadge = document.createElement("span");
      const isExtSuccess = page.extraction_status === "SUCCESS";
      extBadge.className = isExtSuccess ? "badge badge-success" : "badge badge-danger";
      extBadge.textContent = page.extraction_status || "UNKNOWN";
      tdExt.appendChild(extBadge);

      // Col 5: Word Count
      const tdWords = document.createElement("td");
      tdWords.style.fontFamily = "var(--font-code)";
      tdWords.textContent = `${(page.word_count || 0).toLocaleString()} w`;

      // Col 6: Linked Evidence
      const tdEvidence = document.createElement("td");
      if (page.evidence_id) {
        const evTag = document.createElement("span");
        evTag.className = "badge badge-evidence";
        evTag.textContent = `#${page.evidence_id}`;
        evTag.title = "Verified ScrapeEvidence linked";
        tdEvidence.appendChild(evTag);
      } else {
        tdEvidence.style.color = "var(--text-muted)";
        tdEvidence.style.fontSize = "0.82rem";
        tdEvidence.textContent = "None";
      }

      // Col 7: Action (Inspect)
      const tdAction = document.createElement("td");
      tdAction.style.textAlign = "center";
      const btnInspect = document.createElement("button");
      btnInspect.type = "button";
      btnInspect.className = "btn-inspect";
      btnInspect.innerHTML = "🔍 Inspect";
      btnInspect.title = "View complete extracted text, headings, metadata, and evidence";
      btnInspect.addEventListener("click", () => openRecordModal(page));
      tdAction.appendChild(btnInspect);

      tr.appendChild(tdDepth);
      tr.appendChild(tdTitle);
      tr.appendChild(tdHttp);
      tr.appendChild(tdExt);
      tr.appendChild(tdWords);
      tr.appendChild(tdEvidence);
      tr.appendChild(tdAction);

      workspaceTbody.appendChild(tr);
    });
  }

  // ==========================================
  // RECORD INSPECTION SLIDE-OVER MODAL
  // ==========================================
  async function openRecordModal(record) {
    currentInspectedRecord = record;

    // Header metadata
    modalPageTitle.textContent = record.title || "Untitled Page";
    modalDepthBadge.textContent = `d:${record.depth}`;
    
    modalStatusBadge.textContent = record.extraction_status || "UNKNOWN";
    modalStatusBadge.className = record.extraction_status === "SUCCESS" ? "badge badge-success" : "badge badge-danger";

    modalPageUrl.textContent = record.final_url || record.original_url;
    modalPageUrl.href = record.final_url || record.original_url;
    modalHttpStatus.textContent = record.http_status ? String(record.http_status) : "N/A";
    modalWordCount.textContent = (record.word_count || 0).toLocaleString();
    modalEvidenceTag.textContent = record.evidence_id ? `#${record.evidence_id}` : "None";

    // Tab 1: Extracted Text
    const textContent = record.extracted_text || "";
    modalTextBody.textContent = textContent || (record.error_message ? `Extraction Error: ${record.error_message}` : "No extracted text captured.");
    modalTextStats.textContent = `${(record.word_count || 0).toLocaleString()} words • ${textContent.length.toLocaleString()} characters`;

    // Tab 2: Headings
    renderModalHeadings(record.headings_json);

    // Tab 3: Metadata
    renderModalMetadata(record.metadata_json, record);

    // Tab 4: Linked Evidence (Dynamic fetch if evidence_id exists)
    await renderModalEvidence(record.evidence_id);

    // Tab 5: Raw JSON
    modalJsonBody.textContent = JSON.stringify(record.raw_record || record, null, 2);

    // Reset to default tab (Text)
    modalTabBtns.forEach(b => b.classList.remove("active"));
    modalTabContents.forEach(c => c.classList.remove("active"));
    document.querySelector('.modal-tab-btn[data-target="modtab-text"]').classList.add("active");
    document.getElementById("modtab-text").classList.add("active");

    // Show modal
    recordModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeRecordModal() {
    recordModal.classList.add("hidden");
    document.body.style.overflow = "";
    currentInspectedRecord = null;
  }

  function renderModalHeadings(headings) {
    const h = headings || { h1: [], h2: [], h3: [] };
    const h1Arr = h.h1 || [];
    const h2Arr = h.h2 || [];
    const h3Arr = h.h3 || [];

    modalCountH1.textContent = String(h1Arr.length);
    modalCountH2.textContent = String(h2Arr.length);
    modalCountH3.textContent = String(h3Arr.length);

    modalListH1.innerHTML = h1Arr.length ? h1Arr.map(t => `<li>${escapeHtml(t)}</li>`).join("") : `<li class="text-muted">None detected</li>`;
    modalListH2.innerHTML = h2Arr.length ? h2Arr.map(t => `<li>${escapeHtml(t)}</li>`).join("") : `<li class="text-muted">None detected</li>`;
    modalListH3.innerHTML = h3Arr.length ? h3Arr.map(t => `<li>${escapeHtml(t)}</li>`).join("") : `<li class="text-muted">None detected</li>`;
  }

  function renderModalMetadata(metadata, record) {
    modalMetaTbody.innerHTML = "";
    const meta = metadata || {};
    
    // Core system metadata
    const rows = [
      { key: "Original Target URL", val: record.original_url },
      { key: "Final Landed URL", val: record.final_url },
      { key: "HTTP Status Code", val: record.http_status },
      { key: "Extraction Engine Mode", val: record.source_mode === "single" ? "HTTPX (Single-Page)" : "Scrapy Spider (Recursive)" },
      { key: "Crawl Depth Level", val: record.depth }
    ];

    if (record.error_message) {
      rows.push({ key: "Engine Error Message", val: record.error_message });
    }

    // Append all custom page metadata keys
    Object.keys(meta).forEach(k => {
      const v = typeof meta[k] === "object" ? JSON.stringify(meta[k]) : String(meta[k]);
      rows.push({ key: k, val: v });
    });

    rows.forEach(r => {
      const tr = document.createElement("tr");
      const tdKey = document.createElement("td");
      tdKey.style.fontWeight = "600";
      tdKey.style.color = "var(--text-main)";
      tdKey.textContent = r.key;

      const tdVal = document.createElement("td");
      tdVal.style.fontFamily = "var(--font-code)";
      tdVal.style.wordBreak = "break-all";
      tdVal.textContent = r.val !== null && r.val !== undefined ? r.val : "null";

      tr.appendChild(tdKey);
      tr.appendChild(tdVal);
      modalMetaTbody.appendChild(tr);
    });
  }

  async function renderModalEvidence(evidenceId) {
    if (!evidenceId) {
      modalEvidenceDetails.innerHTML = `
        <div class="empty-state">
          <p>🛡️ No linked ScrapeEvidence record for this page.</p>
          <span style="font-size:0.82rem; color:var(--text-muted); display:block; margin-top:0.4rem;">
            Evidence records are generated when a crawl job specifies a registered Company ID or qualification context.
          </span>
        </div>
      `;
      return;
    }

    modalEvidenceDetails.innerHTML = `
      <div class="empty-state">
        <p>Fetching linked evidence #${evidenceId} from backend database...</p>
      </div>
    `;

    try {
      const resp = await fetch(`/api/evidence/${evidenceId}`);
      if (!resp.ok) {
        modalEvidenceDetails.innerHTML = `
          <div class="empty-state" style="color:var(--accent-warning);">
            <p>Evidence ID #${evidenceId} is recorded in crawl page, but record lookup returned HTTP ${resp.status}.</p>
          </div>
        `;
        return;
      }

      const ev = await resp.json();
      modalEvidenceDetails.innerHTML = `
        <div class="evidence-box">
          <div class="evidence-header-row">
            <h4>Verified ScrapeEvidence Record #${ev.id}</h4>
            <span class="badge badge-success">Confidence: ${ev.confidence_score !== undefined ? (ev.confidence_score * 100).toFixed(0) + '%' : '100%'}</span>
          </div>
          <table class="data-table" style="margin-top:0.75rem;">
            <tbody>
              <tr><td style="width:30%; font-weight:600;">Evidence ID</td><td style="font-family:var(--font-code);">#${ev.id}</td></tr>
              <tr><td style="font-weight:600;">Company ID</td><td style="font-family:var(--font-code);">${ev.company_id || "None (General Crawl)"}</td></tr>
              <tr><td style="font-weight:600;">Source URL</td><td style="word-break:break-all;"><a href="${escapeHtml(ev.source_url)}" target="_blank">${escapeHtml(ev.source_url)}</a></td></tr>
              <tr><td style="font-weight:600;">Captured At</td><td>${ev.created_at || "Recorded in DB"}</td></tr>
              <tr><td style="font-weight:600;">Content Hash</td><td style="font-family:var(--font-code); font-size:0.75rem;">${ev.content_hash || "Calculated"}</td></tr>
            </tbody>
          </table>
          <h5 style="margin-top:1rem; margin-bottom:0.4rem; color:var(--text-main);">Evidence Content Snippet:</h5>
          <pre style="background:var(--bg-main); padding:0.75rem; border-radius:6px; font-size:0.8rem; max-height:200px; overflow-y:auto;">${escapeHtml(ev.text_content || "No raw text attached to evidence.")}</pre>
        </div>
      `;
    } catch (err) {
      modalEvidenceDetails.innerHTML = `
        <div class="empty-state" style="color:var(--accent-danger);">
          <p>Failed to load evidence details: ${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  // ==========================================
  // EXPORT CAPABILITIES (CSV & JSON)
  // ==========================================
  function exportAsCsv() {
    if (workspaceRecords.length === 0) {
      showError("Export Error", "No workspace records available to export. Run a scrape or crawl first.");
      return;
    }

    const headers = [
      "depth",
      "title",
      "original_url",
      "final_url",
      "http_status",
      "extraction_status",
      "word_count",
      "evidence_id",
      "error_message",
      "extracted_text_preview",
      "extracted_text_full"
    ];

    const csvRows = [headers.join(",")];

    workspaceRecords.forEach(r => {
      const text = r.extracted_text || "";
      const preview = text.substring(0, 200).replace(/\s+/g, " ").trim();

      const row = [
        r.depth,
        csvEscape(r.title || ""),
        csvEscape(r.original_url || ""),
        csvEscape(r.final_url || ""),
        r.http_status || "",
        csvEscape(r.extraction_status || ""),
        r.word_count || 0,
        r.evidence_id || "",
        csvEscape(r.error_message || ""),
        csvEscape(preview),
        csvEscape(text)
      ];
      csvRows.push(row.join(","));
    });

    const csvString = csvRows.join("\r\n");
    downloadBlob(csvString, `web_research_export_${getTimestamp()}.csv`, "text/csv;charset=utf-8;");
  }

  function exportAsJson() {
    if (workspaceRecords.length === 0) {
      showError("Export Error", "No workspace records available to export. Run a scrape or crawl first.");
      return;
    }

    const exportPayload = {
      exported_at: new Date().toISOString(),
      total_records: workspaceRecords.length,
      mode: "crawl",
      records: workspaceRecords.map(r => ({
        id: r.id,
        depth: r.depth,
        title: r.title,
        original_url: r.original_url,
        final_url: r.final_url,
        http_status: r.http_status,
        extraction_status: r.extraction_status,
        word_count: r.word_count,
        evidence_id: r.evidence_id,
        error_message: r.error_message,
        metadata: r.metadata_json,
        headings: r.headings_json,
        extracted_text: r.extracted_text
      }))
    };

    const jsonString = JSON.stringify(exportPayload, null, 2);
    downloadBlob(jsonString, `web_research_export_${getTimestamp()}.json`, "application/json;charset=utf-8;");
  }

  function csvEscape(value) {
    if (value === null || value === undefined) return '""';
    const stringVal = String(value);
    // Escape internal quotes by doubling them
    const escaped = stringVal.replace(/"/g, '""');
    return `"${escaped}"`;
  }

  function downloadBlob(content, fileName, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }

  // ==========================================
  // INTELLIGENCE DASHBOARD & CONTROLS
  // ==========================================
  let intelCandidates = [];
  let intelDecisionMakers = [];
  let intelContacts = [];
  let intelDocuments = [];
  let intelEvidence = [];

  // Tab switching handler
  document.querySelectorAll(".intel-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      document.querySelectorAll(".intel-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".intel-tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add("active");
    });
  });

  // Action Buttons
  const btnReverify = document.getElementById("btn-reverify-candidates");
  if (btnReverify) {
    btnReverify.addEventListener("click", async () => {
      if (activeCrawlJobId) {
        btnReverify.disabled = true;
        btnReverify.textContent = "⏳ Verifying...";
        await runCandidateVerificationAndFetchIntel(activeCrawlJobId);
        btnReverify.disabled = false;
        btnReverify.textContent = "⚡ Re-Verify All Findings";
      }
    });
  }

  const btnExportExcelIntel = document.getElementById("btn-export-excel");
  if (btnExportExcelIntel) {
    btnExportExcelIntel.addEventListener("click", () => {
      if (activeCrawlJobId) {
        window.open(`/api/crawl/jobs/${activeCrawlJobId}/export?format=excel`, "_blank");
      } else {
        showError("No Active Job", "Please run or select a research crawl job first.");
      }
    });
  }

  const btnExportCsvIntel = document.getElementById("btn-export-csv-dataset");
  if (btnExportCsvIntel) {
    btnExportCsvIntel.addEventListener("click", () => {
      if (activeCrawlJobId) {
        window.open(`/api/crawl/jobs/${activeCrawlJobId}/export?format=csv`, "_blank");
      } else {
        showError("No Active Job", "Please run or select a research crawl job first.");
      }
    });
  }

  // Filter Listeners
  const filterCompSearch = document.getElementById("filter-companies-search");
  const filterCompClass = document.getElementById("filter-companies-classification");
  const filterCompCat = document.getElementById("filter-companies-category");
  if (filterCompSearch) filterCompSearch.addEventListener("input", renderCompaniesTable);
  if (filterCompClass) filterCompClass.addEventListener("change", renderCompaniesTable);
  if (filterCompCat) filterCompCat.addEventListener("change", renderCompaniesTable);

  const filterRelSearch = document.getElementById("filter-rel-search");
  if (filterRelSearch) filterRelSearch.addEventListener("input", renderRelationshipEvidenceTable);

  const filterUsageSearch = document.getElementById("filter-usage-search");
  if (filterUsageSearch) filterUsageSearch.addEventListener("input", renderProductUsageEvidenceTable);

  const filterDmSearch = document.getElementById("filter-dms-search");
  const filterDmRole = document.getElementById("filter-dms-role");
  if (filterDmSearch) filterDmSearch.addEventListener("input", renderDecisionMakersTable);
  if (filterDmRole) filterDmRole.addEventListener("change", renderDecisionMakersTable);

  const filterCtSearch = document.getElementById("filter-contacts-search");
  const filterCtType = document.getElementById("filter-contacts-type");
  if (filterCtSearch) filterCtSearch.addEventListener("input", renderPublicContactsTable);
  if (filterCtType) filterCtType.addEventListener("change", renderPublicContactsTable);

  const filterDocSearch = document.getElementById("filter-docs-search");
  const filterDocFormat = document.getElementById("filter-docs-format");
  if (filterDocSearch) filterDocSearch.addEventListener("input", renderDocumentsTable);
  if (filterDocFormat) filterDocFormat.addEventListener("change", renderDocumentsTable);

  const filterEvSearch = document.getElementById("filter-evidence-search");
  const filterEvClaim = document.getElementById("filter-evidence-claim");
  if (filterEvSearch) filterEvSearch.addEventListener("input", renderUnifiedEvidenceTable);
  if (filterEvClaim) filterEvClaim.addEventListener("change", renderUnifiedEvidenceTable);

  async function runCandidateVerificationAndFetchIntel(jobId) {
    const intelSection = document.getElementById("intel-workspace-section");
    if (intelSection) intelSection.classList.remove("hidden");
    const jobIndicator = document.getElementById("intel-job-indicator");
    if (jobIndicator) jobIndicator.textContent = `Job #${jobId} • Processing Intelligence...`;

    try {
      // 1. Trigger verification
      await fetch(`/api/crawl/jobs/${jobId}/verify-candidates`, { method: "POST" });

      // 2. Fetch all collections in parallel
      const [resCands, resDms, resContacts, resDocs, resEv] = await Promise.all([
        fetch(`/api/crawl/jobs/${jobId}/candidates`),
        fetch(`/api/crawl/jobs/${jobId}/decision-makers`),
        fetch(`/api/crawl/jobs/${jobId}/contacts`),
        fetch(`/api/crawl/jobs/${jobId}/documents`),
        fetch(`/api/crawl/jobs/${jobId}/evidence`),
      ]);

      intelCandidates = resCands.ok ? await resCands.json() : [];
      intelDecisionMakers = resDms.ok ? await resDms.json() : [];
      intelContacts = resContacts.ok ? await resContacts.json() : [];
      intelDocuments = resDocs.ok ? await resDocs.json() : [];
      intelEvidence = resEv.ok ? await resEv.json() : [];

      if (jobIndicator) jobIndicator.textContent = `Job #${jobId} • Verified Findings`;

      // 3. Render all tabs & KPIs
      updateIntelKpis();
      renderCompaniesTable();
      renderRelationshipEvidenceTable();
      renderProductUsageEvidenceTable();
      renderDecisionMakersTable();
      renderPublicContactsTable();
      renderDocumentsTable();
      renderUnifiedEvidenceTable();
      renderFailuresTable();
    } catch (e) {
      console.error("Failed to load intelligence data:", e);
      if (jobIndicator) jobIndicator.textContent = `Job #${jobId} • Extraction Incomplete`;
    }
  }

  function updateIntelKpis() {
    const confirmedCount = intelCandidates.filter(c => c.classification === "CONFIRMED").length;
    const partialCount = intelCandidates.filter(c => c.classification === "PARTIALLY_VERIFIED").length;
    const unverifiedCount = intelCandidates.filter(c => c.classification !== "CONFIRMED" && c.classification !== "PARTIALLY_VERIFIED").length;

    const elConf = document.getElementById("kpi-confirmed-companies");
    if (elConf) elConf.textContent = confirmedCount;
    const elPart = document.getElementById("kpi-partial-companies");
    if (elPart) elPart.textContent = partialCount;
    const elUnv = document.getElementById("kpi-unverified-companies");
    if (elUnv) elUnv.textContent = unverifiedCount;

    const elDm = document.getElementById("kpi-decision-makers");
    if (elDm) elDm.textContent = intelDecisionMakers.length;
    const elCt = document.getElementById("kpi-public-contacts");
    if (elCt) elCt.textContent = intelContacts.length;
    const elDocs = document.getElementById("kpi-documents-processed");
    if (elDocs) elDocs.textContent = intelDocuments.length;
    const elEv = document.getElementById("kpi-evidence-count");
    if (elEv) elEv.textContent = intelEvidence.length;

    // Failures: failed documents or unverified incomplete candidates
    const failedDocs = intelDocuments.filter(d => d.download_status === "FAILED" || d.extraction_status === "FAILED" || d.extraction_status === "UNSUPPORTED").length;
    const elFail = document.getElementById("kpi-failures-logged");
    if (elFail) elFail.textContent = failedDocs;

    // Update tab badges
    document.getElementById("tab-count-companies").textContent = intelCandidates.length;
    document.getElementById("tab-count-rel").textContent = intelEvidence.filter(e => e.claim_type === "RELATIONSHIP" || e.claim_type === "CUSTOMER_RELATIONSHIP").length;
    document.getElementById("tab-count-usage").textContent = intelEvidence.filter(e => e.claim_type === "PRODUCT_USAGE").length;
    document.getElementById("tab-count-dms").textContent = intelDecisionMakers.length;
    document.getElementById("tab-count-contacts").textContent = intelContacts.length;
    document.getElementById("tab-count-docs").textContent = intelDocuments.length;
    document.getElementById("tab-count-evidence").textContent = intelEvidence.length;
    document.getElementById("tab-count-failures").textContent = failedDocs;

    // Refresh overview tab with updated findings
    if (currentJobData) {
      updateOverviewTab(currentJobData);
    }
  }

  function renderCompaniesTable() {
    const tbody = document.getElementById("tbody-companies");
    if (!tbody) return;

    const q = (filterCompSearch ? filterCompSearch.value.trim().toLowerCase() : "");
    const filterClass = (filterCompClass ? filterCompClass.value : "ALL");
    const filterCat = (filterCompCat ? filterCompCat.value : "ALL");

    const filtered = intelCandidates.filter(c => {
      if (filterClass !== "ALL" && c.classification !== filterClass) return false;
      if (filterCat !== "ALL" && c.candidate_category !== filterCat) return false;
      if (q) {
        const text = `${c.candidate_name} ${c.relationship_type} ${c.missing_evidence_reason || ""}`.toLowerCase();
        if (!text.includes(q)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No matching company candidates found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(c => {
      let classBadge = "badge-unverified";
      if (c.classification === "CONFIRMED") classBadge = "badge-confirmed";
      else if (c.classification === "PARTIALLY_VERIFIED") classBadge = "badge-partial";
      else if (c.classification === "RESEARCH_INCOMPLETE") classBadge = "badge-incomplete";

      const catBadge = c.candidate_category === "NAMED_COMPANY" ? "badge-confirmed" : "badge-category";
      const usageStatus = c.product_usage_status || "UNVERIFIED";
      const usageBadge = usageStatus === "CONFIRMED" ? "badge-confirmed" : (usageStatus.includes("PARTNER") ? "badge-partial" : "badge-unverified");

      return `
        <tr>
          <td><strong>${escapeHtml(c.candidate_name)}</strong></td>
          <td><span class="badge ${catBadge}">${escapeHtml(c.candidate_category || "NAMED_COMPANY")}</span></td>
          <td><span class="badge ${classBadge}">${escapeHtml(c.classification)}</span></td>
          <td><span class="badge badge-unverified">${escapeHtml(c.relationship_type)}</span></td>
          <td><span class="badge ${usageBadge}">${escapeHtml(usageStatus)}</span></td>
          <td style="font-size:0.82rem; color:var(--text-muted);">${escapeHtml(c.missing_evidence_reason || "-")}</td>
          <td style="text-align:center;"><span class="badge badge-category">${(c.sources || []).length} quotes</span></td>
        </tr>
      `;
    }).join("");
  }

  function renderRelationshipEvidenceTable() {
    const tbody = document.getElementById("tbody-rel-evidence");
    if (!tbody) return;

    const q = (filterRelSearch ? filterRelSearch.value.trim().toLowerCase() : "");
    const items = intelEvidence.filter(e => e.claim_type === "RELATIONSHIP" || e.claim_type === "CUSTOMER_RELATIONSHIP");

    const filtered = items.filter(e => {
      if (q && !`${e.claim_text} ${e.supporting_quote} ${e.source_url}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No relationship evidence records matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(e => `
      <tr>
        <td><strong>${escapeHtml(e.claim_text.split(":")[0] || "Target Company")}</strong></td>
        <td>${escapeHtml(e.claim_text.split(":")[1] || e.claim_text)}</td>
        <td><div class="intel-quote-block">“${escapeHtml(e.supporting_quote)}”</div></td>
        <td>
          <a href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(e.source_url)}</a>
          <br><span class="badge ${e.verification_status === "CONFIRMED" ? "badge-confirmed" : "badge-partial"}">${escapeHtml(e.verification_status)}</span>
        </td>
      </tr>
    `).join("");
  }

  function renderProductUsageEvidenceTable() {
    const tbody = document.getElementById("tbody-usage-evidence");
    if (!tbody) return;

    const q = (filterUsageSearch ? filterUsageSearch.value.trim().toLowerCase() : "");
    const items = intelEvidence.filter(e => e.claim_type === "PRODUCT_USAGE");

    const filtered = items.filter(e => {
      if (q && !`${e.claim_text} ${e.supporting_quote} ${e.source_url}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No target product usage evidence matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(e => `
      <tr>
        <td><strong>${escapeHtml(e.claim_text.split(" ")[0] || "Company")}</strong></td>
        <td><span class="badge badge-category">Target Product</span></td>
        <td>${escapeHtml(e.claim_text)}</td>
        <td>
          <div class="intel-quote-block">“${escapeHtml(e.supporting_quote)}”</div>
          ${e.source_location ? `<div style="font-size:0.78rem; color:var(--text-muted); margin-top:4px;">📍 <strong>Location:</strong> ${escapeHtml(e.source_location)}</div>` : ""}
        </td>
        <td>
          <a href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(e.source_url)}</a>
          <br><span class="badge ${e.verification_status === "CONFIRMED" ? "badge-confirmed" : "badge-unverified"}">${escapeHtml(e.verification_status)}</span>
        </td>
      </tr>
    `).join("");
  }

  function renderDecisionMakersTable() {
    const tbody = document.getElementById("tbody-decision-makers");
    if (!tbody) return;

    const q = (filterDmSearch ? filterDmSearch.value.trim().toLowerCase() : "");
    const role = (filterDmRole ? filterDmRole.value : "ALL");

    const filtered = intelDecisionMakers.filter(dm => {
      if (role !== "ALL" && dm.role_category !== role) return false;
      const name = dm.full_name || dm.name || "";
      const title = dm.published_title || dm.title || "";
      const comp = dm.associated_company || "";
      if (q && !`${name} ${title} ${comp}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No decision-maker profiles found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(dm => `
      <tr>
        <td><strong>${escapeHtml(dm.full_name || dm.name || "Unknown")}</strong></td>
        <td>${escapeHtml(dm.published_title || dm.title || "-")}</td>
        <td><span class="badge badge-category">${escapeHtml(dm.role_category || "OTHER")}</span></td>
        <td><strong>${escapeHtml(dm.associated_company || "Target Company")}</strong></td>
        <td style="font-size:0.83rem; color:var(--text-muted);">${escapeHtml(dm.professional_relevance || "-")}</td>
        <td>
          <a href="${escapeHtml(dm.source_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(dm.source_url)}</a>
          ${dm.supporting_quote ? `<div class="intel-quote-block">“${escapeHtml(dm.supporting_quote)}”</div>` : ""}
        </td>
      </tr>
    `).join("");
  }

  function renderPublicContactsTable() {
    const tbody = document.getElementById("tbody-public-contacts");
    if (!tbody) return;

    const q = (filterCtSearch ? filterCtSearch.value.trim().toLowerCase() : "");
    const type = (filterCtType ? filterCtType.value : "ALL");

    const filtered = intelContacts.filter(c => {
      if (type !== "ALL" && c.contact_type !== type) return false;
      const val = c.contact_value || "";
      const pName = c.person_name || c.associated_person_name || "";
      const comp = c.associated_company || "";
      if (q && !`${val} ${pName} ${comp}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No public professional contacts found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(c => `
      <tr>
        <td><span class="badge badge-category">${escapeHtml(c.contact_type)}</span></td>
        <td><code style="color:#a5b4fc; font-weight:600;">${escapeHtml(c.contact_value)}</code></td>
        <td>${escapeHtml(c.person_name || c.associated_person_name || "-")}</td>
        <td><strong>${escapeHtml(c.associated_company || "-")}</strong></td>
        <td><span class="badge badge-verified-public">${escapeHtml(c.verification_status || "VERIFIED_PUBLIC")}</span></td>
        <td>
          <a href="${escapeHtml(c.source_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(c.source_url)}</a>
          ${c.supporting_quote ? `<div class="intel-quote-block">“${escapeHtml(c.supporting_quote)}”</div>` : ""}
        </td>
      </tr>
    `).join("");
  }

  function renderDocumentsTable() {
    const tbody = document.getElementById("tbody-documents");
    if (!tbody) return;

    const q = (filterDocSearch ? filterDocSearch.value.trim().toLowerCase() : "");
    const fmt = (filterDocFormat ? filterDocFormat.value : "ALL");

    const filtered = intelDocuments.filter(d => {
      if (fmt !== "ALL" && d.file_format !== fmt) return false;
      if (q && !`${d.file_name} ${d.file_format} ${d.document_url}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No documents or media matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(d => {
      let extBadge = "badge-unverified";
      if (d.extraction_status === "SUCCESS") extBadge = "badge-confirmed";
      else if (d.extraction_status === "FAILED") extBadge = "badge-incomplete";
      else if (d.extraction_status === "UNSUPPORTED") extBadge = "badge-partial";

      return `
        <tr>
          <td><strong>${escapeHtml(d.file_name || "Document")}</strong></td>
          <td><span class="badge badge-category">${escapeHtml(d.file_format)}</span></td>
          <td style="font-family:var(--font-code); font-size:0.8rem;">${formatBytes(d.file_size_bytes)}</td>
          <td><span class="badge ${d.download_status === "DOWNLOADED" ? "badge-confirmed" : "badge-incomplete"}">${escapeHtml(d.download_status)}</span></td>
          <td><span class="badge ${extBadge}">${escapeHtml(d.extraction_status)}</span></td>
          <td>
            <a href="${escapeHtml(d.document_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(d.document_url)}</a>
            ${d.error_message ? `<div style="color:#f87171; font-size:0.78rem; margin-top:4px;">${escapeHtml(d.error_message)}</div>` : ""}
          </td>
        </tr>
      `;
    }).join("");
  }

  function renderUnifiedEvidenceTable() {
    const tbody = document.getElementById("tbody-unified-evidence");
    if (!tbody) return;

    const q = (filterEvSearch ? filterEvSearch.value.trim().toLowerCase() : "");
    const claim = (filterEvClaim ? filterEvClaim.value : "ALL");

    const filtered = intelEvidence.filter(e => {
      if (claim !== "ALL") {
        if (claim === "RELATIONSHIP" && e.claim_type !== "RELATIONSHIP" && e.claim_type !== "CUSTOMER_RELATIONSHIP") return false;
        else if (claim === "CONTACT" && e.claim_type !== "CONTACT" && e.claim_type !== "CONTACT_INFO") return false;
        else if (claim !== "RELATIONSHIP" && claim !== "CONTACT" && e.claim_type !== claim) return false;
      }
      if (q && !`${e.claim_text} ${e.supporting_quote} ${e.source_url}`.toLowerCase().includes(q)) return false;
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No unified evidence audit items found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(e => `
      <tr>
        <td><span class="badge badge-category">${escapeHtml(e.claim_type)}</span></td>
        <td><strong>${escapeHtml(e.claim_text)}</strong></td>
        <td><div class="intel-quote-block">“${escapeHtml(e.supporting_quote)}”</div></td>
        <td>
          <a href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener" class="table-link">${escapeHtml(e.source_url)}</a>
          <br><span style="font-size:0.75rem; color:var(--text-subtle);">${escapeHtml(e.source_location || e.source_format)}</span>
        </td>
        <td><span class="badge ${e.verification_status === "CONFIRMED" ? "badge-confirmed" : "badge-partial"}">${escapeHtml(e.verification_status)}</span></td>
      </tr>
    `).join("");
  }

  function renderFailuresTable() {
    const tbody = document.getElementById("tbody-failures");
    if (!tbody) return;

    const failures = [];
    // 1. Failed documents
    intelDocuments.forEach(d => {
      if (d.download_status === "FAILED" || d.extraction_status === "FAILED" || d.extraction_status === "UNSUPPORTED") {
        failures.push({
          target: d.file_name || d.document_url,
          type: `DOCUMENT (${d.file_format})`,
          error: d.error_message || "Extraction was unsuccessful",
          download_status: d.download_status,
          extraction_status: d.extraction_status,
        });
      }
    });

    // 2. Failed crawled pages
    workspaceRecords.forEach(p => {
      if (p.extraction_status === "FAILED" || (p.http_status && p.http_status >= 400)) {
        failures.push({
          target: p.original_url,
          type: "WEBPAGE (HTML)",
          error: p.error_message || `HTTP ${p.http_status} Response Failure`,
          download_status: "FAILED",
          extraction_status: "FAILED",
        });
      }
    });

    if (failures.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No extraction failures or unsupported format errors logged for this job.</td></tr>`;
      return;
    }

    tbody.innerHTML = failures.map(f => `
      <tr>
        <td><code style="color:#f87171;">${escapeHtml(f.target)}</code></td>
        <td><span class="badge badge-category">${escapeHtml(f.type)}</span></td>
        <td style="color:#fca5a5; font-size:0.85rem;">${escapeHtml(f.error)}</td>
        <td><span class="badge badge-incomplete">${escapeHtml(f.download_status)}</span></td>
        <td><span class="badge badge-incomplete">${escapeHtml(f.extraction_status)}</span></td>
      </tr>
    `).join("");
  }

  // ==========================================
  // HELPER UTILITIES
  // ==========================================
  function setLoading(isLoading, text) {
    if (isLoading) {
      btnStartResearch.disabled = true;
      btnClearUrl.disabled = true;
      researchSpinner.style.display = "inline-block";
      researchBtnText.textContent = text || "Processing...";
    } else {
      btnStartResearch.disabled = false;
      btnClearUrl.disabled = false;
      researchSpinner.style.display = "none";
      researchBtnText.textContent = "🕷️ Start Website Crawl";
    }
  }

  function showError(title, msg) {
    if (errorTitle) errorTitle.textContent = title || "Action Failed";
    if (errorMessage) errorMessage.textContent = msg || "An unknown error occurred.";
    if (errorBanner) {
      errorBanner.classList.remove("hidden");
      errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function hideError() {
    if (errorBanner) errorBanner.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${bytes} B`;
  }

  function getTimestamp() {
    const now = new Date();
    return now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  }

  function escapeHtml(text) {
    if (!text) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function copyToClipboard(text, btn, defaultLabel) {
    if (!navigator.clipboard) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      flashButton(btn, defaultLabel);
      return;
    }

    navigator.clipboard.writeText(text).then(() => {
      flashButton(btn, defaultLabel);
    }).catch(err => {
      console.error("Clipboard copy failed:", err);
    });
  }

  function flashButton(btn, defaultLabel) {
    btn.textContent = "✓ Copied!";
    btn.style.borderColor = "var(--accent-success)";
    btn.style.color = "var(--accent-success)";
    setTimeout(() => {
      btn.textContent = defaultLabel;
      btn.style.borderColor = "";
      btn.style.color = "";
    }, 1800);
  }

  // Load recent jobs into selector on startup
  fetchRecentJobs();
});
