"""
Package-level config & API key management.

- API keys ek fixed .env file mein store hoti hain — bhavai package
  ke apne folder ke andar — CWD (jahan se `bhav wake up` chala) se
  independent. Isliye kisi bhi project folder se command chalao,
  key wahi ek jagah save/load hogi.
- CONFIG_FILE (~/.bhavai/config_file.json) sirf metadata / future use
  ke liye rakha hai (e.g. kaunse projects mein bhavai use hua).
"""
from __future__ import annotations

import json
from pathlib import Path

# bhavai/core/config_store.py -> bhavai/core -> bhavai (package root)
PACKAGE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PACKAGE_DIR / ".env"

CONFIG_FILE = Path.home() / ".bhavai" / "config_file.json"


def _load_config_json() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config_json(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_env_file(env_path: Path) -> dict:
    """.env file ko simple KEY=VALUE dict mein parse karta hai."""
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()
    return env_vars


def _write_env_file(env_path: Path, env_vars: dict) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in env_vars.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_api_key_to_env(key_name: str, key_value: str) -> Path:
    """
    bhavai package ke apne .env file mein key_name=key_value save/update
    karta hai — chahe command kisi bhi CWD se chalaya jaye.
    """
    env_vars = _read_env_file(ENV_FILE)
    env_vars[key_name] = key_value
    _write_env_file(ENV_FILE, env_vars)
    return ENV_FILE


def get_api_key_from_env(key_name: str) -> str | None:
    """Package ke .env se key nikaalta hai."""
    env_vars = _read_env_file(ENV_FILE)
    return env_vars.get(key_name)


def list_all_keys() -> dict:
    """Debug ke liye — saari saved keys dikhata hai (values ke saath)."""
    return _read_env_file(ENV_FILE)
