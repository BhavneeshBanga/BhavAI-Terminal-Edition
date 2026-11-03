# 🛡️ 04 — Sandboxing: Security System Kaise Kaam Karta Hai

## TL;DR

BhavAI mein **4 layers** of security hain:

```
Layer 1: Path Sandboxing    → Agent sirf CWD ke andar kaam kar sakta hai
Layer 2: Command Blocklist  → rm, rmdir, del, format etc. BLOCKED hain
Layer 3: Secrets Guard      → .env files kabhi nahi read/write hongi
Layer 4: Trust System       → Har nayi folder trust karna padta hai
```

---

## Layer 1: Path Sandboxing — `validate_path()`

**File:** [`bhavai/tools.py`](../bhavai/tools.py) — Line 41

Yeh function **har** file operation se pehle call hota hai — `read_file`, `write_file`, `append_chunk`, `list_folder` sab mein.

```python
def validate_path(path_str: str) -> Path:
    """
    Ensures path_str resolves strictly inside CWD or PROMPTS_DIR.
    Raises ValueError if outside.
    """
    raw = Path(path_str).expanduser()
    resolved = raw.resolve() if raw.is_absolute() else (CWD / raw).resolve()

    # Check 1: Kya yeh CWD ke andar hai?
    try:
        resolved.relative_to(CWD)
        return resolved  # ✅ ALLOWED
    except ValueError:
        pass

    # Check 2: Kya yeh skills/prompts directory mein hai?
    try:
        resolved.relative_to(PROMPTS_DIR.resolve())
        return resolved  # ✅ ALLOWED (skills read karne ke liye)
    except ValueError:
        pass

    # Check 3: Alternate case (~/.BhavAI/ vs ~/.bhavai/)
    alt_prompts = (Path.home() / ".BhavAI" / "config" / "prompts").resolve()
    try:
        resolved.relative_to(alt_prompts)
        return resolved  # ✅ ALLOWED
    except ValueError:
        pass

    # Kuch nahi mila → ACCESS DENIED
    raise ValueError(
        f"Access Denied: '{path_str}' → '{resolved}' is outside "
        f"the sandboxed directory '{CWD}'."
    )
```

### Allowed Paths:
| Path | Allowed? |
|------|----------|
| `./src/main.py` | ✅ CWD ke andar |
| `../other-project/` | ❌ CWD se bahar |
| `~/.bhavai/config/prompts/Weather.md` | ✅ Skills read allowed |
| `~/.bhavai/brain/session.json` | ❌ Brain directory blocked |
| `/etc/passwd` | ❌ System files blocked |
| `C:\Windows\system32` | ❌ System files blocked |

### Path Traversal Attack Prevention:
```
agent tries: path = "../../etc/passwd"
    → (CWD / "../../etc/passwd").resolve()
    → "/etc/passwd"  (absolute path)
    → relative_to(CWD) → ValueError
    → relative_to(PROMPTS_DIR) → ValueError
    → RAISES: "Access Denied: '../../etc/passwd' → '/etc/passwd' is outside..."
```

---

## Layer 2: Command Blocklist — `validate_command()`

**File:** [`bhavai/tools.py`](../bhavai/tools.py) — Line 30

```python
BLOCKED_COMMANDS = [
    "rm", "rmdir", "del", "unlink",
    "shutil.rmtree", "os.remove",
    "format", "mkfs", "drop table",
]

def validate_command(command: str) -> None:
    """Word-boundary regex check against BLOCKED_COMMANDS."""
    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if re.search(rf"(?:^|\W){re.escape(blocked)}(?:$|\W)", cmd_lower):
            raise ValueError(
                f"Security Violation: blocked operation '{blocked}' in command."
            )
```

### Word Boundary Check (Important):
`\W` se match hota hai, isliye:
- `rm file.txt` → ❌ BLOCKED (`rm` word boundary pe hai)
- `npm` → ✅ ALLOWED (`rm` yahan word boundary pe nahi)
- `git commit -m "fix remove bug"` → ✅ ALLOWED (`remove` mein `rm` hai lekin boundary nahi)

### `run_command()` mein usage:
**File:** [`bhavai/tools.py`](../bhavai/tools.py)

```python
def run_command(command: str) -> str:
    ensure_git_initialized()
    validate_command(command)   # ← Pehle blocklist check

    result = subprocess.run(
        command,
        shell=True,
        cwd=CWD,           # ← Always CWD mein run
        capture_output=True,
        text=True,
        timeout=60,
    )
    ...
```

---

## Layer 3: Secrets Guard — `is_env_file()`

**File:** [`bhavai/context.py`](../bhavai/context.py) — Line 19

```python
def is_env_file(path: Path) -> bool:
    """
    Returns True if this file is an environment/secrets file.
    NEVER shown in folder tree or read by agent.
    """
    name = path.name.lower()
    if name.startswith(".env"):      # .env, .env.local, .env.production...
        return True
    if name in {
        ".envrc", ".secrets", ".secret",
        ".netrc", ".htpasswd",
        "credentials.json",
        "secrets.yaml", "secrets.yml", "secrets.json"
    }:
        return True
    return False
```

### Yeh kahan-kahan use hota hai:

**1. Folder Tree mein (context.py):**
```python
def should_ignore(path, root_dir, gitignore_patterns):
    # ── 1. Env / secrets files — never shown to LLM ──
    if path.is_file() and is_env_file(path):
        return True  # Tree mein nahi dikhega
```

