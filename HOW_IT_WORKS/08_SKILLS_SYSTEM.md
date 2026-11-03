# 🎯 08 — Skills System: Custom Capabilities kaise Add hoti hain

## TL;DR

```
Skills = .md files jo agent ko batati hain koi special task kaise karna hai

2 types:
  1. Global Skills:  ~/.bhavai/config/prompts/*.md
  2. Local Skills:   CWD/.bhavai/skills/<skill-name>/SKILL.md

Agent ko system prompt mein instruction diya jaata hai ki:
    "Agar tujhe koi unfamiliar task mile → ~/.bhavai/config/prompts/ check kar"
```

---

## Skill Discovery — `discover_skills_from_dot_bhavai()`

**File:** [`bhavai/skill_getter.py`](../bhavai/skill_getter.py) — Line 101

Yeh function system prompt ke liye ek **instruction block** return karta hai:

```python
def discover_skills_from_dot_bhavai(cwd: Path = None) -> str:
    return (
        "━━━━ DYNAMIC SKILLS & UNFAMILIAR CAPABILITIES ━━━━\n"
        "If the user asks you to perform an unfamiliar task:\n"
        "1. Check skills directory: `list_folder(path='~/.bhavai/config/prompts')`\n"
        "2. Match user request against available skill files.\n"
        "3. If matching skill found:\n"
        "   - Read: `read_file(path='~/.bhavai/config/prompts/<SkillName>.md')`\n"
        "   - Follow the skill's instructions and execute the tool.\n"
        "4. If NO matching skill:\n"
        "   - Call `final_answer` and say you cannot perform this task.\n"
    )
```

**Note:** Yeh function agent ko pehle se saari skills load karke nahi deta — balki agent ko **dynamically discover** karne ki instruction deta hai. Token budget bachane ke liye yeh design decision hai.

---

## Skill File Format

Har skill ek `.md` file hai with YAML frontmatter:

```markdown
---
name: Weather Skill
description: "Handles user requests about weather for any city."
---

# Weather Skill

## Purpose & Scope
This skill gives BhavAI capability to get live weather data.

## Activation Triggers
Use this when user asks:
- "What's the weather in <city>?"
- "Is it raining in <place>?"

## Tool To Use
- Tool: `check_weather`
- Arguments: `{"location": "<city_name>"}`

## Method of Calling
{
  "thought": "Checking weather",
  "tool_name": "check_weather",
  "tool_args": {"location": "<city>"}
}

## Execution Workflow
1. Extract city from user request
2. Call check_weather with location
3. Format and return result
```

---

## Global Skills — Default Skills

**Location:** `~/.bhavai/config/prompts/`

BhavAI startup par automatically create karta hai (agar exist nahi):

### `Weather.md` — Weather Skill
**File created by:** `config.py:ensure_prompts_dir()`

```
- Activation: "weather in Delhi", "temperature forecast"
- Tool: check_weather
```

### `SampleSkill.md` — Proof of Concept
```
- Activation: "run sample skill", "test skill"
- Tool: duckduckgo_search / run_command
```

**Code in `config.py`:**
```python
def ensure_prompts_dir() -> Path:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Default skills create karo
    sample_file = PROMPTS_DIR / "SampleSkill.md"
    if not sample_file.exists():
        sample_file.write_text(DEFAULT_SAMPLE_SKILL_CONTENT)

    weather_file = PROMPTS_DIR / "Weather.md"
    if not weather_file.exists():
        weather_file.write_text(DEFAULT_WEATHER_SKILL_CONTENT)

    return PROMPTS_DIR
```

---

## Local Skills — Per-Project Skills

**Location:** `CWD/.bhavai/skills/<skill-name>/SKILL.md`

### Example Structure:
```
.bhavai/
└── skills/
    ├── learning-mode/
    │   └── SKILL.md    ← "How to teach the user step-by-step"
    └── dummy/
        └── SKILL.md    ← Demo skill
```

### Kaise add karein apna skill:
```bash
mkdir -p .bhavai/skills/my-skill
cat > .bhavai/skills/my-skill/SKILL.md << 'EOF'
---
name: My Custom Skill
description: "Does something special for this project."
---

# My Custom Skill

## Activation Triggers
- When user asks to do X
- When user says Y

## Tool To Use
- Tool: `run_command`
- Command: `python my_script.py`

## Workflow
1. Run the script
2. Parse output
3. Return result
EOF
```

---

## Skill Listing — `list_available_skills()`

