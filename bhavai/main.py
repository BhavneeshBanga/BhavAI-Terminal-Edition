"""
the main entry point of this project 

run 
```
bhav wake up 
```
in terminal to use this project
"""
from __future__ import annotations


import click
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from bhavai.config import get_config_summary, CWD, logger, ensure_prompts_dir
from bhavai.context import get_folder_tree_string
from bhavai.memory import ConversationMemory
from bhavai.modes import AgentMode, prompt_and_confirm_plan
from bhavai.agent import run_agent_loop_plan, run_agent_loop_autonomous

import getpass
import time
import webbrowser
import random
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import urllib.error

from bhavai.ui.shimmer import ShimmerStatus


from prompt_toolkit.formatted_text import HTML
from prompt_toolkit import prompt
from prompt_toolkit import PromptSession


from bhavai.scripts.initialize_markdown import generate_bhavai_md
from bhavai.updater.updates import show_update_message
from bhavai.banner.bhavai_agent import print_bhavai_agent


import os
import re
import time

import json
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from bhavai.config_commands import config_group

from bhavai.helper.create_first_file_Note_from_bhavai_ import create_first_file_Note_from_bhavai

TRUST_FILE = Path.home() / ".bhavai" / "trusted_folders.json"

def _load_trusted_folders() -> list:
    if TRUST_FILE.exists():
        try:
            return json.loads(TRUST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_trusted_folder(path_str: str) -> None:
    trusted = _load_trusted_folders()
    if path_str not in trusted:
        trusted.append(path_str)
        TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRUST_FILE.write_text(json.dumps(trusted, indent=2), encoding="utf-8")


def is_folder_trusted(cwd: Path) -> bool:
    trusted = _load_trusted_folders()
    cwd_str = str(cwd.resolve())
    return any(
        cwd_str == t or cwd_str.startswith(t.rstrip("/\\") + os.sep)
        for t in trusted
    )


def _inline_arrow_menu(options: list) -> int:
    """
    Lightweight inline arrow-key menu — full screen NAHI, terminal ke normal
    flow mein render hota hai. Enter dabate hi turant selected index return
    karta hai, koi separate 'Ok' button nahi.
    Returns selected index, ya None agar Esc/Ctrl-C dabaya.
    """
    selected = {"idx": 0}
    result = {"value": None}

    def get_text():
        lines = []
        for i, opt in enumerate(options):
            if i == selected["idx"]:
                lines.append(("class:selected", f"  ● {opt}\n"))
            else:
                lines.append(("class:normal", f"    {opt}\n"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        selected["idx"] = (selected["idx"] - 1) % len(options)

    @kb.add("down")
    def _(event):
        selected["idx"] = (selected["idx"] + 1) % len(options)

    @kb.add("enter")
    def _(event):
        result["value"] = selected["idx"]
        event.app.exit()

    @kb.add("c-c")
    @kb.add("escape")
    def _(event):
        result["value"] = None
        event.app.exit()

    from prompt_toolkit.styles import Style
    style = Style.from_dict({
        "selected": "#aaaaaa bold",
        "normal": "#aaaaaa",
    })

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_text))),
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )
    app.run()
    return result["value"]


def prompt_trust_folder(console: Console, cwd: Path) -> bool:
    """
    BhavAI ka trust-check — screenshot jaisa inline box, Enter se turant confirm.
    Return True = trust ho gaya, False = 'Don't trust' ya cancel (exit).
    """
    folder_name = cwd.name
    parent_name = cwd.parent.name

    console.print(Panel(
        "[bold white]Do you trust the files in this folder?[/bold white]\n\n"
        "Trusting a folder allows BhavAI to load its local configurations,\n"
        "including custom commands, skills, and settings. These configurations\n"
        "could execute code on your behalf or change BhavAI's behavior.",
        title="[bold white]BhavAI - Trust Check[/bold white]",
        border_style="white",
        padding=(1, 2),
    ))

    options = [
        f"Trust folder ({folder_name})",
        f"Trust parent folder ({parent_name})",
        "Don't trust",
    ]

    choice = _inline_arrow_menu(options)

    if choice is None or choice == 2:
        return False

    if choice == 0:
        time.sleep(1)
        _save_trusted_folder(str(cwd.resolve()))
    elif choice == 1:
        _save_trusted_folder(str(cwd.parent.resolve()))

    return True




