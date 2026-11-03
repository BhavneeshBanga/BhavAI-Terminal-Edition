# 📚 BhavAI — HOW IT WORKS (Developer Documentation)

> **Yeh folder ek naye developer ke liye hai** jo pehli baar BhavAI ka code dekh raha hai.
> Yahan har ek important flow ko function-level detail mein explain kiya gaya hai.

---

## 📂 Files in this Folder

| File | Kya explain karta hai |
|------|-----------------------|
| [`01_WAKE_UP_FLOW.md`](./01_WAKE_UP_FLOW.md) | `bhav wake up` likhne se kya kya hota hai — startup se leke REPL loop tak |
| [`02_MODE_SWITCHING.md`](./02_MODE_SWITCHING.md) | `mode agent` / `mode plan` switch karne par kya hota hai |
| [`03_PROMPT_TO_EXECUTION.md`](./03_PROMPT_TO_EXECUTION.md) | User ka prompt → System Prompt assembly → LLM → Tool execution — pura flow |
| [`04_SANDBOXING.md`](./04_SANDBOXING.md) | Sandboxing kaise kaam karta hai — path validation, command blocklist, secrets guard |
| [`05_PLAN_MODE_DEEP_DIVE.md`](./05_PLAN_MODE_DEEP_DIVE.md) | Plan Mode ka poora internals — planner.py, PlannerState, deep plan generation |
| [`06_AGENT_MODE_DEEP_DIVE.md`](./06_AGENT_MODE_DEEP_DIVE.md) | Agent Mode ka ReAct loop — step-by-step, JSON parsing, tool dispatch |
| [`07_MEMORY_SYSTEM.md`](./07_MEMORY_SYSTEM.md) | Conversation memory — kaise messages store hote hain, session resume, pruning |
| [`08_SKILLS_SYSTEM.md`](./08_SKILLS_SYSTEM.md) | Skills kya hain, kaise discover hoti hain, kaise agent use karta hai |
| [`09_TOOLS_REFERENCE.md`](./09_TOOLS_REFERENCE.md) | Har tool kya karta hai — tools.py ka walkthrough |
| [`10_ARCHITECTURE_OVERVIEW.md`](./10_ARCHITECTURE_OVERVIEW.md) | Poora system ek jagah — module map, data flow diagram |

---

## ⚡ Quick Start Reading Order

**Naye developer ke liye recommended order:**

```
00_INDEX.md (yahi hai)
    ↓
10_ARCHITECTURE_OVERVIEW.md  ← pehle bada picture dekho
    ↓
01_WAKE_UP_FLOW.md           ← entry point samjho
    ↓
02_MODE_SWITCHING.md         ← modes ka concept
    ↓
03_PROMPT_TO_EXECUTION.md    ← sabse important flow
    ↓
04_SANDBOXING.md             ← security layer
    ↓
05_PLAN_MODE_DEEP_DIVE.md    ← plan mode internals
    ↓
06_AGENT_MODE_DEEP_DIVE.md   ← agent mode internals
    ↓
07_MEMORY_SYSTEM.md          ← memory aur sessions
    ↓
08_SKILLS_SYSTEM.md          ← extensibility
    ↓
09_TOOLS_REFERENCE.md        ← tool reference
```

---

## 🗂️ Project Structure (High Level)

```
BhavAI-Terminal-Edition/
├── bhavai/                 ← Main source code package
│   ├── main.py             ← CLI entry point (bhav wake up)
│   ├── agent.py            ← ReAct loop, system prompt, JSON parsing
│   ├── modes.py            ← AgentMode, plan display, plan confirmation
│   ├── planner.py          ← Deep plan generation, PlannerState
│   ├── memory.py           ← ConversationMemory class
│   ├── tools.py            ← All sandboxed tools (read_file, write_file, etc.)
│   ├── tools_extended.py   ← Extra tools (web search, calendar, etc.)
│   ├── config.py           ← API keys, paths, logging setup
│   ├── context.py          ← Folder tree builder, secrets detection
│   ├── skill_getter.py     ← Skills discovery system
│   ├── llm.py              ← LLM API calls (Sarvam + Groq)
│   ├── ui/                 ← Terminal UI components
│   │   ├── shimmer.py      ← Loading animation
│   │   ├── live_thinking.py← Live "Thinking..." display
│   │   └── clipboard_paste.py ← Image paste support
│   ├── banner/             ← ASCII art banners
│   └── scripts/            ← Helper scripts (BHAVAI.md generator)
├── .bhavai/                ← Per-project config (local)
│   ├── commands/           ← Custom slash commands (.md files)
│   ├── skills/             ← Local skills (SKILL.md files)
│   └── memories/           ← Exported conversation histories
├── ~/.bhavai/              ← Global BhavAI config (home directory)
│   ├── config/prompts/     ← Global skills (.md files)
│   ├── brain/              ← Saved sessions (.json + .md)
│   ├── logs/               ← bhavai.log
│   └── trusted_folders.json← Trust list
└── pyproject.toml          ← Entry point: bhav = bhavai.main:main
```
