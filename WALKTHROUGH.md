# BhavAI — Terminal Coding Agent

This markdown file explains how your **BhavAI** agent works internally —
where the ReAct loop runs, how tool calling is dispatched, how the
4096-token limit is handled, and what the exact role of each file is.

---

## 1. One-line project summary

The user types a task in the terminal → the LLM (Sarvam) returns a JSON
containing `thought` + `tool_name` + `tool_args` → the agent actually
calls that tool in Python → the result (observation) is sent back to the
LLM → this loop keeps running until the LLM says `final_answer`.

This cycle is called the **ReAct loop** (**Re**ason → **Act** → Observe).

---

## 2. File-by-file: who does what

```
bhavai/
├── agent.py              ← Core of the ReAct loop. System prompt lives here.
├── llm.py                ← Talks to the Sarvam API (with retries + continuation)
├── tools.py               ← Core sandboxed tools (read/write/run_command) + dispatch registry
├── tools_extended.py      ← Extra read-oriented tools (search, outline, diff, AST edit...)
├── config.py              ← CWD, API key, logger (referenced, file not in this drop)
├── context.py             ← .gitignore parsing, folder tree, .env detection (referenced)
└── memory.py               ← ConversationMemory — keeps message history (referenced)
```

> Note: `config.py`, `context.py`, `memory.py` are described in this README
> **based on usage** (based on functions imported from them) — their
> actual file contents were not uploaded in this conversation, so if they
> contain any custom logic not covered here, it won't be reflected in
> this README.

---

## 3. Starting from the entry point: `run_agent_loop()` — `agent.py`

This function runs the entire ReAct loop. Step by step:

```python
def run_agent_loop(user_input, memory, current_mode, plan_steps=None,
                    max_steps=30, console=None):
```

### What happens step-by-step (each "step" = one LLM call + one tool call):

1. **The task prompt is built.**
   If `plan_steps` is given (a multi-step approved plan), the plan is
   appended to the user_input in the prompt, along with a reminder:
   "for files > 50 lines, use append_chunk."

2. **`memory.add_message("user", task_prompt)`** — this turn gets recorded
   in the conversation history.