if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
def expand_pasted_text(text: str, paste_store: dict) -> str:
    pattern = re.compile(r"\[Pasted text #(\d+) \+\d+ lines\]")

    def _replace(match):
        idx = int(match.group(1))
        return paste_store.get(idx, match.group(0))

    return pattern.sub(_replace, text)




def collapse_bursts_for_display(text: str, bursts: list, paste_store: dict, paste_counter: dict, threshold: int = 5) -> str:
    display_text = text
    for burst_text in bursts:
        line_count = burst_text.count("\n") + 1
        if line_count > threshold and burst_text in display_text:
            paste_counter["n"] += 1
            idx = paste_counter["n"]
            paste_store[idx] = burst_text
            placeholder = f"[Pasted text #{idx} +{line_count} lines]"
            display_text = display_text.replace(burst_text, placeholder, 1)
    return display_text




lists = [
    "💭 Do you know you can insert images into your terminal",
    "💭 Do you know run /export command can export your entire session into .bhavai/memories/<NAME>.md",
    "💭 Do you know run /init command make BHAVAI.md file specific to this folder",
    "💭 Do you know run /rename command rename the session",
    "💭 Do you know run ! <COMMAND> can be used for running bash commands",
    "💭 Do you know run /compact will summarize the entire conversation to free up context window",
    "💭 Do you know you can insert images into your terminal",
    "💭 Do you know run bhav --help tell you about the BhavAI project",
    "💭 Do you know run bhav dev opens your browswer so that you can manage your config related keys",
    "💭 Do you know you can add your own custom skill in .bhavai/skills/<SKILL_NAME>/SKILL.md",
    "💭 Do you know plan mode ask you for every permission",
    "💭 Do you know run (bhav update) you can download the latest version of BhavAI!",
    "💭 Do you know you can insert images into your terminal",
        ]

do_you_know = random.choice(lists)



console = Console()

# threshold_width_ = 180
size = shutil.get_terminal_size()
threshold_width_ = size.columns

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

  [green]/export[/green]
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

[yellow]🥷  bSlash Commands [/yellow]
  [cyan]/<COMMANDL_NAME>[/cyan]
  
