// AI Web Research & Data Extraction - Unified Platform Controller
// Integrates Single-Page Scraper (HTTPX) & Recursive Scrapy Crawler into one cohesive frontend

document.addEventListener("DOMContentLoaded", () => {
  // ==========================================
  // DOM ELEMENT REFERENCES
  // ==========================================
  // Unified Control Form & Inputs
  const form = document.getElementById("unified-research-form");
  const modeSingleBtn = document.getElementById("mode-single");
  const modeCrawlBtn = document.getElementById("mode-crawl");
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
  const crawlProgressWrapper = document.getElementById("crawl-progress-wrapper");
  const crawlProgressFill = document.getElementById("crawl-progress-fill");
  const crawlProgressText = document.getElementById("crawl-progress-text");

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
  const workspaceSection = document.getElementById("workspace-section");
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
  let currentMode = "single"; // "single" | "crawl"
  let activeCrawlJobId = null;
  let crawlPollTimer = null;
  let workspaceRecords = []; // Normalized records array
  let currentInspectedRecord = null;

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
  
  // Mode Switcher
  modeSingleBtn.addEventListener("click", () => setMode("single"));
  modeCrawlBtn.addEventListener("click", () => setMode("crawl"));

  function setMode(mode) {
    currentMode = mode;
    if (mode === "single") {
      modeSingleBtn.classList.add("active");
      modeSingleBtn.setAttribute("aria-checked", "true");
      modeCrawlBtn.classList.remove("active");
      modeCrawlBtn.setAttribute("aria-checked", "false");
      crawlParamsPanel.classList.add("hidden");
      urlInputLabel.textContent = "Target Webpage URL (Single-Page Ingestion)";
      researchBtnText.textContent = "⚡ Scrape Page";
      if (!urlInput.value) urlInput.placeholder = "https://cooperatives.gov.in/";
    } else {
      modeCrawlBtn.classList.add("active");
      modeCrawlBtn.setAttribute("aria-checked", "true");
      modeSingleBtn.classList.remove("active");
      modeSingleBtn.setAttribute("aria-checked", "false");
      crawlParamsPanel.classList.remove("hidden");
      urlInputLabel.textContent = "Seed URL for Recursive Website Crawl";
      researchBtnText.textContent = "🕷️ Start Website Crawl";
      if (!urlInput.value) urlInput.placeholder = "https://cooperatives.gov.in/";
    }
  }

  // Presets
  presetChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const url = chip.getAttribute("data-url");
      if (url) {
        urlInput.value = url;
        urlInput.focus();
      }
    });
  });

  // Clear URL button
  btnClearUrl.addEventListener("click", () => {
    urlInput.value = "";
    hideError();
    urlInput.focus();
  });

  // Dismiss error
  btnDismissError.addEventListener("click", hideError);

  // Form Submission
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    startResearch();
  });

  // Cancel Job
  btnCancelCrawl.addEventListener("click", cancelActiveCrawlJob);

  // Retry Failed
  btnRetryCrawl.addEventListener("click", retryActiveCrawlJob);

  // Manual Refresh
  btnRefreshJob.addEventListener("click", () => {
    if (activeCrawlJobId) {
      pollJobDetails(activeCrawlJobId);
      pollJobResults(activeCrawlJobId);
    }
  });

  // Table Search and Filtering
  workspaceSearchInput.addEventListener("input", renderWorkspaceTable);
  workspaceStatusFilter.addEventListener("change", renderWorkspaceTable);
  workspaceSortSelect.addEventListener("change", renderWorkspaceTable);

  // CSV & JSON Exports
  btnExportCsv.addEventListener("click", exportAsCsv);
  btnExportJson.addEventListener("click", exportAsJson);

  // Modal Close Handlers
  btnCloseModal.addEventListener("click", closeRecordModal);
  recordModal.addEventListener("click", (e) => {
    if (e.target === recordModal) closeRecordModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !recordModal.classList.contains("hidden")) {
      closeRecordModal();
    }
  });

  // Modal Copy Buttons
  btnModalCopyText.addEventListener("click", () => {
    copyToClipboard(modalTextBody.textContent, btnModalCopyText, "📋 Copy Full Text");
  });
  btnModalCopyJson.addEventListener("click", () => {
    copyToClipboard(modalJsonBody.textContent, btnModalCopyJson, "📋 Copy JSON");
  });

  // Modal Tab Switching
  modalTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      modalTabBtns.forEach(b => b.classList.remove("active"));
      modalTabContents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add("active");
    });
  });

  // ==========================================
  // CORE RESEARCH WORKFLOW
  // ==========================================
  async function startResearch() {
    hideError();
    const rawUrl = urlInput.value.trim();

    // Validation
    if (!rawUrl) {
      showError("URL Required", "Please enter a valid HTTP or HTTPS destination URL to proceed.");
      urlInput.focus();
      return;
    }

    if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
      showError("Invalid Protocol", "URL must begin with http:// or https:// (e.g. https://cooperatives.gov.in/)");
      urlInput.focus();
      return;
    }

    // Dispatch based on active mode
    if (currentMode === "single") {
      await executeSinglePageScrape(rawUrl);
    } else {
      await executeWebsiteCrawl(rawUrl);
    }
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
    liveJobCard.classList.remove("hidden");
    jobTitleText.textContent = "Single-Page Ingestion";
    jobDisplayId.textContent = "DIRECT";
    jobStatusBadge.textContent = "INGESTING";
    jobStatusBadge.className = "badge badge-running";
    btnCancelCrawl.disabled = true;
    btnRetryCrawl.classList.add("hidden");
    btnRefreshJob.classList.add("hidden");

    crawlProgressFill.style.width = "40%";
    crawlProgressText.textContent = "Connecting with SSRF & TLS verification...";
    jobPagesCrawled.textContent = "0";
    jobDiscoveredUrls.textContent = "0";
    jobPagesFailed.textContent = "0";
    jobMaxDepth.textContent = "0";

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
      workspaceSection.classList.remove("hidden");
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

    const payload = {
      url: url,
      workflow: crawlWorkflow.value || "GENERAL",
      company_name: crawlCompanyName.value.trim() || undefined,
      max_depth: parseInt(crawlMaxDepth.value, 10) || 2,
      max_pages: parseInt(crawlMaxPages.value, 10) || 20,
      max_pages_per_domain: parseInt(crawlMaxDomain.value, 10) || 20
    };

    try {
      const resp = await fetch("/api/crawl/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const job = await resp.json();
      setLoading(false);

      if (!resp.ok) {
        showError("Failed to Start Crawl Job", job.detail || "Crawl job submission rejected.");
        return;
      }

      activeCrawlJobId = job.id;
      displayCrawlJobHeader(job);
      workspaceSection.classList.remove("hidden");

      // Begin active polling
      startJobPolling(job.id);

    } catch (err) {
      setLoading(false);
      showError("Crawl Dispatch Error", err.message || "Unable to reach /api/crawl/jobs");
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
        btnRefreshJob.classList.remove("hidden");
      }
    }, 2000);
  }

  async function pollJobDetails(jobId) {
    try {
      const resp = await fetch(`/api/crawl/jobs/${jobId}`);
      if (!resp.ok) return true;
      const job = await resp.json();
      displayCrawlJobHeader(job);
      return (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED");
    } catch (err) {
      console.warn("Poll job details error:", err);
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

  function displayCrawlJobHeader(job) {
    liveJobCard.classList.remove("hidden");
    jobTitleText.textContent = "Recursive Crawl Job #";
    jobDisplayId.textContent = job.id;

    // Status Badge
    jobStatusBadge.textContent = job.status || "UNKNOWN";
    if (job.status === "COMPLETED") {
      jobStatusBadge.className = "badge badge-success";
    } else if (job.status === "RUNNING") {
      jobStatusBadge.className = "badge badge-running";
    } else if (job.status === "FAILED") {
      jobStatusBadge.className = "badge badge-danger";
    } else if (job.status === "CANCELLED") {
      jobStatusBadge.className = "badge badge-cancelled";
    } else {
      jobStatusBadge.className = "badge badge-pending";
    }

    // Progress Bar
    const maxP = job.max_pages || 20;
    const crawled = job.pages_crawled || 0;
    const pct = Math.min(100, Math.round((crawled / maxP) * 100));
    crawlProgressFill.style.width = `${pct}%`;
    crawlProgressText.textContent = `${crawled} / ${maxP} Pages Crawled (${pct}%)`;

    // Counters
    jobPagesCrawled.textContent = crawled.toLocaleString();
    jobDiscoveredUrls.textContent = (job.discovered_urls_count || 0).toLocaleString();
    jobPagesFailed.textContent = (job.pages_failed || 0).toLocaleString();
    jobMaxDepth.textContent = String(job.max_depth || 2);

    // Button states
    btnCancelCrawl.disabled = (job.status === "COMPLETED" || job.status === "CANCELLED" || job.status === "FAILED");
    if (job.status === "FAILED" || (job.pages_failed > 0 && job.status === "COMPLETED")) {
      btnRetryCrawl.classList.remove("hidden");
    } else {
      btnRetryCrawl.classList.add("hidden");
    }
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
    metricStopReason.textContent = m.stop_reason || "-";
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
    workspaceResultsCount.textContent = `Showing ${records.length} of ${workspaceRecords.length} pages`;

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
      mode: currentMode,
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
      researchBtnText.textContent = currentMode === "single" ? "⚡ Scrape Page" : "🕷️ Start Website Crawl";
    }
  }

  function showError(title, msg) {
    errorTitle.textContent = title || "Action Failed";
    errorMessage.textContent = msg || "An unknown error occurred.";
    errorBanner.classList.remove("hidden");
    errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideError() {
    errorBanner.classList.add("hidden");
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
});
