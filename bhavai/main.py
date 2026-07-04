"""
the main entry point of this project 

run 
```
bhav wake up 
```
in terminal to use this project
"""
import threading
import click
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
# from rich.prompt import Prompt

from bhavai.config import get_config_summary, CWD, logger
from bhavai.context import get_folder_tree_string
from bhavai.memory import ConversationMemory
from bhavai.modes import AgentMode, prompt_and_confirm_plan
from bhavai.agent import run_agent_loop

import getpass
import time

from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import prompt
from prompt_toolkit import PromptSession


from bhavai.scripts.initialize_markdown import generate_bhavai_md
from bhavai.updater.updates import show_update_message

import random

lists = [
    "💭Do you know run /save command can save your entire session into .bhavai/memories/<NAME>.md",
    "💭Do you know run /init command make BHAVAI.md file specific to this folder",
    "💭Do you know run /rename command rename the session",
    "💭Do you know run ! <COMMAND> can be used for running bash commands",
    "💭Do you know run /compact will summarize the entire conversation to free up context window",

        ]

do_you_know = random.choice(lists)



console = Console()

# @click.group(invoke_without_command=True)
# @click.group(
#     invoke_without_command=True,
#     help="""
# 🚀 BhavAI — Personal Terminal AI Agent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 📝 Session Commands
#   /rename <session_name>   Rename the current session
#   /save                    Save the current conversation

# 💻 Shell Commands
#   ! <command>              Run a terminal/bash command
#                            Example: ! git status

# ⚡ Agent Commands
#   bhav wake up             Start BhavAI

# 📚 Examples
#   bhav wake up
#   bhav --help
#   /rename My_Project
#   /save
#   ! git status
#   ! python app.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# """
# )
# @click.pass_context
# def main(ctx):
#     """BhavAI - A production-ready, personal AI agent in your terminal."""
#     if ctx.invoked_subcommand is None:
#         console.print("[bold red]Error:[/bold red] Missing command. Use [green]bhav wake up[/green] to activate the agent.")
#         sys.exit(1)
@click.group(invoke_without_command=True, add_help_option=False)
@click.option("--help", "show_help", is_flag=True)
@click.pass_context
def main(ctx, show_help):
    if show_help:
        console.print(
            Panel.fit(
                """
[bold cyan]🚀 BhavAI — Personal Terminal AI Agent[/bold cyan]

[yellow]📝 Session Commands[/yellow]
  [green]/rename <session_name>[/green]
      Rename the current session

  [green]/save[/green]
      Save the current conversation

[yellow]💻 Shell Commands[/yellow]
  [green]! <command>[/green]
      Run a terminal command
      Example: [cyan]! git status[/cyan]

[yellow]⚡ Agent Commands[/yellow]
  [green]bhav wake up[/green]
      Start BhavAI

[yellow]📚 Examples[/yellow]
  [cyan]bhav wake up[/cyan]
  [cyan]bhav --help[/cyan]
  [cyan]/rename My_Project[/cyan]
  [cyan]! python app.py[/cyan]
  [cyan]/push[/cyan]

[yellow]🥷  Slash Commands[/yellow]
  [cyan]/{COMMANDL_NAME}[/cyan]
  
""",
                title="BhavAI Help",
                border_style="bright_blue",
            )
        )
        ctx.exit()

    if ctx.invoked_subcommand is None:
        console.print(
            "[bold red]Error:[/bold red] Missing command. "
            "Use [green]bhav wake up[/green] to activate the agent."
        )
        ctx.exit(1)

#-------------------------------------------------------------------------------------------------------------------