3. **`while step_count < max_steps:` loop starts** (default cap = 30
   steps, so the agent can't get stuck in an infinite loop).

   In each iteration:

   a. **The folder tree is freshly regenerated** (`get_folder_tree_string(CWD)`)
      — so the LLM sees the current directory structure at every step (in
      case a file was created/moved in the previous step).

   b. **The system prompt is formatted** (`SYSTEM_PROMPT_TEMPLATE.format(...)`)
      — this contains the CWD path, folder tree, and the **full list of
      available tools + their argument schemas** hardcoded (see Section 5).

   c. **The LLM is called:**
      ```python
      messages = memory.get_messages(system_prompt)
      raw_response = query_llm_with_continuation(messages)
      ```
      This is a function in `llm.py` — if the LLM's response gets cut off
      at the 4096-token limit, this automatically issues a continuation
      call and stitches together the full response (details in Section 6).

   d. **JSON is parsed:** `parse_llm_json(raw_response)`.
      If the JSON is malformed (usually due to truncation), the agent
      sends a structured error message back to the LLM with an exact
      instruction: "use append_chunk, ≤50 lines per chunk." After 3
      consecutive JSON errors, the loop **aborts** (to avoid infinite
      retries).

   e. **The `thought` is printed to the console** (via a Rich `Panel`) —
      so you can see what the LLM is "thinking."

   f. **Tool dispatch (this is where the actual work happens):**
      ```python
      if tool_name == "final_answer":
          return tool_args.get("answer")

      if tool_name in TOOL_DISPATCH:
          tool_func = TOOL_DISPATCH[tool_name]
          result = tool_func(**tool_args)
      else:
          result = f"Error: Unknown tool '{tool_name}'."
      ```
      `TOOL_DISPATCH` is a plain Python dict that maps a tool's name
      (string) → the actual Python function. Full details are in
      Section 4.

   g. **The observation is added to memory:**
      ```python
      memory.add_message("assistant", raw_response)
      memory.add_message("user", f"Observation from {tool_name}:\n{result}")
      ```
      So the tool's result becomes the "user" turn for the next LLM call
      — this is how the LLM learns what result its previous action
      produced.

4. The loop keeps running until the LLM sends `tool_name = "final_answer"`,
   or `max_steps` (30) is exhausted.

### Visual flow:

```
┌────────────────────────────────────────────────────────────────────┐
│                         run_agent_loop()                           │
│                                                                    │
│   user_input ──► memory.add_message("user", task_prompt)           │
│                                                                    │
│   ┌──────────────── while step_count < 30 ───────────────────────┐ │
│   │                                                              │ │
│   │  1. system_prompt = SYSTEM_PROMPT_TEMPLATE.format(...)       │ │
│   │  2. messages = memory.get_messages(system_prompt)            │ │
│   │  3. raw_response = query_llm_with_continuation(messages)   ──┼─┼──► llm.py
│   │  4. parsed = parse_llm_json(raw_response)                    │ │
│   │              │                                               │ │
│   │              ├─ tool_name == "final_answer" ──► RETURN       │ │
│   │              │                                               │ │
│   │              └─ tool_name in TOOL_DISPATCH:                  │ │
│   │                     result = TOOL_DISPATCH[tool_name](**args)┼─┼──► tools.py /
│   │              │                                               │ │    tools_extended.py
│   │  5. memory.add_message("assistant", raw_response)            │ │
│   │  6. memory.add_message("user", f"Observation: {result}")     │ │
│   │                                                              │ │
│   └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tool calling — where it happens (the most important part)

Tool calling is involved in **3 places**:

### (a) In the system prompt — showing the LLM the "menu"

In `agent.py`'s `SYSTEM_PROMPT_TEMPLATE`, for every tool:
- its name
- expected JSON args (`{"path": "string", ...}`)
- a one-line usage hint

...all of this is sent to the LLM **as plain text**. The LLM isn't using
any "function calling" API feature — this is plain JSON-output prompting.
The LLM itself decides which tool to run, and just returns JSON:

```json
{
  "thought": "...",
  "tool_name": "search_code",
  "tool_args": {"query": "validate_token", "path": "."}
}
```

### (b) The `TOOL_DISPATCH` registry — name → function mapping

At the bottom of `tools.py`:

```python
TOOL_DISPATCH = {
    "list_folder":   list_folder,
    "read_file":     read_file,
    "write_file":    write_file,
    "update_file":   update_file,
    "append_chunk":  append_chunk,
    "run_command":   run_command,
}

from bhavai.tools_extended import EXTENDED_TOOL_DISPATCH
TOOL_DISPATCH.update(EXTENDED_TOOL_DISPATCH)   # merge both dicts
```

And at the bottom of `tools_extended.py`:

```python
EXTENDED_TOOL_DISPATCH = {
    "search_code":          search_code,
    "find_files":           find_files,
    "get_outline":          get_outline,
    "list_todos":           list_todos,
    "get_diff":              get_diff,
    "check_dependencies":   check_dependencies,
    "rename_path":           rename_path,
    "fetch_url":             fetch_url,
    "get_function_source":  get_function_source,
    "insert_function":       insert_function,
    "replace_function":      replace_function,
}
```

**How circular imports are avoided:** `tools_extended.py` imports
`validate_path`, `_git_stage`, `ensure_git_initialized` from `tools.py`.
That's why `tools.py` imports `tools_extended` only **after** defining
its own `TOOL_DISPATCH` (at the very bottom of the file, with a
`# noqa: E402` comment). If this order were reversed, Python would throw
a circular import error.

### (c) The actual dispatch — the moment it's called in `agent.py`

```python
tool_func = TOOL_DISPATCH[tool_name]
result = tool_func(**tool_args) if isinstance(tool_args, dict) else tool_func()
```

This is the **single line** where the LLM's decision (`tool_name` +
`tool_args` JSON) turns into a real Python function call. If the LLM
invents some crazy tool name, the `else` branch gives a fallback with
the list of valid tool names — so the LLM can correct itself on the next
attempt.

### Full request flow for one tool (example: `replace_function`)

