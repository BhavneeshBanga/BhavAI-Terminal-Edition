# import json
# import re
# from rich.console import Console
# from rich.panel import Panel
# from rich.prompt import Prompt
# from bhavai.config import logger
# from bhavai.llm import query_llm

# class AgentMode:
#     PLAN = "plan"
#     AGENT = "agent"

# def generate_plan(user_input: str, folder_tree: str, feedback: str = None) -> list:
#     """
#     Queries Sarvam-105B to generate a step-by-step plan for the user task.
#     Supports feeding back refinement instructions.
#     """
#     system_prompt = (
#         "You are BhavAI, a planning assistant. Your job is to break down the user's task into a sequential, "
#         "numbered plan of action. Do not run any tools yet. Show what tools you intend to use at each step.\n\n"
#         "You MUST reply in a strict JSON format containing a single key 'plan' which is a list of step strings. "
#         "Do not include any text, headers, or markdown formatting before or after the JSON payload.\n"
#         "Example output:\n"
#         "{\n"
#         '  "plan": [\n'
#         '    "Read README.md using read_file to check existing installation instructions",\n'
#         '    "Add Installation section using update_file with pip install instructions"\n'
#         "  ]\n"
#         "}"
#     )
    
#     user_prompt = f"Current folder structure:\n{folder_tree}\n\nUser task: {user_input}"
#     if feedback:
#         user_prompt += f"\n\nUser feedback to adjust the plan: {feedback}"
        
#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user", "content": user_prompt}
#     ]
#     raw_response = ''
    
#     try:
#         raw_response = query_llm(messages)
#         # Parse JSON from response
#         # Strip markdown formatting just in case
#         clean_json = raw_response.strip()
#         if clean_json.startswith("```"):
#             # Try to extract content inside code block
#             match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_json, re.DOTALL)
#             if match:
#                 clean_json = match.group(1).strip()
                
#         # If no markdown blocks, find first { and last }
#         if not (clean_json.startswith("{") and clean_json.endswith("}")):
#             start_idx = clean_json.find("{")
#             end_idx = clean_json.rfind("}")
#             if start_idx != -1 and end_idx != -1:
#                 clean_json = clean_json[start_idx:end_idx+1]
                
#         plan_data = json.loads(clean_json)
#         return plan_data.get("plan", [f"Execute user request: {user_input}"])
#     except Exception as e:
#         logger.error("Failed to generate or parse plan: %s. Raw response: %s", e, raw_response)
#         # Fallback plan if LLM parsing fails
#         return [
#             f"Analyze folder tree and context.",
#             f"Execute requested task: {user_input}"
#         ]



# ## comment kar rha hoon 
# # def prompt_and_confirm_plan(user_input: str, folder_tree: str, console: Console) -> tuple[bool, list]:
# #     """
# #     Shows the step-by-step plan to the user in the terminal and waits for approval.
# #     Allows user to confirm (y), cancel (n), or input feedback to regenerate the plan.
# #     Returns (should_proceed, plan_steps).
# #     """
# #     feedback = None
# #     while True:
# #         with console.status("[bold blue]Generating plan...", spinner="dots"):
# #             plan_steps = generate_plan(user_input, folder_tree, feedback)
            
# #         console.print("\n[bold cyan]Here's my plan:[/bold cyan]")
# #         for idx, step in enumerate(plan_steps, 1):
# #             console.print(f" [bold cyan]{idx}.[/bold cyan] {step}")
# #         console.print()
        
# #         ans = Prompt.ask(
# #             "[bold yellow]Proceed?[/bold yellow] ([green]y[/green] to proceed, [red]n[/red] to cancel, or type feedback to edit the plan)"
# #         ).strip()
        
# #         if ans.lower() == 'y':
# #             return True, plan_steps
# #         elif ans.lower() in ('n', 'no', ''):
# #             console.print("[yellow]Plan execution cancelled.[/yellow]")
# #             return False, []
# #         else:
# #             # if  user provided feedback to adjust the plan
# #             feedback = ans
# #             console.print(f"[blue]Updating plan based on feedback: '{feedback}'...[/blue]")

