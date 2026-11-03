# 📋 05 — Plan Mode Deep Dive: Planner System Kaise Kaam Karta Hai

## TL;DR

```
User ka prompt (Plan Mode mein)
    ↓
modes.py: prompt_and_confirm_plan()
    ↓
planner.py: generate_deep_plan()
    ↓
LLM ko "Strategic Planning Module" system prompt bhejo
    ↓
LLM returns JSON: {refined_goal, analysis, plan: [{step_id, title, tools, depends_on}]}
    ↓
PlannerState object bano
    ↓
planner.json + planner.md save karo
    ↓
Rich table mein dikhao
    ↓
User y/n/feedback deta hai
    ↓
Agar "y" → run_agent_loop_plan() → ReAct execution
```

---

## Data Models

**File:** [`bhavai/planner.py`](../bhavai/planner.py)

### `PlanStep` — Ek step ka blueprint:

```python
@dataclass
class PlanStep:
    step_id:      str           # "step-1", "step-2"...
    order:        int           # 1, 2, 3...
    title:        str           # "Analyze project structure"
    description:  str           # Detailed instruction
    status:       str = "pending"  # pending|in_progress|completed|failed|skipped
    tools:        List[str]     # ["read_file", "search_code"]
    depends_on:   List[str]     # ["step-1"] → step-2 step-1 ke baad
    artifacts:    List[str]     # Files created by this step
    notes:        str           # Agent ke observations
    started_at:   Optional[str] # ISO timestamp
    completed_at: Optional[str] # ISO timestamp
```

### `PlannerState` — Poore plan ka state:

```python
@dataclass
class PlannerState:
    version:        str         # "1.0"
    session_id:     str         # UUID 8-char, e.g. "a3f9b12c"
    created_at:     str         # ISO timestamp
    updated_at:     str
    original_query: str         # User ka original input
    refined_goal:   str         # LLM ka refined 1-line goal
    context:        dict        # {folder_tree, analysis}
    status:         str         # planning|in_progress|completed|paused
    plan:           List[PlanStep]
    current_step_id: Optional[str]
    findings:       List[str]   # Agent discoveries during execution
    metadata:       dict        # {total_steps, completed_steps, failed_steps, model_used}
```

---

## Deep Plan Generation — `generate_deep_plan()`

**File:** [`bhavai/planner.py`](../bhavai/planner.py) — Line 140

```python
def generate_deep_plan(user_input, folder_tree, skills_block="", feedback=None):
    user_prompt = f"""User request: {user_input}

Current workspace:
{folder_tree}

Available skills:
{skills_block}

Generate the deep plan now."""

    if feedback:
        user_prompt += f"\n\nUser feedback to adjust the plan: {feedback}"

    messages = [
        {"role": "system", "content": DEEP_PLAN_SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt}
    ]

    raw = query_llm_with_continuation(messages)   # LLM call

    state = _parse_plan_response(raw, user_input, folder_tree)
    _save(state)       # planner.json write
    _sync_md(state)    # planner.md write
    return state
```

### `DEEP_PLAN_SYSTEM_PROMPT` — Planning LLM ka special prompt:

```
You are BhavAI's Strategic Planning Module.

THINKING PROCESS:
1. Clarify Intent: What does the user REALLY want?
2. Decompose: Break into atomic, verifiable steps.
3. Identify Dependencies: Which steps must finish first?
4. Assess Risks: What could go wrong?
5. Select Tools: Name specific BhavAI tools.
6. Estimate Order: Sequence steps logically.

OUTPUT FORMAT — strict JSON only:
{
  "refined_goal": "...",
  "analysis": "...",
  "plan": [
    {
      "step_id": "step-1",
      "order": 1,
      "title": "Short title",
      "description": "Detailed instruction...",
      "tools": ["tool_name"],
      "depends_on": []
    }
  ]
}
```

---

## Plan Response Parsing — `_parse_plan_response()`

**File:** [`bhavai/planner.py`](../bhavai/planner.py) — Line 175

