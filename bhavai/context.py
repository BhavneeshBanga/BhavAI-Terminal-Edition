import os
from pathlib import Path
import fnmatch
from bhavai.config import logger

def parse_gitignore(root_dir: Path) -> list:
    """Parses a .gitignore file if present, returning list of glob patterns."""
    patterns = []
    gitignore_path = root_dir / ".gitignore"
    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Normalize pattern: strip leading slash for match relative to root
                    if line.startswith("/"):
                        line = line[1:]
                    patterns.append(line)
        except Exception as e:
            logger.error("Failed to parse .gitignore: %s", e)
    return patterns

def should_ignore(path: Path, root_dir: Path, gitignore_patterns: list) -> bool:
    """Determines whether a given path should be ignored based on gitignore and default filters."""
    # Standard directories/files we always ignore for safety & token budget
    default_ignores = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
        ".bhavai",
    }
    
    # Check parts of the path against default ignores
    for part in path.relative_to(root_dir).parts:
        if part in default_ignores:
            return True
        if part.endswith(".egg-info"):
            return True

    # Check against gitignore patterns
    rel_path_str = str(path.relative_to(root_dir)).replace("\\", "/")
    for pattern in gitignore_patterns:
        # If pattern is folder-specific and ends with slash
        if pattern.endswith("/"):
            clean_pattern = pattern.rstrip("/")
            # Check if any path segment matches the folder name
            if clean_pattern in path.relative_to(root_dir).parts:
                return True
        else:
            # General file glob check
            if fnmatch.fnmatch(rel_path_str, pattern) or any(fnmatch.fnmatch(part, pattern) for part in path.relative_to(root_dir).parts):
                return True
                
    return False

def build_folder_tree(root_dir: Path, current_dir: Path = None, prefix: str = "", gitignore_patterns: list = None) -> list:
    """Recursively builds lines representing the folder tree structure."""
    if current_dir is None:
        current_dir = root_dir
    if gitignore_patterns is None:
        gitignore_patterns = parse_gitignore(root_dir)

    tree_lines = []
    
    try:
        # Gather directory entries sorted: directories first, then files
        entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return [prefix + "└── [Permission Denied]"]
    except Exception as e:
        return [prefix + f"└── [Error: {str(e)}]"]

    # Filter entries that should be ignored
    filtered_entries = [e for e in entries if not should_ignore(e, root_dir, gitignore_patterns)]
    
    count = len(filtered_entries)
    for i, entry in enumerate(filtered_entries):
        is_last = (i == count - 1)
        connector = "└── " if is_last else "├── "
        
        tree_lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
        
        if entry.is_dir():
            next_prefix = prefix + ("    " if is_last else "│   ")
            tree_lines.extend(build_folder_tree(root_dir, entry, next_prefix, gitignore_patterns))
            
    return tree_lines

def get_folder_tree_string(root_dir: Path) -> str:
    """Returns the visual folder tree as a single string."""
    lines = [f"{root_dir.name}/"]
    lines.extend(build_folder_tree(root_dir))
    return "\n".join(lines)
