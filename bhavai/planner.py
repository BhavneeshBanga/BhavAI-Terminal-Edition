"""
planner.py — Deep-Thinking Task Planner for BhavAI

Features:
  • Generates deeply-analyzed plans (not just echoing the query)
  • Persists plan state to planner.json + human-readable planner.md
  • Tracks completion, dependencies, findings, and notes per step
  • Supports editing steps mid-flight (add / remove / modify / mark done)
  • Resumes interrupted sessions automatically
"""

import json
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

from bhavai.config import CWD, logger
from bhavai.llm import query_llm_with_continuation

PLANNER_JSON = Path(CWD) / "planner.json"
PLANNER_MD   = Path(CWD) / "planner.md"

# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanStep:
    step_id:      str
    order:        int
    title:        str
    description:  str
    status:       str = "pending"   # pending | in_progress | completed | failed | skipped
    tools:        List[str] = field(default_factory=list)
    depends_on:   List[str] = field(default_factory=list)
    artifacts:    List[str] = field(default_factory=list)
    notes:        str = ""
    started_at:   Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep":
        return cls(**d)


@dataclass
class PlannerState:
    version:        str = "1.0"
    session_id:     str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at:     str = field(default_factory=lambda: _now())
    updated_at:     str = field(default_factory=lambda: _now())
    original_query: str = ""
    refined_goal:   str = ""
    context:        dict = field(default_factory=dict)
    status:         str = "planning"  # planning | in_progress | completed | paused
    plan:           List[PlanStep] = field(default_factory=list)
    current_step_id: Optional[str] = None
    findings:       List[str] = field(default_factory=list)
    metadata:       dict = field(default_factory=lambda: {
        "total_steps": 0,
        "completed_steps": 0,
        "failed_steps": 0,
        "model_used": "Sarvam-105B"
    })

    def to_dict(self) -> dict:
        d = asdict(self)
        d["plan"] = [s.to_dict() for s in self.plan]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PlannerState":
        state = cls(
            version=d.get("version", "1.0"),
            session_id=d.get("session_id", str(uuid.uuid4())[:8]),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            original_query=d.get("original_query", ""),
            refined_goal=d.get("refined_goal", ""),
            context=d.get("context", {}),
            status=d.get("status", "planning"),
            current_step_id=d.get("current_step_id"),
            findings=d.get("findings", []),
            metadata=d.get("metadata", {}),
        )
        state.plan = [PlanStep.from_dict(s) for s in d.get("plan", [])]
        return state


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Deep-Thinking Plan Generation
# ─────────────────────────────────────────────────────────────────────────────

DEEP_PLAN_SYSTEM_PROMPT = """You are BhavAI's Strategic Planning Module.

Your job is NOT to echo the user's query. Your job is to THINK DEEPLY and break the task into a rigorous, actionable plan.

THINKING PROCESS (do this internally before outputting):
1.  **Clarify Intent**: What does the user REALLY want? Are there hidden sub-tasks?
2.  **Decompose**: Break into atomic, verifiable steps. Each step must be something a tool can actually execute.
3.  **Identify Dependencies**: Which steps must finish before others start?
4.  **Assess Risks**: What could go wrong? Missing files? Network calls? Ambiguous queries?
5.  **Select Tools**: For each step, name the specific BhavAI tools needed (web_search, read_file, etc.).
6.  **Estimate Order**: Sequence steps logically. Parallel steps are OK if independent.

OUTPUT FORMAT — strict JSON only, no markdown fences:
{
  "refined_goal": "One-sentence summary of what we are actually solving",
  "analysis": "2-3 sentences on your reasoning: ambiguities resolved, risks noted, approach chosen",
  "plan": [
    {
      "step_id": "step-1",
      "order": 1,
      "title": "Short action title (max 6 words)",
      "description": "Detailed instruction: what to do, what success looks like, what data to capture",
      "tools": ["tool_name"],
      "depends_on": []
    }
  ]
}

RULES:
• Minimum 3 steps for any non-trivial task. Simple tasks still need: (1) gather info, (2) execute, (3) verify/summarize.
• Step descriptions must be SPECIFIC. Bad: "Search web". Good: "Search web for 'CJP protest Delhi 2024' and extract dates, locations, and key organizers."
• If the task involves multiple distinct topics (e.g. two people, two projects), create separate research steps for each BEFORE a synthesis step.
• depends_on must reference valid step_ids from this same plan.
"""