```python
def _parse_plan_response(raw, user_input, folder_tree):
    text = raw.strip()

    # Markdown fences hata do
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m: text = m.group(1).strip()

    # Outermost { } extract karo
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _fallback_plan(user_input, folder_tree)  # Fallback plan

    # PlanStep objects bano
    plan_steps = []
    for i, item in enumerate(data.get("plan", []), start=1):
        plan_steps.append(PlanStep(
            step_id=item.get("step_id", f"step-{i}"),
            order=item.get("order", i),
            title=item.get("title", f"Step {i}"),
            description=item.get("description", ""),
            tools=item.get("tools", []),
            depends_on=item.get("depends_on", []),
        ))

    return PlannerState(
        original_query=user_input,
        refined_goal=data.get("refined_goal", user_input),
        context={"folder_tree": folder_tree, "analysis": data.get("analysis", "")},
        plan=plan_steps,
    )
```

### Fallback Plan — Jab LLM JSON fail kare:

```python
def _fallback_plan(user_input, folder_tree):
    """Structured fallback jab LLM ka JSON parse nahi hua."""
    return PlannerState(
        plan=[
            PlanStep(step_id="step-1", title="Analyze request scope",
                     tools=["search_code", "find_files"]),
            PlanStep(step_id="step-2", title="Gather information",
                     tools=["web_search", "fetch_url"], depends_on=["step-1"]),
            PlanStep(step_id="step-3", title="Synthesize and deliver",
                     tools=["final_answer"], depends_on=["step-2"]),
        ]
    )
```

---

## Plan Persistence — `_save()` aur `_sync_md()`

**planner.json** (machine-readable):
```json
{
  "version": "1.0",
  "session_id": "a3f9b12c",
  "original_query": "make a README",
  "refined_goal": "Create comprehensive README.md",
  "status": "planning",
  "plan": [
    {
      "step_id": "step-1",
      "order": 1,
      "title": "Analyze project structure",
      "description": "Use list_folder and read_file to understand the project",
      "status": "pending",
      "tools": ["list_folder", "read_file"],
      "depends_on": []
    }
  ]
}
```

**planner.md** (human-readable):
```markdown
# 📋 BhavAI Planner — Session `a3f9b12c`

**Status:** `planning`

## 🎯 Refined Goal
> Create comprehensive README.md

## 📊 Progress
- **Completed:** 0/3 (0%)
`░░░░░░░░░░░░░░░░░░░░`

## 📝 Plan Steps

### ⬜ Step 1: Analyze project structure
- **Status:** `pending`
- **Tools:** list_folder, read_file
...
```

---

## Plan Display — `display_deep_plan()`

**File:** [`bhavai/modes.py`](../bhavai/modes.py) — Line 33

```python
def display_deep_plan(planner_state, console):
    # Header Panel: Goal + Analysis
    console.print(Panel(
        f"🎯 Goal: {planner_state.refined_goal}\n"
        f"📝 Analysis: {analysis}",
        title="📋 BhavAI Deep Plan",
        border_style="cyan",
    ))

    # Steps Table
    table = Table(show_header=True, border_style="dim", expand=True)
    table.add_column("#", width=3)
    table.add_column("Step", ratio=3)
    table.add_column("Tools", ratio=2)
    table.add_column("Depends On", ratio=1)

    for step in planner_state.plan:
        icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅",
                "failed": "❌", "skipped": "⏭️"}.get(step.status, "⬜")

        table.add_row(
            str(step.order),
            f"{icon} {step.title}\n{step.description}",
            ", ".join(step.tools),
            ", ".join(step.depends_on)
        )
    console.print(table)
```

---

## User Confirmation Loop

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 751

```python
feedback = None

while True:
    planner_state = prompt_and_confirm_plan(
        user_input, folder_tree, console, feedback, skills_block=skills_block
    )

    ans = console.input(
        "[bold yellow]Proceed?[/bold yellow] (y / n / type feedback to edit plan) > "
    ).strip()

    if ans.lower() == "y":
        break                          # → Plan execute hoga
    elif ans.lower() in ("n", "no", ""):
        planner_state = None
        break                          # → Cancel
    else:
        feedback = ans                 # → Plan regenerate with feedback
        console.print(f"Regenerating plan with feedback: '{feedback}'...")
        # → Loop back: generate_deep_plan(feedback=feedback) call hoga
```