```
LLM JSON:
  {"tool_name": "replace_function",
   "tool_args": {"path": "app.py", "function_name": "foo", "new_source": "..."}}
        │
        ▼
agent.py: tool_func = TOOL_DISPATCH["replace_function"]
        │
        ▼
tools_extended.py: replace_function(path="app.py", function_name="foo", new_source="...")
        │
        ├─► tools.py: ensure_git_initialized()      (at the start of every mutating call)
        ├─► tools.py: validate_path("app.py")        (sandbox check — can't go outside CWD)
        ├─► context.py: is_env_file(resolved)         (.env / secrets guard)
        ├─► ast.parse(new_source)                       (validate syntax BEFORE writing the file)
        ├─► ast.walk(tree) to find the function's exact lineno/end_lineno
        ├─► splice the old lines with the new lines
        ├─► resolved.write_text(...)                     (file written to disk)
        └─► tools.py: _git_stage(resolved)               (git add, so the diff shows)
        │
        ▼
return "✓ Replaced 'foo' ... Run `git diff HEAD` to review."
        │
        ▼
agent.py: result printed to console, becomes "Observation" in memory
```

---

## 5. List of all tools (which file it's in, what it does)

| Tool | File | Mutating? | What it does |
|---|---|---|---|
| `list_folder` | `tools.py` | No | Shows a gitignore-aware folder tree |
| `read_file` | `tools.py` | No | Returns the full file content (.env blocked) |
| `write_file` | `tools.py` | **Yes** | Creates a new file or overwrites one — only for files <60 lines |
| `update_file` | `tools.py` | **Yes** | Legacy append/overwrite — new code should use `append_chunk` |
| `append_chunk` | `tools.py` | **Yes** | Core fix for the 4096-token limit — writes files in ≤50-line chunks |
| `run_command` | `tools.py` | **Yes** (shell) | Runs a blocklist-checked shell command, 10s timeout |
| `search_code` | `tools_extended.py` | No | Grep-like text/regex search, the most-used tool |
| `find_files` | `tools_extended.py` | No | Filename search via glob pattern |
| `get_outline` | `tools_extended.py` | No | Class/function signatures + line numbers via AST |
| `list_todos` | `tools_extended.py` | No | Scans for TODO/FIXME/HACK/XXX/BUG markers |
| `get_diff` | `tools_extended.py` | No | Shows `git diff HEAD` |
| `check_dependencies` | `tools_extended.py` | No | Checks requirements.txt/pyproject.toml/package.json |
| `rename_path` | `tools_extended.py` | **Yes** | Safe move/rename — never overwrites the destination |
| `fetch_url` | `tools_extended.py` | No (network) | Fetches real docs/API pages |
| `get_function_source` | `tools_extended.py` | No | **New** — extracts a function's exact source via AST |
| `insert_function` | `tools_extended.py` | **Yes** | **New** — adds a new function to the end of a file |
| `replace_function` | `tools_extended.py` | **Yes** | **New** — replaces a function using AST line numbers |

I added the last 3 tools in a previous session — I've included them in
the README too so the documentation stays in sync.

---

## 6. The 4096-token problem — the full 5-layer defense

Your Sarvam-105B model can only give a maximum of **4096 output tokens**
in one go. If the LLM tried to write a long file inside the JSON, it
would get cut off midway and the JSON would end up corrupted. To handle
this, there are **5 layers**:

```
Layer 1 — The rule is written right into the SYSTEM PROMPT:
           "MAXIMUM 50 LINES OF CODE PER TOOL CALL"
           (agent.py, SYSTEM_PROMPT_TEMPLATE)

Layer 2 — The append_chunk() tool ENFORCES this same rule:
           write one chunk (≤50 lines), keep done=false,
           send the next chunk, set done=true on the last one.
           (tools.py)

Layer 3 — query_llm_with_continuation() — if the LLM still crosses
           4096 tokens in a single response (stop_reason ==
           "max_tokens"), llm.py automatically issues a "continue from
           where you left off" follow-up call, and stitches all the
           content together into one string — up to 6 rounds max.
           (llm.py, query_llm_with_continuation)

Layer 4 — JSON repair pipeline — if the JSON still comes out truncated
           (e.g. an unterminated string), _fix_truncated_json() walks
           the text, closes open braces/brackets/quotes, and tries
           parsing again.
           (agent.py, clean_json_text → _fix_truncated_json)

Layer 5 — Recovery feedback — if the JSON still fails to parse,
           the agent sends the LLM an EXACT instruction back:
           "Use append_chunk instead with ≤50 lines per chunk."
           After 3 consecutive failures, the loop aborts.
           (agent.py, run_agent_loop's try/except ValueError block)
```

