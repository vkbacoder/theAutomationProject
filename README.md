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

### Starting the Web Application & Background Crawler Worker:

1. **Terminal 1: Start the FastAPI Backend**:
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app:app --host 127.0.0.1 --port 8000
```
- Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** to access the Web Scraper & Recursive Crawler dashboard.
- Toggle between **Single-Page Scraper** and **Recursive Scrapy Crawler**.
- Open **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** for interactive OpenAPI documentation.

2. **Terminal 2: Start the Crawler Worker Daemon**:
```powershell
.\.venv\Scripts\Activate.ps1
python crawler_worker.py
```
*(Runs autonomously in the background, polling SQLite for pending crawl jobs, enforcing bounded concurrency, recovering interrupted jobs, and managing Scrapy child runner processes).*

### Scrapy Recursive Crawling API Endpoints:
- `POST /api/crawl/jobs`: Create a recursive crawl job (seed URL, workflow, max depth, max pages, allowed domains).
- `GET /api/crawl/jobs`: List crawl jobs with optional status filter (`PENDING`, `RUNNING`, `COMPLETED`, `CANCELLED`, `FAILED`).
- `GET /api/crawl/jobs/{id}`: Retrieve real-time progress and status of a crawl job.
- `GET /api/crawl/jobs/{id}/results`: Retrieve all extracted pages with depth, HTTP status, word counts, content hashes, and structured evidence.
- `POST /api/crawl/jobs/{id}/cancel`: Request cooperative cancellation of a pending or running crawl.
- `POST /api/crawl/jobs/{id}/retry`: Create a new crawl job retrying failed pages.

### Running the Recursive Crawling Demo:
```powershell
python example_crawl.py
```

### Running Automated Tests:
```powershell
# Run all automated tests (scraper + pipeline + Scrapy crawler + API)
pytest -v
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