### Feedback Loop kaise kaam karta hai:
```
User: "write a python calculator"
LLM: Plan with 3 steps

User types: "add steps for tests too"
    → generate_deep_plan(feedback="add steps for tests too") call hota hai
    → user_prompt mein feedback append hota hai
    → LLM naya plan banata hai (tests ke steps ke saath)
    → Plan dobara display hota hai
```

---

## Plan Execution — `run_agent_loop_plan()`

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — Line 942

```python
def run_agent_loop_plan(user_input, memory, current_mode, planner_state, ...):
    # Plan status update
    set_plan_status(planner_state, "in_progress")

    # Task prompt build karo with approved steps
    steps_str = "\n".join(
        f"  {step.order}. [{step.step_id}] {step.title}: {step.description}"
        f" (Tools: {', '.join(step.tools)})"
        for step in planner_state.plan
    )
    task_prompt = (
        f"Task: {user_input}\n\n"
        f"Refined Goal: {planner_state.refined_goal}\n\n"
        f"Approved plan (execute ALL steps in order):\n{steps_str}\n\n"
        f"After completing ALL steps, call final_answer."
    )

    return _run_agent_loop(
        task_prompt=task_prompt,
        require_approval=True,      # ← Plan mode: tools ke liye approval chahiye
        planner_state=planner_state,
    )
```

---

## Plan State Tracking

**`set_plan_status()`** — Overall plan status:
```python
set_plan_status(planner_state, "in_progress")  # execution shuru
set_plan_status(planner_state, "completed")    # final_answer ke baad
```

**`mark_step_status()`** — Individual step update:
```python
mark_step_status(state, "step-1", "completed", note="Found 5 Python files")
```

**`get_next_pending_step()`** — Dependencies check:
```python
def get_next_pending_step(state):
    completed_ids = {s.step_id for s in state.plan if s.status == "completed"}
    for step in state.plan:
        if step.status == "pending":
            if all(dep in completed_ids for dep in step.depends_on):
                return step  # Ye step execute ho sakta hai
    return None
```

---

## Existing Planner Backup

Agar user dobara Plan Mode use kare aur pehle se planner.json ho:

```python
def start_new_plan(user_input, folder_tree, skills_block=""):
    if PLANNER_JSON.exists():
        # Pehle wale ko backup karo
        backup = Path(CWD) / f"planner_backup_{timestamp}.json"
        PLANNER_JSON.rename(backup)
    return generate_deep_plan(user_input, folder_tree, skills_block)
```

---

## Complete Plan Mode Call Graph

```
User: "create a Flask API" (Plan Mode)
    │
    ▼ main.py:743
get_folder_tree_string(CWD)          → context.py
discover_skills_from_dot_bhavai(CWD) → skill_getter.py
    │
    ▼ modes.py:117
prompt_and_confirm_plan()
    │
    ├── ShimmerStatus("Generating deep plan...")
    │
    ├── planner.py:364 start_new_plan()
    │   ├── planner.json backup (if exists)
    │   └── generate_deep_plan(user_input, folder_tree, skills_block)
    │       ├── DEEP_PLAN_SYSTEM_PROMPT + user_prompt
    │       ├── query_llm_with_continuation(messages)  → LLM API
    │       ├── _parse_plan_response(raw)
    │       │   ├── JSON parse
    │       │   └── PlanStep[] + PlannerState create
    │       ├── _save(state) → planner.json write
    │       └── _sync_md(state) → planner.md write
    │
    └── display_deep_plan(planner_state)
        ├── Rich Panel (Goal + Analysis)
        └── Rich Table (Steps with tools, dependencies)
    │
    ▼ main.py: User types "y"
    │
    ▼ agent.py:942
run_agent_loop_plan(user_input, memory, planner_state)
    ├── set_plan_status("in_progress")
    ├── task_prompt = "Task: ...\nApproved plan:\n1. ..."
    └── _run_agent_loop(require_approval=True)
        └── [ReAct Loop → tool execution with y/n approval]
        └── final_answer → set_plan_status("completed")
```
