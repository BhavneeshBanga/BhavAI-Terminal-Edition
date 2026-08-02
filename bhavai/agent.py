"""
agent.py — BhavAI Core ReAct Loop

Architecture for 4096-token LLM output limit
=============================================
The Sarvam-105B model has a hard 4096-token output limit.
This file implements a 5-layer defence (was 4 in v1):

  Layer 1 — System prompt teaches the model to CHUNK large writes
             (never write more than 50 lines per tool call).

  Layer 2 — write_file / append_chunk tools enforce chunked writing.

  Layer 3 — query_llm_with_continuation() in llm.py automatically
             stitches together responses that hit max_tokens.
             THIS IS THE NEW LAYER — directly answers the question:
             "agar 4096 cross kare toh dubara call lagao aur append karo"

  Layer 4 — JSON repair pipeline (_fix_truncated_json) handles any
             remaining partial JSON after continuation.

  Layer 5 — Recovery feedback message tells the model exactly what went
             wrong and how to fix it before the next attempt.
"""


from bhavai.ui.shimmer import ShimmerStatus

import json
import re
from rich.console import Console
from rich.panel import Panel

from bhavai.config import CWD, logger
from bhavai.context import get_folder_tree_string
from bhavai.llm import query_llm_with_continuation, provider_needs_chunking
from bhavai.memory import ConversationMemory
from bhavai.tools import TOOL_DISPATCH, get_project_memory_string
from bhavai.skill_getter import discover_skills_from_dot_bhavai
from bhavai.llm import query_llm_with_continuation, provider_needs_chunking



def _token_budget_block() -> str:
    if not provider_needs_chunking():
        return ""   # Groq ke liye poora section gayab
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠  OUTPUT TOKEN BUDGET — READ CAREFULLY\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Your maximum output is 4096 tokens (~3000 words).\n"
        "...\n"
        "GOLDEN RULE → MAXIMUM 50 LINES OF CODE PER TOOL CALL.\n"
        "For ANY file longer than 50 lines you MUST use append_chunk...\n"
    )

def _chunk_reminder_suffix() -> str:
    if not provider_needs_chunking():
        return ""
    return "REMINDER: For any file > 50 lines use append_chunk (≤50 lines per call).\n"

MUTATING_TOOLS = {"run_command"}

# MUTATING_TOOLS = {"write_file", "update_file", "append_chunk", "run_command",
#                   "replace_function", "insert_function", "replace_lines",
#                   "insert_lines", "delete_lines", "rename_path"}

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are BhavAI, a personal AI agent running inside the terminal.
Activated folder: {cwd}

