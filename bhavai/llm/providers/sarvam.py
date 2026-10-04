# bhavai/llm/providers/sarvam.py
import time, httpx
from bhavai.config import SARVAM_API_KEY, SARVAM_BASE_URL, SARVAM_MODEL, logger
from bhavai.llm.base import LLMProvider
from rich.console import Console

console = Console()
from rich.panel import Panel

class SarvamProvider(LLMProvider):
    name = "sarvam"
    max_output_tokens = 4096
    needs_chunking_instruction = True     # ← isi ki wajah se agent.py conditional banega

    def call(self, messages: list, temperature: float = 0.0, calls: int = 0) -> tuple[str, str]:
        if not SARVAM_API_KEY:
            raise ValueError("SARVAM_API_KEY is not set. Add it to your .env file.")
        url = f"{SARVAM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
        payload = {"model": SARVAM_MODEL, "messages": messages,
                   "temperature": temperature, "max_tokens": self.max_output_tokens}
        max_retries = 3
        delay       = 2.0
        last_error  = None
    
        for attempt in range(1, max_retries + 1):
            logger.debug(
                "Sarvam API request — attempt %d/%d  url=%s  model=%s",
                attempt, max_retries, url, SARVAM_MODEL,
            )
    
            try:
                with httpx.Client(timeout=90.0) as client:
                    response = client.post(url, json=payload, headers=headers)
                    # print("response", response)
    
                status = response.status_code
    
                if status == 200:
                    data = response.json()
                    # print("json response ", data)
                    try:
                        choice      = data["choices"][0]
                        content     = choice["message"]["content"]
                        # Sarvam follows OpenAI spec: finish_reason field
                        stop_reason = choice.get("finish_reason", "end_turn") or "end_turn"
    
    
    
    
                        # print("\n===== MODEL CONTENT =====")
                        # print(content)
                        # print("=========================\n")
    
    
    
                    except (KeyError, IndexError, TypeError) as exc:
                        raise RuntimeError(
                            f"Sarvam API returned 200 but structure is unexpected: "
                            f"{exc}. Raw: {str(data)[:300]}"
                        )
    
                    if not isinstance(content, str) or not content.strip():
                        raise RuntimeError(
                            "Sarvam API returned 200 but 'content' is empty or not a string."
                        )
    
                    logger.debug(
                        "Sarvam API success on attempt %d. stop_reason=%s",
                        attempt, stop_reason,
                    )
                    return content, stop_reason
    
                elif status in (429, 500, 502, 503, 504):
                    logger.warning(
                        "Sarvam API transient %d on attempt %d/%d — retrying in %.1f s…",
                        status, attempt, max_retries, delay,
                    )
                    last_error = RuntimeError(
                        f"Sarvam API transient error {status} after {attempt} attempt(s)."
                    )
                    time.sleep(delay)
                    delay *= 2.0
                    continue
    
                else:
                    # print("sarvam ki api wrong/expired hain ")
                    # console.print("[bold red]Error:[/bold red] Missing command. "
                    #             "Use []bhav wake up[/green] to activate the agent.")
                    raise RuntimeError(
                        f"Sarvam API non-retryable error {status}: {response.text[:300]}"
                    )
            except httpx.RequestError as exc:
                logger.warning(
                    "Sarvam API network error on attempt %d/%d: %s",
                    attempt, max_retries, exc,
                )
                last_error = RuntimeError(f"Sarvam API network error: {exc}")
                if attempt == max_retries:
                    break
                time.sleep(delay)
                delay *= 2.0
                continue
    
            except RuntimeError:
                raise
    
            except Exception as exc:
                raise RuntimeError(f"Unexpected error querying Sarvam API: {exc}") from exc
    
        raise last_error or RuntimeError(
            f"Sarvam API failed after {max_retries} attempts with no response."
        )

    def stream(
        self,
        messages: list,
        temperature: float = 0.0,
        calls: int = 0,
        on_token=None,
    ) -> tuple[str, str]:
        import json
        if not SARVAM_API_KEY:
            raise ValueError("SARVAM_API_KEY is not set. Add it to your .env file.")
        url = f"{SARVAM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
        payload = {
            "model": SARVAM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_output_tokens,
            "stream": True,
        }
        max_retries = 3
        delay       = 2.0
        last_error  = None

        for attempt in range(1, max_retries + 1):
            logger.debug(
                "Sarvam API stream request — attempt %d/%d  url=%s  model=%s",
                attempt, max_retries, url, SARVAM_MODEL,
            )
            try:
                full_content = []
                stop_reason = "end_turn"
                with httpx.Client(timeout=90.0) as client:
                    with client.stream("POST", url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            if response.status_code in (429, 500, 502, 503, 504):
                                logger.warning(
                                    "Sarvam API transient %d on attempt %d/%d — retrying in %.1f s…",
                                    response.status_code, attempt, max_retries, delay,
                                )
                                last_error = RuntimeError(
                                    f"Sarvam API transient error {response.status_code} after {attempt} attempt(s)."
                                )
                                time.sleep(delay)
                                delay *= 2.0
                                continue
                            else:
                                text = response.read().decode("utf-8", errors="ignore")
                                raise RuntimeError(
                                    f"Sarvam API non-retryable error {response.status_code}: {text[:300]}"
                                )

                        for line in response.iter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if choices:
                                    choice = choices[0]
                                    delta = choice.get("delta", {})
                                    token = delta.get("content", "")
                                    finish = choice.get("finish_reason")
                                    if finish:
                                        stop_reason = finish
                                    if token:
                                        full_content.append(token)
                                        if on_token:
                                            on_token(token)
                            except Exception:
                                continue

                content_str = "".join(full_content)
                if not content_str.strip():
                    raise RuntimeError("Sarvam API returned 200 stream but content is empty.")

                return content_str, stop_reason

            except httpx.RequestError as exc:
                logger.warning(
                    "Sarvam API stream network error on attempt %d/%d: %s",
                    attempt, max_retries, exc,
                )
                last_error = RuntimeError(f"Sarvam API network error: {exc}")
                if attempt == max_retries:
                    break
                time.sleep(delay)
                delay *= 2.0
                continue

            except RuntimeError:
                raise

            except Exception as exc:
                raise RuntimeError(f"Unexpected error streaming from Sarvam API: {exc}") from exc

        raise last_error or RuntimeError(
            f"Sarvam API stream failed after {max_retries} attempts with no response."
        )