@main.command()
@click.argument("action", default="up")
def wake(action):
    """Activates the agent in the current working directory."""
    if action != "up":
        console.print(f"[bold red]Error:[/bold red] Invalid action '{action}'. Did you mean [green]bhav wake up[/green]?")
        sys.exit(1)

    
        
    # Load configuration
    cfg = get_config_summary()
    
    # Check for API key
    if not cfg["API_KEY_PRESENT"]:
        console.print(Panel(
            "[bold red]API KEY MISSING[/bold red]\n\n"
            "Please create a [bold].env[/bold] file in this folder or set the [bold]SARVAM_API_KEY[/bold] environment variable.\n"
            "Visit https://dashboard.sarvam.ai/ to get your subscription key.",
            title="BhavAI - Setup Required",
            border_style="red"
        ))
        sys.exit(1)
        
    # Print beautiful activation banner
    import time
    R   = "\033[0m"
    YEL = "\033[1;93m"
    BOLD= "\033[1m"
    YEL = "\033[1;93m"
    GOLD= "\033[33m"

    def typewrite(text, delay=0.015, color=""):
        for ch in text:
            sys.stdout.write(color + ch + R)
            sys.stdout.flush()
            time.sleep(delay)
        print()
    import os
    def clear():
        os.system("cls" if os.name == "nt" else "clear")

    clear()
    print(YEL + "▄" * 58 + R)
    print()
    # logo = [
    # r" ██████╗ ██╗  ██╗ █████╗ ██╗   ██╗ █████╗ ██╗    ████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗",
    # r" ██╔══██╗██║  ██║██╔══██╗██║   ██║██╔══██╗██║       ██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║",
    # r" ██████╔╝███████║███████║██║   ██║███████║██║       ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║",
    # r" ██╔══██╗██╔══██║██╔══██║╚██╗ ██╔╝██╔══██║██║       ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║",
    # r" ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║  ██║██║       ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║███████╗",
    # r" ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝       ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝",
    # ]
    logo = [
        r" ██████╗ ██╗  ██╗ █████╗ ██╗   ██╗ █████╗ ██╗    ████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗        █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
        r" ██╔══██╗██║  ██║██╔══██╗██║   ██║██╔══██╗██║       ██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║       ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
        r" ██████╔╝███████║███████║██║   ██║███████║██║       ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║       ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
        r" ██╔══██╗██╔══██║██╔══██║╚██╗ ██╔╝██╔══██║██║       ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║       ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
        r" ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║  ██║██║       ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██████╗   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
        r" ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝       ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═════╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
    ]
    for line in logo:
        print(GOLD + BOLD + line + R)
    print()
    username = getpass.getuser()
    typewrite(f"  ⚡  Terminal Edition — {username} ke liye  ⚡", delay=0.022, color=GOLD + BOLD)
    print(YEL + "▀" * 58 + R)
    print()

    banner_text = (
        f"🚀[bold green]BhavAI Activated Successfully![/bold green]\n\n"
        f"📍  [bold]Location:[/bold] {cfg['CWD']}\n"
        f"⚙️  [bold]Model:[/bold] {cfg['MODEL']}\n"
        f"🛡️  [bold]Initial Mode:[/bold] [bold cyan]Plan Mode[/bold cyan] (Default)\n"
        f"📝 [bold]Logs Path:[/bold] {cfg['LOG_FILE']}\n"
        # f"{do_you_know}\n\n"
        f"[dim]Type your requests below. Use 'mode agent' or 'mode plan' to toggle modes, 'exit' or 'quit' to close.[/dim]"
    )
    console.print(Panel(banner_text, title="BhavAI Personal Terminal Agent", border_style="green"))
    
    # Print initial folder tree
    console.print("\n[bold]Current Directory Structure:[/bold]")
    try:
        tree_str = get_folder_tree_string(CWD)
        console.print(tree_str)
        console.print("")
        show_update_message(console)
        console.print("")
        console.print(do_you_know)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not build folder tree: {e}[/yellow]")
    console.print()
    
    # Initialize session state
    current_mode = AgentMode.PLAN
    memory = ConversationMemory()

    from prompt_toolkit.formatted_text import HTML

    session = PromptSession()



    def get_prompt_text():
        """
        Live prompt that re-evaluate for every key stroke.
        """
        buf = session.default_buffer.text
        if buf.startswith("!"):
            return HTML('<ansired><b>(bash)</b></ansired> > ')
        if current_mode == AgentMode.PLAN:
            return HTML('<ansicyan><b>(plan)</b></ansicyan> > ')
        else:
            return HTML('<ansiyellow><b>(agent)</b></ansiyellow> > ')
        

    SESSION_NAME = "NEW_CHAT_" + str(int(time.time()))


    # Interactive REPL Loop
    while True:
        try:
            # Styled prompt input
            mode_color = "cyan" if current_mode == AgentMode.PLAN else "yellow"
            prompt_label = f"[bold {mode_color}]({current_mode})[/bold {mode_color}] > "
            user_input = session.prompt(get_prompt_text).strip()
            # user_input = Prompt.ask(prompt_label).strip()
            
            if not user_input:
                continue

            # if user_input.startswith("!"):
            #     prompt_label = "[bold red](bash)[/bold red] > "

            # from textual.widgets import Header, Footer, Input, RichLog
            # log = query_one("#log", RichLog)
            low = user_input.lower()


            ## ! to run bash commands
            import subprocess
            import os

            if user_input.startswith("!"):
                command = user_input[1:].strip()

                if not command:
                    console.print("[red]No command provided.[/red]")
                    continue

                try:
                    subprocess.run(
                        command,
                        shell=True,
                        cwd=CWD,      # current project directory
                        check=False
                    )
                except Exception as e:
                    console.print(f"[red]Command failed:[/red] {e}")

                continue


            ## To rename the session
            if user_input.startswith("/rename"):
                conversation_name = user_input.replace("/rename", "")
                SESSION_NAME = conversation_name + "_" + str(int(time.time()))
                console.print(f"Conversation renamed to {conversation_name}")
                continue
                # print((result[1:]))


            if low == "/save":
                # save_path = CWD /  f"{SESSION_NAME}.md"
                memories_dir = CWD / ".bhavai" / "memories"
                memories_dir.mkdir(parents=True, exist_ok=True)

                save_path = memories_dir / f"{SESSION_NAME}.md"
                try:
                    # self.memory.save_to_file(save_path)
                    memory.save_to_file(save_path)
                    # log.write(f"[green]✓ Conversation saved to {save_path}[/green]")
                    console.print(f"[green]✓ Conversation saved to {save_path}[/green]")
                except Exception as e:
                    # log.write(f"[red]Failed to save conversation: {e}[/red]")
                    console.print(f"[red]Failed to save conversation: {e}[/red]")
                
                continue
            
            if low == "/init":
                with console.status("[bold yellow]Generating BhavAI.md[/bold yellow]", spinner="dots"):
                
                    try:
                        path = generate_bhavai_md(CWD)
                        # stop_event.set()
                        console.print(f"[green]✓ Created {path}[/green]")
                    except Exception as e:
                        # stop_event.set()
                        console.print(f"[red]Failed to generate BHAVAI.md: {e}[/red]")






            ## COMMANDS
            is_command = False

            if user_input.startswith("/"):
                command_name = user_input[1:].strip()
                command_path = CWD / ".bhavai" / "commands" / f"{command_name}.md"
                if command_path.exists():
                    user_input = command_path.read_text(encoding="utf-8").strip()
                    is_command = True
                    if is_command:
                        console.print(Panel(
                            user_input,
                            title=f"[bold cyan]📄 /{command_name}.md[/bold cyan]",
                            border_style="cyan"
                        ))
                    console.print(f"[cyan]▶ Running command:[/cyan] [bold]/{command_name}[/bold]")
                else:
                    console.print(f"[bold red]✗ Error:[/bold red] Command '/{command_name}' Doesn't Exist.")
                    continue




                
            # Mode switching command
            if not is_command and user_input.lower() == "mode agent":
                current_mode = AgentMode.AGENT
                console.print("[yellow]Switched to Agent Mode (Tasks will execute autonomously).[/yellow]")
                continue

            elif not is_command and user_input.lower() == "mode plan":
                current_mode = AgentMode.PLAN
                console.print("[cyan]Switched to Plan Mode (Tasks will show a checklist plan first).[/cyan]")
                continue
                
            # Exit conditions
            if not is_command and user_input.lower() in ("exit", "quit"):
                console.print("[green]Goodbye from BhavAI! Waking down...[/green]")
                break
                
            # Task Execution
            if is_command or current_mode == AgentMode.PLAN:
                # 1. Generate and confirm plan
                folder_tree = get_folder_tree_string(CWD)
                should_proceed, plan_steps = prompt_and_confirm_plan(user_input, folder_tree, console)
                
                # 2. Run agent loop if approved
                if should_proceed:
                    console.print("[bold green]Plan approved. Executing step-by-step...[/bold green]")
                    run_agent_loop(
                        user_input=user_input,
                        memory=memory,
                        current_mode=current_mode,
                        plan_steps=plan_steps,
                        console=console
                    )
            else: # Agent Mode (autonomous execution)
                console.print("[bold yellow]Executing task autonomously...[/bold yellow]")
                run_agent_loop(
                    user_input=user_input,
                    memory=memory,
                    current_mode=current_mode,
                    console=console
                )
                
            console.print() # Print trailing spacing after task complete
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Task interrupted by user. Returning to prompt...[/yellow]")
            logger.info("REPL session task execution interrupted via KeyboardInterrupt.")
        except Exception as e:
            console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
            logger.exception("REPL session encountered unexpected error: %s", e)


@main.command()
def dev():
    print("Opening developer dashboard...")




if __name__ == "__main__":
    main()

#-------------------------------------------------------------------------------------------------------------------


# uncomment bottom code and commend upper code block to change ui
# from bhavai.tui import BhavAI



# @main.command()
# @click.argument("action", default="up")
# def wake(action):
#     """Activates the agent in the current working directory."""
#     if action != "up":
#         console.print(f"[bold red]Error:[/bold red] Invalid action '{action}'. Did you mean [green]bhav wake up[/green]?")
#         sys.exit(1)

#     # Load configuration
#     cfg = get_config_summary()

#     # Check for API key
#     if not cfg["API_KEY_PRESENT"]:
#         console.print(Panel(
#             "[bold red]API KEY MISSING[/bold red]\n\n"
#             "Please create a [bold].env[/bold] file in this folder or set the [bold]SARVAM_API_KEY[/bold] environment variable.\n"
#             "Visit https://dashboard.sarvam.ai/ to get your subscription key.",
#             title="BhavAI - Setup Required",
#             border_style="red"
#         ))
#         sys.exit(1)

#     from bhavai.tui import BhavAI
#     BhavAI().run()