# 💬 03 — Prompt to Execution: User ka Input → LLM → Tool

## TL;DR

```
User types: "make a README file for my project"
    ↓
[Plan Mode] → LLM se plan generate karo → User confirm kare
    ↓
run_agent_loop_plan() call hota hai
    ↓
System Prompt assemble hota hai (CWD + folder tree + skills + rules)
    ↓
messages = [system_prompt + history + user_task]
    ↓
LLM ko bhejo (Sarvam-105B ya Groq)
    ↓
LLM returns JSON: {"thought": "...", "tool_name": "write_file", "tool_args": {...}}
    ↓
JSON parse karo → tool execute karo → result memory mein daalo
    ↓
Loop repeat (jab tak final_answer na aaye)
```

---

## Phase 1: User Input Processing (main.py)

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 595

```python
user_input = session.prompt(get_prompt_text).strip()
user_input = expand_pasted_text(user_input, paste_store)
```

### `expand_pasted_text()` kya karta hai?

Jab user terminal mein bahut saari lines paste karta hai (e.g., code paste), toh woh ek placeholder mein compress ho jaata hai:
```
[Pasted text #1 +47 lines]
```

`expand_pasted_text()` is placeholder ko wapas original pasted text se replace karta hai before sending to agent.

---

## Phase 2: Task Prompt Assembly

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 743 (Plan Mode)

```python
folder_tree = get_folder_tree_string(CWD)
skills_block = discover_skills_from_dot_bhavai(CWD)
```

Phir Plan Mode mein:

```python
planner_state = prompt_and_confirm_plan(user_input, folder_tree, console, skills_block=skills_block)
```

Agent ko jo actual task prompt bheja jaata hai woh `run_agent_loop_plan()` mein banta hai:

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 963

```python
steps_str = "\n".join(
    f"  {step.order}. [{step.step_id}] {step.title}: {step.description}"
    f" (Tools: {', '.join(step.tools) if step.tools else 'any'})"
    for step in planner_state.plan
)
task_prompt = (
    f"Task: {user_input}\n\n"
    f"Refined Goal: {planner_state.refined_goal}\n\n"
    f"Approved plan (execute ALL steps in order):\n{steps_str}\n\n"
    f"{_chunk_reminder_suffix()}"
    f"After completing ALL steps, call final_answer with a summary of what was done."
)
```

**Agent Mode mein** task prompt directly user input hi hota hai:
```python
task_prompt = user_input  # No plan steps
```

---

## Phase 3: System Prompt Assembly

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 726

Yeh sabse important step hai — System Prompt ek dynamic template hai jo har baar freshly build hota hai:

```python
folder_tree           = get_folder_tree_string(CWD)
project_context_block = _build_project_context_block(CWD)
system_prompt         = SYSTEM_PROMPT_TEMPLATE.format(
    cwd=str(CWD),
    project_context_block=project_context_block,
    folder_tree=folder_tree,
    skills_block=discover_skills_from_dot_bhavai(CWD),
    token_budget_block=_token_budget_block(),
)
```

### System Prompt ke Sections:

```
┌────────────────────────────────────────────────────────┐
│ "You are BhavAI, a personal AI agent..."               │
│ "Activated folder: {cwd}"                              │
│                                                        │
│ ━━━━ PROJECT CONTEXT (BHAVAI.md se) ━━━━               │
│ {project_context_block}                                │
│                                                        │
│ Current folder structure:                              │
│ {folder_tree}  ← real-time tree                        │
│                                                        │
│ Additional skills you have:                            │
│ {skills_block} ← dynamic skill instructions           │
│                                                        │
│ ━━━━ AVAILABLE TOOLS ━━━━                              │
│ list_folder, read_file, write_file, ...                │
│                                                        │
│ ━━━━ STRICT RULES ━━━━                                 │
│ 1. NEVER delete entire files...                        │
│ 2. Stay inside {cwd}...                                │
│ 3. Blocked commands: rm, rmdir, del...                 │
│ ...                                                    │
│                                                        │
│ ━━━━ RESPONSE FORMAT ━━━━                              │
│ Raw JSON only: {thought, tool_name, tool_args}         │
│                                                        │
│ {token_budget_block} ← Sarvam ke liye 4096 limit hint │
└────────────────────────────────────────────────────────┘
```

