"""
bhavai/agents/calendar/parser.py
─────────────────────────────────
Pure parsing helpers for the Google Calendar agent.
NO Google API calls here — only text → structured-data conversion.

Functions
---------
parse_time(t)               → (hour, minute) | None
parse_date(d, now)          → datetime | None
parse_reminder_minutes(txt) → int (minutes before event)
parse_event(user_message)   → dict with all event fields
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env", override=True)

USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Asia/Kolkata")
TZ = pytz.timezone(USER_TIMEZONE)

# ── Lookup tables ────────────────────────────────────────────────────────────

MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

WEEKDAYS: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}

# Common stop-words when auto-generating an event title
_TITLE_STOP = {
    "on", "at", "in", "the", "a", "an", "to", "for", "me", "my",
    "remind", "schedule", "set", "create", "add", "book", "inform",
    "notify", "and", "with", "about", "please", "i", "want", "need",
}


# ── Time parser ──────────────────────────────────────────────────────────────

def parse_time(t: str) -> tuple[int, int] | None:
    """
    Converts a human-readable time string to (hour_24, minute).

    Handles:
      "half past 3"  → (3, 30)
      "quarter to 4" → (3, 45)
      "quarter past 4" → (4, 15)
      "9am", "9:30pm", "21:00", "14:30"
    Returns None if no time pattern found.
    """
    t = t.lower().strip()

    m = re.search(r"half past (\d+)", t)
    if m:
        return (int(m.group(1)) % 24, 30)

    m = re.search(r"quarter to (\d+)", t)
    if m:
        return ((int(m.group(1)) - 1) % 24, 45)

    m = re.search(r"quarter past (\d+)", t)
    if m:
        return (int(m.group(1)) % 24, 15)

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        h  = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        ap = m.group(3)
        if ap == "pm" and h != 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        return (h % 24, mn)

    return None


# ── Date parser ──────────────────────────────────────────────────────────────

def parse_date(d: str, now: datetime) -> datetime | None:
    """
    Converts a human-readable date string to a datetime (time zeroed).

    Handles:
      "today", "aaj", "tomorrow", "kal", "day after tomorrow", "parso"
      weekday names: "monday", "next friday"
      ISO:      "2026-04-15"
      DD/MM/YYYY: "15/04/2026"
      Natural:  "4 apr", "April 4", "4 april 2026"
    Returns None if no date pattern found.
    """
    d = d.lower().strip()

    if d in ("today", "aaj"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if d in ("tomorrow", "kal", "tmrw", "tmr"):
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if d in ("day after tomorrow", "parso"):
        return (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    for day_name, day_num in WEEKDAYS.items():
        if day_name in d:
            ahead = day_num - now.weekday()
            if "next" in d or ahead <= 0:
                ahead += 7
            return (now + timedelta(days=ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ISO: 2026-04-15
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m:
        return now.replace(
            year=int(m.group(1)), month=int(m.group(2)),
            day=int(m.group(3)), hour=0, minute=0, second=0, microsecond=0,
        )

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", d)
    if m:
        return now.replace(
            year=int(m.group(3)), month=int(m.group(2)),
            day=int(m.group(1)), hour=0, minute=0, second=0, microsecond=0,
        )

    # "4 apr 2026" / "april 4" / "4 april"
    for mname, mnum in MONTHS.items():
        if mname in d:
            day_m  = re.search(r"\b(\d{1,2})\b", d)
            year_m = re.search(r"\b(20\d{2})\b", d)
            if day_m:
                day  = int(day_m.group(1))
                year = int(year_m.group(1)) if year_m else now.year
                try:
                    result = now.replace(
                        year=year, month=mnum, day=day,
                        hour=0, minute=0, second=0, microsecond=0,
                    )
                    if result < now and not year_m:
                        result = result.replace(year=now.year + 1)
                    return result
                except ValueError:
                    pass

    return None


# ── Reminder parser ──────────────────────────────────────────────────────────

def parse_reminder_minutes(text: str) -> int:
    """
    Extracts reminder lead-time (in minutes) from natural language.

    Examples:
      "remind me 2 hours before"  → 120
      "notify 15 minutes before"  → 15
      "half hour before"          → 30
    Defaults to 30 if no pattern found.
    """
    t = text.lower()
    m = re.search(r"(\d+)\s*hour[s]?\s*before", t)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*min(?:utes?)?\s*before", t)
    if m:
        return int(m.group(1))
    if "half hour before" in t:
        return 30
    return 30


# ── Smart Event Parser ───────────────────────────────────────────────────────

def parse_event(user_message: str) -> dict:
    """
    Full event extraction: LLM + Regex dual-pass.
    Regex result wins for time/date (more accurate than LLM for structured data).
    LLM fills in title, description, location.

    Returns a dict with keys:
        title, date (YYYY-MM-DD), start_time (HH:MM), end_time (HH:MM),
        description, reminder_minutes, attendees (list[str]), location
    """
    from bhavai.llm import query_llm_with_continuation  # avoid circular import at top

    now = datetime.now(TZ)

    # ── LLM parse ────────────────────────────────────────────────────────────
    prompt = f"""Extract calendar event details from: "{user_message}"

