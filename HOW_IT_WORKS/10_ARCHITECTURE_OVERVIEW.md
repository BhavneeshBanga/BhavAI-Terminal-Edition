# 🏗️ 10 — Architecture Overview: Poora System Ek Jagah

## Module Map

```
BhavAI-Terminal-Edition/
│
├── pyproject.toml
│   └── entry_points: bhav = bhavai.main:main
│
└── bhavai/
    │
    ├── main.py              [REPL + CLI entry point]
    │   ├── imports: click, prompt_toolkit, rich
    │   ├── Trust system (is_folder_trusted, _inline_arrow_menu)
    │   ├── wake() command handler
    │   └── REPL while loop (input → route → agent/command/bash)
    │
    ├── agent.py             [ReAct Loop Core]
    │   ├── SYSTEM_PROMPT_TEMPLATE (tool definitions + rules)
    │   ├── _run_agent_loop() (shared by plan + autonomous)
    │   ├── run_agent_loop_plan() (public, require_approval=True)
    │   ├── run_agent_loop_autonomous() (public, require_approval=False)
    │   ├── parse_llm_json() (3-layer JSON parsing)
    │   └── _build_project_context_block() (BHAVAI.md reader)
    │
    ├── modes.py             [Plan UI + Mode Enum]
    │   ├── AgentMode (PLAN="plan", AGENT="agent")
    │   ├── prompt_and_confirm_plan() (plan gen + display)
    │   └── display_deep_plan() (Rich table render)
    │
    ├── planner.py           [Deep Plan Generation]
    │   ├── PlanStep (dataclass)
    │   ├── PlannerState (dataclass)
    │   ├── DEEP_PLAN_SYSTEM_PROMPT
    │   ├── generate_deep_plan() → LLM → PlannerState
    │   ├── _save() → planner.json
    │   ├── _sync_md() → planner.md
    │   └── mark_step_status(), add_finding(), get_next_pending_step()
    │
    ├── memory.py            [Conversation History]
    │   └── ConversationMemory
    │       ├── add_message(), add_image_message()
    │       ├── get_messages() (prune if > 100k chars)
    │       ├── save_to_json(), save_to_file()
    │       └── load_from_json()
    │
    ├── config.py            [Configuration + Constants]
    │   ├── API keys (SARVAM_API_KEY, GROQ_API_KEY1-4)
    │   ├── CWD, BHAVAI_HOME, PROMPTS_DIR, BRAIN_DIR
    │   ├── ensure_prompts_dir() (default skills create)
    │   ├── ensure_brain_dir()
    │   └── get_config_summary()
    │
    ├── context.py           [Folder Tree + Secrets]
    │   ├── is_env_file() (secrets detection)
    │   ├── parse_gitignore()
    │   ├── should_ignore() (tree filtering)
    │   ├── build_folder_tree() (recursive)
    │   └── get_folder_tree_string()
    │
    ├── tools.py             [Core Sandboxed Tools]
    │   ├── validate_path() [SANDBOX]
    │   ├── validate_command() [BLOCKLIST]
    │   ├── ensure_git_initialized()
    │   ├── _git_stage()
    │   ├── list_folder, read_file, write_file
    │   ├── append_chunk (4096-token fix)
    │   ├── run_command (streaming, timeout, blocklist)
    │   ├── get_project_memory_string()
    │   └── TOOL_DISPATCH (registry)
    │
    ├── tools_extended.py    [Extended Tools]
    │   ├── search_code, find_files, get_outline
    │   ├── find_symbol, find_references, get_function_source
    │   ├── replace_lines, insert_lines, delete_lines
    │   ├── patch_file, insert_function, replace_function
    │   ├── create_directory, rename_path
    │   ├── run_tests, lint_file, check_dependencies
    │   ├── get_diff, revert_file, git_commit
    │   ├── fetch_url, duckduckgo_search, check_weather, read_image
    │   ├── list_todos
    │   └── EXTENDED_TOOL_DISPATCH
    │
    ├── skill_getter.py      [Skills Discovery]
    │   ├── _parse_skill_header()
    │   ├── list_available_skills()
    │   └── discover_skills_from_dot_bhavai() → instruction block
    │
    ├── llm.py               [LLM API Client]
    │   ├── query_llm_with_continuation() (non-streaming)
    │   ├── query_llm_with_continuation_stream() (streaming)
    │   └── provider_needs_chunking() (Sarvam=True, Groq=False)
    │
    ├── agents/              [Sub-Agents]
    │   └── calendar agent (Google Calendar integration)
    │       └── AGENT_DISPATCHERS (calendar_schedule, etc.)
    │
    ├── ui/                  [Terminal UI]
    │   ├── shimmer.py       (ShimmerStatus loading animation)
    │   ├── live_thinking.py (LiveThinkingDisplay streaming display)
    │   └── clipboard_paste.py (Image paste from clipboard)
    │
    ├── banner/
    │   └── bhavai_agent.py  (Medium-width ASCII art banner)
    │
    ├── scripts/
    │   └── initialize_markdown.py (/init command, BHAVAI.md generator)
    │
    ├── updater/
    │   └── updates.py       (Update notification on startup)
    │
    ├── helper/
    │   └── create_first_file_Note_from_bhavai_.py
    │
    └── config_commands.py   [bhav config subcommands]
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           USER INPUT                                │
│                    terminal: "bhav wake up"                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     pyproject.toml entry point                      │
│                 bhav → bhavai.main:main() [Click CLI]               │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         wake() function                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  Trust   │  │  API Key │  │  Banner  │  │  Folder Tree     │   │
│  │  Check   │  │  Check   │  │  Print   │  │  get_folder_tree │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
│                                                                     │
│  ConversationMemory() initialized                                   │
│  session_hash = uuid4().hex[:8]                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     REPL Loop (while True)                          │
│              session.prompt(get_prompt_text).strip()                │
│                                                                     │
│  Input Type Detection:                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  !cmd    │  │  /slash  │  │   mode   │  │  Regular prompt  │   │
│  │ bash run │  │ command  │  │  switch  │  │  → agent/plan    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
└───────────────────┬────────────────────────────────────────────────┘
                    │ Regular prompt
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   MODE CHECK (current_mode)                         │
├─────────────────────────┬───────────────────────────────────────────┤
│     PLAN MODE           │        AGENT MODE                         │
│                         │                                           │
│  prompt_and_confirm_plan│  run_agent_loop_autonomous()              │
│  └→ generate_deep_plan()│  └→ task_prompt = user_input             │
│     └→ LLM API call     │                                           │
│     └→ PlannerState     │                                           │
│  display_deep_plan()    │                                           │
│  y/n/feedback loop      │                                           │
│  run_agent_loop_plan()  │                                           │
└─────────────────────────┴───────────────────────────────────────────┘
                    │ (Both paths)
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    _run_agent_loop()                                │
│                                                                     │
│  System Prompt Assembly:                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SYSTEM_PROMPT = "You are BhavAI..."                         │   │
│  │   + CWD                                                     │   │
│  │   + BHAVAI.md (project context)                             │   │
│  │   + folder_tree (real-time)                                 │   │
│  │   + skills_block (dynamic instructions)                     │   │
│  │   + tool definitions                                        │   │
│  │   + strict rules                                            │   │
│  │   + response format (JSON only)                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   ReAct Loop (max 60)                       │   │
│  │                                                             │   │
│  │  1. memory.get_messages(system_prompt)                      │   │
│  │     └→ [system + history + task]                            │   │
│  │                                                             │   │
│  │  2. query_llm_with_continuation_stream(messages)            │   │
│  │     └→ Sarvam-105B / Groq (streaming)                       │   │
│  │     └→ LiveThinkingDisplay shows tokens                     │   │
│  │                                                             │   │
│  │  3. parse_llm_json(raw_response)                            │   │
│  │     ├→ XML tool_call tag parser (fallback)                  │   │
│  │     ├→ JSON pipeline (extract + escape + repair)            │   │
│  │     └→ Structural regex fallback                            │   │
│  │                                                             │   │
│  │  4. Display "💭 Thought" panel                              │   │
│  │                                                             │   │
│  │  5. if final_answer → RETURN ✅                             │   │
│  │                                                             │   │
│  │  6. Repeat-call guard (3x same call → block)               │   │
│  │                                                             │   │
│  │  7. Plan mode: mutating tool → ask y/n                      │   │
│  │                                                             │   │
│  │  8. TOOL_DISPATCH[tool_name](**tool_args)                   │   │
│  │     ├→ validate_path() [sandbox]                            │   │
│  │     ├→ validate_command() [blocklist]                       │   │
│  │     ├→ is_env_file() [secrets guard]                        │   │
│  │     └→ execute tool → return result                         │   │
│  │                                                             │   │
│  │  9. Display "🔍 Observation" panel                          │   │
│  │                                                             │   │
│  │  10. memory.add_message("assistant", llm_response)          │   │
│  │      memory.add_message("user", f"Observation:\n{result}")  │   │
│  │                                                             │   │
│  │  → Loop                                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                    │ After agent done
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│              REPL loop continues (next user input)                  │
│    memory preserved in RAM for conversation continuity              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. JSON-only LLM Communication
LLM ko sirf JSON format mein respond karne ki training di gayi hai via system prompt. XML tags, markdown fences — sab reject.

**Why:** Tool dispatch `json.loads()` se hota hai — structured, deterministic.

**Fallback:** 3-layer parsing strategy (XML parser → JSON pipeline → regex fallback)

---

### 2. 4096-Token Output Limit (Sarvam-105B)
Sarvam model ki hard limit hai 4096 output tokens. BhavAI mein **5-layer defense:**

| Layer | Implementation |
|-------|----------------|
| System prompt instruction | "Max 50 lines per tool call" |
| `append_chunk` tool | Chunked writing |
| `query_llm_with_continuation()` | Auto-stitch responses |
| `_fix_truncated_json()` | Repair cut-off JSON |
| Recovery feedback message | Error → retry with fix |

---

### 3. Conversation Memory Architecture
```
RAM:           ConversationMemory.messages[]
               → Prune oldest if > 100k chars
               → Always keep: [system_prompt, first_user_msg, recent_msgs]

