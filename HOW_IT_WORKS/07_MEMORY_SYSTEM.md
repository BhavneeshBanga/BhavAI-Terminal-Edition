# 🧠 07 — Memory System: Conversation History kaise Manage hoti hai

## TL;DR

```
ConversationMemory class:
    - messages[] list mein sab store hota hai
    - max 100,000 characters (≈25,000 tokens)
    - Limit cross hone par: first message + recent messages keep, middle prune
    - Session hash se ~/.bhavai/brain/ mein .json + .md save
    - --resume flag se purana session wapas load
```

---

## `ConversationMemory` Class

**File:** [`bhavai/memory.py`](../bhavai/memory.py)

```python
class ConversationMemory:
    def __init__(self, max_chars: int = 100000):
        self.messages = []
        self.max_chars = max_chars   # ≈25,000 tokens
```

---

## Message Structure

Har message ek dict hai:

**Normal message:**
```python
{"role": "user",      "content": "Write a README file"}
{"role": "assistant", "content": '{"thought":"...","tool_name":"write_file","tool_args":{...}}'}
{"role": "user",      "content": "Observation from write_file:\n✓ README.md written"}
{"role": "system",    "content": "<system prompt>"}
```

**Image message:**
```python
{
    "role": "user",
    "content": "analyze this screenshot",
    "images": ["C:/Users/bhavi/screenshot.png"]  # Extra field
}
```

---

## Messages Add Karna

**Normal text:**
```python
def add_message(self, role: str, content: str):
    self.messages.append({"role": role, "content": content})
    logger.debug("Memory added message from role: %s (length: %d)", role, len(content))
```

**Image message:**
```python
def add_image_message(self, role: str, text: str, image_paths: list[str]):
    self.messages.append({
        "role": role,
        "content": text,
        "images": image_paths,
    })
```

---

## Memory Compilation — `get_messages()`

**File:** [`bhavai/memory.py`](../bhavai/memory.py) — Line 69

Yeh function har LLM call se pehle call hota hai. System prompt + history combine karta hai:

```python
def get_messages(self, system_prompt: str) -> list:
    compiled = [{"role": "system", "content": system_prompt}]

    if not self.messages:
        return compiled

    total_chars = sum(len(m["content"]) for m in self.messages)

    # Case 1: Limit ke andar → sab include karo
    if total_chars <= self.max_chars:
        compiled.extend(self.messages)
        return compiled

    # Case 2: Limit cross → pruning
    logger.warning("Conversation history exceeds limit (%d > %d). Pruning...", total_chars, self.max_chars)
    ...
```

### Pruning Strategy:

```python
# Budget calculation
reserved_len = len(system_prompt) + len(first_msg["content"])
available_budget = self.max_chars - reserved_len

# Newest se oldest tak messages collect karo
recent_messages = []
accumulated_len = 0
for msg in reversed(self.messages[1:]):  # First message skip
    msg_len = len(msg["content"])
    if accumulated_len + msg_len > available_budget:
        break                            # Budget full → stop
    recent_messages.insert(0, msg)
    accumulated_len += msg_len

# Final compiled list:
compiled = [
    {"role": "system", "content": system_prompt},     # System prompt (ALWAYS)
    first_msg,                                          # First user message (ALWAYS)
    {"role": "user", "content": "... [Older history truncated] ..."},  # Placeholder
    *recent_messages                                    # Recent messages (fit in budget)
]
```

**Visual:**
```
Full history: [msg1, msg2, msg3, msg4, msg5, msg6, msg7, msg8, msg9, msg10]
                ↑                                              ↑
           ALWAYS keep                                   ALWAYS keep recent

After pruning: [system, msg1, "...[truncated]...", msg7, msg8, msg9, msg10]
```

---

## Session Persistence

### Session Hash:
```python
import uuid
session_hash = uuid.uuid4().hex[:8]  # e.g., "a3f9b12c"
```

### Session Files in `~/.bhavai/brain/`:
```
~/.bhavai/brain/
    a3f9b12c.json   ← JSON format (machine-readable, resumable)
    a3f9b12c.md     ← Markdown format (human-readable)
```

### Save to JSON:
```python
def save_to_json(self, path) -> None:
    Path(path).write_text(
        json.dumps(self.messages, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
```

**JSON format:**
```json
[
  {
    "role": "user",
    "content": "write a Flask hello world app"
  },
  {
    "role": "assistant",
    "content": "{\"thought\": \"I'll create a simple Flask app\", \"tool_name\": \"write_file\", ...}"
  },
  {
    "role": "user",
    "content": "Observation from write_file:\n✓ 'app.py' written (45 chars, 5 lines)."
  }
]
```