Now: {now.strftime("%Y-%m-%d %H:%M")} | Timezone: {USER_TIMEZONE}
Today: {now.strftime("%A, %d %B %Y")}
Tomorrow: {(now + timedelta(days=1)).strftime("%Y-%m-%d")}

Return ONLY valid JSON (no markdown, no extra text):
{{
  "title": "event title",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "description": "",
  "reminder_minutes": 30,
  "attendees": [],
  "location": ""
}}

RULES:
- Return ONLY a valid JSON object. No markdown. No extra text.
- Always make the Title best suitable for the Event.
- Extract EXACT time user mentioned: "9am"="09:00", "6pm"="18:00"
- NEVER default to 10:00 unless user said 10.
- end_time = start_time + 1 hour.
- "remind me at 9am" = event at 09:00.
"""

    llm_data: dict = {}
    try:
        messages = [
            {"role": "system", "content": "You are a calendar event parser. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        raw = query_llm_with_continuation(messages)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            llm_data = json.loads(m.group())
    except Exception:
        pass  # regex fallback handles it

    # ── Regex parse ───────────────────────────────────────────────────────────
    msg = user_message.lower()

    # Date — try keywords first, then weekday, then calendar date
    regex_date = None
    for keyword in ["day after tomorrow", "parso", "tomorrow", "kal", "today", "aaj"]:
        if keyword in msg:
            regex_date = parse_date(keyword, now)
            break

    if not regex_date:
        for day in WEEKDAYS:
            pattern = f"next {day}" if f"next {day}" in msg else day
            if day in msg:
                regex_date = parse_date(pattern, now)
                break

    if not regex_date:
        date_m = re.search(
            r"(\d{1,2})\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
            r"nov(?:ember)?|dec(?:ember)?)\s*(?:20(\d{2}))?",
            msg,
        )
        if date_m:
            regex_date = parse_date(date_m.group(0), now)

    # Time — extract all AM/PM / 24-hour tokens
    time_matches = re.findall(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{2}:\d{2})\b", msg)
    regex_times = [parse_time(t) for t in time_matches if parse_time(t)]

    # ── Combine best results ──────────────────────────────────────────────────

    # Date: regex > LLM
    final_date = now.date()
    if regex_date:
        final_date = regex_date.date()
    elif llm_data.get("date"):
        try:
            final_date = datetime.strptime(llm_data["date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    # Time: regex wins; fallback to LLM; last resort 9:00
    if regex_times:
        sh, sm = regex_times[0]
        eh, em = (sh + 1) % 24, sm
    elif llm_data.get("start_time"):
        t = parse_time(llm_data["start_time"])
        sh, sm = t if t else (9, 0)
        eh, em = (sh + 1) % 24, sm
    else:
        sh, sm, eh, em = 9, 0, 10, 0

    # End time override from LLM if user specified explicitly
    if llm_data.get("end_time") and not regex_times:
        et = parse_time(llm_data["end_time"])
        if et:
            eh, em = et

    # Title
    title = (llm_data.get("title") or "").strip()
    if not title or title.lower() in ("meeting", "event", "reminder", "appointment"):
        words = [
            w for w in user_message.split()
            if w.lower() not in _TITLE_STOP
            and not re.match(r"[\d:]+", w)
            and len(w) > 2
        ][:5]
        title = " ".join(words).title() if words else "Meeting"

    # Reminder: explicit regex > LLM (if LLM changed from default 30)
    reminder = parse_reminder_minutes(user_message)
    if llm_data.get("reminder_minutes") and int(llm_data["reminder_minutes"]) != 30:
        reminder = int(llm_data["reminder_minutes"])

    # Attendees: only real email addresses
    attendees = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", user_message)

    return {
        "title":            title,
        "date":             final_date.strftime("%Y-%m-%d"),
        "start_time":       f"{sh:02d}:{sm:02d}",
        "end_time":         f"{eh:02d}:{em:02d}",
        "description":      llm_data.get("description", ""),
        "reminder_minutes": reminder,
        "attendees":        attendees,
        "location":         llm_data.get("location", ""),
    }