**File:** [`bhavai/skill_getter.py`](../bhavai/skill_getter.py) — Line 58

```python
def list_available_skills(cwd: Path = None) -> list[dict]:
    skills = []
    seen_paths = set()

    # 1. Global skills (~/.bhavai/config/prompts/*.md)
    prompts_dir = ensure_prompts_dir()
    for skill_file in sorted(prompts_dir.glob("*.md")):
        title, desc = _parse_skill_header(skill_file)
        skills.append({
            "id": skill_file.stem,
            "title": title,
            "description": desc,
            "path": skill_file,
        })

    # 2. Local skills (CWD/.bhavai/skills/*/SKILL.md)
    if cwd:
        local_skills_dir = cwd / ".bhavai" / "skills"
        for skill_folder in sorted(local_skills_dir.iterdir()):
            skill_file = skill_folder / "SKILL.md"
            if skill_file.is_file():
                title, desc = _parse_skill_header(skill_file)
                skills.append({...})

    return skills
```

---

## Skill Header Parsing — `_parse_skill_header()`

**File:** [`bhavai/skill_getter.py`](../bhavai/skill_getter.py) — Line 9

```python
_NAME_RE = re.compile(r'^name:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_DESC_RE = re.compile(r'^description:\s*"(.+?)"\s*$', re.MULTILINE | re.DOTALL)

def _parse_skill_header(skill_file: Path, max_desc_len: int = 220) -> tuple[str, str]:
    text = skill_file.read_text(encoding="utf-8")

    name_match = _NAME_RE.search(text)
    desc_match = _DESC_RE.search(text)

    title = name_match.group(1).strip() if name_match else ""
    desc  = desc_match.group(1).strip() if desc_match else ""

    # Fallback: pehla markdown heading
    if not title:
        for line in text.splitlines():
            if line.strip().startswith("#"):
                title = line.strip().lstrip("#").strip()
                break
        if not title:
            title = skill_file.stem

    # Description truncate
    if len(desc) > max_desc_len:
        desc = desc[:max_desc_len].rsplit(" ", 1)[0] + "..."

    return title, desc
```

---

## Skill Runtime Flow — Agent ka Perspective

**User asks:** "check the weather in Mumbai"

```
Step 1: Agent ke system prompt mein skill instruction hai:
    "Check ~/.bhavai/config/prompts/ for matching skills"

Step 2: Agent calls:
    {"tool_name": "list_folder", "tool_args": {"path": "~/.bhavai/config/prompts"}}

Step 3: Observation:
    "SampleSkill.md
     Weather.md"

Step 4: Agent calls:
    {"tool_name": "read_file", "tool_args": {"path": "~/.bhavai/config/prompts/Weather.md"}}

Step 5: Observation: [Full Weather.md content]
    "...Tool: check_weather\n...Arguments: {\"location\": \"<city>\"}"

Step 6: Agent follows skill instructions:
    {"tool_name": "check_weather", "tool_args": {"location": "Mumbai"}}

Step 7: Weather result return → final_answer
```

---

## Slash Commands vs Skills

| Feature | Slash Commands (`/cmd`) | Skills |
|---------|------------------------|--------|
| **Location** | `.bhavai/commands/<name>.md` | `.bhavai/skills/<name>/SKILL.md` or `~/.bhavai/config/prompts/*.md` |
| **Triggered by** | User typing `/cmd_name` | Agent dynamically (unfamiliar task) |
| **Format** | Free text (becomes user prompt) | Structured (name, description, workflow) |
| **Access** | Directly read + send to agent | Agent reads on-demand |
| **Scope** | Project-local only | Global + project-local |

### Slash Command Example:
`.bhavai/commands/push.md`:
```markdown
Push the current code to GitHub with a meaningful commit message.
First check git status, create a commit, and push to origin main.
```

When user types `/push`:
```python
command_path = CWD / ".bhavai" / "commands" / "push.md"
user_input = command_path.read_text(encoding="utf-8").strip()
# → agent gets: "Push the current code to GitHub..."
```

---

## `/init` — BHAVAI.md Generator

**File:** [`bhavai/scripts/initialize_markdown.py`](../bhavai/scripts/initialize_markdown.py)

`/init` command `generate_bhavai_md(CWD)` call karta hai jo LLM se project ka summary generate karwaata hai aur `BHAVAI.md` mein save karta hai.

Yeh file phir system prompt mein inject hoti hai har session mein:
```python
project_context_block = _build_project_context_block(CWD)
# → reads BHAVAI.md and adds to system prompt
```
