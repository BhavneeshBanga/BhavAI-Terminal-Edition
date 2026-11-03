# 🔧 09 — Tools Reference: Har Tool ka Walkthrough

## Overview

BhavAI ke tools **3 files** mein distributed hain:
- [`bhavai/tools.py`](../bhavai/tools.py) — Core file/shell tools
- [`bhavai/tools_extended.py`](../bhavai/tools_extended.py) — Web, search, code navigation
- [`bhavai/agents/`](../bhavai/agents/) — Calendar agent tools

Sab tools `TOOL_DISPATCH` dict mein register hote hain — agent `tool_name` se function lookup karta hai.

```python
TOOL_DISPATCH = {}
TOOL_DISPATCH.update(core_tools)          # tools.py
TOOL_DISPATCH.update(EXTENDED_TOOL_DISPATCH)  # tools_extended.py
TOOL_DISPATCH.update(AGENT_DISPATCHERS)   # agents/
```

---

## 📁 File Operations (tools.py)

### `list_folder(path=".")`
**Kya karta hai:** Directory contents ko tree format mein return karta hai.

```python
def list_folder(path: str = ".") -> str:
    resolved = validate_path(path)           # Sandbox check
    return get_folder_tree_string(resolved)  # Tree build
```

- `.gitignore`, `__pycache__`, `.git`, `.env` etc. automatically hide
- Return format: `├──`, `└──` Unicode tree

**Agent use example:**
```json
{"tool_name": "list_folder", "tool_args": {"path": "src/"}}
```

---

### `read_file(path)`
**Kya karta hai:** File ka pura text content return karta hai.

```python
def read_file(path: str) -> str:
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):             # .env blocked!
        return "Access Denied..."

    return resolved.read_text(encoding="utf-8")
```

**Security:** `.env`, `credentials.json` etc. kabhi nahi read hote.

---

### `write_file(path, content)`
**Kya karta hai:** File create/overwrite karta hai. Short files ke liye (< 60 lines).

```python
def write_file(path: str, content: str) -> str:
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):
        return "Access Denied..."

    resolved.parent.mkdir(parents=True, exist_ok=True)  # Parent dirs bhi create
    resolved.write_text(content, encoding="utf-8")
    _git_stage(resolved)                                 # Git add

    return f"✓ '{path}' written ({len(content)} chars, {line_count} lines)."
```

**Warning:** 80+ lines pe logger warning aata hai — `append_chunk` use karo.

---

### `append_chunk(path, chunk, done=False)`
**Kya karta hai:** 4096-token limit ke liye chunked file writing.

```python
_chunk_state: dict[str, int] = {}   # path → total chars so far

def append_chunk(path: str, chunk: str, done: bool = False) -> str:
    resolved = validate_path(path)

    # First chunk → "w" mode; subsequent → "a" mode
    write_mode = "a" if (path in _chunk_state or resolved.exists()) else "w"

    with open(resolved, write_mode, encoding="utf-8") as fh:
        fh.write(chunk)

    _chunk_state[path] = _chunk_state.get(path, 0) + len(chunk)

    if done:
        _git_stage(resolved)
        del _chunk_state[path]                    # Reset state
        return f"✓ Final chunk written. '{path}' complete."
    else:
        return f"✓ Chunk appended ({chunk_count} lines). Continue or set done=true."
```

**Usage pattern:**
```json
{"tool_name": "append_chunk", "tool_args": {"path": "big.py", "chunk": "lines 1-50", "done": false}}
{"tool_name": "append_chunk", "tool_args": {"path": "big.py", "chunk": "lines 51-100", "done": false}}
{"tool_name": "append_chunk", "tool_args": {"path": "big.py", "chunk": "lines 101-150", "done": true}}
```

---

### `run_command(command)`
**Kya karta hai:** Shell command CWD mein execute karta hai. MUTATING TOOL — Plan mode mein approval chahiye.

```python
def run_command(command: str) -> str:
    validate_command(command)   # Blocklist check: rm, rmdir, del...

    proc = subprocess.Popen(
        command, shell=True, cwd=CWD,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    # Streaming output + 30-second timeout
    t = threading.Thread(target=stream_reader, args=(proc.stdout,))
    t.start()
    proc.wait(timeout=30)

    # Output truncate if > 40 lines
    full_output = _truncate_output(output_lines)
    return full_output + f"[exit code: {exit_code}]"
```

