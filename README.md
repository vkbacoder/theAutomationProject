# Vishnu LLM Project

This project connects to the Vishnu LLM (`qwen3:8b`) hosted temporarily on Kaggle via Cloudflare Quick Tunnels.

## Quick Start: Updating the Kaggle Public URL

Whenever you start a new Kaggle session, Cloudflare Quick Tunnel assigns a new temporary public URL.

### File to Edit:
Edit the **[`.env`](file:///c:/Users/user/Desktop/theAutomatioProject/.env)** file in this directory:

```env
LLM_API_URL=https://your-new-tunnel-url.trycloudflare.com
```

Save the file and run `chatbot.py`. No code files need to be changed!

---

## Project Structure

- **`.env`**: Contains the single configurable `LLM_API_URL` variable.
- **`.env.example`**: Example template for the environment file.
- **`config.py`**: Central configuration loader that constructs:
  - Health check endpoint: `${LLM_API_URL}/health`
  - Generation endpoint: `${LLM_API_URL}/generate`
- **`chatbot.py`**: Interactive terminal chat client with health checking and error handling.
- **`test_api.py`**: Automated test script to verify configuration, `/health`, and `/generate` endpoints.
- **`requirements.txt`**: Python dependencies (`requests`, `python-dotenv`).

---

## Web Scraper & Lead Research Pipeline

This repository includes a secure, high-performance web scraping and persistent lead research pipeline designed for the **RECOV** (debt recovery & credit intelligence) and **Jedox** (FP&A & enterprise planning) qualification workflows.

### Starting the Web Application:
```bash
# In PowerShell:
.\.venv\Scripts\Activate.ps1
uvicorn app:app --host 127.0.0.1 --port 8000
```
- Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** to access the **Web Scraper Test** interface.
- Open **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** for the interactive OpenAPI documentation for all lead research endpoints.

### Lead Research API Endpoints:
- `POST /api/leads/ingest`: Ingest, scrape, deduplicate, and record a company profile with source evidence.
- `GET /api/leads`: Query leads filtered by `workflow` (`RECOV`, `JEDOX`, `GENERAL`), `status`, and `search`.
- `GET /api/leads/{id}`: Retrieve a complete lead record with linked scrape evidence, decision-makers, and audit history.
- `POST /api/leads/{id}/contacts`: Attach a verified decision maker with exact source evidence URL.
- `POST /api/leads/{id}/qualify`: Record a qualification score (tracking factual vs AI-generated claims).
- `POST /api/leads/{id}/evaluate`: Run heuristic signal evaluation for RECOV/Jedox fit.

### SQLite Database Architecture:
Persistent storage is maintained in `leads.db` with foreign keys enabled:
- `companies`: Core profiles with unique `(domain, workflow)` constraints.
- `scrape_evidence`: Raw body text, HTML titles, meta tags, and structured headings linked to the company.
- `contacts`: Corporate decision-makers with traceable `source_url`.
- `qualification_scores`: Structured fit scores with `is_ai_generated` provenance tracking.
- `research_history`: Chronological audit trail of all ingestion and research events.

### Running Automated Tests:
```bash
# Run complete test suite (scraper + database pipeline)
pytest -v test_scraper.py test_pipeline.py
```

---

## How to Run the Terminal Chatbot

1. **Test the API Connection**:
   ```bash
   python test_api.py
   ```

2. **Start the Chatbot**:
   ```bash
   python chatbot.py
   ```


