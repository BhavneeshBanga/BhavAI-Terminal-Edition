"""
config_schema.py — schema + safe read/write helpers for ~/.bhavai/config.json

This is the single source of truth the FastAPI settings router uses to
validate and persist BhavAI's provider configuration. It intentionally
mirrors the config.json shape you already have, so nothing you've built
against SARVAM_API_KEY / GROQ_API_KEY1..4 style env-driven config breaks —
this just gives you a proper file-backed version with a UI on top.

Provider "shapes" in this app:
  - multi-key providers (round robin over N keys): groq, openrouter, sarvam
  - server-list provider (round robin over N ollama servers): ollama
  - single-key providers: openai, gemini
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ──────────────────────────────────────────────────────────────────────────
# Location of the config file. Respects BHAVAI_HOME if set (useful for
# testing), otherwise defaults to the real ~/.bhavai/config.json path.
# ──────────────────────────────────────────────────────────────────────────
CONFIG_DIR = Path(os.environ.get("BHAVAI_HOME", str(Path.home() / ".bhavai")))
CONFIG_PATH = CONFIG_DIR / "config.json"


# ──────────────────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────────────────
class Credential(BaseModel):
    api_key: str = ""


class LoadBalancing(BaseModel):
    # Only round_robin is supported right now — the field exists so the
    # config shape stays stable if you add strategies later, but the API
    # rejects anything else.
    strategy: str = "round_robin"
    retry_on_429: Optional[bool] = True
    cooldown_seconds: int = 60

    @field_validator("strategy")
    @classmethod
    def only_round_robin(cls, v: str) -> str:
        if v != "round_robin":
            raise ValueError("Only 'round_robin' load balancing is supported right now.")
        return v


class MultiKeyProvider(BaseModel):
    """groq / openrouter / sarvam — round-robin over a list of API keys."""

    model: str
    base_url: str = ""
    credentials: List[Credential] = Field(default_factory=list)
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    load_balancing: LoadBalancing = Field(default_factory=LoadBalancing)


class OllamaProvider(BaseModel):
    """ollama — round-robin over a list of local/remote server URLs."""

    model: str
    servers: List[str] = Field(default_factory=lambda: ["http://localhost:11434"])
    load_balancing: LoadBalancing = Field(
        default_factory=lambda: LoadBalancing(retry_on_429=None, cooldown_seconds=30)
    )


class SingleKeyProvider(BaseModel):
    """openai / gemini — one key, no load balancing."""

    model: str
    base_url: str = ""
    api_key: str = ""


class ProvidersConfig(BaseModel):
    groq: MultiKeyProvider
    openrouter: MultiKeyProvider
    sarvam: MultiKeyProvider
    ollama: OllamaProvider
    openai: SingleKeyProvider
    gemini: SingleKeyProvider


class AppConfig(BaseModel):
    active_provider: str
    providers: ProvidersConfig

    @field_validator("active_provider")
    @classmethod
    def valid_provider_name(cls, v: str) -> str:
        allowed = {"groq", "openrouter", "sarvam", "ollama", "openai", "gemini"}
        if v not in allowed:
            raise ValueError(f"active_provider must be one of {sorted(allowed)}")
        return v


DEFAULT_CONFIG: dict = {
    "active_provider": "groq",
    "providers": {
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "base_url": "https://api.groq.com/openai/v1",
            "credentials": [],
            "extra_headers": {},
            "load_balancing": {
                "strategy": "round_robin",
                "retry_on_429": True,
                "cooldown_seconds": 60,
            },
        },
        "openrouter": {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "base_url": "https://openrouter.ai/api/v1",
            "credentials": [],
            "extra_headers": {"HTTP-Referer": "https://bhavai.local", "X-Title": "BhavAI"},
            "load_balancing": {
                "strategy": "round_robin",
                "retry_on_429": True,
                "cooldown_seconds": 60,
            },
        },
        "sarvam": {
            "model": "sarvam-105b",
            "base_url": "https://api.sarvam.ai/v1",
            "credentials": [],
            "extra_headers": {"HTTP-Referer": "https://bhavai.local", "X-Title": "BhavAI"},
            "load_balancing": {
                "strategy": "round_robin",
                "retry_on_429": True,
                "cooldown_seconds": 60,
            },
        },
        "ollama": {
            "model": "qwen3:8b",
            "servers": ["http://localhost:11434"],
            "load_balancing": {"strategy": "round_robin", "cooldown_seconds": 30},
        },
        "openai": {
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
        },
        "gemini": {
            "model": "gemini-2.0-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "",
        },
    },
}


def _deep_merge(defaults: dict, override: dict) -> dict:
    """Fill in any keys missing from `override` using `defaults`, recursively."""
    result = dict(defaults)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def read_config() -> AppConfig:
    """
    Read config.json from disk. If it doesn't exist yet, create it from
    DEFAULT_CONFIG. If it exists but is missing newer fields, those fields
    are backfilled from the defaults (so upgrading BhavAI never crashes the
    settings page).
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        write_config(AppConfig.model_validate(DEFAULT_CONFIG))
        return AppConfig.model_validate(DEFAULT_CONFIG)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    merged = _deep_merge(DEFAULT_CONFIG, raw)
    return AppConfig.model_validate(merged)


def write_config(config: AppConfig) -> None:
    """
    Atomically write config to disk (write to a temp file, then replace),
    so a crash or power loss mid-write never corrupts the real config.json.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")

    fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CONFIG_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