def generate_deep_plan(user_input: str, folder_tree: str, skills_block: str = "", feedback: Optional[str] = None) -> "PlannerState":
    """
    Queries the LLM with a deep-thinking prompt and returns a fully populated PlannerState.
    Falls back to a minimal but still-structured plan if JSON parsing fails.
    """
    user_prompt = f"""User request: {user_input}

Current workspace:
{folder_tree}

Available skills:
{skills_block}

Generate the deep plan now."""

    if feedback:
        user_prompt += f"\n\nUser feedback to adjust the plan: {feedback}"

    messages = [
        {"role": "system", "content": DEEP_PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    raw = ""
    try:
        raw = query_llm_with_continuation(messages)
    except Exception as exc:
        logger.error("LLM plan generation failed: %s", exc)

    state = _parse_plan_response(raw, user_input, folder_tree)
    _save(state)
    _sync_md(state)
    return state


def _parse_plan_response(raw: str, user_input: str, folder_tree: str) -> "PlannerState":
    """Extract JSON from LLM response and build PlannerState."""
    # Strip markdown fences
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()

    # Find outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Plan JSON parse failed: %s | raw=%r", e, raw[:500])
        # Fallback: create a minimal structured plan instead of echoing the query
        return _fallback_plan(user_input, folder_tree)

    plan_steps = []
    for i, item in enumerate(data.get("plan", []), start=1):
        plan_steps.append(PlanStep(
            step_id=item.get("step_id", f"step-{i}"),
            order=item.get("order", i),
            title=item.get("title", f"Step {i}"),
            description=item.get("description", ""),
            tools=item.get("tools", []),
            depends_on=item.get("depends_on", []),
        ))

    state = PlannerState(
        original_query=user_input,
        refined_goal=data.get("refined_goal", user_input),
        context={"folder_tree": folder_tree, "analysis": data.get("analysis", "")},
        status="planning",
        plan=plan_steps,
    )
    state.metadata["total_steps"] = len(plan_steps)
    return state


def _fallback_plan(user_input: str, folder_tree: str) -> "PlannerState":
    """When LLM JSON fails, still produce a meaningful multi-step plan."""
    return PlannerState(
        original_query=user_input,
        refined_goal=f"Research and execute: {user_input}",
        context={"folder_tree": folder_tree, "note": "LLM JSON failed — using fallback planner"},
        status="planning",
        plan=[
            PlanStep(
                step_id="step-1", order=1,
                title="Analyze request scope",
                description=f"Break down the user request into sub-topics. Identify key entities, names, and concepts in: {user_input}",
                tools=["search_code", "find_files"],
            ),
            PlanStep(
                step_id="step-2", order=2,
                title="Gather external information",
                description="Use web_search and fetch_url to collect current, factual data related to the query.",
                tools=["web_search", "fetch_url"],
                depends_on=["step-1"],
            ),
            PlanStep(
                step_id="step-3", order=3,
                title="Synthesize and deliver",
                description="Compile findings into a coherent answer. Verify all claims against sources.",
                tools=["final_answer"],
                depends_on=["step-2"],
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Persistence & Markdown Sync
# ─────────────────────────────────────────────────────────────────────────────

def _save(state: "PlannerState") -> None:
    """Write planner.json."""
    state.updated_at = _now()
    try:
        with open(PLANNER_JSON, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("Planner saved to %s", PLANNER_JSON)
    except Exception as exc:
        logger.error("Failed to save planner: %s", exc)


def _sync_md(state: "PlannerState") -> None:
    """Regenerate planner.md for human readability."""
    lines = [
        f"# 📋 BhavAI Planner — Session `{state.session_id}`",
        "",
        f"**Status:** `{state.status}`  ",
        f"**Created:** {state.created_at}  ",
        f"**Updated:** {state.updated_at}",
        "",
        "## 🎯 Refined Goal",
        f"> {state.refined_goal}",
        "",
        f"**Original query:** {state.original_query}",
        "",
        "## 📊 Progress",
    ]

    total = len(state.plan)
    done  = sum(1 for s in state.plan if s.status == "completed")
    fail  = sum(1 for s in state.plan if s.status == "failed")
    skip  = sum(1 for s in state.plan if s.status == "skipped")
    pct   = (done / total * 100) if total else 0

    lines.append(f"- **Completed:** {done}/{total} ({pct:.0f}%)")
    lines.append(f"- **Failed:** {fail}")
    lines.append(f"- **Skipped:** {skip}")
    lines.append("")

    # Progress bar
    bar_len = 20
    filled = int(bar_len * done / total) if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    lines.append(f"`{bar}`")
    lines.append("")

    lines.append("## 📝 Plan Steps")
    lines.append("")

    for step in state.plan:
        icon = {
            "pending":     "⬜",
            "in_progress": "🔄",
            "completed":   "✅",
            "failed":      "❌",
            "skipped":     "⏭️",
        }.get(step.status, "⬜")

        lines.append(f"### {icon} Step {step.order}: {step.title}")
        lines.append(f"- **ID:** `{step.step_id}`")
        lines.append(f"- **Status:** `{step.status}`")
        lines.append(f"- **Tools:** {', '.join(step.tools) if step.tools else '—'}")
        if step.depends_on:
            lines.append(f"- **Depends on:** {', '.join(step.depends_on)}")
        lines.append(f"- **Description:** {step.description}")
        if step.notes:
            lines.append(f"- **Notes:** {step.notes}")
        if step.artifacts:
            lines.append(f"- **Artifacts:** {', '.join(step.artifacts)}")
        if step.started_at:
            lines.append(f"- **Started:** {step.started_at}")
        if step.completed_at:
            lines.append(f"- **Completed:** {step.completed_at}")
        lines.append("")

    if state.findings:
        lines.append("## 🔍 Findings / Notes")
        lines.append("")
        for i, finding in enumerate(state.findings, 1):
            lines.append(f"{i}. {finding}")
        lines.append("")

    lines.append("---")
    lines.append("*Auto-generated from planner.json. Do NOT edit this file manually — use the planner tools instead.*")

    try:
        with open(PLANNER_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as exc:
        logger.error("Failed to write planner.md: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Public API used by agent.py
# ─────────────────────────────────────────────────────────────────────────────

def load_planner() -> Optional["PlannerState"]:
    """Load existing planner.json if present."""
    if not PLANNER_JSON.exists():
        return None
    try:
        with open(PLANNER_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PlannerState.from_dict(data)
    except Exception as exc:
        logger.error("Failed to load planner: %s", exc)
        return None


def start_new_plan(user_input: str, folder_tree: str, skills_block: str = "", feedback: Optional[str] = None) -> "PlannerState":
    """Create a fresh deep-thinking plan. Overwrites any existing planner."""
    if PLANNER_JSON.exists():
        backup = Path(CWD) / f"planner_backup_{_now().replace(':', '-')}.json"
        try:
            PLANNER_JSON.rename(backup)
        except Exception:
            pass
    return generate_deep_plan(user_input, folder_tree, skills_block, feedback)


def get_plan_summary(state: "PlannerState") -> str:
    """Return a concise text summary for display in the TUI."""
    lines = [f"📋 Plan: {state.refined_goal}", ""]
    for step in state.plan:
        icon = {"pending":"⬜","in_progress":"🔄","completed":"✅","failed":"❌","skipped":"⏭️"}.get(step.status, "⬜")
        lines.append(f"  {icon} {step.order}. {step.title}")
    lines.append("")
    lines.append(f"Status: {state.status} | Steps: {sum(1 for s in state.plan if s.status=='completed')}/{len(state.plan)} done")
    return "\n".join(lines)


def mark_step_status(state: "PlannerState", step_id: str, new_status: str, note: str = "") -> "PlannerState":
    """Update a step's status and optionally add a note."""
    for step in state.plan:
        if step.step_id == step_id:
            old = step.status
            step.status = new_status
            if new_status == "in_progress" and old != "in_progress":
                step.started_at = _now()
            if new_status in ("completed", "failed", "skipped"):
                step.completed_at = _now()
            if note:
                step.notes = (step.notes + "\n" + note).strip() if step.notes else note
            state.current_step_id = step_id if new_status == "in_progress" else state.current_step_id
            break
    _recalc_metadata(state)
    _save(state)
    _sync_md(state)
    return state


def add_finding(state: "PlannerState", finding: str) -> "PlannerState":
    """Append a finding/observation to the planner."""
    state.findings.append(f"[{_now()}] {finding}")
    _save(state)
    _sync_md(state)
    return state


def edit_step(state: "PlannerState", step_id: str, **kwargs) -> "PlannerState":
    """Edit any field of a step (title, description, tools, etc.)."""
    for step in state.plan:
        if step.step_id == step_id:
            for key, val in kwargs.items():
                if hasattr(step, key):
                    setattr(step, key, val)
            break
    _save(state)
    _sync_md(state)
    return state


def add_step(state: "PlannerState", title: str, description: str, tools: List[str] = None,
             depends_on: List[str] = None, after_step_id: Optional[str] = None) -> "PlannerState":
    """Insert a new step. If after_step_id is given, insert after that step; else append."""
    new_id = f"step-{len(state.plan)+1}"
    new_step = PlanStep(
        step_id=new_id,
        order=len(state.plan)+1,
        title=title,
        description=description,
        tools=tools or [],
        depends_on=depends_on or [],
    )
    if after_step_id:
        idx = next((i for i, s in enumerate(state.plan) if s.step_id == after_step_id), -1)
        if idx != -1:
            state.plan.insert(idx + 1, new_step)
        else:
            state.plan.append(new_step)
    else:
        state.plan.append(new_step)
    _reorder(state)
    _recalc_metadata(state)
    _save(state)
    _sync_md(state)
    return state


def remove_step(state: "PlannerState", step_id: str) -> "PlannerState":
    """Remove a step and renumber."""
    state.plan = [s for s in state.plan if s.step_id != step_id]
    _reorder(state)
    _recalc_metadata(state)
    _save(state)
    _sync_md(state)
    return state


def set_plan_status(state: "PlannerState", status: str) -> "PlannerState":
    """Set overall plan status (planning | in_progress | completed | paused)."""
    state.status = status
    _save(state)
    _sync_md(state)
    return state


def get_next_pending_step(state: "PlannerState") -> Optional[PlanStep]:
    """Return the next step that is pending and has all dependencies satisfied."""
    completed_ids = {s.step_id for s in state.plan if s.status == "completed"}
    for step in state.plan:
        if step.status == "pending":
            if all(dep in completed_ids for dep in step.depends_on):
                return step
    return None


def _reorder(state: "PlannerState") -> None:
    """Renumber orders sequentially."""
    for i, step in enumerate(state.plan, 1):
        step.order = i


def _recalc_metadata(state: "PlannerState") -> None:
    state.metadata["total_steps"] = len(state.plan)
    state.metadata["completed_steps"] = sum(1 for s in state.plan if s.status == "completed")
    state.metadata["failed_steps"] = sum(1 for s in state.plan if s.status == "failed")
