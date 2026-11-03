# 🤖 06 — Agent Mode (ReAct Loop) Deep Dive

## TL;DR

```
User prompt (Agent Mode mein)
    ↓
run_agent_loop_autonomous() → _run_agent_loop(require_approval=False)
    ↓
WHILE loop (max 60 iterations):
    ├── LLM call → raw_response
    ├── parse_llm_json(raw_response) → {thought, tool_name, tool_args}
    ├── Display "💭 Thought" panel
    ├── [if final_answer] → RETURN
    ├── [if run_command in Plan Mode] → ask y/n
    ├── tool = TOOL_DISPATCH[tool_name](**tool_args)
    ├── Display "🔍 Observation" panel
    └── memory.add_message(assistant + user observation)
```

---

## ReAct Pattern — Reason → Act → Observe

BhavAI **ReAct** (Reasoning + Acting) pattern follow karta hai. Yeh AI agents ka standard pattern hai:

```
Step 1 — REASON:   LLM sochta hai aur ek tool call decide karta hai
Step 2 — ACT:      Tool execute hota hai
Step 3 — OBSERVE:  Result wapas LLM ko bheja jaata hai
           ↓
Step 4 — Dobara REASON from updated context
           ↓
[Loop continues until final_answer]
```

---

## Core Function: `_run_agent_loop()`

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 699

```python
def _run_agent_loop(
    user_input:       str,
    memory:           ConversationMemory,
    current_mode:     str,
    task_prompt:      str,
    max_steps:        int     = 60,     # Maximum iterations
    console:          Console = None,
    require_approval: bool    = True,   # Plan=True, Agent=False
    planner_state     = None,
) -> str:
```

### Step 0: Task Prompt → Memory

```python
memory.add_message("user", task_prompt)
```

Pehle task prompt memory mein daala jaata hai.

### Step 1: System Prompt Build (Har Iteration mein Fresh)

```python
folder_tree           = get_folder_tree_string(CWD)
project_context_block = _build_project_context_block(CWD)
system_prompt         = SYSTEM_PROMPT_TEMPLATE.format(
    cwd=str(CWD),
    project_context_block=project_context_block,
    folder_tree=folder_tree,           # Real-time folder state
    skills_block=discover_skills_from_dot_bhavai(CWD),
    token_budget_block=_token_budget_block(),
)
```

### Step 2: Main While Loop

```python
step_count            = 0
consecutive_json_errs = 0
calls                 = 0
recent_tool_calls     = []  # Repeat detection ke liye

while step_count < max_steps:
    step_count += 1
    logger.info("ReAct step %d/%d", step_count, max_steps)
```

---

## LLM Call in Each Step

```python
raw_response = ""
with LiveThinkingDisplay("Thinking…", shimmer_color="grey") as live_disp:
    try:
        messages     = memory.get_messages(system_prompt)
        raw_response = query_llm_with_continuation_stream(
            messages,
            calls=calls % 4,          # Groq key rotation
            on_token=live_disp.on_token,  # Live token display
        )
    except Exception as exc:
        err = f"LLM Error: {exc}"
        console.print(f"[bold red]{err}[/bold red]")
        return err
```

### `LiveThinkingDisplay` kya karta hai?
- Terminal mein "Thinking…" shimmer animation dikhata hai
- Streaming tokens ko real-time display karta hai
- Context manager hai — `with` block khatam hone par animation stop

---

## JSON Parsing — 3-Layer Strategy

```python
try:
    parsed = parse_llm_json(raw_response)
    consecutive_json_errs = 0      # Reset error counter
except ValueError as exc:
    consecutive_json_errs += 1
    explanation = str(exc)

    if consecutive_json_errs >= 3:
        return "Aborting: 3 consecutive JSON errors."

    # LLM ko error feedback bhejo
    memory.add_message("assistant", raw_response)
    memory.add_message("user",
        f"ERROR: Your response could not be parsed.\n"
        f"Reason: {explanation}\n\n"
        "CRITICAL: You MUST reply with raw JSON ONLY.\n"
        '{"thought": "...", "tool_name": "...", "tool_args": {...}}'
    )
    continue  # ← Next iteration mein LLM dobara try karega
```

---

## Thought Display

```python
thought   = parsed.get("thought", "")
tool_name = parsed.get("tool_name", "")
tool_args = parsed.get("tool_args", {})

if not thought and tool_name:
    # Auto-generate thought if missing
    thought = f"Executing `{tool_name}` ({_fmt_args(tool_args)})"

if thought:
    console.print(Panel(
        f"[dim italic]{thought}[/dim italic]",
        title="[bold]💭 BhavAI Thought[/bold]",
        border_style="dim",
    ))
```

---

## `final_answer` — Loop Exit

```python
if tool_name == "final_answer":
    answer = tool_args.get("answer", "Task complete.")

    console.print("\n[bold green]✅ BhavAI Final Answer:[/bold green]")
    console.print(answer)

    memory.add_message("assistant", raw_response)

    # Planner state update
    if planner_state:
        set_plan_status(planner_state, "completed")

    return answer  # ← LOOP EXIT
```

---

## Repeat-Call Guard

```python
call_signature = (tool_name, json.dumps(tool_args, sort_keys=True, default=str))
recent_tool_calls.append(call_signature)
recent_tool_calls = recent_tool_calls[-4:]   # Last 4 rakho

if recent_tool_calls.count(call_signature) >= 3:
    result = (
        f"NOTICE: You already called {tool_name} with these exact "
        f"arguments {count} times in a row. Do NOT repeat this call. "
        "Move to the NEXT step of your plan."
    )
    memory.add_message("user", f"Observation from {tool_name}:\n{result}")
    console.print(f"[bold red]⚠  Repeat-call detected: {tool_name} — blocked[/bold red]")
    continue  # ← Tool execute nahi hoga, LLM ko warning
```