### `_build_project_context_block()`:

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 650

```python
def _build_project_context_block(cwd) -> str:
    memory = get_project_memory_string(cwd)   # BHAVAI.md padho
    if not memory:
        return ""
    return (
        "\n━━━━ PROJECT CONTEXT (loaded from BHAVAI.md) ━━━━\n"
        f"{memory}\n"
    )
```

`BHAVAI.md` project-specific context file hai. Agar exist kare toh system prompt mein automatically include ho jaati hai, agent ko project ke baare mein context milta hai.

---

## Phase 4: Memory Compilation

**File:** [`bhavai/memory.py`](../bhavai/memory.py) — Line 69

```python
def get_messages(self, system_prompt: str) -> list:
    compiled = [{"role": "system", "content": system_prompt}]

    total_chars = sum(len(m["content"]) for m in self.messages)
    if total_chars <= self.max_chars:  # 100,000 chars limit
        compiled.extend(self.messages)
        return compiled

    # Pruning: first message + recent messages jo fit hain
    ...
```

Final messages array structure:
```json
[
    {"role": "system", "content": "<full system prompt>"},
    {"role": "user", "content": "<original task>"},
    {"role": "assistant", "content": "{\"thought\":\"...\", \"tool_name\":\"read_file\", ...}"},
    {"role": "user", "content": "Observation from read_file:\n<file contents>"},
    {"role": "assistant", "content": "{\"thought\":\"...\", \"tool_name\":\"write_file\", ...}"},
    ...
]
```

---

## Phase 5: LLM API Call

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 750

```python
with LiveThinkingDisplay("Thinking…", shimmer_color="grey") as live_disp:
    messages     = memory.get_messages(system_prompt)
    raw_response = query_llm_with_continuation_stream(
        messages,
        calls=calls % 4,
        on_token=live_disp.on_token,
    )
```

### Provider Selection:
BhavAI ke paas **2 LLM providers** hain:

1. **Sarvam-105B** (primary) — Indian LLM, `api.sarvam.ai`
2. **Groq** (fallback / rotation) — `llama-3.3-70b-versatile`

`calls % 4` pattern se Groq ke 4 API keys rotate hote hain:
- calls=0 → GROQ_API_KEY1
- calls=1 → GROQ_API_KEY2
- calls=2 → GROQ_API_KEY3
- calls=3 → GROQ_API_KEY4

### `query_llm_with_continuation_stream()`:
Yeh function streaming response handle karta hai aur 4096-token limit se paar hone par automatically continuation call karta hai (stitching responses).

---

## Phase 6: JSON Parsing — LLM Output Parse karna

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 769

```python
parsed = parse_llm_json(raw_response)
```

### `parse_llm_json()` — 3-Layer Strategy:

```python
def parse_llm_json(raw_text: str) -> dict:
    # Layer 0: XML <tool_call> format (Sarvam-105B sometimes returns this)
    xml_result = _parse_tool_call_tags(raw_text)
    if xml_result:
        return xml_result

    # Layer 1: Standard JSON cleaning pipeline
    cleaned = clean_json_text(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Layer 2: Structural regex fallback (malformed JSON with unescaped quotes)
    structural = _structural_fallback_parse(raw_text)
    if structural and structural.get("tool_name"):
        return structural

    raise ValueError("All JSON parsing strategies failed")
```

### `clean_json_text()` pipeline:
```
raw_text
    → _extract_json_block()    # <think> tags strip, markdown fences remove, {..} extract
    → _escape_control_chars()  # Raw \n \t inside strings ko \\n \\t se replace karo
    → _fix_truncated_json()    # Cut-off JSON ko close karo (", }, ])
```

---

## Phase 7: Tool Dispatch

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 846

```python
thought   = parsed.get("thought", "")
tool_name = parsed.get("tool_name", "")
tool_args = parsed.get("tool_args", {})

if tool_name == "final_answer":
    # Task complete → return answer
    answer = tool_args.get("answer", "Task complete.")
    memory.add_message("assistant", raw_response)
    return answer

if tool_name in TOOL_DISPATCH:
    tool_func = TOOL_DISPATCH[tool_name]
    result = tool_func(**tool_args)
```