""",
                title="BhavAI Help",
                subtitle="[dim]type 'bhav wake up' to begin[/dim]",
                border_style="bright_blue",
                padding=(1, 3),
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

    if sys.platform == "win32":
        import subprocess
        subprocess.run("chcp 65001", shell=True, stdout=subprocess.DEVNULL)
    # for first time setup
    # it create empty .bhavai folder in home directory
    BhavAI_dot_folder = Path.home() / ".bhavai"
    if not BhavAI_dot_folder.exists():
        BhavAI_dot_folder.mkdir()
        create_first_file_Note_from_bhavai()
    ensure_prompts_dir()


    if not is_folder_trusted(CWD):
        trusted_now = prompt_trust_folder(console, CWD)
        if not trusted_now:
            console.print(Panel(
                "[bold red]Folder not trusted.[/bold red]\n"
                "BhavAI ko is folder mein chalane ke liye trust karna zaroori hai.",
                title="BhavAI - Access Denied",
                border_style="red"
            ))
            sys.exit(1)
    cfg = get_config_summary()


    # it loads the config related configuration
    # cfg = get_config_summary()
    
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

    from rich.table import Table

    # =========================================================================
    # Wolf-core art — ab yeh panel ke andar, left side mein baithega
    # =========================================================================
    BHAVAI_WOLF = """[#B8C4D0]⠀⠀⠀⠀⠀    ⣀⣠⣤⣤⣤⣤⣄⣀⠀⠀⠀⠀⠀[/]
    [#B8C4D0]⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡀⠀⠀[/]
    [#9BAAB8]⠀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⢿⣿⣷⡀⠀[/]
    [#9BAAB8]⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠁⠀⣴⢿⣿⣧⠀[/]
    [#7B8A99]⣿⣿⣿⣿⣿⡿⠛⣩⠍⠀⠀⠀⠐⠉⢠⣿⣿⡇[/]
    [#7B8A99]⣿⡿⠛⠋⠉⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿[/]
    [#5C6B7A]⢹⣿⣤⠄⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿⡏[/]
    [#5C6B7A]⠀⠻⡏⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⣿⣿⣿⠟⠀[/]
    [#3C4B5A]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⠟⠁⠀⠀[/]"""


    def print_bhavai_terminal_agent():

        clear()
        print(YEL + "▄" * 58 + R)
        print()
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

    if(threshold_width_ > 160):
        print_bhavai_terminal_agent()
    elif(threshold_width_ > 94 and threshold_width_ < 160):
        print_bhavai_agent()
    else:
        pass

    banner_text = (
        f"\n🚀 [bold white]BhavAI Activated Successfully![/bold white]\n"
        f"📍  [bold]Location:[/bold] {cfg['CWD']}\n"
        f"⚙️  [bold]Model:[/bold] {cfg['MODEL']}\n"
        f"🛡️  [bold]Initial Mode:[/bold] [bold cyan]Plan Mode[/bold cyan] (Default)\n"
        f"📝 [bold]Logs Path:[/bold] {cfg['LOG_FILE']}\n"
        f"[dim]Type your requests below. Use 'mode agent' or 'mode plan' to toggle modes, 'exit' or 'quit' to close.[/dim]"
    )

    # --- NEW: wolf + banner_text ek hi grid mein, jo phir ek hi Panel ke andar jaayega ---
    inner_layout = Table.grid(padding=(0, 2))
    inner_layout.add_column("wolf", justify="center", vertical="middle")
    inner_layout.add_column("info", justify="left", ratio=1)
    inner_layout.add_row(BHAVAI_WOLF, banner_text)

    console.print(
        Panel(inner_layout, title="BhavAI Personal Terminal Agent", border_style="white")
    )
    # --- end new block, replaces the old: console.print(Panel(banner_text, ...)) ---

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
    from bhavai.ui.clipboard_paste import build_paste_keybindings

    pasted_images = []   # is turn mein jitni images paste hui unki list

    def _record_pasted_image(path):
        pasted_images.append(path)

    paste_kb, paste_store, paste_counter, get_and_reset_bursts = build_paste_keybindings(
        CWD, on_image_pasted=_record_pasted_image
    )
    # paste_store: dict[int, str] = {}

    session = PromptSession(key_bindings=paste_kb)


    def get_prompt_text():
        """
        Live prompt that re-evaluate for every key stroke.
        """
        buf = session.default_buffer.text
        if buf.startswith("!"):
            return HTML('<ansired><b>(bash)</b></ansired> > ')
        if buf.startswith("/"):
            return HTML('<ansiyellow><b>(command)</b></ansiyellow> > ')
        if current_mode == AgentMode.PLAN:
            return HTML('<ansicyan><b>(plan)</b></ansicyan> > ')
        else:
            return HTML('<ansiyellow><b>(agent)</b></ansiyellow> > ')


    SESSION_NAME = "NEW_CHAT_" + str(int(time.time()))
# SESSION_NAME = "NEW_CHAT_" + str(int(time.time()))
    # def print_bhavai_terminal_agent():
        
    #     clear()
    #     print(YEL + "▄" * 58 + R)
    #     print()
    #     logo = [
    #         r" ██████╗ ██╗  ██╗ █████╗ ██╗   ██╗ █████╗ ██╗    ████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗        █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
    #         r" ██╔══██╗██║  ██║██╔══██╗██║   ██║██╔══██╗██║       ██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║       ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    #         r" ██████╔╝███████║███████║██║   ██║███████║██║       ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║       ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
    #         r" ██╔══██╗██╔══██║██╔══██║╚██╗ ██╔╝██╔══██║██║       ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║       ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
    #         r" ██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║  ██║██║       ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██████╗   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
    #         r" ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝       ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═════╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
    #     ]
    #     for line in logo:
    #         print(GOLD + BOLD + line + R)
    #     print()
    #     username = getpass.getuser()
    #     typewrite(f"  ⚡  Terminal Edition — {username} ke liye  ⚡", delay=0.022, color=GOLD + BOLD)
    #     print(YEL + "▀" * 58 + R)
    #     print()

    # if(threshold_width_ > 160):
    #     print_bhavai_terminal_agent()
    # elif(threshold_width_ > 94 and threshold_width_ < 160):
    #     print(print_bhavai_agent())
    # else:
    #     pass
    
    # banner_text = (
    #     f"🚀 [bold green]BhavAI Activated Successfully![/bold green]\n\n"
    #     f"📍  [bold]Location:[/bold] {cfg['CWD']}\n"
    #     f"⚙️  [bold]Model:[/bold] {cfg['MODEL']}\n"
    #     f"🛡️  [bold]Initial Mode:[/bold] [bold cyan]Plan Mode[/bold cyan] (Default)\n"
    #     f"📝 [bold]Logs Path:[/bold] {cfg['LOG_FILE']}\n"
    #     # f"{do_you_know}\n\n"
    #     f"[dim]Type your requests below. Use 'mode agent' or 'mode plan' to toggle modes, 'exit' or 'quit' to close.[/dim]"
    # )
    # console.print(Panel(banner_text, title="BhavAI Personal Terminal Agent", border_style="green"))
    
    # # Print initial folder tree
    # console.print("\n[bold]Current Directory Structure:[/bold]")
    # try:
    #     tree_str = get_folder_tree_string(CWD)
    #     console.print(tree_str)
    #     console.print("")
    #     show_update_message(console)
    #     console.print("")
    #     console.print(do_you_know)
    # except Exception as e:
    #     console.print(f"[yellow]Warning: Could not build folder tree: {e}[/yellow]")
    # console.print()
    
    # # Initialize session state
    # current_mode = AgentMode.PLAN
    # memory = ConversationMemory()

    # from prompt_toolkit.formatted_text import HTML

    # session = PromptSession()



    # def get_prompt_text():
    #     """
    #     Live prompt that re-evaluate for every key stroke.
    #     """
    #     buf = session.default_buffer.text
    #     if buf.startswith("!"):
    #         return HTML('<ansired><b>(bash)</b></ansired> > ')
    #     if buf.startswith("/"):
    #         return HTML('<ansiyellow><b>(command)</b></ansiyellow> > ')
    #     if current_mode == AgentMode.PLAN:
    #         return HTML('<ansicyan><b>(plan)</b></ansicyan> > ')
    #     else:
    #         return HTML('<ansiyellow><b>(agent)</b></ansiyellow> > ')
        

    SESSION_NAME = "NEW_CHAT_" + str(int(time.time()))


    # Interactive REPL Loop
    while True:
        try:
            # Styled prompt input
            mode_color = "cyan" if current_mode == AgentMode.PLAN else "yellow"
            prompt_label = f"[bold {mode_color}]({current_mode})[/bold {mode_color}] > "

            user_input = session.prompt(get_prompt_text).strip()
            user_input = expand_pasted_text(user_input, paste_store)

            if pasted_images:
                console.print(Panel(
                    "\n".join(f"🖼  {p}" for p in pasted_images),
                    title="[bold green]Image(s) pasted[/bold green]",
                    border_style="green"
                ))
                memory.add_image_message("user", user_input, pasted_images)
                pasted_images.clear()

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


            if low == "/export":
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
                    # log.write(f"[red]Failed to export conversation: {e}[/red]")
                    console.print(f"[red]Failed to export conversation: {e}[/red]")
                
                continue
            
            if low == "/init":
                # with console.status("[bold yellow]Generating BhavAI.md[/bold yellow]", spinner="dots"):
                with ShimmerStatus("Generating BhavAI.md", color="yellow"):
                
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
            # if is_command or current_mode == AgentMode.PLAN:
            #     # 1. Generate and confirm plan
            #     folder_tree = get_folder_tree_string(CWD)
            #     should_proceed, plan_steps = prompt_and_confirm_plan(user_input, folder_tree, console)
                
            #     # 2. Run agent loop if approved
            #     if should_proceed:
            #         console.print("[bold green]Plan approved. Executing step-by-step...[/bold green]")
            #         run_agent_loop(
            #             user_input=user_input,
            #             memory=memory,
            #             current_mode=current_mode,
            #             plan_steps=plan_steps,
            #             console=console
            #         )

            if is_command or current_mode == AgentMode.PLAN:
                folder_tree = get_folder_tree_string(CWD)
                from bhavai.skill_getter import discover_skills_from_dot_bhavai
                skills_block = discover_skills_from_dot_bhavai(CWD)
                feedback = None
                planner_state = None

                # Loop: generate → show → confirm/feedback → regenerate if needed
                while True:
                    planner_state = prompt_and_confirm_plan(
                        user_input, folder_tree, console, feedback, skills_block=skills_block
                    )
                    ans = console.input(
                        "[bold yellow]Proceed?[/bold yellow] (y / n / type feedback to edit plan) > "
                    ).strip()

                    if ans.lower() == "y":
                        break
                    elif ans.lower() in ("n", "no", ""):
                        planner_state = None
                        break
                    else:
                        feedback = ans
                        console.print(f"[blue]Regenerating plan with feedback: '{feedback}'...[/blue]")

                if planner_state:
                    console.print("[bold green]Plan approved. Executing step-by-step...[/bold green]")
                    run_agent_loop_plan(
                        user_input=user_input,
                        memory=memory,
                        current_mode=current_mode,
                        planner_state=planner_state,
                        console=console
                    )
                else:
                    console.print("[yellow]Plan execution cancelled.[/yellow]")


            else: # Agent Mode (autonomous execution)
                console.print("[bold yellow]Executing task autonomously...[/bold yellow]")
                run_agent_loop_autonomous(
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



BACKEND_APP = "bhavai.api:app"          # bhavai/api.py → app = FastAPI(...)
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

FRONTEND_DIR = Path(__file__).resolve().parent / "webui"   # bhavai/webui/
FRONTEND_PORT = 3000

def _wait_for_server(url: str, timeout_seconds: int = 45) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1.5)
            return True
        except urllib.error.HTTPError:
            # Koi bhi HTTP response mila (chahe 404) — matlab server chal raha hai.
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _npm_executable() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise click.ClickException(
            "Could not find npm on your PATH. Install Node.js from "
            "https://nodejs.org and try again."
        )
    return npm


@main.command()
def dev():
    """
    Start the backend + frontend 
    and open the dashboard.
    """
    if not FRONTEND_DIR.exists():
        raise click.ClickException(f"Frontend directory not found: {FRONTEND_DIR}")

    print("Opening developer dashboard...")

    backend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", BACKEND_APP,
            "--host", BACKEND_HOST,
            "--port", str(BACKEND_PORT),
            "--reload",
        ],
    )

    frontend_proc = subprocess.Popen(
        [_npm_executable(), "run", "dev"],
        cwd=str(FRONTEND_DIR),
    )

    try:
        frontend_url = f"http://localhost:{FRONTEND_PORT}/dev"
        if _wait_for_server(f"http://localhost:{FRONTEND_PORT}"):
            click.echo(f"Opening developer dashboard at {frontend_url}")
            webbrowser.open(frontend_url)
        else:
            click.echo(f"Frontend didn't respond in time — open {frontend_url} manually.")

        click.echo("Press Ctrl+C to stop both servers.")
        while True:
            if backend_proc.poll() is not None:
                click.echo("Backend process exited unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                click.echo("Frontend process exited unexpectedly.")
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        click.echo("\nShutting down...")
    finally:
        for proc in (frontend_proc, backend_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        click.echo("Stopped.")


@main.command()
def update():
    """
    update the current version
    it redirect user to my official github repo of BhavAI so that user can download latest version
    """
    webbrowser.open("https://github.com/BhavneeshBanga/Terminal-agent")
    

main.add_command(config_group)

if __name__ == "__main__":
    main()

# #-------------------------------------------------------------------------------------------------------------------


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