# ## erro de rha hai ui update mai 
# ## claude ne bola uncommment karne ko

# def prompt_and_confirm_plan(user_input: str, folder_tree: str, console: Console, feedback: str = None) -> list:
#     """
#     Generates and displays the plan. Does NOT block for confirmation —
#     the TUI's Input box handles that via its own state machine.
#     Returns the plan_steps list.
#     """
#     with console.status("[bold blue]Generating plan...", spinner="dots"):
#         plan_steps = generate_plan(user_input, folder_tree, feedback)

#     console.print("\n[bold cyan]Here's my plan:[/bold cyan]")
#     for idx, step in enumerate(plan_steps, 1):
#         console.print(f" [bold cyan]{idx}.[/bold cyan] {step}")
#     console.print()
#     console.print(
#         "[bold yellow]Proceed?[/bold yellow] ([green]y[/green] to proceed, "
#         "[red]n[/red] to cancel, or type feedback to edit the plan)"
#     )
#     return plan_steps














## below code is generted by kimi k - 2.6

import json
import re
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from bhavai.config import logger
from bhavai.llm import query_llm


class AgentMode:
    """Enumeration of available agent execution modes."""
    PLAN = "plan"
    AGENT = "agent"


class PlanGenerationError(Exception):
    """Raised when plan generation or parsing fails."""
    pass


def _extract_json_from_markdown(text: str) -> str:
    """
    Extract JSON payload from a markdown-formatted string.

    Handles three cases:
      1. Code block wrapped in ```json ... ```
      2. Code block wrapped in ``` ... ```
      3. Raw JSON object starting with { and ending with }

    Args:
        text: Raw LLM response string.

    Returns:
        Cleaned JSON string.

    Raises:
        ValueError: If no valid JSON object is found.
    """
    text = text.strip()

    # Case 1 & 2: Markdown code blocks
    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    # Case 3: Raw JSON — find outermost braces
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        raise ValueError("No JSON object found in response.")

    return text[start_idx:end_idx + 1]


def generate_plan(
    user_input: str,
    folder_tree: str,
    feedback: Optional[str] = None
) -> list[str]:
    """
    Query Sarvam-105B to generate a step-by-step plan for the user's task.

    Supports iterative refinement by passing previous feedback.

    Args:
        user_input: The task description from the user.
        folder_tree: String representation of the current directory structure.
        feedback: Optional refinement instructions from a previous iteration.

    Returns:
        A list of plan step strings.

    Raises:
        PlanGenerationError: If the LLM response cannot be parsed into a valid plan.
    """
    system_prompt = (
        "You are BhavAI, a planning assistant. Your job is to break down the user's task "
        "into a sequential, numbered plan of action. Do not run any tools yet. Show what "
        "tools you intend to use at each step.\n\n"
        "You MUST reply in a strict JSON format containing a single key 'plan' which is a "
        "list of step strings. Do not include any text, headers, or markdown formatting "
        "before or after the JSON payload.\n"
        "Example output:\n"
        '{\n  "plan": [\n    "Read README.md using read_file to check existing installation instructions",\n    "Add Installation section using update_file with pip install instructions"\n  ]\n}'
    )

    user_prompt = f"Current folder structure:\n{folder_tree}\n\nUser task: {user_input}"
    if feedback:
        user_prompt += f"\n\nUser feedback to adjust the plan: {feedback}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    raw_response: str = ""

    try:
        raw_response = query_llm(messages)
        clean_json = _extract_json_from_markdown(raw_response)
        plan_data = json.loads(clean_json)

        plan_steps = plan_data.get("plan")
        if not isinstance(plan_steps, list):
            raise PlanGenerationError(
                f"Expected 'plan' to be a list, got {type(plan_steps).__name__}"
            )
        if not plan_steps:
            raise PlanGenerationError("Plan list is empty.")

        # Validate that all steps are strings
        for i, step in enumerate(plan_steps):
            if not isinstance(step, str):
                raise PlanGenerationError(
                    f"Plan step {i + 1} is not a string (got {type(step).__name__})"
                )

        return plan_steps

    except (json.JSONDecodeError, ValueError, PlanGenerationError) as exc:
        logger.error(
            "Failed to generate or parse plan: %s. Raw response: %s",
            exc,
            raw_response,
        )
        # Graceful fallback: return a minimal plan so the agent can still proceed
        return [
            f"Analyze folder tree and context for task: {user_input}",
            f"Execute requested task: {user_input}",
        ]
    except Exception as exc:
        # Catch-all for unexpected LLM/API errors
        logger.exception("Unexpected error during plan generation.")
        return [
            f"Analyze folder tree and context for task: {user_input}",
            f"Execute requested task: {user_input}",
        ]


