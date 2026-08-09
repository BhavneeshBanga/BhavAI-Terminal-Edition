# How to Add a New LLM Provider in the Future

It's simple — just 4 steps, and you don't need to touch any existing code anywhere. Let's take a real example: suppose you want to add **OpenAI**.

## Step 1: Add a new key in `.env`

```
OPENAI_API_KEY=sk-xxxxx
```

Add a line in `bhavai/config.py` (this is already an existing pattern, you've seen it yourself for Sarvam/Groq):

```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"
```

**Why here:** secrets/config values live in `config.py` (.env-backed) — we decided that `config.json` is only for provider selection, not for keys.

## Step 2: Create a new provider file — `bhavai/llm/providers/openai.py`

```python
import httpx, time
from bhavai.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, logger
from bhavai.llm.base import LLMProvider

class OpenAIProvider(LLMProvider):
    name = "openai"
    max_output_tokens = 16384          # put OpenAI's actual output limit here
    needs_chunking_instruction = False  # or True, as needed

    def call(self, messages: list, temperature: float = 0.0, calls: int = 0) -> tuple[str, str]:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in .env")

        url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_output_tokens,
        }

        # paste the same retry/backoff pattern here that's in Sarvam/Groq
        # (max_retries=3, exponential backoff, retry on 429/5xx)
        with httpx.Client(timeout=90.0) as client:
            response = client.post(url, json=payload, headers=headers)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        stop_reason = data["choices"][0].get("finish_reason", "stop")

        # check OpenAI's truncation-signal name and normalize it to "max_tokens"
        return content, stop_reason
```

**Why extend `LLMProvider`:** the `base.py` contract forces you to define exactly 4 things — `name`, `max_output_tokens`, `needs_chunking_instruction`, and `call()`. If any of these is missing, Python will throw an error on its own (since `call` is an `@abstractmethod`).

## Step 3: Add 1 line in `factory.py`

```python
# bhavai/llm/factory.py
from bhavai.llm.providers.sarvam import SarvamProvider
from bhavai.llm.providers.groq import GroqProvider
from bhavai.llm.providers.openai import OpenAIProvider   # ← new import

_PROVIDERS = {
    "sarvam": SarvamProvider,
    "groq":   GroqProvider,
    "openai": OpenAIProvider,   # ← just this one line
}
```

That's it. Don't touch `_call_api()`, `query_llm()`, `agent.py`, or `SYSTEM_PROMPT_TEMPLATE` — none of that needs to change. That was the whole point of the factory pattern.

## Step 4: Switch it in `config.json`

```json
{ "llm": { "provider": "openai", "temperature": 0.2 } }
```

Save it, and the next LLM call will automatically go to OpenAI — no restart needed either, since `get_provider()` reads `config.json` fresh on every call.

## Checklist to follow for every new provider

| Question | What to set |
|---|---|
| What's the output token limit? | `max_output_tokens` |
| Does it have a small hard truncation limit (like Sarvam's 4096)? | `needs_chunking_instruction = True` |
| Or does it have a large limit (like Groq/OpenAI)? | `needs_chunking_instruction = False` |
| What's the provider's truncation-signal name? (`"max_tokens"`, `"length"`, something else) | Normalize it inside `call()` and return `"max_tokens"` — we did `"length" → "max_tokens"` for Groq, follow the same pattern |
| Need multiple keys/rotation? | Set up `itertools.cycle` in `__init__()` (like Groq) |

Let me know the next step — whether it's a specific provider (Anthropic, local Ollama, etc.), I can guide you through it following the same pattern.