**Features:**
- Live streaming output (terminal mein real-time dikhta hai)
- 30-second timeout (Windows pe `taskkill`, Linux pe `kill`)
- Output 40 lines se zyada ho toh `head + ... [N lines omitted] ... + tail`

---

### `update_file(path, content, mode="append")` *(deprecated)*
Legacy tool — `write_file` ya `append_chunk` use karo.

---

### `get_project_memory_string(cwd)` *(helper, not a tool)*
```python
def get_project_memory_string(cwd: Path) -> str:
    # Case-insensitive glob: BHAVAI.md / bhavai.md / Bhavai.md
    for candidate in cwd.glob("[Bb][Hh][Aa][Vv][Aa][Ii].md"):
        return candidate.read_text(encoding="utf-8").strip()
    return ""
```

---

## 🔍 Code Navigation (tools_extended.py)

### `search_code(query, path=".", regex=False, case_sensitive=False)`
**Kya karta hai:** Grep-like search across project files.

**Agent use example:**
```json
{"tool_name": "search_code", "tool_args": {"query": "def validate_path", "path": "bhavai/"}}
```

---

### `find_files(pattern, path=".")`
**Kya karta hai:** Glob pattern se files dhundhta hai.

```json
{"tool_name": "find_files", "tool_args": {"pattern": "*.py", "path": "."}}
```

---

### `get_outline(path)`
**Kya karta hai:** File ke function/class signatures + line numbers return karta hai WITHOUT full content.

---

### `find_symbol(name, path=".")`
**Kya karta hai:** Project-wide "go to definition" — AST se kisi class/function ka definition dhundhta hai.

---

### `find_references(name, path=".")`
**Kya karta hai:** Koi symbol kahin use ho raha hai — AST-based reference search.

---

### `read_file_chunk(path, start_line, end_line)`
**Kya karta hai:** File ka sirf ek part (line range) padta hai — token budget bachane ke liye.

```json
{"tool_name": "read_file_chunk", "tool_args": {"path": "agent.py", "start_line": 700, "end_line": 750}}
```

---

### `get_function_source(path, function_name)`
**Kya karta hai:** Python AST se ek specific function ka exact source return karta hai.

---

## ✏️ Code Editing (tools_extended.py)

### `replace_lines(path, start_line, end_line, new_content)`
**Kya karta hai:** Exact line range replace karta hai kisi bhi file mein.

```json
{"tool_name": "replace_lines", "tool_args": {"path": "main.py", "start_line": 10, "end_line": 15, "new_content": "new code here"}}
```

---

### `insert_lines(path, after_line, content)`
**Kya karta hai:** Specific line ke baad content insert karta hai. `after_line=0` → file ke top pe.

---

### `delete_lines(path, start_line, end_line)`
**Kya karta hai:** Lines remove karta hai. Git checkpoint pehle — always recoverable.

---

### `patch_file(path, search_text, replace_text, occurrence=1)`
**Kya karta hai:** Search-and-replace — line numbers ki zaroorat nahi. Fastest editing tool.

```json
{"tool_name": "patch_file", "tool_args": {"path": "app.py", "search_text": "def old_func(", "replace_text": "def new_func("}}
```

---

### `insert_function(path, new_source)`
**Kya karta hai:** Python file ke end mein ek naya top-level function add karta hai (AST-based).

---

### `replace_function(path, function_name, new_source)`
**Kya karta hai:** Existing Python function ko completely replace karta hai (AST-based).

---

### `create_directory(path)`
**Kya karta hai:** Directory (aur parent dirs) create karta hai. Idempotent — exist kare toh no-op.

---

### `rename_path(source, destination)`
**Kya karta hai:** File/folder move ya rename karta hai. Existing destination pe refuse karta hai.

---

## 🖥️ Shell & Testing (tools_extended.py)

### `run_tests(path=".", command=None)`
**Kya karta hai:** Test suite run karta hai. Auto-detect: `pytest` ya `npm test`.

---

### `lint_file(path)`
**Kya karta hai:** Linter run karta hai: `ruff`/`flake8` for `.py`, `eslint` for `.js`/`.ts`.

---

### `check_dependencies(path=".")`
**Kya karta hai:** `requirements.txt`, `pyproject.toml`, `package.json` parse karta hai aur missing deps report karta hai.

---

## 🔄 Git & Recovery (tools_extended.py)

### `get_diff(path=None)`
**Kya karta hai:** `git diff HEAD` — BhavAI ne kya kya badla.

---

