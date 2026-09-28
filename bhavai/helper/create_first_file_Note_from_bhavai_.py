from pathlib import Path



def create_first_file_Note_from_bhavai():
    desktop = Path.home() / "Desktop"

    file_path = desktop / "Note From BhavAI.txt"

    content = """Hello from BhavAI.

    You ask. I can do – now directly on your computer, too."""

    file_path.write_text(content, encoding="utf-8")

