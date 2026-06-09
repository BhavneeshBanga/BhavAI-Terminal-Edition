import json
import re
from rich.console import Console
from rich.panel import Panel
from bhavai.config import CWD, logger
from bhavai.context import get_folder_tree_string
from bhavai.llm import query_llm
from bhavai.memory import ConversationMemory
from bhavai.tools import TOOL_DISPATCH

# Prompt templates
SYSTEM_PROMPT_TEMPLATE = """You are BhavAI, a personal AI agent running inside the terminal.
You are activated in this folder: {cwd}

Current folder structure:
{folder_tree}

You have access to the following tools:
- list_folder:
    description: List the file and folder tree structure of a directory path relative to CWD.
    parameters: {{"path": "string (default: '.')"}}
- read_file:
    description: Read the content of a file at the given path relative to CWD.
    parameters: {{"path": "string"}}
- write_file:
    description: Create a new file or overwrite an existing file with the given content.
    parameters: {{"path": "string", "content": "string"}}
- update_file:
    description: Append or partially update content in an existing file.
    parameters: {{"path": "string", "content": "string", "mode": "append|overwrite"}}
- run_command:
    description: Run a safe, read-only shell command (e.g., git status, ls, cat). Must not include any destructive commands.
    parameters: {{"command": "string"}}
- final_answer:
    description: Return the final response to the user when the task is complete.
    parameters: {{"answer": "string"}}

Rules you must always follow:
1. You can NEVER delete files or directories. If asked to delete, refuse and explain why.
2. Always work within the current working directory only. Path sandboxing restricts you to {cwd}.
3. The command blocklist prevents running: rm, rmdir, del, unlink, shutil.rmtree, os.remove, format, mkfs, drop table.
4. You must execute tasks step-by-step, explaining your progress.
5. Use the final_answer tool when your task is complete.
6. You MUST respond ONLY in a strict JSON format. Do not write any text outside the JSON object. Do not include markdown code block formatting (like ```json). Just the raw JSON object.

Response Schema:
{{
  "thought": "your step-by-step reasoning or thought",
  "tool_name": "name of the tool to execute",
  "tool_args": {{
    "arg_name": "arg_value"
  }}
}}
"""

def clean_json_text(text: str) -> str:
    """
    Cleans raw LLM response text by removing <think> tags,
    extracting the JSON block, and escaping invalid control characters
    (newlines, carriage returns, tabs) inside string literals.
    """
    # Remove <think>...</think> tags if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    
    # Check for markdown code block wrappers (e.g. ```json ... ```)
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
            
    # Try to find first '{' and last '}' if structure isn't perfect
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]
        
    # Escape literal control characters inside JSON string values
    result = []
    in_string = False
    escaped = False
    
    for char in text:
        if char == '"' and not escaped:
            in_string = not in_string
            result.append(char)
        elif in_string:
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            elif char == '\\':
                escaped = not escaped
                result.append(char)
            else:
                escaped = False
                result.append(char)
        else:
            if char == '\\':
                escaped = not escaped
                result.append(char)
            else:
                escaped = False
                result.append(char)
                
    return "".join(result)

def parse_llm_json(raw_text: str) -> dict:
    """
    Cleans and parses a JSON string returned by the LLM.
    Handles standard text wrappers, markdown code block backticks, and partial JSON strings.
    """
    try:
        cleaned = clean_json_text(raw_text)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failure: %s on input: %r", e, raw_text)
        raise ValueError(
            f"Invalid JSON returned by LLM. Please output raw JSON format. "
            f"Error details: {e.msg} at line {e.lineno} col {e.colno}."
        )

def format_args(args: dict) -> str:
    """Formats argument dictionary into a clean string representation."""
    if not isinstance(args, dict):
        return str(args)
    return ", ".join(f'{k}="{v}"' for k, v in args.items())

