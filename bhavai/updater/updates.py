from rich.panel import Panel
from rich.console import Console
import requests
from packaging.version import Version
from pathlib import Path
import json

CONFIG_PATH = Path.home() / ".BhavAI" / "metadata.json"


def get_current_version():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        return config.get("version", "0.0.0")

    except Exception:
        return "0.0.0"
VERSION_URL = (
    "https://bhavneeshbanga.github.io/version/docs/latest.json"
)

def get_latest_info():
    try:
        response = requests.get(
            VERSION_URL,
            timeout=5
            )

        response.raise_for_status()

        return response.json()

    except Exception:
        return None


def check_for_updates():

    current_version = get_current_version()

    data = get_latest_info()

    if data is None:
        return None

    latest_version = data["version"]

    if Version(latest_version) > Version(current_version):
        return data

    return None




def show_update_message(console):

    data = check_for_updates()

    if data is None:
        return

    notes = "\n".join(
        f"• {note}"
        for note in data.get("notes", [])
    )

    console.print()

    console.print(
        Panel(
            f"""
🎉 New Version Available!

Current Version : {get_current_version()}
Latest Version  : {data['version']}

What's New:
{notes}

Run:
bhav update
""",
            title="BhavAI Update",
            border_style="green"
        )
    )