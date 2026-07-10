from rich.panel import Panel
from rich.console import Console
import requests
from packaging.version import Version
from pathlib import Path
import json

CONFIG_PATH = Path.home() / ".BhavAI" / "metadata.json"
current_version = {
    "version" : "1.1.1"
}

def get_current_version():
    "it returns the current version if not exist it make the fiel metadata.json and dumps current version there"
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        return config.get("version", "1.1.1")

    except Exception:
        with open(CONFIG_PATH, "w", encoding="utf-8") as json_file:
            json.dump(current_version, json_file, indent=4, ensure_ascii=False)
        return "1.1.1"
    

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
    """
    only show when the current version is lower then the latest one
    """

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