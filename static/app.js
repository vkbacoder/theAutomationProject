// AI Lead Research & Qualification System - Frontend Script

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const form = document.getElementById("scraper-form");
  const urlInput = document.getElementById("url-input");
  const btnScrape = document.getElementById("btn-scrape");
  const btnClear = document.getElementById("btn-clear");
  const btnSpinner = document.getElementById("btn-spinner");
  const btnText = document.getElementById("btn-text");
  
  const loadingState = document.getElementById("loading-state");
  const errorBanner = document.getElementById("error-banner");
  const errorTitle = document.getElementById("error-title");
  const errorMessage = document.getElementById("error-message");
  const btnDismissError = document.getElementById("btn-dismiss-error");
  
  const resultsSection = document.getElementById("results-section");
  const resTitle = document.getElementById("res-title");
  const resFinalUrl = document.getElementById("res-final-url");
  const resStatusBadge = document.getElementById("res-status-badge");
  const resDescription = document.getElementById("res-description");
  const resCanonical = document.getElementById("res-canonical");
  const resContentType = document.getElementById("res-content-type");
  
  const statWords = document.getElementById("stat-words");
  const statLinks = document.getElementById("stat-links");
  const statHeadings = document.getElementById("stat-headings");
  const statMeta = document.getElementById("stat-meta");
  
  const resExtractedText = document.getElementById("res-extracted-text");
  const textWordStats = document.getElementById("text-word-stats");
  const btnCopyText = document.getElementById("btn-copy-text");
  
  const countH1 = document.getElementById("count-h1");
  const countH2 = document.getElementById("count-h2");
  const countH3 = document.getElementById("count-h3");
  const listH1 = document.getElementById("list-h1");
  const listH2 = document.getElementById("list-h2");
  const listH3 = document.getElementById("list-h3");
  
  const linksSearch = document.getElementById("links-search");
  const linksFilteredCount = document.getElementById("links-filtered-count");
  const linksTbody = document.getElementById("links-tbody");
  
  const metaTbody = document.getElementById("meta-tbody");
  const resRawJson = document.getElementById("res-raw-json");
  
  const btnCopyJson = document.getElementById("btn-copy-json");
  const btnDownloadJson = document.getElementById("btn-download-json");
  
  // State
  let currentResult = null;
  let allExtractedLinks = [];

  // Preset chips
  document.querySelectorAll(".preset-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const targetUrl = chip.getAttribute("data-url");
      if (targetUrl) {
        urlInput.value = targetUrl;
        urlInput.focus();
      }
    });
  });

  // Clear button
  btnClear.addEventListener("click", () => {
    urlInput.value = "";
    hideError();
    resultsSection.classList.add("hidden");
    currentResult = null;
    allExtractedLinks = [];
    urlInput.focus();
  });

  // Dismiss Error
  btnDismissError.addEventListener("click", hideError);

  function showError(title, message) {
    errorTitle.textContent = title || "Scraping Failed";
    errorMessage.textContent = message || "An unknown error occurred.";
    errorBanner.classList.remove("hidden");
    loadingState.classList.add("hidden");
  }

  function hideError() {
    errorBanner.classList.add("hidden");
  }

  function setLoading(isLoading) {
    if (isLoading) {
      btnScrape.disabled = true;
      btnClear.disabled = true;
      btnScrape.classList.add("loading");
      btnText.textContent = "Scraping...";
      loadingState.classList.remove("hidden");
      hideError();
      resultsSection.classList.add("hidden");
    } else {
      btnScrape.disabled = false;
      btnClear.disabled = false;
      btnScrape.classList.remove("loading");
      btnText.textContent = "Scrape Website";
      loadingState.classList.add("hidden");
    }
  }

  // Tabs navigation
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-target");
      const targetContent = document.getElementById(targetId);
      if (targetContent) {
        targetContent.classList.add("active");
      }
    });
  });

  // Submit Handler
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const rawUrl = urlInput.value.trim();

    if (!rawUrl) {
      showError("Validation Error", "Please enter a valid website URL.");
      return;
    }

    if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
      showError("Invalid Protocol", "URL must start with http:// or https://");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: rawUrl }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        const errorMsg = data.error || `HTTP error ${response.status}: ${response.statusText}`;
        const errorType = data.error_type ? `[${data.error_type}] ` : "";
        showError("Scraping Failed", `${errorType}${errorMsg}`);
        return;
      }

      // Success: render structured data
      renderResults(data);

    } catch (err) {
      showError("Network Error", `Could not reach backend scraper service: ${err.message}`);
    } finally {
      setLoading(false);
    }
  });

  function renderResults(data) {
    currentResult = data;
    allExtractedLinks = data.links || [];

    // Header info
    resTitle.textContent = data.title || "Untitled Document";
    resFinalUrl.textContent = data.final_url || data.url;
    resFinalUrl.href = data.final_url || data.url;

    // Status code badge
    const statusCode = data.status_code || 200;
    resStatusBadge.textContent = `${statusCode} ${statusCode === 200 ? 'OK' : ''}`;
    resStatusBadge.className = statusCode >= 200 && statusCode < 300 
      ? "badge badge-success" 
      : "badge badge-danger";

    // Overview fields
    resDescription.textContent = data.description || "No meta description provided.";
    resCanonical.textContent = data.canonical_url || "None specified";
    resContentType.textContent = data.content_type || "text/html";

    // Stats
    const totalHeadings = (data.headings?.h1?.length || 0) + 
                          (data.headings?.h2?.length || 0) + 
                          (data.headings?.h3?.length || 0);
    const metaCount = Object.keys(data.metadata || {}).length;

    statWords.textContent = (data.word_count || 0).toLocaleString();
    statLinks.textContent = (allExtractedLinks.length).toLocaleString();
    statHeadings.textContent = totalHeadings.toLocaleString();
    statMeta.textContent = metaCount.toLocaleString();

    // Extracted Text
    resExtractedText.textContent = data.text || "(No readable body text extracted from this page)";
    textWordStats.textContent = `${(data.word_count || 0).toLocaleString()} words extracted`;

    // Headings
    renderHeadingsList(listH1, countH1, data.headings?.h1);
    renderHeadingsList(listH2, countH2, data.headings?.h2);
    renderHeadingsList(listH3, countH3, data.headings?.h3);

    // Links Table
    renderLinksTable(allExtractedLinks);

    // Metadata Table
    renderMetadataTable(data.metadata);

    // Raw JSON
    resRawJson.textContent = JSON.stringify(data, null, 2);

    // Show Results Section
    resultsSection.classList.remove("hidden");
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderHeadingsList(element, countElement, items) {
    element.innerHTML = "";
    const list = items || [];
    countElement.textContent = list.length;

    if (list.length === 0) {
      const empty = document.createElement("li");
      empty.textContent = "None found";
      empty.style.color = "var(--text-subtle)";
      empty.style.borderLeft = "none";
      empty.style.background = "transparent";
      element.appendChild(empty);
      return;
    }

    list.forEach(item => {
      const li = document.createElement("li");
      li.textContent = item;
      element.appendChild(li);
    });
  }

  function renderLinksTable(links) {
    linksTbody.innerHTML = "";
    linksFilteredCount.textContent = `Showing ${links.length} of ${allExtractedLinks.length} links`;

    if (links.length === 0) {
      linksTbody.innerHTML = `<tr><td colspan="2" class="empty-state">No links found</td></tr>`;
      return;
    }

    links.forEach(link => {
      const tr = document.createElement("tr");
      
      const tdText = document.createElement("td");
      tdText.textContent = link.text || "(no text)";
      
      const tdUrl = document.createElement("td");
      const a = document.createElement("a");
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "final-url-link";
      a.textContent = link.url;
      tdUrl.appendChild(a);

      tr.appendChild(tdText);
      tr.appendChild(tdUrl);
      linksTbody.appendChild(tr);
    });
  }

  // Links filter
  linksSearch.addEventListener("input", () => {
    const query = linksSearch.value.toLowerCase().trim();
    if (!query) {
      renderLinksTable(allExtractedLinks);
      return;
    }
    const filtered = allExtractedLinks.filter(l => 
      (l.text && l.text.toLowerCase().includes(query)) ||
      (l.url && l.url.toLowerCase().includes(query))
    );
    renderLinksTable(filtered);
  });

  function renderMetadataTable(meta) {
    metaTbody.innerHTML = "";
    const entries = Object.entries(meta || {});

    if (entries.length === 0) {
      metaTbody.innerHTML = `<tr><td colspan="2" class="empty-state">No metadata tags found</td></tr>`;
      return;
    }

    entries.forEach(([k, v]) => {
      const tr = document.createElement("tr");
      
      const tdKey = document.createElement("td");
      tdKey.style.fontWeight = "600";
      tdKey.style.color = "#c7d2fe";
      tdKey.textContent = k;
      
      const tdVal = document.createElement("td");
      tdVal.textContent = v;

      tr.appendChild(tdKey);
      tr.appendChild(tdVal);
      metaTbody.appendChild(tr);
    });
  }

  // Copy Extracted Text
  btnCopyText.addEventListener("click", () => {
    const text = resExtractedText.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const orig = btnCopyText.textContent;
      btnCopyText.textContent = "Copied!";
      setTimeout(() => btnCopyText.textContent = orig, 1800);
    });
  });

  // Copy JSON
  btnCopyJson.addEventListener("click", () => {
    if (!currentResult) return;
    const jsonStr = JSON.stringify(currentResult, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
      const orig = btnCopyJson.textContent;
      btnCopyJson.textContent = "✓ Copied JSON!";
      setTimeout(() => btnCopyJson.textContent = orig, 1800);
    });
  });

  // Download JSON
  btnDownloadJson.addEventListener("click", () => {
    if (!currentResult) return;
    const jsonStr = JSON.stringify(currentResult, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeDomain = (currentResult.title || "scraped_data")
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "_")
      .slice(0, 30);
    a.href = url;
    a.download = `${safeDomain}_scraped.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });
});