### `TOOL_DISPATCH` dictionary:
**File:** [`bhavai/tools.py`](../bhavai/tools.py) — End of file

```python
TOOL_DISPATCH = {
    "list_folder":        list_folder,
    "read_file":          read_file,
    "write_file":         write_file,
    "append_chunk":       append_chunk,
    "run_command":        run_command,
    "search_code":        search_code,
    # ... etc.
}
```

---

## Phase 8: Plan Mode Tool Approval

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 872

```python
MUTATING_TOOLS = {"run_command"}  # sirf yahi approval maangte hain

is_mutating = tool_name in MUTATING_TOOLS
needs_approval = require_approval and is_mutating  # Plan mode mein True

if needs_approval:
    _notify_safe("BhavAI — Permission Required", f"Tool: {tool_name}({args_display})")
    user_answer = console.input("⚡ Run run_command(...)? (y/n/exit): ").strip().lower()

    if user_answer == "n":
        result = "User declined to run..."
        continue
    if user_answer == "exit":
        return "Agent loop exited by user."
```

---

## Phase 9: Memory Update & Loop Continue

```python
# Tool result dikhao
console.print(Panel(
    str(result[:100]),
    title=f"🔍 Observation — {tool_name}",
))

# Memory mein daalo
memory.add_message("assistant", raw_response)
memory.add_message("user", f"Observation from {tool_name}:\n{result}")

calls = calls + 1
# → Loop next iteration → LLM dobara call hota hai
```

---

## Complete End-to-End Flow Diagram

```
User: "make a README for this project"
    │
    ▼ main.py REPL
[Plan Mode detected]
    │
    ├── get_folder_tree_string(CWD)          context.py
    ├── discover_skills_from_dot_bhavai(CWD) skill_getter.py
    │
    ▼ modes.py
prompt_and_confirm_plan()
    ├── start_new_plan(user_input, folder_tree, skills_block)
    │       └── generate_deep_plan()         planner.py
    │               └── query_llm_with_continuation()   [LLM: Plan generation]
    │                       └── returns JSON plan
    │               └── _parse_plan_response() → PlannerState
    │               └── _save() → planner.json
    │               └── _sync_md() → planner.md
    └── display_deep_plan(planner_state)
        └── Rich Table with steps
    │
    ▼ user types "y"
    │
    ▼ agent.py
run_agent_loop_plan(user_input, memory, planner_state)
    ├── task_prompt = "Task: ...\nApproved plan:\n1. Analyze...\n2. Write..."
    └── _run_agent_loop(task_prompt, require_approval=True)
            │
            ├── memory.add_message("user", task_prompt)
            │
            ├── [SYSTEM PROMPT BUILD]
            │   ├── get_folder_tree_string(CWD)
            │   ├── _build_project_context_block()  ← BHAVAI.md read
            │   ├── discover_skills_from_dot_bhavai()
            │   └── SYSTEM_PROMPT_TEMPLATE.format(...)
            │
            └── ─── ReAct Loop (max 60 steps) ───────────────────────
                │
                ├── memory.get_messages(system_prompt)   memory.py
                ├── query_llm_with_continuation_stream() llm.py
                │       └── HTTP POST to Sarvam/Groq API
                │           └── streaming tokens → LiveThinkingDisplay
                │
                ├── parse_llm_json(raw_response)
                │   ├── _parse_tool_call_tags()  [XML fallback]
                │   ├── clean_json_text()         [JSON pipeline]
                │   └── _structural_fallback_parse() [regex fallback]
                │
                ├── Display "💭 BhavAI Thought" panel
                │
                ├── [if final_answer] → return answer ✅
                │
                ├── [if mutating tool + plan mode] → ask y/n
                │
                ├── tool_func(**tool_args)   [TOOL_DISPATCH]
                │   └── tools.py / tools_extended.py
                │       ├── validate_path()   [sandboxing]
                │       ├── validate_command() [blocklist]
                │       └── execute tool
                │
                ├── Display "🔍 Observation" panel
                ├── memory.add_message("assistant", raw_response)
                └── memory.add_message("user", f"Observation:\n{result}")
                │
                └── [loop continues until final_answer or 60 steps]
```