Disk (auto):   ~/.bhavai/brain/<session_hash>.json  (resumable)
               ~/.bhavai/brain/<session_hash>.md    (human-readable)

Disk (manual): CWD/.bhavai/memories/<name>.md       (/export command)
```

---

### 4. Path Sandboxing — Two Allowed Roots
```
ALLOWED:
  1. CWD (current working directory) — project files
  2. ~/.bhavai/config/prompts/ — skill files only

BLOCKED:
  - Everything else (system files, other projects, etc.)
```

---

### 5. Trust-First Security Model
Folder ko trust karna mandatory hai. Reason: `.bhavai/` folder mein custom skills/commands hote hain jo code execute kar sakte hain. Trust confirmation se user ko awareness milti hai.

---

### 6. Dual Provider Strategy
```
Primary:  Sarvam-105B (Indian LLM, api.sarvam.ai)
Fallback: Groq (llama-3.3-70b-versatile, 4 API keys rotate)

provider_needs_chunking():
  → Sarvam = True  (4096 token limit → chunked writes needed)
  → Groq   = False (higher limit → no chunking needed)
```

---

## File Dependency Graph

```
main.py
├── config.py          (CWD, API keys, logger)
├── context.py         (folder tree, is_env_file)
├── memory.py          (ConversationMemory)
├── modes.py           (AgentMode, prompt_and_confirm_plan)
│   └── planner.py     (generate_deep_plan, PlannerState)
│       └── llm.py     (query_llm_with_continuation)
├── agent.py           (run_agent_loop_*)
│   ├── config.py
│   ├── context.py
│   ├── llm.py
│   ├── memory.py
│   ├── tools.py       (TOOL_DISPATCH)
│   │   ├── config.py
│   │   ├── context.py
│   │   └── tools_extended.py → EXTENDED_TOOL_DISPATCH
│   │       └── agents/ → AGENT_DISPATCHERS
│   └── skill_getter.py (discover_skills_from_dot_bhavai)
│       └── config.py
├── ui/shimmer.py
├── ui/live_thinking.py
├── ui/clipboard_paste.py
├── banner/bhavai_agent.py
├── scripts/initialize_markdown.py
│   └── llm.py
├── updater/updates.py
└── config_commands.py
```

---

## Quick Reference: "Kab kaunsa function?"

| Situation | Function | File |
|-----------|----------|------|
| `bhav wake up` typed | `wake()` | `main.py` |
| Trust check | `is_folder_trusted()` | `main.py` |
| Arrow-key menu | `_inline_arrow_menu()` | `main.py` |
| API key verify | `get_config_summary()` | `config.py` |
| Folder tree render | `get_folder_tree_string()` | `context.py` |
| `.env` file ka naam check | `is_env_file()` | `context.py` |
| `mode agent` typed | `current_mode = AgentMode.AGENT` | `main.py` |
| Plan generate | `generate_deep_plan()` | `planner.py` |
| Plan display | `display_deep_plan()` | `modes.py` |
| Agent loop start | `_run_agent_loop()` | `agent.py` |
| System prompt build | `SYSTEM_PROMPT_TEMPLATE.format()` | `agent.py` |
| BHAVAI.md read | `_build_project_context_block()` | `agent.py` |
| LLM ko call | `query_llm_with_continuation_stream()` | `llm.py` |
| LLM output parse | `parse_llm_json()` | `agent.py` |
| Tool execute | `TOOL_DISPATCH[name](**args)` | `tools.py` |
| Path safe hai? | `validate_path()` | `tools.py` |
| Command safe hai? | `validate_command()` | `tools.py` |
| Skills discover | `discover_skills_from_dot_bhavai()` | `skill_getter.py` |
| Memory save | `memory.save_to_json()` | `memory.py` |
| Memory load | `memory.load_from_json()` | `memory.py` |
| Session resume | `--resume` flag + `load_from_json()` | `main.py` |
