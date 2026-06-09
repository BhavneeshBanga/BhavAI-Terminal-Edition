import time
import httpx
from bhavai.config import SARVAM_API_KEY, SARVAM_BASE_URL, SARVAM_MODEL, logger

def query_llm(messages: list, temperature: float = 0.0) -> str:
    """
    Queries the Sarvam-105B API using standard chat completion messages.
    Uses httpx for request management and implements exponential backoff on retry.
    """
    if not SARVAM_API_KEY:
        raise ValueError(
            "SARVAM_API_KEY is not set. Please configure it in your environment or a .env file."
        )
        
    url = f"{SARVAM_BASE_URL.rstrip('/')}/chat/completions"
    
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": SARVAM_MODEL,
        "messages": messages,
        "temperature": temperature
    }
    
    max_retries = 3
    delay = 2.0
    
    for attempt in range(max_retries):
        try:
            logger.debug(
                "Sending POST request to Sarvam API. URL: %s, Model: %s (Attempt %d/%d)",
                url, SARVAM_MODEL, attempt + 1, max_retries
            )
            
            with httpx.Client(timeout=90.0) as client:
                response = client.post(url, json=payload, headers=headers)
                
                # Check for successful response
                if response.status_code == 200:
                    data = response.json()
                    try:
                        content = data["choices"][0]["message"]["content"]
                        logger.debug("Received successful response from Sarvam API.")
                        return content
                    except (KeyError, IndexError) as e:
                        logger.error("Response JSON parser failed to parse message choices: %s. Data: %s", e, data)
                        raise RuntimeError(f"Sarvam API response structure invalid: {e}")
                        
                # Retry on rate limit (429) or server errors (5xx)
                elif response.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "Sarvam API returned transient status %d on attempt %d. Retrying in %.1fs...",
                        response.status_code, attempt + 1, delay
                    )
                    time.sleep(delay)
                    delay *= 2.0
                else:
                    # Non-retryable error
                    logger.error(
                        "Sarvam API returned non-retryable status %d: %s",
                        response.status_code, response.text
                    )
                    raise RuntimeError(
                        f"Sarvam API query failed with status code {response.status_code}. Response: {response.text}"
                    )
                    
        except httpx.RequestError as exc:
            logger.warning(
                "Network request error contacting Sarvam API on attempt %d: %s",
                attempt + 1, exc
            )
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Sarvam API is unreachable after {max_retries} attempts: {exc}"
                )
            time.sleep(delay)
            delay *= 2.0

    raise RuntimeError("Sarvam API failed due to consecutive retries expiring.")