### Save to Markdown:
```python
def save_to_file(self, path) -> None:
    lines = []
    for msg in self.messages:
        lines.append(f"### {msg['role'].upper()}\n\n{msg['content']}\n")
    Path(path).write_text("\n---\n\n".join(lines), encoding="utf-8")
```

**Markdown format:**
```markdown
### USER

write a Flask hello world app

---

### ASSISTANT

{"thought": "I'll create...", "tool_name": "write_file", ...}

---

### USER

Observation from write_file:
✓ 'app.py' written (45 chars, 5 lines).
```

---

## Session Resume

**Command:**
```bash
bhav wake up --resume a3f9b12c
```

**Code:**
```python
if resume:
    session_hash = str(resume).strip().removesuffix(".json").removesuffix(".md")
    json_file = brain_dir / f"{session_hash}.json"
    md_file   = brain_dir / f"{session_hash}.md"

    loaded = False
    if json_file.exists():
        loaded = memory.load_from_json(json_file)
    elif md_file.exists():
        loaded = memory.load_from_json(md_file)

    if loaded:
        console.print(f"✓ Conversation resumed ({len(memory.messages)} messages loaded)")
    else:
        console.print(f"Error: Could not find session '{resume}'")
        sys.exit(1)
```

### `load_from_json()`:
```python
def load_from_json(self, path) -> bool:
    data = json.loads(file_path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        self.messages = data         # ← Direct list of messages
        return True
    elif isinstance(data, dict) and "messages" in data:
        self.messages = data["messages"]  # ← Wrapped format (legacy)
        return True

    return False
```

---

## Session Auto-Save on Exit

```python
def _save_brain_session():
    if memory.messages:   # Sirf agar kuch messages hain toh
        memory.save_to_json(brain_dir / f"{session_hash}.json")
        memory.save_to_file(brain_dir / f"{session_hash}.md")

# Called at:
if not is_command and user_input.lower() in ("exit", "quit"):
    _save_brain_session()
    console.print(
        f"To resume run: bhav wake up --resume {session_hash}"
    )
    break
```

---

## `/export` Command — Manual Export to Project Memories

```python
if low == "/export":
    memories_dir = CWD / ".bhavai" / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    save_path = memories_dir / f"{SESSION_NAME}.md"
    memory.save_to_file(save_path)
    console.print(f"✓ Conversation saved to {save_path}")
```

Session name format: `NEW_CHAT_<unix_timestamp>` ya `/rename` se set naam.

---

## Memory in ReAct Loop — How it Grows

```
Start: messages = []

Agent loop begins:
  memory.add_message("user", task_prompt)
  messages = [
    {"role": "user", "content": "Task: write README\n\nApproved plan:\n1. Analyze..."}
  ]

Step 1 — LLM call:
  messages to LLM = [system_prompt] + messages
  LLM returns: '{"thought":"...","tool_name":"read_file","tool_args":{"path":"pyproject.toml"}}'

  memory.add_message("assistant", llm_response)
  memory.add_message("user", "Observation from read_file:\n[project]\nname = 'bhavai'...")

  messages = [
    {"role": "user",      "content": "Task: write README..."},
    {"role": "assistant", "content": '{"thought":"...","tool_name":"read_file"...}'},
    {"role": "user",      "content": "Observation from read_file:\n[project]\n..."},
  ]

Step 2 — LLM call:
  [Full message history bheja jaata hai context ke saath]
  LLM returns: '{"thought":"Now I'll write the README","tool_name":"write_file",...}'
  ...and so on
```

---

## Project Memory vs Conversation Memory

| Feature | `ConversationMemory` | `BHAVAI.md` (Project Memory) |
|---------|---------------------|------------------------------|
| **Location** | RAM (in-memory) + `~/.bhavai/brain/` | `CWD/BHAVAI.md` (project folder) |
| **Scope** | Ek session ki history | Project-level context (permanent) |
| **Used by** | Agent loop ke har step mein | System prompt mein inject hota hai |
| **Created by** | Auto (every message) | `/init` command ya agent |
| **Format** | `[{"role": "...", "content": "..."}]` | Free-form markdown |
| **Limit** | 100,000 chars, phir prune | No limit |

**`get_project_memory_string()`:**
```python
def get_project_memory_string(cwd) -> str:
    """BHAVAI.md padho aur return karo (agent ke system prompt ke liye)."""
    bhavai_md = cwd / "BHAVAI.md"
    if bhavai_md.exists():
        return bhavai_md.read_text(encoding="utf-8")
    return ""
```
