import os
import re
import subprocess
from pathlib import Path
from bhavai.config import logger, CWD
from bhavai.context import get_folder_tree_string

# Hard restrictions blocklist
BLOCKED_COMMANDS = [
    "rm", 
    "rmdir", 
    "del", 
    "unlink", 
    "shutil.rmtree", 
    "os.remove", 
    "format", 
    "mkfs", 
    "drop table"
]

def validate_path(path_str: str) -> Path:
    """
    Validates that the given path string resolves to a location
    strictly within the current working directory (sandboxing).
    Raises ValueError if path lies outside CWD.
    """
    # Standardize path
    raw_path = Path(path_str)
    
    # If the path is absolute on Windows/Linux, resolve it.
    # Otherwise, treat it relative to CWD.
    if raw_path.is_absolute():
        resolved_path = raw_path.resolve()
    else:
        resolved_path = (CWD / raw_path).resolve()
        
    try:
        # Check if the path is relative to the CWD.
        # This will raise ValueError if resolved_path is not a child of CWD.
        resolved_path.relative_to(CWD)
    except ValueError:
        raise ValueError(
            f"Access Denied: Path '{path_str}' (resolved: '{resolved_path}') "
            f"is outside the sandboxed working directory '{CWD}'."
        )
        
    return resolved_path

def validate_command(command: str) -> None:
    """
    Checks the command string against dangerous patterns in BLOCKED_COMMANDS.
    Raises ValueError if a blocked command is detected.
    """
    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        # Regex to match the blocked word/command with word boundaries or special separators.
        # This covers cases like "rm -rf", "shutil.rmtree()", "drop table;".
        # It avoids false positives like "format" in "formatting".
        pattern = rf"(?:^|\W){re.escape(blocked)}(?:$|\W)"
        if re.search(pattern, cmd_lower):
            raise ValueError(
                f"Security Violation: Command contains blocked operation '{blocked}'."
            )

# Tool definitions callable by agent

def ensure_git_initialized() -> None:
    """
    Checks if a git repository is initialized in CWD.
    If not, initializes git, creates a default .gitignore if missing,
    configures local name/email, and commits existing files so that
    future edits are clearly visible in git diff (red/green format).
    """
    git_dir = CWD / ".git"
    if git_dir.exists() and git_dir.is_dir():
        return

    logger.info("Initializing Git repository in CWD to track changes...")
    try:
        # Create default .gitignore if it doesn't exist
        gitignore_path = CWD / ".gitignore"
        if not gitignore_path.exists():
            default_gitignore = (
                "__pycache__/\n"
                "*.py[cod]\n"
                ".pytest_cache/\n"
                ".bhavai/\n"
                ".env\n"
            )
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(default_gitignore)
            logger.info("Created default .gitignore file.")

        # Run git init
        subprocess.run(["git", "init"], cwd=CWD, capture_output=True, text=True, check=True)

        # Configure local git user to avoid commit errors
        subprocess.run(["git", "config", "user.name", "BhavAI"], cwd=CWD, capture_output=True, text=True, check=True)
        subprocess.run(["git", "config", "user.email", "bhavai@local.ai"], cwd=CWD, capture_output=True, text=True, check=True)

        # Stage and commit any existing files
        subprocess.run(["git", "add", "."], cwd=CWD, capture_output=True, text=True, check=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit (automatically initialized by BhavAI)"],
            cwd=CWD,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Git repository successfully initialized with initial commit.")
    except Exception as e:
        logger.error("Failed to initialize git repository: %s", e)

def list_folder(path: str = ".") -> str:
    """List the file and folder tree of a directory path relative to CWD."""
    logger.info("Executing list_folder on path: %s", path)
    resolved_path = validate_path(path)
    
    if not resolved_path.exists():
        return f"Error: Path '{path}' does not exist."
    if not resolved_path.is_dir():
        return f"Error: Path '{path}' is a file, not a directory."
        
    return get_folder_tree_string(resolved_path)

def read_file(path: str) -> str:
    """Read the content of a file at the given path relative to CWD."""
    logger.info("Executing read_file on path: %s", path)
    ensure_git_initialized()
    resolved_path = validate_path(path)
    
    if not resolved_path.exists():
        return f"Error: File '{path}' does not exist."
    if not resolved_path.is_file():
        return f"Error: Path '{path}' is a directory, not a file."
        
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error("Error reading file %s: %s", path, e)
        return f"Error reading file '{path}': {str(e)}"

def write_file(path: str, content: str) -> str:
    """Create a new file or overwrite an existing file with the given content."""
    logger.info("Executing write_file on path: %s", path)
    ensure_git_initialized()
    resolved_path = validate_path(path)
    
    # Hard restriction: Do not allow deletion via empty writing if that's a security concern,
    # but overwriting/creating files is generally fine.
    try:
        # Ensure parent directories exist
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{path}' written successfully ({len(content)} characters)."
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing file '{path}': {str(e)}"

def update_file(path: str, content: str, mode: str = "append") -> str:
    """Append or partially update content in an existing file."""
    logger.info("Executing update_file on path: %s with mode: %s", path, mode)
    ensure_git_initialized()
    resolved_path = validate_path(path)
    
    if mode not in ("append", "overwrite"):
        return f"Error: Invalid mode '{mode}'. Must be 'append' or 'overwrite'."
        
    if mode == "overwrite":
        return write_file(path, content)
        
    # Mode is append
    try:
        # If file doesn't exist, create it.
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Success: Content appended to '{path}' successfully."
    except Exception as e:
        logger.error("Error appending to file %s: %s", path, e)
        return f"Error updating file '{path}': {str(e)}"

def run_command(command: str) -> str:
    """Run a safe, read-only shell command (e.g. git status, ls, cat)."""
    logger.info("Executing run_command: %s", command)
    try:
        validate_command(command)
    except ValueError as e:
        return str(e)
        
    import sys
    
    try:
        # Spawn the process in the sandboxed CWD
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=CWD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            # Wait for the process to complete with a 10s timeout
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            logger.error("Command '%s' timed out", command)
            
            # Kill process tree depending on platform
            if sys.platform == "win32":
                # Force kill process tree recursively on Windows
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                # Standard kill on Unix/macOS
                proc.kill()
                
            # Collect any stdout/stderr written before process termination
            stdout, stderr = proc.communicate()
            
            output = []
            if stdout:
                output.append(f"Stdout before timeout:\n{stdout}")
            if stderr:
                output.append(f"Stderr before timeout:\n{stderr}")
                
            output_msg = "\n".join(output) if output else "No output was produced."
            return (
                f"Error: Command execution timed out (10s limit).\n"
                f"{output_msg}"
            )
            
        output = []
        if stdout:
            output.append(stdout)
        if stderr:
            output.append(f"Stderr:\n{stderr}")
            
        if not output:
            return "Command executed with no output."
            
        return "\n".join(output)
        
    except Exception as e:
        logger.error("Error running command '%s': %s", command, e)
        return f"Error executing command: {str(e)}"

# Registry of available tools for routing
TOOL_DISPATCH = {
    "list_folder": list_folder,
    "read_file": read_file,
    "write_file": write_file,
    "update_file": update_file,
    "run_command": run_command
}