def run_agent_loop(
    user_input: str,
    memory: ConversationMemory,
    current_mode: str,
    plan_steps: list = None,
    max_steps: int = 15,
    console: Console = None
) -> str:
    """
    Executes the main ReAct loop.
    Iteratively queries LLM, executes parsed tools, and feeds observations back until completion.
    """
    if console is None:
        console = Console()
        
    # Prime prompt context with approved plan steps if in plan mode
    task_prompt = user_input
    if plan_steps:
        steps_str = "\n".join(f"- {step}" for step in plan_steps)
        task_prompt = (
            f"Task: {user_input}\n\n"
            f"Approved Step-by-Step Plan to follow:\n{steps_str}"
        )
        
    memory.add_message("user", task_prompt)
    
    step_count = 0
    consecutive_json_errors = 0
    
    while step_count < max_steps:
        step_count += 1
        logger.info("Starting ReAct Step %d/%d", step_count, max_steps)
        
        # Build system prompt dynamically with the current folder context tree
        folder_tree = get_folder_tree_string(CWD)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            cwd=str(CWD),
            folder_tree=folder_tree
        )
        
        # Query LLM
        with console.status("[bold blue]Thinking...", spinner="dots"):
            try:
                messages = memory.get_messages(system_prompt)
                raw_response = query_llm(messages)
            except Exception as e:
                error_msg = f"LLM Query Error: {e}"
                console.print(f"[bold red]Error:[/bold red] {error_msg}")
                logger.error(error_msg)
                return error_msg
                
        # Attempt to parse response
        try:
            parsed = parse_llm_json(raw_response)
            consecutive_json_errors = 0  # reset on success
        except ValueError as e:
            consecutive_json_errors += 1
            error_explanation = str(e)
            
            console.print(f"[bold red]JSON Parse Error:[/bold red] {error_explanation}")
            logger.warning("Malformed JSON response: %s", raw_response)
            
            if consecutive_json_errors >= 3:
                fail_msg = "Aborting due to consecutive malformed JSON responses from LLM."
                console.print(f"[bold red]Error:[/bold red] {fail_msg}")
                return fail_msg
                
            # Feed error back to memory to let the model recover
            memory.add_message("assistant", raw_response)
            memory.add_message(
                "user",
                f"Error: Your last response was invalid JSON. Please correct it. "
                f"Error details: {error_explanation}"
            )
            continue
            
        # Extract fields
        thought = parsed.get("thought", "Thinking...")
        tool_name = parsed.get("tool_name")
        tool_args = parsed.get("tool_args", {})
        
        # Print thoughts
        console.print(Panel(
            f"[dim italic]{thought}[/dim italic]",
            title="BhavAI Thought",
            title_align="left",
            border_style="dim"
        ))
        
        if not tool_name:
            # Missing tool name, ask model to try again
            memory.add_message("assistant", raw_response)
            memory.add_message("user", "Error: 'tool_name' is missing in your JSON response.")
            continue
            
        # Handle final answer
        if tool_name == "final_answer":
            answer = tool_args.get("answer", "Task complete.")
            console.print(f"\n[bold green]BhavAI Final Answer:[/bold green]")
            console.print(answer)
            console.print()
            # Add to memory for ongoing context
            memory.add_message("assistant", raw_response)
            return answer
            
        # Route and execute tool
        if tool_name in TOOL_DISPATCH:
            tool_func = TOOL_DISPATCH[tool_name]
            args_str = format_args(tool_args)
            
            # Show TOOL spinner status
            console_msg = f"[bold blue]\[TOOL][/bold blue] Running [bold green]{tool_name}[/bold green]({args_str})..."
            with console.status(console_msg, spinner="dots"):
                try:
                    # Resolve keyword arguments matching parameters
                    if isinstance(tool_args, dict):
                        result = tool_func(**tool_args)
                    else:
                        result = tool_func()
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"
                    logger.error("Tool crash on %s: %s", tool_name, e)
        else:
            result = f"Error: Unknown tool '{tool_name}'."
            logger.warning("Model requested unknown tool: %s", tool_name)
            
        # Print observation panel
        console.print(Panel(
            result,
            title=f"Observation - {tool_name}",
            title_align="left",
            border_style="blue"
        ))
        
        # Add conversation step to memory
        memory.add_message("assistant", raw_response)
        memory.add_message("user", f"Observation from {tool_name}:\n{result}")
        
    timeout_msg = "ReAct loop reached maximum step limit before completion."
    console.print(f"[bold red]Error:[/bold red] {timeout_msg}")
    return timeout_msg