{project_context_block}
Current folder structure:
{folder_tree}
skills you have:
{skills_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE TOOLS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- list_folder   → {{"path": "string (default '.')"}}
- read_file     → {{"path": "string"}}
- write_file    → {{"path": "string", "content": "string"}}
    Use ONLY for short files (< 60 lines). For larger files use append_chunk.
- append_chunk  → {{"path": "string", "chunk": "string", "done": true|false}}
    Appends one chunk to a file. Set done=true on the LAST chunk only.
    Use this for ANY file > 60 lines by splitting into chunks of ≤50 lines each.
    Use this feature if you want to write after text , this append_chunk tool can add code at the end of file

- run_command   → {{"command": "string"}}
    Safe read-only shell commands only (git status, ls, cat …).
- search_code   → {{"query": "string", "path": "string (default '.')", "regex": true|false, "case_sensitive": true|false}}
    Grep-like search across the project. Use this FIRST when asked "where is X
    used/defined" instead of reading files one by one.
- find_files    → {{"pattern": "string (glob, e.g. '*.py')", "path": "string (default '.')"}}
    Locates files by name pattern without reading the whole tree.
- get_outline   → {{"path": "string"}}
    Returns function/class signatures + line numbers for a file WITHOUT its
    full content. Use this before read_file when you just need to navigate.
- list_todos    → {{"path": "string (default '.')"}}
    Scans for TODO / FIXME / HACK / XXX / BUG comments across the project.
- get_diff      → {{"path": "string (optional — omit for whole workspace)"}}
    Shows git diff HEAD — what BhavAI has actually changed so far.
- check_dependencies → {{"path": "string (default '.')"}}
    Parses requirements.txt / pyproject.toml / package.json and reports which
    declared dependencies are missing from the environment, with the install
    command to fix it. Run this before executing code that imports packages.
- rename_path   → {{"source": "string", "destination": "string"}}
    Moves/renames a file or folder. Refuses to overwrite an existing
    destination. This is the ONLY way to reorganize files — there is no
    delete tool, by design.
- fetch_url     → {{"url": "string", "max_chars": "int (default 8000)"}}
    Fetches real documentation/API reference/Stack Overflow pages so you can
    answer from ground truth instead of guessing library APIs from memory.
- duckduckgo_search → {{"query": "string", "max_results": "int (default 5)"}}
    Searches DuckDuckGo on the web for live query results (prices, news, docs).
    Pair with fetch_url to read full pages from search result links.
- get_function_source → {{"path": "string", "function_name": "string"}}
    Returns ONE function's exact source + line numbers, found via AST. Use
    this instead of read_file when you only need to inspect one function.
- insert_function → {{"path": "string", "new_source": "string"}}
    Appends a brand-new top-level function to the end of a Python file.
    new_source must be a complete, syntactically valid function definition.
    Use this only when the function does NOT already exist.
- replace_function → {{"path": "string", "function_name": "string", "new_source": "string"}}
    Replaces an existing top-level function's full source, located precisely
    via AST line numbers. new_source must be a complete, syntactically valid
    replacement function. Use get_function_source first if you need to see
    the current body before rewriting it.
- final_answer  → {{"answer": "string"}}
    Call this when the entire task is complete.


- read_file_chunk → {{"path": "string", "start_line": "int", "end_line": "int"}}
    Reads only a specific line range (1-indexed, inclusive) from a file,
    with line numbers. Use this instead of read_file for files longer than
    ~100 lines when you only need a portion of it.
- find_symbol   → {{"name": "string", "path": "string (default '.')"}}
    Project-wide "go to definition" — finds every class/function/variable
    named `name` across ALL .py files, not just one file. Use this FIRST
    when you need to know WHERE something is defined anywhere in the project.
- find_references → {{"name": "string", "path": "string (default '.')"}}
    Finds every place `name` is USED (not defined) across the project.
    More precise than search_code for symbols — pairs with find_symbol
    ("defined where" vs "used where").
- replace_lines → {{"path": "string", "start_line": "int", "end_line": "int", "new_content": "string"}}
    Replaces an exact line range in ANY file (not limited to Python
    functions). Use get_outline / find_symbol / read_file_chunk first to
    know the exact line numbers before calling this. you can edit multiple lines at once means start and end line might not be same.
- insert_lines  → {{"path": "string", "after_line": "int", "content": "string"}}
    Inserts new content after a specific line number, in any file type.
    Use after_line=0 to insert at the very top of the file.
- delete_lines  → {{"path": "string", "start_line": "int", "end_line": "int"}}
    Deletes an exact line range from a file. A git checkpoint is committed
    automatically BEFORE the deletion happens, so it is always recoverable
    with revert_file. Use only when you are CERTAIN those lines should go —
    prefer replace_lines if you're actually replacing content, not removing it.
- run_tests     → {{"path": "string (default '.')", "command": "string (optional)"}}
    Runs the project's test suite (auto-detects pytest / npm test if
    `command` is omitted). ALWAYS run this after making code changes,
    before calling final_answer, to verify your change didn't break anything.
- lint_file     → {{"path": "string"}}
    Runs a linter (ruff/flake8 for .py, eslint for .js/.ts) on one file, if
    installed. Use to catch syntax/style issues before calling final_answer.
