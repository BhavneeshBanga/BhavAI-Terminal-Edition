# Future Mein Naya LLM Provider Kaise Add Karein

Bilkul simple hai — bas 4 steps, aur kahin bhi existing code touch nahi karna padta. Chalo ek real example lete hain: maan lo tumhe **OpenAI** add karna hai.

## Step 1: `.env` mein naya key add karo

```
OPENAI_API_KEY=sk-xxxxx
```

`bhavai/config.py` mein ek line add karo (yeh already existing pattern hai, tumne khud dekha hai Sarvam/Groq ke liye):

```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"
```

**Kyun yahan:** secrets/config values `config.py` (.env-backed) mein hi rehte hain — humne decide kiya tha ki `config.json` sirf provider selection ke liye hai, keys ke liye nahi.

## Step 2: Naya provider file banao — `bhavai/llm/providers/openai.py`

```python
import httpx, time
from bhavai.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, logger
from bhavai.llm.base import LLMProvider

class OpenAIProvider(LLMProvider):
    name = "openai"
    max_output_tokens = 16384          # OpenAI ka actual output limit daalo
    needs_chunking_instruction = False  # ya True, jitna zaroorat ho

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

        # yahan wahi retry/backoff pattern paste karo jo Sarvam/Groq mein hai
        # (max_retries=3, exponential backoff, 429/5xx pe retry)
        with httpx.Client(timeout=90.0) as client:
            response = client.post(url, json=payload, headers=headers)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        stop_reason = data["choices"][0].get("finish_reason", "stop")

        # OpenAI ka truncation-signal naam check karo aur "max_tokens" mein normalize karo
        return content, stop_reason
```

**Kyun `LLMProvider` extend karo:** `base.py` ka contract force karta hai ki tum `name`, `max_output_tokens`, `needs_chunking_instruction`, aur `call()` — yeh 4 cheezein zaroor define karo. Agar koi chhoot gayi, Python khud error dega (kyunki `call` ek `@abstractmethod` hai).

## Step 3: `factory.py` mein 1 line add karo

```python
# bhavai/llm/factory.py
from bhavai.llm.providers.sarvam import SarvamProvider
from bhavai.llm.providers.groq import GroqProvider
from bhavai.llm.providers.openai import OpenAIProvider   # ← naya import

_PROVIDERS = {
    "sarvam": SarvamProvider,
    "groq":   GroqProvider,
    "openai": OpenAIProvider,   # ← bas yeh ek line
}
```

Bas itna hi. `_call_api()`, `query_llm()`, `agent.py`, `SYSTEM_PROMPT_TEMPLATE` — inme se kuch bhi touch nahi karna. Yehi factory pattern ka poora point tha.

## Step 4: `config.json` mein switch karo

```json
{ "llm": { "provider": "openai", "temperature": 0.2 } }
```

Save karo, agla LLM call automatically OpenAI se jayega — koi restart bhi nahi chahiye, kyunki `get_provider()` har call pe `config.json` fresh padhta hai.

## Checklist jo har naye provider ke liye follow karni hai

| Question | Kya set karna hai |
|---|---|
| Output token limit kitni hai? | `max_output_tokens` |
| Kya iska hard truncation limit chhota hai (jaise Sarvam ka 4096)? | `needs_chunking_instruction = True` |
| Ya bada limit hai (Groq/OpenAI jaisa)? | `needs_chunking_instruction = False` |
| Provider ka truncation-signal ka naam kya hai? (`"max_tokens"`, `"length"`, kuch aur) | `call()` ke andar normalize karke `"max_tokens"` return karo — Groq mein humne `"length" → "max_tokens"` kiya tha, isi pattern follow karo |
| Multiple keys/rotation chahiye? | `__init__()` mein `itertools.cycle` setup karo (Groq jaisa) |

Agla step ho to bata dena — chahe koi specific provider (Anthropic, local Ollama, etc.) ho, same pattern follow karke guide kiya ja sakta hai.

<!-- https://claude.ai/share/d42b3801-812b-4bf4-a235-f1ce4582fe7f -->