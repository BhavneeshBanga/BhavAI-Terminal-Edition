import os
import getpass
import sys
import time
from rich.console import Console



BOLD= "\033[1m"
YEL = "\033[1;93m"
GOLD= "\033[33m"
R   = "\033[0m"
YEL = "\033[1;93m"

main = {
    "1. Cyan -> Violet (original)": [
        "bold #00F5FF", "bold #00F5FF", "#7B2FF7", "#7B2FF7", "#B026FF", "#B026FF",
    ],
    "2. Neon Green -> Cyan": [
        "bold #39FF14", "bold #39FF14", "#00FF9C", "#00FF9C", "#00E5FF", "#00E5FF",
    ],
    "3. Gold -> Orange (fire)": [
        "bold #FFD700", "bold #FFD700", "#FFA500", "#FFA500", "#FF6B35", "#FF6B35",
    ],
    "4. Ice Blue -> White": [
        "bold #38BDF8", "bold #38BDF8", "#7DD3FC", "#7DD3FC", "#E0F2FE", "#E0F2FE",
    ],
    
}


def typewrite(text, delay=0.015, color=""):
    for ch in text:
        sys.stdout.write(color + ch + R)
        sys.stdout.flush()
        time.sleep(delay)
    print()



def clear():
    os.system("cls" if os.name == "nt" else "clear")

LOGO_LINES = [
    "██████╗ ██╗  ██╗ █████╗ ██╗   ██╗ █████╗ ██╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
    "██╔══██╗██║  ██║██╔══██╗██║   ██║██╔══██╗██║      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    "██████╔╝███████║███████║██║   ██║███████║██║█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║",
    "██╔══██╗██╔══██║██╔══██║╚██╗ ██╔╝██╔══██║██║╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║",
    "██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║  ██║██║      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║",
    "╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝",
]



def print_variant(console: Console,  colors: list[str]):
    for line, color in zip(LOGO_LINES, colors):
        console.print(f"[{color}]{line}[/]")

def print_bhavai_agent():
    console = Console()
    import random
    colors = random.choice(list(main.values()))
    print()
    print_variant(console, colors)
    print()