### Internal logic of `query_llm_with_continuation()` (`llm.py`)

```
Round 1: _call_api(messages) → (content_1, stop_reason_1)
         if stop_reason_1 == "end_turn": return content_1   # done

         if stop_reason_1 == "max_tokens":
             history.append({"role": "assistant", "content": content_1})
             history.append({"role": "user", "content": CONTINUATION_PROMPT})
             # CONTINUATION_PROMPT = "Continue exactly from where you left
             # off. Do NOT repeat any content already written..."

Round 2: _call_api(history) → (content_2, stop_reason_2)
         full_output = content_1 + content_2
         ... repeat until end_turn or max_rounds=6
```

All of this runs through a single `_call_api()` function — the same
function also handles retries (exponential backoff on 429/500/502/503/504)
and error handling.

---

## 7. Security / Sandbox model

There are three guarantees that **every** tool follows (whether it's in
`tools.py` or `tools_extended.py`):

1. **Path sandboxing — `validate_path()`** (`tools.py`)
   Every path is resolved against `CWD` and checked to confirm it's
   inside `CWD`. If it goes outside, a `ValueError` is raised — traversal
   attempts like `../../etc/passwd` get blocked.

2. **Secrets guard — `is_env_file()`** (`context.py`, used everywhere)
   Files like `.env`, `.env.*`, `credentials.json` can never be read/
   written/moved — nor does their content ever reach the LLM.

3. **Zero-deletion policy**
   There is no delete tool anywhere in the codebase — by design.
   `rename_path` only moves files, and **refuses** if the destination
   already exists (never overwrites). In `run_command` too, commands
   like `rm`, `rmdir`, `del`, `shutil.rmtree`, `os.remove` are rejected
   via a word-boundary regex check against the `BLOCKED_COMMANDS` list.

4. **Git safety net — `ensure_git_initialized()` + `_git_stage()`**
   On the first mutating call, `git init` runs automatically (if not
   already initialized), and every successful write gets `git add`-ed.
   That means you can always run `git diff HEAD` to see exactly what
   the agent changed — this acts as a built-in undo/audit trail.

---

## 8. How `get_function_source` / `insert_function` / `replace_function` work

All three tools use the **AST (Abstract Syntax Tree)**, not text-matching
— so they don't get confused if a function's name happens to appear in a
comment or docstring somewhere.

```
get_function_source(path, function_name)
   1. parse the file: tree = ast.parse(text)
   2. walk the tree with ast.walk(tree) to find a matching
      FunctionDef/AsyncFunctionDef by name
   3. get the exact line range from node.lineno / node.end_lineno
   4. return those lines in a numbered format

insert_function(path, new_source)
   1. ast.parse(new_source) — validate the syntax is valid first
      (if invalid, don't touch the file at all)
   2. read the file's existing content
   3. content + "\n\n\n" + new_source + "\n" — append at the end
   4. write the file, stage it in git

replace_function(path, function_name, new_source)
   1. ast.parse(new_source) — validate syntax
   2. parse the file, find the function (same as in get_function_source)
   3. lines[:start-1] + new_function_lines + lines[end:] — splice
   4. write the file, stage it in git
```

Use case for these: when you want to change **just one function**, you
don't need to rewrite the entire file with `write_file`/`append_chunk` —
this saves token budget and reduces the risk of accidentally corrupting
some other function.

---

## 9. Quick mental model (TL;DR)

```
User types task
      │
      ▼
agent.py: run_agent_loop()
      │
      ├──► llm.py: query_llm_with_continuation()  ──► Sarvam API
      │         (handles the 4096-token limit)
      │
      ▼
agent.py: parse_llm_json()  ──► {thought, tool_name, tool_args}
      │
      ▼
tools.py: TOOL_DISPATCH[tool_name]   (12 + 11 = ~17 tools available)
      │
      ├──► tools.py          (file I/O, shell, chunked writes)
      └──► tools_extended.py (search, outline, diff, deps, AST edits, fetch_url)
      │
      ▼
result string ──► becomes an "Observation" in memory
      │
      ▼
Loop repeats until tool_name == "final_answer"
```

That's it — that's your entire agent: **one prompt, one dict, one loop.**
All the "intelligence" is in the prompt engineering and tool design; the
code itself is very simple and readable.