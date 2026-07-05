"""
skills_router.py — FastAPI routes backing the Skills tab of the settings dashboard.

Mount this on your existing FastAPI app, alongside settings_router:
    from bhavai.skills_router import router as skills_router
    app.include_router(skills_router)

Endpoints
---------
GET  /api/skills          -> { skills: [{id, name, description, category, enabled}], total, enabled_count }
PUT  /api/skills          -> body: { enabled_ids: [str, ...] } persists the per-agent allowlist
POST /api/skills/reload   -> re-scans the skills directory from disk

NOTE — this is a starting point, not wired to your real skill registry yet.
`list_builtin_skills()` below just walks a skills directory looking for
SKILL.md files (matching the pattern used elsewhere in this project). Point
SKILLS_DIR at wherever your agent's skills actually live, or replace
`list_builtin_skills()` with a call into your existing skill-loading code
if you already have one (e.g. something like `bhavai.skills.discover_skills()`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Where built-in skills live. Adjust to match your project's real layout.
SKILLS_DIR = Path(os.environ.get("BHAVAI_SKILLS_DIR", str(Path(__file__).resolve().parent / "skills")))

# Where the per-agent allowlist is stored (mirrors config_schema.py's CONFIG_DIR pattern).
BHAVAI_HOME = Path(os.environ.get("BHAVAI_HOME", str(Path.home() / ".bhavai")))
ALLOWLIST_PATH = BHAVAI_HOME / "skills_allowlist.json"

router = APIRouter(prefix="/api/skills", tags=["skills"])


class Skill(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "Built-in skills"
    enabled: bool = True


class SkillsResponse(BaseModel):
    skills: List[Skill]
    total: int
    enabled_count: int


class SaveSkillsRequest(BaseModel):
    enabled_ids: List[str]


def _read_allowlist() -> Optional[List[str]]:
    """Returns None if no allowlist file exists yet (meaning: everything enabled)."""
    if not ALLOWLIST_PATH.exists():
        return None
    try:
        with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("enabled_ids", [])
    except Exception:
        return None


def _write_allowlist(enabled_ids: List[str]) -> None:
    BHAVAI_HOME.mkdir(parents=True, exist_ok=True)
    with open(ALLOWLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"enabled_ids": enabled_ids}, f, indent=2)


def _parse_skill_md(skill_id: str, md_path: Path) -> Skill:
    """Very small parser: first line of a `description:` field in frontmatter,
    falling back to the first non-empty line of the file."""
    name = skill_id
    description = ""
    try:
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        # naive YAML-frontmatter scan
        in_frontmatter = lines and lines[0].strip() == "---"
        if in_frontmatter:
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
        if not description:
            for line in lines:
                stripped = line.strip().lstrip("#").strip()
                if stripped and not stripped.startswith("---"):
                    description = stripped
                    break
    except Exception:
        pass
    return Skill(id=skill_id, name=name, description=description)


def list_builtin_skills() -> List[Skill]:
    """
    Scans SKILLS_DIR for `<skill_name>/SKILL.md` folders. Replace this with
    a call into your real skill registry if one already exists.
    """
    skills: List[Skill] = []
    if not SKILLS_DIR.exists():
        return skills
    for entry in sorted(SKILLS_DIR.iterdir()):
        skill_md = entry / "SKILL.md"
        if entry.is_dir() and skill_md.exists():
            skills.append(_parse_skill_md(entry.name, skill_md))
    return skills


def _apply_allowlist(skills: List[Skill]) -> List[Skill]:
    allowlist = _read_allowlist()
    if allowlist is None:
        return skills  # no allowlist yet => everything enabled
    allowed = set(allowlist)
    for s in skills:
        s.enabled = s.id in allowed
    return skills


@router.get("", response_model=SkillsResponse)
def get_skills() -> SkillsResponse:
    try:
        skills = _apply_allowlist(list_builtin_skills())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not list skills: {exc}")
    return SkillsResponse(
        skills=skills,
        total=len(skills),
        enabled_count=sum(1 for s in skills if s.enabled),
    )


@router.put("", response_model=SkillsResponse)
def save_skills(body: SaveSkillsRequest) -> SkillsResponse:
    try:
        _write_allowlist(body.enabled_ids)
        skills = _apply_allowlist(list_builtin_skills())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save skills: {exc}")
    return SkillsResponse(
        skills=skills,
        total=len(skills),
        enabled_count=sum(1 for s in skills if s.enabled),
    )


@router.post("/reload", response_model=SkillsResponse)
def reload_skills() -> SkillsResponse:
    # list_builtin_skills() already re-reads from disk each call, so this
    # just re-runs the same scan — kept as a separate endpoint so the UI's
    # "Reload Config" button has something explicit to hit.
    return get_skills()