- revert_file   → {{"path": "string"}}
    Restores a file to its last git-committed state — the undo button for
    write_file / append_chunk / replace_lines / insert_lines / delete_lines.
    Use this if a change you just made turns out to be wrong.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULES  (never break these)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. NEVER delete files or directories.
2. Stay inside {cwd} — all paths are sandboxed.
3. Blocked commands: rm, rmdir, del, unlink, shutil.rmtree, os.remove, format, mkfs, drop table.
4. Work step-by-step; show reasoning in "thought".
5. Call final_answer when done.
6. NEVER attempt to read .env, .env.local, .env.example, .env.*, credentials.json or any
   secrets file. These are permanently blocked.
7. Prefer search_code / find_files / get_outline over read_file when you only need to
   locate something — this saves tokens and avoids dumping whole files into context.
8. There is still NO tool to delete an entire file or directory, on purpose. To reorganize
   files use rename_path, never run_command with rm/mv shell tricks (they will be blocked
   anyway). delete_lines only removes lines WITHIN a file that still exists — it is not a
   file-deletion tool, and it always checkpoints via git first.
9. To add or change a SINGLE function in an existing Python file, prefer insert_function /
   replace_function over write_file or append_chunk — they only touch that one function via
   AST, so the rest of the file (and your token budget) is untouched.
10. Use find_symbol / find_references instead of search_code when looking for a specific
    class, function, or variable by name — they use AST, so they won't be confused by that
    name appearing inside a comment or string elsewhere.
11. Use replace_lines / insert_lines (not insert_function / replace_function) when editing
    non-Python files, or when the change isn't a whole top-level function.
12. Prefer replace_lines over delete_lines whenever you are swapping content rather than
    purely removing it — delete_lines should only be used when nothing is replacing those
    lines.
13. After making a code change, run run_tests (if a test suite exists) before calling
    final_answer. If a change breaks something, use revert_file to undo it rather than
    trying to manually patch it back.
{token_budget_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT  (raw JSON only — no markdown fences, no extra text)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "thought": "brief reasoning about what you are about to do",
  "tool_name": "one of the tool names above",
  "tool_args": {{
    "arg_name": "arg_value"
  }}
}}

Inside JSON strings:  newline → \\n   quote → \\"   backslash → \\\\
"""

# ─────────────────────────────────────────────────────────────────────────────
# JSON Cleaning Pipeline (unchanged from v1 — still needed as safety net)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json_block(text: str) -> str:
    """Strip <think> tags, markdown fences, and pull the outermost { … }."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()

    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return text


def _escape_control_chars(text: str) -> str:
    """
    Walk raw JSON text character-by-character.
    Inside string literals convert bare control chars to escape sequences.
    """
    result    = []
    in_string = False
    i         = 0
    n         = len(text)

    while i < n:
        ch = text[i]

        if in_string:
            if ch == "\\":
                result.append(ch)
                i += 1
                if i < n:
                    result.append(text[i])
                    i += 1
                continue
            elif ch == '"':
                in_string = False
                result.append(ch)
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            elif ord(ch) < 0x20:
                result.append(f"\\u{ord(ch):04x}")
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
                result.append(ch)
            else:
                result.append(ch)

        i += 1

    return "".join(result)


def _fix_truncated_json(text: str) -> str:
    """
    Attempt to repair JSON that was cut off mid-string.
    Tries json.loads first; on 'Unterminated string' walks the text to close
    open strings/braces/brackets.
    """
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        if "Unterminated string" not in str(e):
            return text

    depth_braces   = 0
    depth_brackets = 0
    in_string      = False
    i              = 0
    n              = len(text)

    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '{':
                depth_braces += 1
            elif ch == '}':
                depth_braces -= 1
            elif ch == '[':
                depth_brackets += 1
            elif ch == ']':
                depth_brackets -= 1
        i += 1

    suffix = []
    if in_string:
        suffix.append('"')
    suffix.extend(']' * depth_brackets)
    suffix.extend('}' * depth_braces)

    repaired = text + "".join(suffix)
    try:
        json.loads(repaired)
        logger.info("_fix_truncated_json: successfully repaired truncated JSON.")
        return repaired
    except json.JSONDecodeError:
        return text


