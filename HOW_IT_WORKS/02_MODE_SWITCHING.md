# 🔄 02 — Mode Switching: `mode agent` / `mode plan` kya karta hai

## TL;DR

```
User types: "mode agent"
    → main.py REPL loop catches it
    → current_mode = AgentMode.AGENT (string: "agent")
    → Next prompt dikhta hai: (agent) >
    → Koi bhi next prompt → run_agent_loop_autonomous() call hoga
```

```
User types: "mode plan"  (default on startup)
    → current_mode = AgentMode.PLAN (string: "plan")
    → Next prompt dikhta hai: (plan) >
    → Koi bhi next prompt → prompt_and_confirm_plan() phir run_agent_loop_plan() call hoga
```

---

## AgentMode Class

**File:** [`bhavai/modes.py`](../bhavai/modes.py) — Line 22

```python
class AgentMode:
    """Enumeration of available agent execution modes."""
    PLAN  = "plan"
    AGENT = "agent"
```

Yeh sirf ek simple class hai jo do constants define karta hai. Koi complex enum nahi.

---

## Mode Variable — REPL mein kahan hai?

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 448

```python
current_mode = AgentMode.PLAN  # DEFAULT: Plan mode se start hota hai
```

Yeh `current_mode` variable `wake()` function ka local variable hai. Poore REPL loop ke andar yeh zinda rehta hai aur har user input ke baad check hota hai.

---

## Mode Switch — Exact Code

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 710

```python
# Mode switching command
if not is_command and user_input.lower() == "mode agent":
    current_mode = AgentMode.AGENT
    console.print("[yellow]Switched to Agent Mode (Tasks will execute autonomously).[/yellow]")
    continue   # ← REPL loop ka agla iteration shuru

elif not is_command and user_input.lower() == "mode plan":
    current_mode = AgentMode.PLAN
    console.print("[cyan]Switched to Plan Mode (Tasks will show a checklist plan first).[/cyan]")
    continue
```

**Important:** `is_command` check isliye hai kyunki agar user ne `/code` jaise slash command se `mode agent` text paste kiya ho toh mode switch na ho — sirf raw typed input se switch hona chahiye.

---

## Mode ka Effect: Prompt Color Change

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 492

```python
def get_prompt_text():
    """Live prompt that re-evaluate for every key stroke."""
    buf = session.default_buffer.text
    if buf.startswith("!"):
        return HTML('<ansired><b>(bash)</b></ansired> > ')
    if buf.startswith("/"):
        return HTML('<ansiyellow><b>(command)</b></ansiyellow> > ')
    if current_mode == AgentMode.PLAN:
        return HTML('<ansicyan><b>(plan)</b></ansicyan> > ')      # CYAN = plan
    else:
        return HTML('<ansiyellow><b>(agent)</b></ansiyellow> > ')  # YELLOW = agent
```

Prompt text **live** update hota hai — kyunki `get_prompt_text` ek callable hai, `session.prompt()` har keystroke pe isse dobara call karta hai.

---

## Mode ka Main Effect: Execution Path

### Plan Mode ka path:

```python
if is_command or current_mode == AgentMode.PLAN:
    folder_tree = get_folder_tree_string(CWD)
    skills_block = discover_skills_from_dot_bhavai(CWD)
    feedback = None

    # Loop: Plan → Show → Confirm/Feedback → Regenerate
    while True:
        planner_state = prompt_and_confirm_plan(
            user_input, folder_tree, console, feedback, skills_block=skills_block
        )
        ans = console.input("Proceed? (y / n / type feedback) > ").strip()

        if ans.lower() == "y":
            break
        elif ans.lower() in ("n", "no", ""):
            planner_state = None
            break
        else:
            feedback = ans  # feedback ke saath plan regenerate karo
            console.print(f"Regenerating plan with feedback: '{feedback}'...")

    if planner_state:
        run_agent_loop_plan(...)
    else:
        console.print("Plan execution cancelled.")
```

### Agent Mode ka path:

```python
else:  # Agent Mode
    console.print("Executing task autonomously...")
    run_agent_loop_autonomous(
        user_input=user_input,
        memory=memory,
        current_mode=current_mode,
        console=console
    )
```

---

## Plan Mode vs Agent Mode — Key Differences

| Feature | Plan Mode | Agent Mode |
|---------|-----------|------------|
| **Plan generation** | ✅ Deep plan generate hota hai pehle | ❌ Direct execute |
| **User confirmation** | ✅ y/n/feedback loop | ❌ Auto execute |
| **Tool approval** | ✅ `run_command` pe y/n poochta hai | ❌ Auto approve |
| **`require_approval`** | `True` | `False` |
| **Entry function** | `run_agent_loop_plan()` | `run_agent_loop_autonomous()` |
| **Prompt color** | Cyan `(plan)` | Yellow `(agent)` |

---

## Functions Called During Mode Switch

```
"mode agent" typed
    └── main.py REPL loop
        └── user_input.lower() == "mode agent" → True
            └── current_mode = AgentMode.AGENT   [variable reassignment]
            └── console.print(...)               [Rich console output]
            └── continue                         [next REPL iteration]

Next prompt typed in agent mode:
    └── main.py:781  else: block
        └── run_agent_loop_autonomous()          [agent.py]
            └── _run_agent_loop(..., require_approval=False)
```

```
"mode plan" typed (ya startup default)
    └── current_mode = AgentMode.PLAN

Next prompt typed in plan mode:
    └── main.py:743  if is_command or current_mode == AgentMode.PLAN:
        ├── get_folder_tree_string(CWD)          [context.py]
        ├── discover_skills_from_dot_bhavai(CWD) [skill_getter.py]
        └── prompt_and_confirm_plan()            [modes.py]
            ├── start_new_plan() / generate_deep_plan()  [planner.py]
            └── display_deep_plan()              [modes.py]
        └── y/n/feedback loop
        └── run_agent_loop_plan()                [agent.py]
            └── _run_agent_loop(..., require_approval=True)
```
