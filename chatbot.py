import requests
from config import LLM_API_URL, HEALTH_URL, GENERATE_URL

def check_api(verbose: bool = True) -> bool:
    """Check the health status of the Vishnu LLM API endpoint."""
    try:
        response = requests.get(HEALTH_URL, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if verbose:
                status = data.get("status", "unknown")
                model = data.get("model", "unknown")
                print(f"[SUCCESS] API Connected: status='{status}', model='{model}'")
                print(f"          Endpoint: {LLM_API_URL}")
            return True
        else:
            if verbose:
                print(f"\n[ERROR] API returned HTTP status {response.status_code}: {response.text}")
                print(f"        Checked URL: {HEALTH_URL}")
                print("        The temporary Kaggle session might be initializing or returned an error.")
            return False

    except requests.exceptions.Timeout:
        if verbose:
            print(f"\n[ERROR] Connection timed out while contacting {HEALTH_URL}.")
            print("        The temporary Kaggle API is not responding.")
            print("        Please verify the Kaggle notebook is active and update LLM_API_URL in .env.")
        return False

    except requests.exceptions.ConnectionError as error:
        if verbose:
            print(f"\n[ERROR] Could not connect to API at {HEALTH_URL}.")
            print(f"        Details: {error}")
            print("        The temporary Kaggle Cloudflare tunnel appears to be offline.")
            print("        Please restart your Kaggle session and update LLM_API_URL in .env.")
        return False

    except requests.RequestException as error:
        if verbose:
            print(f"\n[ERROR] Request failed for {HEALTH_URL}: {error}")
        return False

def generate_response(prompt: str) -> str:
    """Send a prompt to the Vishnu LLM generation endpoint and return the response."""
    # Ensure the API is reachable before sending the generation request
    if not check_api(verbose=False):
        return (
            "[API Offline] The Vishnu LLM API is currently unreachable. "
            "Please check if the Kaggle notebook is running and verify LLM_API_URL in .env."
        )

    try:
        response = requests.post(
            GENERATE_URL,
            json={"prompt": prompt},
            timeout=180
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            return (
                data.get("response")
                or data.get("generated_text")
                or data.get("text")
                or str(data)
            )
        return str(data)

    except requests.exceptions.Timeout:
        return "[Error] Generation request timed out after 180 seconds. The model might be overloaded."
    except requests.exceptions.ConnectionError:
        return f"[Error] Lost connection to {GENERATE_URL}. The Kaggle tunnel may have disconnected."
    except requests.RequestException as error:
        return f"[Error] API request failed: {error}"

def main():
    print("=" * 52)
    print("          VISHNU LLM TERMINAL CHAT")
    print("              Model: Qwen3:8b")
    print(f"  Target: {LLM_API_URL}")
    print("=" * 52)

    print("\nChecking API health before starting...")
    if not check_api(verbose=True):
        print("\nExiting chat. Please update the LLM_API_URL in .env when a new Kaggle tunnel is ready.\n")
        return

    print("\nType 'exit' or 'quit' to stop.\n")

    while True:
        try:
            prompt = input("You: ").strip()

            if prompt.lower() in {"exit", "quit"}:
                print("Chat ended.")
                break

            if not prompt:
                continue

            print("\nBot: ", end="", flush=True)
            print(generate_response(prompt))
            print()

        except KeyboardInterrupt:
            print("\nChat ended.")
            break
        except requests.RequestException as error:
            print(f"\nAPI request failed: {error}\n")
        except Exception as error:
            print(f"\nUnexpected error: {error}\n")

if __name__ == "__main__":
    main()