def clean_json_text(raw_text: str) -> str:
    """Full pipeline: extract → escape → attempt repair."""
    text = _extract_json_block(raw_text)
    text = _escape_control_chars(text)
    text = _fix_truncated_json(text)
    return text


def parse_llm_json(raw_text: str) -> dict:
    """
    Parses LLM output into a dict.
    Raises ValueError with an actionable message on failure.
    """
    cleaned = clean_json_text(raw_text)
    logger.debug("parse_llm_json cleaned: %r", cleaned[:400])

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s | cleaned=%r", e, cleaned[:500])
        raise ValueError(
            f"Invalid JSON — {e.msg} at line {e.lineno} col {e.colno}. "
            + ("Your response was likely cut off due to the 4096-token output limit. "
            "FIX: Use append_chunk with ≤50 lines per call instead of one large write."
            if provider_needs_chunking() else
            "The response may be malformed — check the JSON structure.")
        )


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_project_context_block(cwd) -> str:
    """
    BHAVAI.md se project memory read karta hai aur agar mile to
    system prompt mein daalne layak ek formatted block banata hai.
    Empty string agar file nahi mili — template mein clean skip ho jaata hai.
    """
    memory = get_project_memory_string(cwd)
    if not memory:
        return ""
    return (
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "PROJECT CONTEXT  (loaded from BHAVAI.md)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{memory}\n"
    )

def _fmt_args(args: dict) -> str:
    """Short display of tool args — truncates long content values."""
    if not isinstance(args, dict):
        return str(args)
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            parts.append(f'{k}=<{len(sv)} chars>')
        else:
            parts.append(f'{k}="{sv}"')
    return ", ".join(parts)


