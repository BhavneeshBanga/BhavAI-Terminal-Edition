# bhavai/llm/factory.py
import json
from pathlib import Path
from bhavai.llm.providers.sarvam import SarvamProvider
from bhavai.llm.providers.groq import GroqProvider

CONFIG_PATH = Path.home() / ".bhavai" / "config.json"

_PROVIDERS = {
    "sarvam": SarvamProvider,
    "groq":   GroqProvider,
}

_DEFAULT_LLM_CONFIG = {"provider": "sarvam", "temperature": 0.2}

def load_llm_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"llm": _DEFAULT_LLM_CONFIG}, indent=4))
        return _DEFAULT_LLM_CONFIG
    data = json.loads(CONFIG_PATH.read_text())
    return {**_DEFAULT_LLM_CONFIG, **data.get("llm", {})}

def get_provider():
    provider_name = load_llm_config()["provider"]
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{provider_name}' in config.json")
    return _PROVIDERS[provider_name]()