### `revert_file(path)`
**Kya karta hai:** File ko last git-committed state mein restore karta hai — undo button.

---

### `git_commit(message)`
**Kya karta hai:** All changes stage karta hai aur commit banata hai.

---

## 🌐 Web & Media (tools_extended.py)

### `fetch_url(url, max_chars=8000)`
**Kya karta hai:** Live web page fetch karta hai — documentation, Stack Overflow pages, APIs.

---

### `duckduckgo_search(query, max_results=5)`
**Kya karta hai:** DuckDuckGo search — live web results.

---

### `check_weather(location)`
**Kya karta hai:** City ka current weather data return karta hai.

---

### `read_image(path, include_base64=False)`
**Kya karta hai:** Image metadata (dimensions, format, file size). `include_base64=True` → base64 data URI (vision models ke liye).

---

## 📅 Google Calendar Agent (bhavai/agents/)

### `calendar_schedule(instruction)`
**Kya karta hai:** New Google Calendar event create karta hai.

### `calendar_list(period="today")`
**Kya karta hai:** Upcoming events list karta hai. `period`: today/tomorrow/week.

### `calendar_delete(query)`
**Kya karta hai:** Event search karke delete karta hai.

### `calendar_free_slots(date, instruction)`
**Kya karta hai:** Din ke free 30+ min slots dhundhta hai.

---

## 📋 Task Completion

### `list_todos(path=".")`
**Kya karta hai:** TODO/FIXME/HACK/XXX/BUG comments scan karta hai.

---

### `final_answer(answer)` *(special — agent.py handles directly)*
**Kya karta hai:** Task complete hone ka signal. `TOOL_DISPATCH` mein nahi — `agent.py` khud handle karta hai:

```python
if tool_name == "final_answer":
    answer = tool_args.get("answer", "Task complete.")
    console.print("✅ BhavAI Final Answer:")
    console.print(answer)
    memory.add_message("assistant", raw_response)
    return answer  # ← ReAct loop exit
```

---

## Complete `TOOL_DISPATCH` Registry

```python
# tools.py
TOOL_DISPATCH = {
    "list_folder":    list_folder,
    "read_file":      read_file,
    "write_file":     write_file,
    "update_file":    update_file,    # deprecated
    "append_chunk":   append_chunk,
    "run_command":    run_command,
}

# + tools_extended.py (EXTENDED_TOOL_DISPATCH):
{
    "read_file_chunk":      ...,
    "search_code":          ...,
    "find_files":           ...,
    "get_outline":          ...,
    "find_symbol":          ...,
    "find_references":      ...,
    "get_function_source":  ...,
    "replace_lines":        ...,
    "insert_lines":         ...,
    "delete_lines":         ...,
    "patch_file":           ...,
    "insert_function":      ...,
    "replace_function":     ...,
    "create_directory":     ...,
    "rename_path":          ...,
    "run_tests":            ...,
    "lint_file":            ...,
    "check_dependencies":   ...,
    "get_diff":             ...,
    "revert_file":          ...,
    "git_commit":           ...,
    "fetch_url":            ...,
    "duckduckgo_search":    ...,
    "check_weather":        ...,
    "read_image":           ...,
    "list_todos":           ...,
}

# + agents/ (AGENT_DISPATCHERS):
{
    "calendar_schedule":    ...,
    "calendar_list":        ...,
    "calendar_delete":      ...,
    "calendar_free_slots":  ...,
}
```

---

## Tool Execution Flow in Agent Loop

```
LLM Response: '{"thought":"need to read config","tool_name":"read_file","tool_args":{"path":"config.py"}}'
    │
    ▼ agent.py:846
parsed = parse_llm_json(raw_response)
tool_name = "read_file"
tool_args = {"path": "config.py"}
    │
    ▼ TOOL_DISPATCH.get("read_file")
tool_func = read_file  [from tools.py]
    │
    ▼ (plan mode only) approval check for MUTATING_TOOLS
    │
    ▼
with console.status("[TOOL] read_file(path='config.py')…"):
    result = tool_func(**tool_args)
    # = read_file(path="config.py")
    #   → validate_path("config.py")  ← sandbox check
    #   → is_env_file(resolved)       ← secrets check
    #   → resolved.read_text()
    #   → return file content
    │
    ▼
console.print(Panel(result[:100], title="🔍 Observation — read_file"))
memory.add_message("user", f"Observation from read_file:\n{result}")
    │
    ▼ Next iteration: LLM receives full result in context
```