def _notify_safe(title: str, message: str) -> None:
    """Send desktop notification, but never crash if plyer fails."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="BhavAI",
            timeout=10,
        )
    except Exception:
        pass  # Notification failure should never block agent execution


# ─────────────────────────────────────────────────────────────────────────────
# Unified ReAct Loop (shared by plan + autonomous modes)
# ─────────────────────────────────────────────────────────────────────────────


def _run_agent_loop(
    user_input:       str,
    memory:           ConversationMemory,
    current_mode:     str,
    task_prompt:      str,
    max_steps:        int     = 30,
    console:          Console = None,
    require_approval: bool    = True,
    planner_state     = None,
) -> str:
    """
    Core ReAct (Reason → Act → Observe) loop used by both plan and autonomous modes.

    Parameters
    ----------
    user_input       : Original user request.
    memory           : Conversation memory.
    current_mode     : "plan" or "agent".
    task_prompt      : The formatted task prompt to send to the LLM.
    max_steps        : Maximum ReAct iterations.
    console          : Rich Console for output.
    require_approval : If True, ask y/n for mutating tools only.
                       If False, auto-approve all tools (read-only always auto-approved).
    planner_state    : Optional PlannerState for tracking step completion.
    """
    memory.add_message("user", task_prompt)

    step_count            = 0
    consecutive_json_errs = 0
    calls = 0

    while step_count < max_steps:
        step_count += 1
        logger.info("ReAct step %d/%d", step_count, max_steps)

        folder_tree   = get_folder_tree_string(CWD)
        project_context_block = _build_project_context_block(CWD)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            cwd=str(CWD),
            project_context_block=project_context_block,
            folder_tree=folder_tree,
            skills_block=discover_skills_from_dot_bhavai(CWD),
            token_budget_block=_token_budget_block(),
        )

        raw_response = ""
        with ShimmerStatus("Thinking…", color="blue"):
            try:
                messages     = memory.get_messages(system_prompt)
                raw_response = query_llm_with_continuation(messages, calls=calls % 4)
            except Exception as exc:
                err = f"LLM Error: {exc}"
                console.print(f"[bold red]{err}[/bold red]")
                logger.error(err)
                return err

        if not raw_response:
            err = "LLM returned an empty response. Please try again."
            console.print(f"[bold red]{err}[/bold red]")
            logger.error(err)
            return err

        try:
            parsed = parse_llm_json(raw_response)
            consecutive_json_errs = 0
        except ValueError as exc:
            consecutive_json_errs += 1
            explanation = str(exc)
            console.print(
                f"[bold red]JSON Parse Error "
                f"({consecutive_json_errs}/3):[/bold red] {explanation}"
            )
            logger.warning("Malformed JSON step %d: %r", step_count, raw_response[:300])

            if consecutive_json_errs >= 3:
                msg = ("Aborting: 3 consecutive JSON errors. "
                       "Try a simpler task or break it into smaller steps.")
                console.print(f"[bold red]{msg}[/bold red]")
                return msg

            memory.add_message("assistant", raw_response)
            memory.add_message(
                "user",
                f"ERROR: Your response could not be parsed as JSON.\n"
                f"Reason: {explanation}\n\n"
                + (
                    "This almost always means your response was cut off at the 4096-token limit.\n"
                    "ACTION REQUIRED:\n"
                    "  • Do NOT retry the same large write_file call.\n"
                    "  • Use append_chunk instead with ≤50 lines per chunk.\n"
                    "  • First chunk: append_chunk path=... chunk='<lines 1-50>' done=false\n"
                    "  • Continue until the file is complete, then set done=true.\n"
                    if provider_needs_chunking() else
                    "Check that the JSON structure is valid and complete — "
                    "no missing braces, quotes, or commas.\n"
                )
                + "Reply with a valid JSON object following the response schema."
            )
            continue

        thought   = parsed.get("thought", "")
        tool_name = parsed.get("tool_name", "")
        tool_args = parsed.get("tool_args", {})

        if thought:
            console.print(Panel(
                f"[dim italic]{thought}[/dim italic]",
                title="[bold]💭 BhavAI Thought[/bold]",
                title_align="left",
                border_style="dim",
            ))

        if not tool_name:
            memory.add_message("assistant", raw_response)
            memory.add_message("user",
                "Error: 'tool_name' is missing from your JSON. "
                "Please include it in your next response.")
            continue

        if tool_name == "final_answer":
            answer = tool_args.get("answer", "Task complete.")
            console.print("\n[bold green]✅ BhavAI Final Answer:[/bold green]")
            console.print(answer)
            console.print()
            memory.add_message("assistant", raw_response)

            # Mark plan as completed if we have planner state
            if planner_state:
                try:
                    from bhavai.planner import set_plan_status
                    set_plan_status(planner_state, "completed")
                except Exception:
                    pass

            return answer

        if tool_name in TOOL_DISPATCH:
            tool_func    = TOOL_DISPATCH[tool_name]
            # print()
            # print(tool_args)
            # print()
            args_display = _fmt_args(tool_args)

            # print()
            # print(args_display)
            # print()

            # ── Approval logic ──────────────────────────────────────────
            is_mutating = tool_name in MUTATING_TOOLS
            needs_approval = require_approval and is_mutating

            if needs_approval:
                _notify_safe(
                    "BhavAI — Permission Required",
                    f"Tool: {tool_name}({args_display[:80]})"
                )
                console.print(
                    f"\n[bold yellow]⚡ Run [green]{tool_name}[/green]"
                    f"({tool_args['command']})? (y/n/exit): [/bold yellow]",
                    end=""
                )
                user_answer = console.input("").strip().lower()

                if user_answer == "n":
                    result = f"User declined to run '{tool_name}'. Skipped."
                    console.print(f"[yellow]✗ Skipped {tool_name} (user declined)[/yellow]")
                    memory.add_message("assistant", raw_response)
                    memory.add_message("system", f"Observation from {tool_name}:\n{result}")
                    calls += 1
                    continue

                if user_answer == "exit":
                    return "Agent loop exited by user."

            # ── Execute tool ────────────────────────────────────────────
            with console.status(
                f"[bold blue][TOOL][/bold blue] "
                f"[bold green]{tool_name}[/bold green]({args_display})…",
                spinner="dots"
            ):
                try:
                    result = tool_func(**tool_args) if isinstance(tool_args, dict) else tool_func()
                except Exception as exc:
                    result = f"Tool error — {tool_name}: {exc}"
                    logger.error("Tool crash %s: %s", tool_name, exc)
        else:
            result = (f"Error: Unknown tool '{tool_name}'. "
                      f"Available: {list(TOOL_DISPATCH.keys())}")
            logger.warning("Unknown tool: %s", tool_name)

        text_to_be_displayed_inside_console = result[:100]
        console.print(Panel(
            str(text_to_be_displayed_inside_console),
            title=f"[bold]🔍 Observation — {tool_name}[/bold] ",
            title_align="left",
            border_style="blue",
        ))

        memory.add_message("assistant", raw_response)
        memory.add_message("system", f"Observation from {tool_name}:\n{result}")

        calls = calls + 1

    timeout_msg = (f"ReAct loop hit {max_steps}-step limit. "
                   "Task may be incomplete — try a more specific request.")
    console.print(f"[bold red]⚠  {timeout_msg}[/bold red]")
    return timeout_msg


# ─────────────────────────────────────────────────────────────────────────────
# Public Entry Points
# ─────────────────────────────────────────────────────────────────────────────


def run_agent_loop_plan(
    user_input:   str,
    memory:       ConversationMemory,
    current_mode: str,
    plan_steps    = None,
    planner_state = None,
    max_steps:    int  = 30,
    console:      Console = None,
) -> str:
    """
    Plan mode entry point. Accepts either a PlannerState (rich) or list of step strings (legacy).

    Builds a detailed task prompt with the approved plan steps and executes with
    per-mutating-tool approval.
    """
    # Build the task prompt from the plan
    if planner_state is not None:
        # Rich plan from deep planner
        from bhavai.planner import set_plan_status
        set_plan_status(planner_state, "in_progress")

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
    elif plan_steps:
        # Legacy flat list of step strings
        steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps))
        task_prompt = (
            f"Task: {user_input}\n\n"
            f"Approved plan:\n{steps_str}\n\n"
            f"{_chunk_reminder_suffix()}"
        )
    else:
        task_prompt = user_input

    return _run_agent_loop(
        user_input=user_input,
        memory=memory,
        current_mode=current_mode,
        task_prompt=task_prompt,
        max_steps=max_steps,
        console=console,
        require_approval=True,
        planner_state=planner_state,
    )


def run_agent_loop_autonomous(
    user_input:   str,
    memory:       ConversationMemory,
    current_mode: str,
    plan_steps:   list = None,
    max_steps:    int  = 30,
    console:      Console = None,
) -> str:
    """
    Autonomous mode entry point. Executes without per-tool approval
    (mutating tools still prompt if console supports it).
    """
    task_prompt = user_input
    if plan_steps:
        steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps))
        task_prompt = (
            f"Task: {user_input}\n\n"
            f"Approved plan:\n{steps_str}\n\n"
            f"{_chunk_reminder_suffix()}"
        )

    return _run_agent_loop(
        user_input=user_input,
        memory=memory,
        current_mode=current_mode,
        task_prompt=task_prompt,
        max_steps=max_steps,
        console=console,
        require_approval=False,
    )