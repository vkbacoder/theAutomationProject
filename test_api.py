"""Verification script for Vishnu LLM API centralized configuration and connectivity."""

import sys
import requests
from config import LLM_API_URL, HEALTH_URL, GENERATE_URL

def test_config():
    print("--- 1. Configuration Verification ---")
    print(f"Configured LLM_API_URL : {LLM_API_URL}")
    print(f"Constructed HEALTH_URL : {HEALTH_URL}")
    print(f"Constructed GENERATE_URL: {GENERATE_URL}")
    
    assert HEALTH_URL == f"{LLM_API_URL}/health", "HEALTH_URL mismatch!"
    assert GENERATE_URL == f"{LLM_API_URL}/generate", "GENERATE_URL mismatch!"
    print("[PASS] Endpoint URL construction is valid.\n")

def test_health():
    print("--- 2. Health Check Test ---")
    print(f"Sending GET request to {HEALTH_URL}...")
    try:
        response = requests.get(HEALTH_URL, timeout=15)
        print(f"HTTP Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "online":
                print(f"[PASS] Health check succeeded. Model: {data.get('model')}\n")
                return True
            else:
                print(f"[WARN] Health response status is not 'online': {data}\n")
                return False
        else:
            print(f"[FAIL] Health check returned non-200 code: {response.status_code}\n")
            return False
    except requests.exceptions.Timeout:
        print("[FAIL] Connection timed out while checking health.\n")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection error checking health: {e}\n")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error checking health: {e}\n")
        return False

def test_generate():
    print("--- 3. Generation Endpoint Test ---")
    test_prompt = "Say 'Vishnu LLM is online' in 5 words or less."
    print(f"Sending POST request to {GENERATE_URL} with prompt: {repr(test_prompt)}...")
    try:
        response = requests.post(
            GENERATE_URL,
            json={"prompt": test_prompt},
            timeout=180
        )
        print(f"HTTP Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            reply = (
                data.get("response")
                or data.get("generated_text")
                or data.get("text")
                or str(data)
            )
            print(f"LLM Response:\n{reply.strip()}")
            print("[PASS] Generation request succeeded.\n")
            return True
        else:
            print(f"[FAIL] Generation returned non-200 code: {response.status_code}\n")
            return False
    except requests.exceptions.Timeout:
        print("[FAIL] Generation request timed out.\n")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection error during generation: {e}\n")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error during generation: {e}\n")
        return False

def main():
    print("=" * 60)
    print("   Vishnu LLM API Verification Suite")
    print("=" * 60)
    
    test_config()
    health_ok = test_health()
    
    if not health_ok:
        print("[ABORT] Cannot proceed with generation test because health check failed.")
        sys.exit(1)
        
    generate_ok = test_generate()
    
    print("=" * 60)
    if health_ok and generate_ok:
        print("ALL TESTS PASSED: Centralized configuration and API connectivity verified!")
    else:
        print("TESTS COMPLETED WITH FAILURES.")
    print("=" * 60)

if __name__ == "__main__":
    main()
