# 🚀 01 — `bhav wake up` Flow: Entry Point se REPL Loop tak

## TL;DR
Jab user terminal mein `bhav wake up` likhta hai, toh ye sequence hoti hai:
```
pyproject.toml entry point
    → main() [click group]
        → wake() [click command]
            → Trust check
            → API key check
            → Banner print
            → Folder tree print
            → ConversationMemory initialize
            → PromptSession (REPL) start
                → Infinite while loop (user ka input leta hai)
```

---

## Step 1: Entry Point — `pyproject.toml`

**File:** [`pyproject.toml`](../pyproject.toml)

```toml
[project.scripts]
bhav = "bhavai.main:main"
```

Jab user `bhav` command chalata hai, Python seedha `bhavai/main.py` ke `main()` function ko call karta hai.

---

## Step 2: `main()` — Click Group

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 246

```python
@click.group(invoke_without_command=True, add_help_option=False)
@click.option("--help", "show_help", is_flag=True)
@click.pass_context
def main(ctx, show_help):
```

`main` ek Click **group** hai. Iska matlab — yeh commands ka container hai.
- Agar `bhav --help` ho → help panel print karta hai
- Agar koi subcommand nahi → error deta hai: "bhav wake up use karo"

---

## Step 3: `wake()` — Main Command Handler

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 300

```python
@main.command()
@click.argument("action", default="up")
@click.option("--resume", default=None, help="Resume conversation by session hash.")
def wake(action, resume):
```

Yeh `bhav wake up` ka actual handler hai.

### 3.1 — Action Validation
```python
if action != "up":
    console.print(f"Error: Invalid action '{action}'")
    sys.exit(1)
```
Sirf `up` allowed hai. `bhav wake down` → error.

### 3.2 — First-Time Setup
```python
BhavAI_dot_folder = Path.home() / ".bhavai"
if not BhavAI_dot_folder.exists():
    BhavAI_dot_folder.mkdir()
    create_first_file_Note_from_bhavai()  # welcome note banata hai
ensure_prompts_dir()  # ~/.bhavai/config/prompts/ ensure karta hai
```

**Function:** `create_first_file_Note_from_bhavai()` → [`bhavai/helper/create_first_file_Note_from_bhavai_.py`](../bhavai/helper/create_first_file_Note_from_bhavai_.py)

**Function:** `ensure_prompts_dir()` → [`bhavai/config.py`](../bhavai/config.py) — Default skills (Weather.md, SampleSkill.md) create karta hai agar exist nahi karti.

### 3.3 — Trust Check (Security Gate)
```python
if not is_folder_trusted(CWD):
    trusted_now = prompt_trust_folder(console, CWD)
    if not trusted_now:
        sys.exit(1)
```

**Functions involved:**

