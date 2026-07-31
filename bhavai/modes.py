"""
modes.py — Agent mode definitions and deep plan generation/display for BhavAI.

This module bridges the UI (main.py) and the deep planner (planner.py).
It generates structured plans via the LLM, displays them with Rich formatting,
and handles the plan confirmation flow.
"""

import json
import re
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bhavai.config import logger
from bhavai.ui.shimmer import ShimmerStatus


class AgentMode:
    """Enumeration of available agent execution modes."""
    PLAN = "plan"
    AGENT = "agent"


class PlanGenerationError(Exception):
    """Raised when plan generation or parsing fails."""
    pass


def display_deep_plan(planner_state, console: Console) -> None:
    """
    Render a PlannerState as a beautiful Rich panel with step details.

    Shows: refined goal, analysis, numbered steps with tools and dependencies.
    """
    # Import here to avoid circular import at module level
    from bhavai.planner import PlannerState

    # ── Header: Goal & Analysis ──────────────────────────────────────────
    analysis = planner_state.context.get("analysis", "")

    header_lines = [
        f"[bold cyan]🎯 Goal:[/bold cyan] {planner_state.refined_goal}",
    ]
    if analysis:
        header_lines.append(f"[dim]📝 Analysis: {analysis}[/dim]")
    header_lines.append("")

    # ── Steps Table ──────────────────────────────────────────────────────
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("#", style="bold", width=3, justify="right")
    table.add_column("Step", style="white", ratio=3)
    table.add_column("Tools", style="green", ratio=2)
    table.add_column("Depends On", style="yellow", ratio=1)

    for step in planner_state.plan:
        icon = {
            "pending":     "⬜",
            "in_progress": "🔄",
            "completed":   "✅",
            "failed":      "❌",
            "skipped":     "⏭️",
        }.get(step.status, "⬜")

        step_text = f"{icon} [bold]{step.title}[/bold]\n[dim]{step.description}[/dim]"
        tools_text = ", ".join(step.tools) if step.tools else "—"
        deps_text = ", ".join(step.depends_on) if step.depends_on else "—"

        table.add_row(str(step.order), step_text, tools_text, deps_text)

    # ── Assemble and print ───────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "\n".join(header_lines),
        title="[bold]📋 BhavAI Deep Plan[/bold]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print(table)
    console.print()


def prompt_and_confirm_plan(
    user_input: str,
    folder_tree: str,
    console: Console,
    feedback: Optional[str] = None,
    skills_block: str = "",
):
    """
    Generate a deep plan via the planner module, display it with Rich formatting.

    Does NOT block for confirmation — main.py handles the y/n/feedback loop.

    Args:
        user_input: The task description from the user.
        folder_tree: String representation of the current directory structure.
        console: Rich Console instance for output.
        feedback: Optional refinement instructions from a previous iteration.
        skills_block: Available skills text to include in plan context.

    Returns:
        PlannerState object with the generated plan.
    """
    from bhavai.planner import start_new_plan, generate_deep_plan, load_planner

    with ShimmerStatus("Generating deep plan...", color="blue"):
        if feedback:
            # Regenerate with feedback — create new plan incorporating feedback
            planner_state = generate_deep_plan(user_input, folder_tree, skills_block, feedback)
        else:
            planner_state = start_new_plan(user_input, folder_tree, skills_block)

    display_deep_plan(planner_state, console)

    return planner_state