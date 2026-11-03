"""
base_agent.py — Abstract Base Class for all BhavAI Agents

How to add a new agent (e.g., Gmail):
--------------------------------------
1. Create bhavai/agents/gmail/agent.py
2. Define a class GmailAgent(BaseAgent) with:
   - NAME = "gmail"
   - SKILL_FILE = "~/.bhavai/config/prompts/gmail_agent_skill.md"
   - get_tool_dispatch() → dict
   - run(task, user_id) → tuple[None, str]
3. Add AGENT_TOOL_DISPATCH = GmailAgent.get_tool_dispatch() at bottom
4. In bhavai/agents/__init__.py, import and merge the new dispatcher
5. Create ~/.bhavai/config/prompts/gmail_agent_skill.md

That's it — tools.py, tools_extended.py, agent.py need ZERO changes.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """
    Abstract base for every BhavAI domain agent.

    Subclasses must define:
      NAME          : short lowercase id, e.g. "calendar", "gmail"
      SKILL_FILE    : absolute or ~ path to the agent's skill .md file
      get_tool_dispatch() : returns { "tool_name": callable, ... }
      run(task, user_id)  : main dispatcher called by the ReAct loop
    """

    NAME: str = ""
    SKILL_FILE: str = ""

    # ── Must override ────────────────────────────────────────────────────────

    @classmethod
    @abstractmethod
    def get_tool_dispatch(cls) -> dict[str, Any]:
        """
        Returns a dict mapping BhavAI tool names → callable functions.
        This dict gets merged into TOOL_DISPATCH in tools.py automatically.

        Example:
            return {
                "calendar_schedule":   schedule_event,
                "calendar_list":       list_events,
            }
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def run(cls, task: dict, user_id: int = 0) -> tuple[None, str]:
        """
        Main entry point called by the agent dispatcher.

        Parameters
        ----------
        task    : dict with at least {"sub_type": "..."} and any extra fields
                  the skill file instructs the model to populate.
        user_id : user identifier (default 0 for single-user setups).

        Returns
        -------
        (None, response_string) — first element reserved for future use.
        """
        raise NotImplementedError

    # ── Optional helpers (subclasses may use) ───────────────────────────────

    @classmethod
    def agent_name(cls) -> str:
        return cls.NAME or cls.__name__.lower().replace("agent", "")

    @classmethod
    def skill_path(cls) -> str:
        return cls.SKILL_FILE
