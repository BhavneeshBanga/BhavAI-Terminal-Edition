"""
bhavai/agents/calendar/agent.py
────────────────────────────────
Google Calendar Agent — 4 tools exposed to the BhavAI ReAct loop.

Tools registered in AGENT_TOOL_DISPATCH:
  calendar_schedule   → schedule_event(task, user_id)
  calendar_list       → list_events(task, user_id)
  calendar_delete     → delete_event(task, user_id)
  calendar_free_slots → find_free_slots(task, user_id)

Each tool receives a `task` dict (built by the LLM from the skill file)
and returns (None, response_string).

task dict shapes per tool:
  calendar_schedule:
    { "instruction": "schedule meeting with Raj at 4pm tomorrow" }
    OR { "description": "..." }   (both keys accepted)

  calendar_list:
    { "period": "today" | "tomorrow" | "week" }

  calendar_delete:
    { "query": "team standup" }

  calendar_free_slots:
    { "date": "tomorrow", "instruction": "..." }
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from dotenv import load_dotenv

from bhavai.agents.base_agent import BaseAgent
from bhavai.agents.calendar.auth import get_calendar_service, CalendarAuthError, clear_token
from bhavai.agents.calendar.parser import (
    TZ, USER_TIMEZONE,
    WEEKDAYS,
    parse_date,
    parse_event,
)
from bhavai.config import logger

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env", override=True)

USER_NAME = os.getenv("USER_NAME", "User")

_log = logger  # reuse BhavAI's configured logger


# ── Tool: Schedule Event ──────────────────────────────────────────────────────

def schedule_event(task: dict, user_id: int = 0) -> tuple[None, str]:
    """
    Creates a new Google Calendar event.

    Task fields used:
      instruction / description : free-text event description from user
    """
    instruction = task.get("instruction") or task.get("description", "")
    details = parse_event(instruction)
    _log.info("calendar_schedule: parsed=%s", details)

    try:
        service = get_calendar_service()
    except CalendarAuthError as e:
        return None, f"❌ Google Calendar Auth Error:\n{str(e)}"
    except Exception as e:
        return None, f"❌ Calendar connect failed: {str(e)}"

    try:
        start_dt = TZ.localize(datetime.strptime(
            f"{details['date']} {details['start_time']}", "%Y-%m-%d %H:%M"
        ))
        end_dt = TZ.localize(datetime.strptime(
            f"{details['date']} {details['end_time']}", "%Y-%m-%d %H:%M"
        ))
    except ValueError as e:
        return None, f"❌ Date/time parsing error: {str(e)}"

    reminder_min = int(details.get("reminder_minutes", 30))

    # Build event body
    event: dict = {
        "summary":     details["title"],
        "description": details.get("description") or f"Scheduled via {USER_NAME}'s AI — BhavAI",
        "start":       {"dateTime": start_dt.isoformat(), "timeZone": USER_TIMEZONE},
        "end":         {"dateTime": end_dt.isoformat(),   "timeZone": USER_TIMEZONE},
        "reminders":   {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": reminder_min},
                {"method": "email", "minutes": reminder_min},
                {"method": "popup", "minutes": 10},
            ],
        },
    }

    if details.get("location"):
        event["location"] = details["location"]

    # Only add attendees if present (no attendees → no sendUpdates needed)
    attendees = [{"email": a} for a in details.get("attendees", []) if "@" in str(a)]
    if attendees:
        event["attendees"] = attendees

    try:
        created    = service.events().insert(calendarId="primary", body=event).execute()
        event_link = created.get("htmlLink", "")
        event_id   = created.get("id", "")
        start_str  = start_dt.strftime("%d %B %Y, %I:%M %p")
        end_str    = end_dt.strftime("%I:%M %p")

        _log.info("calendar_schedule: created event_id=%s", event_id)

        response = (
            f"✅ *Event Scheduled!*\n\n"
            f"📅 *{details['title']}*\n"
            f"🗓 {start_str} – {end_str}\n"
            f"⏰ Reminder: {reminder_min} min pehle\n"
        )
        if details.get("location"):
            response += f"📍 {details['location']}\n"
        if attendees:
            response += f"👥 {', '.join(a['email'] for a in attendees)}\n"
        response += (
            f"\n🔗 [See in Calendar]({event_link})\n\n"
            f"📱 *Google Calendar will notify you!*\n"
            f"_(popup + email {reminder_min} min pehle)_"
        )
        return None, response

    except Exception as e:
        _log.error("calendar_schedule error: %s", e)
        # If it looks like an auth error, clear token
        if "401" in str(e) or "invalid_grant" in str(e).lower():
            clear_token()
            return None, (
                "❌ *Google Calendar session expired!*\n\n"
                "token.json delete kar diya. BhavAI ko restart karo:\n"
                "`python -m bhavai.main`\n"
                "Browser khulega — dobara login karo."
            )
        return None, f"❌ Event create nahi hua: {str(e)}"


# ── Tool: List Events ─────────────────────────────────────────────────────────

def list_events(task: dict, user_id: int = 0) -> tuple[None, str]:
    """
    Lists upcoming events from Google Calendar.

    Task fields used:
      period : "today" | "tomorrow" | "week"  (default: "today")
    """
    period = task.get("period", "today")
    now    = datetime.now(TZ)

    if period == "tomorrow":
        d        = now + timedelta(days=1)
        time_min = d.replace(hour=0,  minute=0,  second=0, microsecond=0)
        time_max = d.replace(hour=23, minute=59, second=59)
        label    = "Kal ke Events"
    elif period == "week":
        time_min = now
        time_max = now + timedelta(days=7)
        label    = "Is Hafte ke Events (agle 7 din)"
    else:  # today (default)
        time_min = now.replace(hour=0,  minute=0,  second=0, microsecond=0)
        time_max = now.replace(hour=23, minute=59, second=59)
        label    = "Aaj ke Events"

    try:
        service = get_calendar_service()
        result  = service.events().list(
            calendarId  = "primary",
            timeMin     = time_min.isoformat(),
            timeMax     = time_max.isoformat(),
            maxResults  = 15,
            singleEvents= True,
            orderBy     = "startTime",
        ).execute()
    except CalendarAuthError as e:
        return None, f"❌ Auth error: {str(e)}"
    except Exception as e:
        return None, f"❌ Events fetch failed: {str(e)}"

    events = result.get("items", [])
    if not events:
        return None, f"📅 *{label}*\n\n_Koi event nahi hai! 🎉 You're free!_"

    lines = [f"📅 *{label}* ({len(events)} events)\n"]
    for i, ev in enumerate(events, 1):
        start = ev["start"].get("dateTime", ev["start"].get("date", ""))
        if "T" in start:
            dt  = datetime.fromisoformat(start)
            t   = dt.strftime("%I:%M %p")
            day = dt.strftime("%d %b")
        else:
            t, day = "All day", start
        lines.append(f"{i}. *{ev.get('summary', 'Untitled')}*")
        lines.append(f"   🕐 {day} at {t}\n")

    lines.append("_Event delete karne ke liye: `delete event <title>`_")
    return None, "\n".join(lines)


# ── Tool: Delete Event ────────────────────────────────────────────────────────

def delete_event(task: dict, user_id: int = 0) -> tuple[None, str]:
    """
    Searches for an event by title/keyword and deletes it.

    Task fields used:
      query : search keyword / event title
    """
    query = task.get("query", "")
    if not query:
        return None, "❌ Kaunsa event delete karna hai? `query` field missing."

    try:
        service = get_calendar_service()
        result  = service.events().list(
            calendarId  = "primary",
            timeMin     = datetime.now(TZ).isoformat(),
            maxResults  = 20,
            singleEvents= True,
            orderBy     = "startTime",
            q           = query,
        ).execute()
    except CalendarAuthError as e:
        return None, f"❌ Auth error: {str(e)}"
    except Exception as e:
        return None, f"❌ Event search failed: {str(e)}"

    events = result.get("items", [])
    if not events:
        return None, f"❌ '{query}' naam ka koi upcoming event nahi mila."

    # Exactly one match → delete immediately
    if len(events) == 1:
        ev = events[0]
        try:
            service.events().delete(calendarId="primary", eventId=ev["id"]).execute()
            return None, f"🗑️ *Deleted:* _{ev.get('summary', 'Event')}_"
        except Exception as e:
            return None, f"❌ Delete failed: {str(e)}"

    # Multiple matches → show list and ask user to be more specific
    lines = [f"🔍 *Multiple events mile for '{query}':*\n"]
    for i, ev in enumerate(events[:5], 1):
        start = ev["start"].get("dateTime", "")
        t     = datetime.fromisoformat(start).strftime("%d %b, %I:%M %p") if "T" in start else start
        lines.append(f"{i}. *{ev.get('summary')}* — {t}")
    lines.append(f"\nAur specific title bolo: `delete event <exact title>`")
    return None, "\n".join(lines)


# ── Tool: Find Free Slots ─────────────────────────────────────────────────────

def find_free_slots(task: dict, user_id: int = 0) -> tuple[None, str]:
    """
    Finds free time blocks (≥30 min) for a given day.

    Task fields used:
      date        : natural language date string (optional)
      instruction : full user message (fallback for date extraction)
    Working hours scanned: 9 AM – 9 PM.
    """
    now         = datetime.now(TZ)
    instruction = task.get("instruction", "")
    date_str    = task.get("date", "")

    # Parse target date
    target = None
    if date_str:
        target = parse_date(date_str, now)
    if not target and instruction:
        for kw in ["day after tomorrow", "tomorrow", "today"] + list(WEEKDAYS.keys()):
            if kw in instruction.lower():
                target = parse_date(kw, now)
                break

    target_date = target.date() if target else now.date()
    day_start   = TZ.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9)))
    day_end     = TZ.localize(datetime.combine(target_date, datetime.min.time().replace(hour=21)))

    try:
        service = get_calendar_service()
        result  = service.events().list(
            calendarId  = "primary",
            timeMin     = day_start.isoformat(),
            timeMax     = day_end.isoformat(),
            singleEvents= True,
            orderBy     = "startTime",
        ).execute()
    except CalendarAuthError as e:
        return None, f"❌ Auth error: {str(e)}"
    except Exception as e:
        return None, f"❌ Free slots fetch failed: {str(e)}"

    # Build busy list
    busy: list[tuple[datetime, datetime]] = []
    for ev in result.get("items", []):
        s = ev["start"].get("dateTime")
        e = ev["end"].get("dateTime")
        if s and e:
            busy.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))

    # Calculate free gaps
    free: list[tuple[datetime, datetime]] = []
    current = day_start
    for bs, be in sorted(busy):
        if current < bs:
            free.append((current, bs))
        current = max(current, be)
    if current < day_end:
        free.append((current, day_end))

    label     = target_date.strftime("%d %B %Y (%A)")
    long_free = [(s, e) for s, e in free if (e - s).seconds >= 1800]  # ≥30 min

    if not long_free:
        return None, f"😅 *{label}* — Koi 30+ min ka free slot nahi mila!\n_Bohot busy din hai!_"

    lines = [f"🟢 *Free Slots — {label}*\n"]
    for fs, fe in long_free:
        dur = (fe - fs).seconds // 60
        lines.append(f"• {fs.strftime('%I:%M %p')} – {fe.strftime('%I:%M %p')}  _({dur} min)_")
    lines.append(f"\n_Total {len(long_free)} free slot(s) available_")
    return None, "\n".join(lines)


# ── Agent Class (BaseAgent pattern) ──────────────────────────────────────────

class CalendarAgent(BaseAgent):
    NAME       = "calendar"
    SKILL_FILE = "~/.bhavai/config/prompts/calendar_agent_skill.md"

    @classmethod
    def get_tool_dispatch(cls) -> dict:
        return {
            "calendar_schedule":   schedule_event,
            "calendar_list":       list_events,
            "calendar_delete":     delete_event,
            "calendar_free_slots": find_free_slots,
        }

    @classmethod
    def run(cls, task: dict, user_id: int = 0) -> tuple[None, str]:
        sub = task.get("sub_type", "schedule")
        _log.info("CalendarAgent.run: sub_type=%s", sub)
        dispatch = {
            "list":       list_events,
            "delete":     delete_event,
            "free_slots": find_free_slots,
            "schedule":   schedule_event,
        }
        fn = dispatch.get(sub, schedule_event)
        return fn(task, user_id)


# ── Tool dispatch dict (auto-merged by agents/__init__.py) ────────────────────

AGENT_TOOL_DISPATCH: dict = CalendarAgent.get_tool_dispatch()
