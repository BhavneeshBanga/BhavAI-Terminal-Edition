"""
settings_router.py — FastAPI routes backing the `bhav dev` settings dashboard.

Mount this on your existing FastAPI app:

    from bhavai.settings_router import router as settings_router
    app.include_router(settings_router)

Endpoints
---------
GET  /api/config            -> current config.json contents
PUT  /api/config             -> replace the whole config (used by "Save" in the UI)
POST /api/config/reset        -> reset config.json back to defaults
GET  /api/config/path         -> return the on-disk path, so the UI can show it
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .config_schema import (
    AppConfig,
    CONFIG_PATH,
    DEFAULT_CONFIG,
    read_config,
    write_config,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=AppConfig)
def get_config() -> AppConfig:
    try:
        return read_config()
    except Exception as exc:  # corrupted file, permissions, etc.
        raise HTTPException(status_code=500, detail=f"Could not read config.json: {exc}")


@router.put("", response_model=AppConfig)
def save_config(config: AppConfig) -> AppConfig:
    """
    Full replace — the frontend always sends the complete config object on
    Save, so we don't need to diff/patch anything here.
    """
    try:
        write_config(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not write config.json: {exc}")
    return config


@router.post("/reset", response_model=AppConfig)
def reset_config() -> AppConfig:
    fresh = AppConfig.model_validate(DEFAULT_CONFIG)
    write_config(fresh)
    return fresh


@router.get("/path")
def get_config_path() -> dict:
    return {"path": str(CONFIG_PATH)}