| Function | File | Kaam |
|----------|------|------|
| `is_folder_trusted(cwd)` | `main.py:83` | `~/.bhavai/trusted_folders.json` check karta hai |
| `_load_trusted_folders()` | `main.py:66` | JSON file se trusted paths load karta hai |
| `prompt_trust_folder()` | `main.py:149` | Arrow-key menu dikhata hai (Trust/Don't Trust) |
| `_inline_arrow_menu()` | `main.py:92` | `prompt_toolkit` se interactive menu render karta hai |
| `_save_trusted_folder()` | `main.py:75` | Trust decision ko JSON file mein save karta hai |

**Trust file location:** `~/.bhavai/trusted_folders.json`

### 3.4 — Config Load + API Key Check
```python
cfg = get_config_summary()
if not cfg["API_KEY_PRESENT"]:
    console.print("API KEY MISSING...")
    sys.exit(1)
```

**Function:** `get_config_summary()` → [`bhavai/config.py:193`](../bhavai/config.py) — Returns dict with CWD, MODEL, LOG_FILE, API_KEY_PRESENT

### 3.5 — Banner Print (ASCII Art)
```python
if threshold_width_ > 160:
    print_bhavai_terminal_agent()   # full width ASCII art
elif threshold_width_ > 94:
    print_bhavai_agent()            # medium size banner
else:
    pass                            # narrow terminal → no banner
```

Terminal width check hoti hai (`shutil.get_terminal_size()`), aur accordingly banner choose hota hai.

### 3.6 — Folder Tree Print
```python
tree_str = get_folder_tree_string(CWD)
console.print(tree_str)
```

**Function:** `get_folder_tree_string(CWD)` → [`bhavai/context.py:142`](../bhavai/context.py)
- `.gitignore` patterns parse karta hai
- `.env`, `__pycache__`, `.git`, `node_modules` etc. automatically hide karta hai
- Unicode tree (`├──`, `└──`) format mein return karta hai

### 3.7 — Session Initialization
```python
import uuid
current_mode = AgentMode.PLAN          # DEFAULT mode = PLAN
memory = ConversationMemory()          # fresh memory
brain_dir = ensure_brain_dir()         # ~/.bhavai/brain/ ensure karo

if resume:
    # hash se purana session load karo
    memory.load_from_json(json_file)
else:
    session_hash = uuid.uuid4().hex[:8]  # e.g. "a3f9b12c"
```

**Session hash** ek 8-character random ID hai. Yeh brain ke JSON file ka naam hota hai: `~/.bhavai/brain/a3f9b12c.json`

### 3.8 — PromptSession Setup (Input Handler)
```python
from bhavai.ui.clipboard_paste import build_paste_keybindings
paste_kb, paste_store, paste_counter, get_and_reset_bursts = build_paste_keybindings(
    CWD, on_image_pasted=_record_pasted_image
)
session = PromptSession(key_bindings=paste_kb)
```

`PromptSession` se `prompt_toolkit` ki interactive input milti hai — ye live prompt color change karta hai based on mode.

```python
def get_prompt_text():
    buf = session.default_buffer.text
    if buf.startswith("!"):   return HTML('<ansired><b>(bash)</b></ansired> > ')
    if buf.startswith("/"):   return HTML('<ansiyellow><b>(command)</b></ansiyellow> > ')
    if current_mode == AgentMode.PLAN:
        return HTML('<ansicyan><b>(plan)</b></ansicyan> > ')
    else:
        return HTML('<ansiyellow><b>(agent)</b></ansiyellow> > ')
```

---

## Step 4: REPL Loop — Infinite While Loop

**File:** [`bhavai/main.py`](../bhavai/main.py) — Line 589

```python
while True:
    user_input = session.prompt(get_prompt_text).strip()
    user_input = expand_pasted_text(user_input, paste_store)
    ...
```

### Input ke types aur unka handling:

| Input Pattern | Handler |
|---------------|---------|
| Empty string | `continue` (ignore) |
| `!<command>` | `subprocess.run(command, cwd=CWD)` — bash execute |
| `/rename <name>` | SESSION_NAME update karo |
| `/export` | `memory.save_to_file()` → `.bhavai/memories/` |
| `/init` | `generate_bhavai_md(CWD)` → BHAVAI.md banao |
| `/<command_name>` | `.bhavai/commands/<name>.md` padho, content ko prompt banao |
| `mode agent` | `current_mode = AgentMode.AGENT` |
| `mode plan` | `current_mode = AgentMode.PLAN` |
| `exit` / `quit` | Session save karo, loop break karo |
| Kuch bhi aur | **Agent ko bhejo** (plan ya autonomous mode) |

### Session Save on Exit:
```python
def _save_brain_session():
    if memory.messages:
        memory.save_to_json(brain_dir / f"{session_hash}.json")
        memory.save_to_file(brain_dir / f"{session_hash}.md")
```

---

## Complete Call Graph: `bhav wake up`

```
bhav wake up
└── main() [click group handler]
    └── wake(action="up") [click command]
        ├── create_first_file_Note_from_bhavai()    [first time only]
        ├── ensure_prompts_dir()                    [config.py]
        ├── is_folder_trusted(CWD)                  [main.py]
        │   └── _load_trusted_folders()
        ├── prompt_trust_folder()                   [if not trusted]
        │   └── _inline_arrow_menu()
        │       └── prompt_toolkit Application
        ├── _save_trusted_folder()                  [if user trusts]
        ├── get_config_summary()                    [config.py]
        ├── print_bhavai_terminal_agent() / print_bhavai_agent()
        ├── get_folder_tree_string(CWD)             [context.py]
        │   ├── parse_gitignore()
        │   ├── build_folder_tree()
        │   └── should_ignore()
        ├── show_update_message()                   [updater/updates.py]
        ├── ConversationMemory()                    [memory.py]
        ├── ensure_brain_dir()                      [config.py]
        ├── build_paste_keybindings()               [ui/clipboard_paste.py]
        └── while True:  ← REPL Loop
            ├── session.prompt(get_prompt_text)
            ├── expand_pasted_text()
            └── [input routing] → agent / commands / bash / mode switch
```