Yeh guard **infinite loop** prevent karta hai. Agar LLM ek hi tool ko same args se 3 baar call kare toh block ho jaata hai.

---

## Tool Approval Logic (Plan Mode only)

```python
MUTATING_TOOLS = {"run_command"}

is_mutating = tool_name in MUTATING_TOOLS
needs_approval = require_approval and is_mutating

if needs_approval:
    # Desktop notification
    _notify_safe("BhavAI — Permission Required", f"Tool: {tool_name}({args_display})")

    # Terminal mein poochho
    console.print(
        f"\n[bold yellow]⚡ Run [green]{tool_name}[/green]"
        f"({tool_args['command']})? (y/n/exit): [/bold yellow]",
        end=""
    )
    user_answer = console.input("").strip().lower()

    if user_answer == "n":
        result = f"User declined to run '{tool_name}'. Skipped."
        memory.add_message("user", f"Observation from {tool_name}:\n{result}")
        calls += 1
        continue  # ← Tool skip, LLM ko batao

    if user_answer == "exit":
        return "Agent loop exited by user."
    # "y" ya kuch aur → proceed
```

---

## Tool Execution

```python
if tool_name in TOOL_DISPATCH:
    tool_func    = TOOL_DISPATCH[tool_name]

    with console.status(
        f"[bold white][TOOL][/bold white] "
        f"[bold green]{tool_name}[/bold green]({args_display})…",
        spinner="dots"
    ):
        try:
            result = tool_func(**tool_args) if isinstance(tool_args, dict) else tool_func()
        except Exception as exc:
            result = f"Tool error — {tool_name}: {exc}"
            logger.error("Tool crash %s: %s", tool_name, exc)
else:
    result = f"Error: Unknown tool '{tool_name}'. Available: {list(TOOL_DISPATCH.keys())}"
```

### `tool_func(**tool_args)` — Python magic:
```python
# LLM returns:
# {"tool_name": "write_file", "tool_args": {"path": "README.md", "content": "# Hello"}}

tool_func = TOOL_DISPATCH["write_file"]   # = write_file function
result = tool_func(path="README.md", content="# Hello")
# Equivalent to: write_file(path="README.md", content="# Hello")
```

---

## Observation Display

```python
text_to_display = result[:100]  # Sirf pehle 100 chars terminal mein

console.print(Panel(
    str(text_to_display),
    title=f"[bold]🔍 Observation — {tool_name}[/bold]",
    border_style="white",
))
```

Full result memory mein jaata hai, terminal mein truncated:

```python
memory.add_message("assistant", raw_response)
memory.add_message("user", f"Observation from {tool_name}:\n{result}")  # Full result
```

---

## Timeout Handling

```python
timeout_msg = (f"ReAct loop hit {max_steps}-step limit. "
               "Task may be incomplete — try a more specific request.")
console.print(f"[bold red]⚠  {timeout_msg}[/bold red]")
return timeout_msg
```

Default `max_steps = 60`. Agar 60 iterations mein `final_answer` na aaye → loop exit.

---

## `run_agent_loop_autonomous()` vs `run_agent_loop_plan()`

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Lines 942, 998

```python
def run_agent_loop_plan(user_input, memory, current_mode, planner_state, ...):
    """Plan mode — task prompt has approved steps, approval required."""
    set_plan_status(planner_state, "in_progress")
    task_prompt = f"Task: {user_input}\n\nApproved plan:\n{steps_str}\n\n..."
    return _run_agent_loop(..., require_approval=True, planner_state=planner_state)


def run_agent_loop_autonomous(user_input, memory, current_mode, ...):
    """Autonomous mode — direct execution, no approval."""
    task_prompt = user_input   # No plan steps
    return _run_agent_loop(..., require_approval=False)
```

---

## Agent Mode — Step-by-Step Example

**User:** "list all Python files in this project" (Agent Mode)

```
Step 1:
  LLM Response: {"thought": "I need to find all .py files",
                 "tool_name": "find_files",
                 "tool_args": {"pattern": "*.py", "path": "."}}

  💭 Thought: "I need to find all .py files"
  [TOOL] find_files(pattern="*.py", path=".")…
  🔍 Observation: "bhavai/main.py\nbhavai/agent.py\n..."

  memory.add_message("assistant", raw_response)
  memory.add_message("user", "Observation from find_files:\nbhavai/main.py\n...")

Step 2:
  LLM Response: {"thought": "I have the list, will now provide the answer",
                 "tool_name": "final_answer",
                 "tool_args": {"answer": "Found 12 Python files:\n1. bhavai/main.py\n..."}}

  ✅ BhavAI Final Answer:
  Found 12 Python files:
  1. bhavai/main.py
  ...

  return answer  ← LOOP EXITS
```

---

## Memory Growth Per Step

Har step ke baad memory mein 2 messages add hote hain:
```
Initial: [system_prompt, user_task]
After Step 1: [..., assistant_response_1, user_observation_1]
After Step 2: [..., assistant_response_2, user_observation_2]
After Step N: [..., assistant_response_N, user_observation_N]
```

100,000 character limit ke baad memory pruning hoti hai (oldest messages remove).
