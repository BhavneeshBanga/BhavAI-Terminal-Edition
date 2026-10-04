# bhavai/llm/providers/groq.py
import itertools, time, httpx
from bhavai.config import (
    GROQ_API_KEY1, GROQ_API_KEY2, GROQ_API_KEY3, GROQ_API_KEY4,
    GROQ_BASE_URL, GROQ_MODEL, logger,
)
from bhavai.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    name = "groq"
    max_output_tokens = 16000
    needs_chunking_instruction = False

    def __init__(self):
        keys = [k for k in (GROQ_API_KEY1, GROQ_API_KEY2, GROQ_API_KEY3, GROQ_API_KEY4) if k]
        if not keys:
            raise ValueError("No GROQ_API_KEY* found in .env")
        self._key_cycle = itertools.cycle(keys)

    def call(self, messages: list, temperature: float = 0.0, calls: int = 0) -> tuple[str, str]:
        api_key = next(self._key_cycle)
        url = f"{GROQ_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model":       GROQ_MODEL,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  self.max_output_tokens,
        }

        max_retries = 3
        delay       = 2.0
        last_error  = None

        for attempt in range(1, max_retries + 1):
            logger.debug("Groq API request — attempt %d/%d  url=%s  model=%s",
                         attempt, max_retries, url, GROQ_MODEL)
            try:
                with httpx.Client(timeout=90.0) as client:
                    response = client.post(url, json=payload, headers=headers)

                status = response.status_code

                if status == 200:
                    data = response.json()
                    try:
                        choice      = data["choices"][0]
                        content     = choice["message"]["content"]
                        stop_reason = choice.get("finish_reason", "stop") or "stop"
                    except (KeyError, IndexError, TypeError) as exc:
                        raise RuntimeError(
                            f"Groq API returned 200 but structure is unexpected: "
                            f"{exc}. Raw: {str(data)[:300]}"
                        )

                    if not isinstance(content, str) or not content.strip():
                        raise RuntimeError("Groq API returned 200 but 'content' is empty.")

                    logger.debug("Groq API success on attempt %d. stop_reason=%s", attempt, stop_reason)
                    # Groq ka "length" Sarvam ke "max_tokens" ke barabar hai —
                    # isliye normalize kar dete hain taaki llm_service.py ko
                    # sirf ek hi naam ("max_tokens") ke liye check karna pade
                    return content, ("max_tokens" if stop_reason == "length" else stop_reason)

                elif status in (429, 500, 502, 503, 504):
                    logger.warning("Groq API transient %d on attempt %d/%d — retrying in %.1fs…",
                                   status, attempt, max_retries, delay)
                    last_error = RuntimeError(f"Groq API transient error {status}.")
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                else:
                    raise RuntimeError(f"Groq API non-retryable error {status}: {response.text[:300]}")

            except httpx.RequestError as exc:
                logger.warning("Groq API network error attempt %d/%d: %s", attempt, max_retries, exc)
                last_error = RuntimeError(f"Groq API network error: {exc}")
                if attempt == max_retries:
                    break
                time.sleep(delay)
                delay *= 2.0
                continue
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Unexpected error querying Groq API: {exc}") from exc

        raise last_error or RuntimeError(f"Groq API failed after {max_retries} attempts.")

    def stream(
        self,
        messages: list,
        temperature: float = 0.0,
        calls: int = 0,
        on_token=None,
    ) -> tuple[str, str]:
        import json
        api_key = next(self._key_cycle)
        url = f"{GROQ_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model":       GROQ_MODEL,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  self.max_output_tokens,
            "stream":      True,
        }

        max_retries = 3
        delay       = 2.0
        last_error  = None

        for attempt in range(1, max_retries + 1):
            logger.debug("Groq API stream request — attempt %d/%d  url=%s  model=%s",
                         attempt, max_retries, url, GROQ_MODEL)
            try:
                full_content = []
                stop_reason = "stop"
                with httpx.Client(timeout=90.0) as client:
                    with client.stream("POST", url, json=payload, headers=headers) as response:
                        if response.status_code != 200:
                            if response.status_code in (429, 500, 502, 503, 504):
                                logger.warning("Groq API transient %d on attempt %d/%d — retrying in %.1fs…",
                                               response.status_code, attempt, max_retries, delay)
                                last_error = RuntimeError(f"Groq API transient error {response.status_code}.")
                                time.sleep(delay)
                                delay *= 2.0
                                continue
                            else:
                                text = response.read().decode("utf-8", errors="ignore")
                                raise RuntimeError(f"Groq API non-retryable error {response.status_code}: {text[:300]}")

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
                    raise RuntimeError("Groq API returned 200 stream but content is empty.")

                norm_stop = "max_tokens" if stop_reason == "length" else (stop_reason or "stop")
                return content_str, norm_stop

            except httpx.RequestError as exc:
                logger.warning("Groq API stream network error attempt %d/%d: %s", attempt, max_retries, exc)
                last_error = RuntimeError(f"Groq API network error: {exc}")
                if attempt == max_retries:
                    break
                time.sleep(delay)
                delay *= 2.0
                continue
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Unexpected error streaming from Groq API: {exc}") from exc

        raise last_error or RuntimeError(f"Groq API stream failed after {max_retries} attempts.")