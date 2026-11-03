"""
bhavai/agents/__init__.py
──────────────────────────
Auto-discovery and merging of all agent tool dispatchers.

HOW TO ADD A NEW AGENT (e.g. Gmail)
────────────────────────────────────
1. Create bhavai/agents/gmail/agent.py with AGENT_TOOL_DISPATCH dict
2. Add ONE import line below (marked with # ADD NEW AGENTS HERE)
3. Add the new dispatcher to AGENT_DISPATCHERS merge
4. Create ~/.bhavai/config/prompts/gmail_agent_skill.md

That's it. tools.py, tools_extended.py, agent.py need ZERO changes.
"""

from bhavai.agents.calendar.agent import AGENT_TOOL_DISPATCH as _calendar_dispatch

# ── ADD NEW AGENTS HERE (future) ─────────────────────────────────────────────
# from bhavai.agents.gmail.agent      import AGENT_TOOL_DISPATCH as _gmail_dispatch
# from bhavai.agents.whatsapp.agent   import AGENT_TOOL_DISPATCH as _whatsapp_dispatch
# ─────────────────────────────────────────────────────────────────────────────

AGENT_DISPATCHERS: dict = {
    **_calendar_dispatch,
    # **_gmail_dispatch,      # uncomment when Gmail agent is ready
    # **_whatsapp_dispatch,   # uncomment when WhatsApp agent is ready
}

__all__ = ["AGENT_DISPATCHERS"]