def display_plan(plan_steps: list[str], console: Console) -> None:
    """
    Render the plan steps to the console in a formatted panel.

    Args:
        plan_steps: List of plan step strings.
        console: Rich Console instance for output.
    """
    console.print("\n[bold cyan]Here\'s my plan:[/bold cyan]")
    for idx, step in enumerate(plan_steps, start=1):
        console.print(f" [bold cyan]{idx}.[/bold cyan] {step}")
    console.print()


def prompt_and_confirm_plan(
    user_input: str,
    folder_tree: str,
    console: Console,
    feedback: Optional[str] = None,
) -> list[str]:
    """
    Generate and display a plan. Non-blocking — the TUI handles confirmation
    via its own state machine, so this function only produces output.

    Args:
        user_input: The task description from the user.
        folder_tree: String representation of the current directory structure.
        console: Rich Console instance for output.
        feedback: Optional refinement instructions from a previous iteration.

    Returns:
        The generated plan step strings.
    """
    with console.status("[bold blue]Generating plan...", spinner="dots"):
        plan_steps = generate_plan(user_input, folder_tree, feedback)

    display_plan(plan_steps, console)

    # Print the prompt instruction for the TUI / user
    prompt_text = Text()
    prompt_text.append("Proceed? ", style="bold yellow")
    prompt_text.append("(y", style="green")
    prompt_text.append(" to proceed, ", style="default")
    prompt_text.append("n", style="red")
    prompt_text.append(
        " to cancel, or type feedback to edit the plan)", style="default"
    )
    console.print(prompt_text)

    return plan_steps


# ---------------------------------------------------------------------------
# Deprecated / Legacy — kept for reference but not used in the TUI flow
# ---------------------------------------------------------------------------
# def _interactive_prompt_and_confirm_plan(
#     user_input: str,
#     folder_tree: str,
#     console: Console,
# ) -> tuple[bool, list[str]]:
#     """
#     [DEPRECATED] Blocking version that waits for terminal input.
#     
#     This function is no longer used because the TUI handles user input
#     through its own state machine. Kept here for reference only.
#     
#     Returns:
#         Tuple of (should_proceed: bool, plan_steps: list[str]).
#     """
#     feedback: Optional[str] = None
#     while True:
#         with console.status("[bold blue]Generating plan...", spinner="dots"):
#             plan_steps = generate_plan(user_input, folder_tree, feedback)
#         
#         display_plan(plan_steps, console)
#         
#         ans = Prompt.ask(
#             "[bold yellow]Proceed?[/bold yellow] "
#             "([green]y[/green] to proceed, [red]n[/red] to cancel, "
#             "or type feedback to edit the plan)"
#         ).strip()
#         
#         if ans.lower() == "y":
#             return True, plan_steps
#         elif ans.lower() in ("n", "no", ""):
#             console.print("[yellow]Plan execution cancelled.[/yellow]")
#             return False, []
#         else:
#             feedback = ans
#             console.print(
#                 f"[blue]Updating plan based on feedback: \'{feedback}\'...[/blue]"
#             )