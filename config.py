"""Centralized configuration for Vishnu LLM API endpoints."""

import os
from pathlib import Path

# Locate .env file in the same directory as config.py or working directory
ENV_FILE = Path(__file__).resolve().parent / ".env"

def _load_env_file(filepath: Path) -> None:
    """Load environment variables from a .env file.
    
    Uses python-dotenv if installed, otherwise uses a lightweight fallback parser.
    """
    try:
        from dotenv import load_dotenv
        if filepath.is_file():
            load_dotenv(dotenv_path=filepath, override=True)
            return
    except ImportError:
        pass

    # Lightweight fallback parser if python-dotenv is not installed
    if filepath.is_file():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("\"'")
                        os.environ[key] = val
        except Exception as e:
            print(f"[Warning] Could not load .env file manually: {e}")

# Initial load
_load_env_file(ENV_FILE)

# Base API URL sourced from .env / environment variable
LLM_API_URL = os.getenv("LLM_API_URL", "").strip().rstrip("/")

# Endpoint URLs constructed from LLM_API_URL
HEALTH_URL = f"{LLM_API_URL}/health" if LLM_API_URL else ""
GENERATE_URL = f"{LLM_API_URL}/generate" if LLM_API_URL else ""

def reload_config() -> None:
    """Reload configuration from the .env file."""
    global LLM_API_URL, HEALTH_URL, GENERATE_URL
    _load_env_file(ENV_FILE)
    LLM_API_URL = os.getenv("LLM_API_URL", "").strip().rstrip("/")
    HEALTH_URL = f"{LLM_API_URL}/health" if LLM_API_URL else ""
    GENERATE_URL = f"{LLM_API_URL}/generate" if LLM_API_URL else ""