**2. `read_file()` mein (tools.py):**
```python
def read_file(path: str) -> str:
    resolved = validate_path(path)
    if is_env_file(resolved):
        return "Access Denied: '.env' is an environment/secrets file."
```

**3. `write_file()` mein (tools.py):**
```python
def write_file(path: str, content: str) -> str:
    if is_env_file(resolved):
        return "Access Denied: BhavAI never writes to .env files."
```

**4. `append_chunk()` mein (tools.py):**
```python
def append_chunk(path: str, chunk: str, done: bool = False) -> str:
    if is_env_file(resolved):
        return "Access Denied: BhavAI never writes to .env files."
```

---

## Layer 4: Folder Trust System

**File:** [`bhavai/main.py`](../bhavai/main.py)

Yeh BhavAI ka "sandbox at folder level" hai. User pehli baar kisi folder mein jaata hai toh BhavAI trust permission maangta hai.

### Trust File Location:
```
~/.bhavai/trusted_folders.json
```

**Content example:**
```json
[
  "C:\\Users\\bhavi\\Downloads\\Coding Payground\\BhavAI-Terminal-Edition",
  "C:\\Users\\bhavi\\Projects\\MyApp"
]
```

### Trust Check Logic:

```python
TRUST_FILE = Path.home() / ".bhavai" / "trusted_folders.json"

def is_folder_trusted(cwd: Path) -> bool:
    trusted = _load_trusted_folders()
    cwd_str = str(cwd.resolve())
    return any(
        cwd_str == t or cwd_str.startswith(t.rstrip("/\\") + os.sep)
        for t in trusted
    )
```

**Important:** `startswith` check isliye hai ki agar parent trusted hai toh child folder bhi automatically trusted maana jaata hai.

### Trust Dialog — `prompt_trust_folder()`:

```python
def prompt_trust_folder(console: Console, cwd: Path) -> bool:
    # Rich panel dikhao
    console.print(Panel(
        "Do you trust the files in this folder?\n"
        "Trusting allows BhavAI to load local configurations...",
        title="BhavAI - Trust Check",
    ))

    options = [
        f"Trust folder ({folder_name})",
        f"Trust parent folder ({parent_name})",
        "Don't trust",
    ]

    choice = _inline_arrow_menu(options)

    if choice is None or choice == 2:
        return False  # Don't trust → exit

    if choice == 0:
        _save_trusted_folder(str(cwd.resolve()))
    elif choice == 1:
        _save_trusted_folder(str(cwd.parent.resolve()))

    return True
```

### `_inline_arrow_menu()` — Arrow Key UI:

```python
def _inline_arrow_menu(options: list) -> int:
    # prompt_toolkit Application use karta hai
    # Up/Down arrows se navigate
    # Enter se select
    # Escape/Ctrl-C se cancel
    app = Application(
        layout=Layout(Window(FormattedTextControl(get_text))),
        key_bindings=kb,
        full_screen=False,  # ← Poora screen nahi, inline mein render
    )
    app.run()
    return result["value"]
```

---

## Git Integration as Safety Net

**File:** [`bhavai/tools.py`](../bhavai/tools.py) — Line 95

Har mutating tool se pehle `ensure_git_initialized()` call hota hai:

```python
def ensure_git_initialized() -> None:
    git_dir = CWD / ".git"
    if git_dir.exists():
        return  # Already initialized

    # Pehli baar: git init + initial commit
    _run("git", "init")
    _run("git", "config", "user.name", "BhavAI")
    _run("git", "config", "user.email", "bhavai@local.ai")
    _run("git", "add", ".")
    _run("git", "commit", "--allow-empty", "-m", "Initial commit — BhavAI")
```

Har file write ke baad:
```python
def _git_stage(resolved: Path) -> None:
    subprocess.run(["git", "add", str(resolved)], cwd=CWD)
```

Isse user `git diff HEAD` se dekh sakta hai agent ne kya kya badla, aur `revert_file` tool se undo kar sakta hai.

---

## System Prompt mein Hardcoded Rules

**File:** [`bhavai/agent.py`](../bhavai/agent.py) — SYSTEM_PROMPT_TEMPLATE

LLM ko directly in rules ke baare mein bataya jaata hai:

```
STRICT RULES (never break these):
1. NEVER delete entire files or directories.
2. Stay inside {cwd} — all paths are sandboxed.
3. Blocked commands: rm, rmdir, del, unlink, shutil.rmtree...
4. NEVER attempt to read .env, .env.local, credentials.json...
```

---

## Security Flow Summary

```
Agent wants to: read_file("../../etc/passwd")
    │
    ▼ tools.py: read_file()
    ├── ensure_git_initialized()
    ├── validate_path("../../etc/passwd")
    │   ├── resolved = "/etc/passwd"
    │   ├── relative_to(CWD) → FAIL
    │   ├── relative_to(PROMPTS_DIR) → FAIL
    │   └── RAISES ValueError: "Access Denied"
    └── ❌ Tool returns error string to agent

Agent wants to: run_command("rm -rf /")
    │
    ▼ tools.py: run_command()
    ├── ensure_git_initialized()
    ├── validate_command("rm -rf /")
    │   ├── "rm" matched in BLOCKED_COMMANDS
    │   └── RAISES ValueError: "Security Violation: blocked 'rm'"
    └── ❌ Tool returns error string to agent

Agent wants to: read_file(".env")
    │
    ▼ tools.py: read_file()
    ├── validate_path(".env") → CWD/.env → PASSES (CWD ke andar hai)
    ├── is_env_file(resolved) → TRUE
    └── ❌ Returns "Access Denied: '.env' is an environment/secrets file"
```
