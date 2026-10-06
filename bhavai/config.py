from __future__ import annotations

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Load .env file from current working directory or fallback to system environment variables
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Configuration Settings
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
# SARVAM_API_KEY = ""
SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1")
SARVAM_MODEL = os.getenv("SARVAM_MODEL", "sarvam-105b")


GROQ_API_KEY1 = os.getenv("GROQ_API_KEY1")
GROQ_API_KEY2 = os.getenv("GROQ_API_KEY2")
GROQ_API_KEY3 = os.getenv("GROQ_API_KEY3")
GROQ_API_KEY4 = os.getenv("GROQ_API_KEY4")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"



# Working directory
CWD = Path.cwd().resolve()

# BhavAI Home and Prompts configuration
BHAVAI_HOME = Path(os.environ.get("BHAVAI_HOME", str(Path.home() / ".bhavai")))
CONFIG_DIR = BHAVAI_HOME / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"

DEFAULT_SAMPLE_SKILL_NAME = "SampleSkill.md"
DEFAULT_SAMPLE_SKILL_CONTENT = """---
name: Sample Proof-of-Concept Skill
description: Demonstrates how BhavAI dynamically loads skill instructions to execute specific tools for sample tasks.
---

# Sample Skill (Proof of Concept)

## Purpose & Scope
This skill is a demonstration of BhavAI's skill-based architecture. It is responsible for handling test, health-check, or sample capability queries from the user.

## Activation Triggers
Activate this skill when the user asks to:
- Run a sample skill test or verification
- Perform a proof-of-concept skill execution
- Check sample skill status or test tool execution via skill instructions

## Recommended Tool & Function
- Primary Tool: `duckduckgo_search` (for live external lookups) OR `run_command` / `search_code` (for system/code lookups).

## Execution Workflow
1. Identify the specific sample parameter or query requested by the user.
2. Formulate the appropriate tool call arguments based on the user's intent.
3. Execute the tool.
4. Return a clear and helpful response explaining that the skill instructions were loaded dynamically from `~/.bhavai/config/prompts/` and the tool was executed.

## Constraints & Guidelines
- Always stay within the sandbox rules.
- Do not execute destructive operations.
"""

DEFAULT_WEATHER_SKILL_NAME = "Weather.md"
DEFAULT_WEATHER_SKILL_CONTENT = """---
name: Weather Skill
description: Handles user requests about weather forecasts, temperature, and atmospheric conditions for any city or region.
---

# Weather Skill

## Purpose & Scope
This skill gives BhavAI the capability to retrieve and report live or current weather conditions, temperatures, humidity, and forecasts for any location worldwide.

## Activation Triggers
Activate this skill whenever the user asks:
- "What's the weather in <city>?"
- "Is it raining in <location>?"
- "Check the temperature for <city>"
- "What is the forecast for <city> today/tomorrow?"
- Any general weather or climate-related queries for a specific place.

## Tool To Use
- Tool: `check_weather`
- Arguments: `{"location": "<city_name>"}`

## Method of Calling
Call the `check_weather` tool via JSON tool call with the extracted location:
```json
{
  "thought": "Checking the weather for the requested location",
  "tool_name": "check_weather",
  "tool_args": {
    "location": "<city_name>"
  }
}
```

## Execution Workflow
1. Identify the target city or location from the user request (e.g. "Tokyo", "Delhi", "London").
2. Call `check_weather` with `{"location": "<city_name>"}`.
3. Parse the weather observation returned by the tool.
4. Provide a friendly, well-formatted response to the user summarizing the weather condition, temperature, humidity, and forecast.

## Constraints & Guidelines
- Always provide clean city names.
- Always use the `check_weather` tool rather than guessing weather data.
"""

def ensure_prompts_dir() -> Path:
    """
    Ensures that ~/.bhavai/config/prompts exists and creates default skills
    if they do not exist yet.
    """
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    sample_file = PROMPTS_DIR / DEFAULT_SAMPLE_SKILL_NAME
    if not sample_file.exists():
        sample_file.write_text(DEFAULT_SAMPLE_SKILL_CONTENT, encoding="utf-8")
    
    weather_file = PROMPTS_DIR / DEFAULT_WEATHER_SKILL_NAME
    if not weather_file.exists():
        weather_file.write_text(DEFAULT_WEATHER_SKILL_CONTENT, encoding="utf-8")
        
    return PROMPTS_DIR

# Ensure prompts directory is initialized
ensure_prompts_dir()

# Log folder configuration
LOG_DIR = BHAVAI_HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "bhavai.log"







from dotenv import load_dotenv
import httpx

# Load .env file from current working directory or fallback to system environment variables
from pathlib import Path
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)
import os

# ── Sarvam API ──────────────────────────────────────────────
SARVAM_API_KEY   = os.getenv("SARVAM_API_KEY")
# print(SARVAM_API_KEY)

SARVAM_BASE_URL  = "https://api.sarvam.ai/v1"
SARVAM_MODEL     = "sarvam-105b"   # or "sarvam-30b" for faster/cheaper

# ── Agent settings ───────────────────────────────────────────
MAX_STEPS        = 6      # how many Thought→Action→Observation loops before giving up
TEMPERATURE      = 0.2    # low = more focused/deterministic
MAX_TOKENS       = 4096    # max tokens per LLM response






# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

logger = logging.getLogger("BhavAI")
logger.info("BhavAI initialized. Activated CWD: %s", CWD)

def get_config_summary():
    """Returns a status summary of loaded settings (excluding API key secrets)."""
    return {
        "CWD": str(CWD),
        "API_URL": SARVAM_BASE_URL,
        "MODEL": SARVAM_MODEL,
        "LOG_FILE": str(LOG_FILE),
        "API_KEY_PRESENT": SARVAM_API_KEY is not None
    }
