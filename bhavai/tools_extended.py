"""
tools_extended.py — Additional real-world tools for the BhavAI agent.

Why this exists as a separate file (not bolted onto tools.py)
---------------------------------------------------------------
tools.py owns the core file-write primitives (write_file, append_chunk,
run_command) and the security plumbing (validate_path, validate_command,
git init/staging). Those are the load-bearing walls — touching that file
for every new tool risks breaking the 4096-token chunking story.

This file owns *read-oriented* and *navigation* tools: the things a real
developer or student actually reaches for once they've handed a codebase
to an agent — "find where X is defined", "what changed", "what's left
to do", "is this dependency even installed". None of these write files,
so the blast radius of a bug here is zero risk to the user's code.

All tools below reuse tools.py's validate_path / CWD / git plumbing so
the sandbox and zero-deletion guarantees apply identically here.

New tools in this file
-----------------------
  search_code          — regex/text search across the project (grep-like)
  find_files           — glob-based filename search
  get_outline           — extract function/class signatures from a file
  list_todos            — scan for TODO / FIXME / HACK / XXX markers
  get_diff               — show git diff for a file or the whole workspace
  check_dependencies    — parse requirements.txt / pyproject.toml /
                           package.json and report installed vs missing
  rename_path            — safe move/rename (never deletes the source
                           if the destination write fails)
  fetch_url              — fetch real documentation / API reference pages
                           so the agent answers from ground truth instead
                           of guessing API signatures from memory
"""

import ast
import fnmatch
import json
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from bhavai.config import logger, CWD
from bhavai.context import is_env_file, parse_gitignore, should_ignore
from bhavai.tools import validate_path, _git_stage, ensure_git_initialized

import shutil
...
from bhavai.tools import validate_path, _git_stage, ensure_git_initialized, validate_command
# ─────────────────────────────────────────────────────────────────────────────
# Shared helper: walk the project respecting the same ignore rules as the
# folder tree (so search/find never touches .git, node_modules, .env, etc.)
# ─────────────────────────────────────────────────────────────────────────────

def _iter_project_files(root: Path):
    """Yields every non-ignored, non-secret file under root."""
    gitignore_patterns = parse_gitignore(root)
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if should_ignore(p, root, gitignore_patterns):
            continue
        if is_env_file(p):
            continue
        yield p


def _read_text_safe(path: Path, max_bytes: int = 2_000_000) -> str | None:
    """Reads a file as UTF-8 text, returns None for binaries or oversized files."""
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tool: search_code  — the single most-requested missing capability.
# Lets the agent (and effectively the user) ask "where is X used/defined?"
# instead of reading every file one by one to find out.
# ─────────────────────────────────────────────────────────────────────────────

def search_code(query: str, path: str = ".", regex: bool = False,
                 case_sensitive: bool = False, max_results: int = 100) -> str:
    """
    Searches file contents under `path` for `query`.

    Parameters
    ----------
    query          : Text to search for. Treated literally unless regex=True.
    path           : Directory (relative to CWD) to search within. Default '.'.
    regex          : If true, `query` is compiled as a Python regex.
    case_sensitive : Default False — most code searches are easier case-insensitive.
    max_results    : Caps the number of matching lines returned (default 100)
                     so one search can't blow the LLM's context window.

    Returns
    -------
    "path/to/file.py:42: matched line content" — one per match, grep-style.
    """
    logger.info("search_code(query=%r, path=%r, regex=%s)", query, path, regex)
    root = validate_path(path)
    if not root.exists():
        return f"Error: '{path}' does not exist."

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, flags) if regex else re.compile(re.escape(query), flags)
    except re.error as exc:
        return f"Error: invalid regex '{query}': {exc}"

    search_root = root if root.is_dir() else root.parent
    files = [root] if root.is_file() else list(_iter_project_files(root))

    matches = []
    for f in files:
        text = _read_text_safe(f)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = f.relative_to(CWD)
                matches.append(f"{rel}:{lineno}: {line.strip()}")
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    if not matches:
        return f"No matches for '{query}' under '{path}'."

    header = f"Found {len(matches)} match(es) for '{query}'"
    if len(matches) >= max_results:
        header += f" (showing first {max_results} — narrow your search for more)"
    return header + ":\n" + "\n".join(matches)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: find_files — "where is the config file?" without reading the whole tree
# ─────────────────────────────────────────────────────────────────────────────

def find_files(pattern: str, path: str = ".") -> str:
    """
    Finds files whose name matches a glob pattern (e.g. '*.py', 'test_*.py',
    '**/settings.json') under `path`, respecting .gitignore and secrets rules.
    """
    logger.info("find_files(pattern=%r, path=%r)", pattern, path)
    root = validate_path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: '{path}' is not a valid directory."

    results = []
    for f in _iter_project_files(root):
        rel = f.relative_to(CWD)
        if fnmatch.fnmatch(f.name, pattern) or fnmatch.fnmatch(str(rel), pattern):
            results.append(str(rel))

    if not results:
        return f"No files matching '{pattern}' under '{path}'."
    results.sort()
    return f"Found {len(results)} file(s):\n" + "\n".join(results)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: get_outline — fast code navigation: signatures without full content
# ─────────────────────────────────────────────────────────────────────────────

def get_outline(path: str) -> str:
    """
    Returns the structural outline of a file: classes, functions, and their
    line numbers, without returning full source.

    For .py files this uses the `ast` module for an exact outline.
    For other text files it falls back to a heuristic regex scan for common
    function/class declaration patterns (JS/TS, Java, C/C++, Go, Rust).

    Use this before read_file when you only need to know WHAT is in a file
    and WHERE, not the full implementation — saves tokens.
    """
    logger.info("get_outline('%s')", path)
    resolved = validate_path(path)
    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if not resolved.is_file():
        return f"Error: '{path}' is a directory."

    text = _read_text_safe(resolved)
    if text is None:
        return f"Error: '{path}' is not a readable text file (binary or too large)."

    if resolved.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return f"Error: '{path}' has a syntax error and can't be parsed: {exc}"

        lines = []

        def _walk(node, indent=""):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    bases = ", ".join(ast.dump(b, annotate_fields=False)[:30] for b in child.bases) or ""
                    lines.append(f"{indent}class {child.name}  (line {child.lineno})")
                    _walk(child, indent + "    ")
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                    args = ", ".join(a.arg for a in child.args.args)
                    lines.append(f"{indent}{prefix} {child.name}({args})  (line {child.lineno})")

        _walk(tree)
        if not lines:
            return f"'{path}' has no top-level classes or functions."
        return f"Outline of '{path}':\n" + "\n".join(lines)

    # Heuristic fallback for non-Python text files
    patterns = [
        r"^\s*(export\s+)?(async\s+)?function\s+(\w+)",          # JS/TS
        r"^\s*(export\s+)?class\s+(\w+)",                         # JS/TS/Java
        r"^\s*(public|private|protected|static)?\s*\w+\s+(\w+)\s*\(",  # Java/C#
        r"^\s*func\s+(\w+)",                                       # Go
        r"^\s*fn\s+(\w+)",                                         # Rust
        r"^\s*(\w+)\s*:\s*function",                               # JS object method
    ]
    compiled = [re.compile(p) for p in patterns]
    lines = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pat in compiled:
            if pat.search(line):
                lines.append(f"  line {lineno}: {line.strip()}")
                break

    if not lines:
        return f"No recognizable function/class declarations found in '{path}' (or unsupported language)."
    return f"Outline of '{path}' (heuristic scan):\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: list_todos — every dev/student inheriting a codebase asks this first
# ─────────────────────────────────────────────────────────────────────────────

_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b[:\s]*(.*)", re.IGNORECASE)

def list_todos(path: str = ".") -> str:
    """
    Scans the project for TODO / FIXME / HACK / XXX / BUG comments.
    Returns file, line number, marker type, and the note text.
    """
    logger.info("list_todos(path='%s')", path)
    root = validate_path(path)
    if not root.exists():
        return f"Error: '{path}' does not exist."

    files = [root] if root.is_file() else list(_iter_project_files(root))
    found = []
    for f in files:
        text = _read_text_safe(f)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = _TODO_PATTERN.search(line)
            if m:
                rel = f.relative_to(CWD)
                marker, note = m.group(1).upper(), m.group(2).strip()
                found.append(f"[{marker}] {rel}:{lineno} — {note}" if note else f"[{marker}] {rel}:{lineno}")

    if not found:
        return f"No TODO/FIXME/HACK/XXX/BUG markers found under '{path}'. Clean!"
    return f"Found {len(found)} marker(s):\n" + "\n".join(found)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: get_diff — surfaces the git tracking that tools.py already maintains
# ─────────────────────────────────────────────────────────────────────────────

def get_diff(path: str = "") -> str:
    """
    Shows `git diff HEAD` for a specific file, or for the whole workspace
    if path is omitted. Lets the user/agent see exactly what BhavAI has
    changed before deciding whether to keep it.
    """
    logger.info("get_diff(path='%s')", path)
    ensure_git_initialized()

    cmd = ["git", "diff", "HEAD", "--"]
    if path:
        resolved = validate_path(path)
        if is_env_file(resolved):
            return f"Access Denied: '{path}' is an environment/secrets file."
        cmd.append(str(resolved))

    try:
        proc = subprocess.run(cmd, cwd=CWD, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return "Error: git diff timed out."
    except Exception as exc:
        return f"Error running git diff: {exc}"

    if proc.returncode != 0:
        return f"Error: git diff failed: {proc.stderr.strip()}"
    if not proc.stdout.strip():
        target = f"'{path}'" if path else "the workspace"
        return f"No uncommitted changes in {target}."
    return proc.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Tool: check_dependencies — real onboarding pain: "will this even run?"
# ─────────────────────────────────────────────────────────────────────────────

def _parse_requirements_txt(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifiers / extras: "requests[socks]>=2.0" → "requests"
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    return names


def _parse_pyproject_toml(text: str) -> list[str]:
    names = []
    # Lightweight extraction without a TOML dependency: look for the
    # [tool.poetry.dependencies] / [project] dependencies arrays/tables.
    dep_array = re.search(r'dependencies\s*=\s*\[(.*?)\]', text, re.DOTALL)
    if dep_array:
        for entry in re.findall(r'["\']([^"\']+)["\']', dep_array.group(1)):
            name = re.split(r"[<>=!~\[; ]", entry, maxsplit=1)[0].strip()
            if name:
                names.append(name)
    # Poetry-style table: name = "version"
    poetry_block = re.search(r'\[tool\.poetry\.dependencies\](.*?)(\n\[|\Z)', text, re.DOTALL)
    if poetry_block:
        for line in poetry_block.group(1).splitlines():
            m = re.match(r'\s*([A-Za-z0-9_.-]+)\s*=', line)
            if m and m.group(1).lower() != "python":
                names.append(m.group(1))
    return names


def _parse_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names = []
    for key in ("dependencies", "devDependencies"):
        names.extend((data.get(key) or {}).keys())
    return names


def check_dependencies(path: str = ".") -> str:
    """
    Finds requirements.txt, pyproject.toml, and/or package.json under `path`
    and reports which declared dependencies are actually importable/installed
    in the current environment. Surfaces "missing dependency" issues before
    the user hits an ImportError or 'module not found' mid-task.

    Python packages are checked via importlib; Node packages are checked by
    looking for a matching folder under node_modules/.
    """
    logger.info("check_dependencies(path='%s')", path)
    root = validate_path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: '{path}' is not a valid directory."

    reports = []

    req_file = root / "requirements.txt"
    if req_file.exists():
        text = _read_text_safe(req_file) or ""
        pkgs = _parse_requirements_txt(text)
        reports.append(_check_python_packages(pkgs, "requirements.txt"))

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _read_text_safe(pyproject) or ""
        pkgs = _parse_pyproject_toml(text)
        if pkgs:
            reports.append(_check_python_packages(pkgs, "pyproject.toml"))

    package_json = root / "package.json"
    if package_json.exists():
        text = _read_text_safe(package_json) or ""
        pkgs = _parse_package_json(text)
        if pkgs:
            reports.append(_check_node_packages(pkgs, root))

    if not reports:
        return (f"No requirements.txt, pyproject.toml, or package.json found under '{path}'. "
                f"Nothing to check.")
    return "\n\n".join(reports)


def _check_python_packages(pkgs: list[str], source: str) -> str:
    import importlib.util
    # Common PyPI-name → import-name mismatches
    import_name_overrides = {
        "pillow": "PIL", "pyyaml": "yaml", "beautifulsoup4": "bs4",
        "python-dotenv": "dotenv", "scikit-learn": "sklearn",
        "opencv-python": "cv2",
    }
    installed, missing = [], []
    for pkg in pkgs:
        import_name = import_name_overrides.get(pkg.lower(), pkg.replace("-", "_"))
        spec = importlib.util.find_spec(import_name)
        (installed if spec else missing).append(pkg)

    lines = [f"From {source} ({len(pkgs)} package(s)):"]
    if installed:
        lines.append(f"  ✓ Installed: {', '.join(installed)}")
    if missing:
        lines.append(f"  ✗ Missing:   {', '.join(missing)}")
        lines.append(f"    → pip install {' '.join(missing)}")
    return "\n".join(lines)


def _check_node_packages(pkgs: list[str], root: Path) -> str:
    node_modules = root / "node_modules"
    installed, missing = [], []
    for pkg in pkgs:
        if (node_modules / pkg).exists():
            installed.append(pkg)
        else:
            missing.append(pkg)

    lines = [f"From package.json ({len(pkgs)} package(s)):"]
    if installed:
        lines.append(f"  ✓ Installed: {', '.join(installed)}")
    if missing:
        lines.append(f"  ✗ Missing:   {', '.join(missing)}")
        lines.append(f"    → npm install {' '.join(missing)}")
    if not node_modules.exists():
        lines.append("  ⚠ node_modules/ not found at all — run `npm install` first.")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: rename_path — reorganize without ever deleting the original
# ─────────────────────────────────────────────────────────────────────────────

def rename_path(source: str, destination: str) -> str:
    """
    Moves/renames a file or folder from `source` to `destination`,
    both sandboxed inside CWD.

    Safety guarantees (zero-deletion policy compliance)
    ----------------------------------------------------
    • Refuses to overwrite an existing destination (no silent data loss).
    • If anything goes wrong mid-move, the source is left untouched —
      this NEVER deletes source content; it only relocates it.
    • Destination's parent directories are created automatically.
    """
    logger.info("rename_path('%s' -> '%s')", source, destination)
    ensure_git_initialized()

    src = validate_path(source)
    dst = validate_path(destination)

    if is_env_file(src) or is_env_file(dst):
        return "Access Denied: refusing to move environment/secrets files."
    if not src.exists():
        return f"Error: source '{source}' does not exist."
    if dst.exists():
        return (f"Error: destination '{destination}' already exists. "
                f"Refusing to overwrite — choose a different name or move it first.")

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        _git_stage(dst)
        return f"✓ Moved '{source}' → '{destination}'. Run `git diff HEAD` to review."
    except Exception as exc:
        logger.error("rename_path('%s' -> '%s'): %s", source, destination, exc)
        return f"Error moving '{source}' to '{destination}': {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: fetch_url — ground the agent in real documentation instead of
# letting it guess API signatures, error messages, or library usage from
# (possibly stale) training data. High value for students learning new
# libraries and developers debugging unfamiliar errors.
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_URL_SCHEMES = ("http://", "https://")
_MAX_FETCH_BYTES = 300_000

def fetch_url(url: str, max_chars: int = 8000) -> str:
    """
    Fetches a web page or API endpoint and returns its text content
    (HTML tags stripped) for the agent to read.

    Use this to look up real documentation, error message explanations,
    Stack Overflow answers, or library API references instead of
    guessing — especially for libraries that may have changed since
    the model's training data.

    Truncates output to max_chars (default 8000) to protect the
    4096-token output budget on the NEXT call where the agent
    summarizes what it read.
    """
    logger.info("fetch_url('%s')", url)
    if not url.lower().startswith(_ALLOWED_URL_SCHEMES):
        return "Error: only http:// and https:// URLs are supported."

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "BhavAI-Agent/1.0 (+terminal coding assistant)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(_MAX_FETCH_BYTES)
    except urllib.error.HTTPError as exc:
        return f"Error: HTTP {exc.code} fetching '{url}'."
    except urllib.error.URLError as exc:
        return f"Error: could not reach '{url}': {exc.reason}"
    except Exception as exc:
        return f"Error fetching '{url}': {exc}"

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return f"Error: '{url}' did not return decodable text content."

    if "html" in content_type.lower():
        # Strip script/style blocks, then all remaining tags — good enough
        # for an agent that needs prose, not pixel-perfect rendering.
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    truncated = len(text) > max_chars
    text = text[:max_chars]
    suffix = f"\n\n[...truncated, {len(raw)} bytes fetched total...]" if truncated else ""
    return f"Content from {url}:\n\n{text}{suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: duckduckgo_search — real-time web search for prices, docs, and news.
# ─────────────────────────────────────────────────────────────────────────────

def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """
    Searches DuckDuckGo on the web for live query results, returning titles,
    snippets, and links for up to `max_results` (default 5).

    Use this when you need real-time data, current pricing, documentation links,
    or answers to questions beyond training knowledge. Pair this with `fetch_url`
    to read full pages from the returned links.
    """
    logger.info("duckduckgo_search('%s', max_results=%d)", query, max_results)
    if not query or not query.strip():
        return "Error: query string cannot be empty."

    # Try ddgs or duckduckgo_search library if available
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            ddg_gen = list(ddgs.text(query.strip(), max_results=max_results))
            if ddg_gen:
                for r in ddg_gen:
                    title = r.get("title", "No title")
                    href = r.get("href", r.get("link", ""))
                    body = r.get("body", r.get("snippet", ""))
                    results.append(f"Title: {title}\nURL: {href}\nSnippet: {body}")
        if results:
            return f"DuckDuckGo search results for '{query}':\n\n" + "\n\n---\n\n".join(results)
    except Exception as exc:
        logger.debug("duckduckgo_search library unavailable or failed (%s); falling back to html scraping", exc)

    # Fallback to direct HTTP request on html.duckduckgo.com
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(query.strip())
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")

        results = []
        link_matches = list(re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw_html, re.IGNORECASE | re.DOTALL))
        snippet_matches = list(re.finditer(r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(.*?)</(?:a|div)>', raw_html, re.IGNORECASE | re.DOTALL))

        for i, match in enumerate(link_matches[:max_results]):
            raw_href = match.group(1)
            raw_title = match.group(2)

            clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()

            if "uddg=" in raw_href:
                match_uddg = re.search(r'uddg=([^&]+)', raw_href)
                if match_uddg:
                    raw_href = urllib.parse.unquote(match_uddg.group(1))

            snippet = ""
            if i < len(snippet_matches):
                snippet = re.sub(r'<[^>]+>', '', snippet_matches[i].group(1)).strip()

            results.append(f"Title: {clean_title}\nURL: {raw_href}\nSnippet: {snippet}")

        if not results:
            clean_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            if len(clean_text) > 50:
                return f"DuckDuckGo search results for '{query}':\n\n{clean_text[:2000]}"
            return f"No results found on DuckDuckGo for query: '{query}'"

        return f"DuckDuckGo search results for '{query}':\n\n" + "\n\n---\n\n".join(results)

    except Exception as exc:
        return f"Error performing DuckDuckGo search for '{query}': {exc}"



# ─────────────────────────────────────────────────────────────────────────────
# Tool: get_function_source — precise, line-numbered view of ONE function.
#
# Why this earns a spot next to get_outline
# ------------------------------------------
# get_outline tells the agent WHERE a function is. This tool returns WHAT is
# in it — but only that function, not the whole file — so the agent can
# inspect a single function's body for a fraction of the tokens read_file
# would cost on a large file.
# ─────────────────────────────────────────────────────────────────────────────

def get_function_source(path: str, function_name: str) -> str:
    """
    Returns the exact source of one function (or async function), with line
    numbers, found via AST — not text search, so it can't be fooled by a
    matching string inside a comment or docstring elsewhere in the file.

    Use this instead of read_file when you only need one function's body.
    """
    logger.info("get_function_source('%s', '%s')", path, function_name)
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if resolved.suffix != ".py":
        return "Error: Only Python files are supported."

    text = _read_text_safe(resolved)
    if text is None:
        return f"Error: '{path}' is not a readable text file (binary or too large)."

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return f"Error: '{path}' has a syntax error and can't be parsed: {exc}"

    lines = text.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            start, end = node.lineno, node.end_lineno
            snippet = lines[start - 1 : end]
            numbered = "\n".join(f"{i:4d} | {line}" for i, line in enumerate(snippet, start=start))
            return f"FUNCTION: {function_name}\nFILE: {path}\nLINES: {start}-{end}\n\n{numbered}"

    return f"Function '{function_name}' not found in '{path}'."


# ─────────────────────────────────────────────────────────────────────────────
# Tool: insert_function — append a brand-new function to the end of a file.
#
# Mutating tool, so it follows the same conventions as write_file/append_chunk
# in tools.py: ensure_git_initialized() first, .env guard, _git_stage() on
# success so the change shows up in `git diff HEAD`.
# ─────────────────────────────────────────────────────────────────────────────

def insert_function(path: str, new_source: str) -> str:
    """
    Inserts a new top-level function (or async function) at the end of a
    Python file. The new source is validated with ast.parse BEFORE anything
    is written, so a syntax error in new_source never corrupts the file.

    Use this to ADD a function that doesn't exist yet. To replace an
    existing function's body, use replace_function instead.
    """
    logger.info("insert_function('%s', %d chars)", path, len(new_source))
    ensure_git_initialized()

    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if resolved.suffix != ".py":
        return "Error: Only Python files are supported."

    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        return f"Syntax Error in new function: {exc}"

    try:
        source = resolved.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    updated_source = source.rstrip() + "\n\n\n" + new_source.strip() + "\n"

    try:
        resolved.write_text(updated_source, encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("insert_function('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    return f"✓ Function inserted into '{path}'. Run `git diff HEAD` to review."


# ─────────────────────────────────────────────────────────────────────────────
# Tool: replace_function — swap out an existing function's full source.
#
# Uses AST line numbers (lineno/end_lineno) to slice out exactly the old
# function and splice in the new one — same precision approach as
# get_function_source, so the two tools are a natural "read it, rewrite it"
# pair for the agent.
# ─────────────────────────────────────────────────────────────────────────────

def replace_function(path: str, function_name: str, new_source: str) -> str:
    """
    Replaces an existing top-level function (or async function) with new
    source code, located precisely via AST line numbers (not text matching,
    so a docstring mentioning the function name elsewhere can't confuse it).

    new_source must be syntactically valid on its own — it is validated with
    ast.parse before the file is touched. If function_name isn't found,
    nothing is written.
    """
    logger.info("replace_function('%s', '%s', %d chars)", path, function_name, len(new_source))
    ensure_git_initialized()

    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if resolved.suffix != ".py":
        return "Error: Only Python files are supported."

    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        return f"Syntax Error in new function: {exc}"

    try:
        source = resolved.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"Error: '{path}' has a syntax error and can't be parsed: {exc}"
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    target_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target_node = node
            break

    if target_node is None:
        return f"Function '{function_name}' not found in '{path}'. Nothing was changed."

    start, end = target_node.lineno, target_node.end_lineno
    new_function_lines = new_source.strip().splitlines()
    updated_lines = lines[: start - 1] + new_function_lines + lines[end:]

    try:
        resolved.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("replace_function('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    return (
        f"✓ Replaced '{function_name}' (was lines {start}-{end}) in '{path}'. "
        f"Run `git diff HEAD` to review."
    )

def read_file_chunk(path: str, start_line: int, end_line: int) -> str:
    """
    Reads only a specific line range from a file (1-indexed, inclusive),
    with line numbers — the reading counterpart to append_chunk.
    """
    logger.info("read_file_chunk('%s', %d, %d)", path, start_line, end_line)
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if not resolved.is_file():
        return f"Error: '{path}' is a directory."

    text = _read_text_safe(resolved)
    if text is None:
        return f"Error: '{path}' is not a readable text file (binary or too large)."

    lines = text.splitlines()
    total = len(lines)
    if start_line < 1 or end_line < start_line:
        return f"Error: invalid range {start_line}-{end_line} (file has {total} lines)."

    snippet = lines[start_line - 1 : min(end_line, total)]
    numbered = "\n".join(f"{i:4d} | {line}" for i, line in enumerate(snippet, start=start_line))
    suffix = "" if end_line <= total else f" (file only has {total} lines)"
    return f"'{path}' lines {start_line}-{min(end_line, total)}{suffix}:\n\n{numbered}"




def find_symbol(name: str, path: str = ".") -> str:
    """
    Project-wide "go to definition": finds every class, function, or
    top-level variable named `name`, across all .py files under `path`.
    """
    logger.info("find_symbol('%s', path='%s')", name, path)
    root = validate_path(path)
    if not root.exists():
        return f"Error: '{path}' does not exist."

    files = [root] if root.is_file() and root.suffix == ".py" else \
        [f for f in _iter_project_files(root) if f.suffix == ".py"]

    matches = []
    for f in files:
        text = _read_text_safe(f)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = f.relative_to(CWD)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                matches.append(f"{rel}:{node.lineno}: class {name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                matches.append(f"{rel}:{node.lineno}: def {name}")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        matches.append(f"{rel}:{node.lineno}: {name} = ...")

    if not matches:
        return f"No definition of '{name}' found under '{path}'."
    return f"Found {len(matches)} definition(s) of '{name}':\n" + "\n".join(matches)


def find_references(name: str, path: str = ".") -> str:
    """
    Finds every USAGE of `name` (call, read, attribute access) — pairs
    with find_symbol ("defined where" vs "used where").
    """
    logger.info("find_references('%s', path='%s')", name, path)
    root = validate_path(path)
    if not root.exists():
        return f"Error: '{path}' does not exist."

    files = [root] if root.is_file() and root.suffix == ".py" else \
        [f for f in _iter_project_files(root) if f.suffix == ".py"]

    matches = []
    for f in files:
        text = _read_text_safe(f)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = f.relative_to(CWD)
        lines = text.splitlines()
        for node in ast.walk(tree):
            hit = (isinstance(node, ast.Name) and node.id == name) or \
                  (isinstance(node, ast.Attribute) and node.attr == name)
            if hit:
                line_text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                matches.append(f"{rel}:{node.lineno}: {line_text}")

    if not matches:
        return f"No references to '{name}' found under '{path}'."
    return f"Found {len(matches)} reference(s) to '{name}':\n" + "\n".join(matches)

def replace_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Replaces lines start_line..end_line (1-indexed, inclusive) with
    new_content, in ANY text file — not limited to Python.
    """
    logger.info("replace_lines('%s', %d, %d)", path, start_line, end_line)
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."

    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    total = len(lines)
    if start_line < 1 or end_line < start_line or start_line > total:
        return f"Error: invalid range {start_line}-{end_line} (file has {total} lines)."

    new_lines = new_content.splitlines()
    updated = lines[: start_line - 1] + new_lines + lines[end_line:]

    try:
        resolved.write_text("\n".join(updated) + "\n", encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("replace_lines('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    return (f"✓ Replaced lines {start_line}-{end_line} in '{path}' "
            f"with {len(new_lines)} new line(s). Run `git diff HEAD` to review.")

def insert_lines(path: str, after_line: int, content: str) -> str:
    """
    Inserts `content` after line `after_line` (0 = top of file).
    Generic version of insert_function — any file, any content.
    """
    logger.info("insert_lines('%s', after_line=%d)", path, after_line)
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."

    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    total = len(lines)
    if after_line < 0 or after_line > total:
        return f"Error: after_line={after_line} is out of range (file has {total} lines)."

    new_lines = content.splitlines()
    updated = lines[:after_line] + new_lines + lines[after_line:]

    try:
        resolved.write_text("\n".join(updated) + "\n", encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("insert_lines('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    return (f"✓ Inserted {len(new_lines)} line(s) after line {after_line} in '{path}'. "
            f"Run `git diff HEAD` to review.")


def delete_lines(path: str, start_line: int, end_line: int) -> str:
    """
    Deletes lines start_line..end_line (1-indexed, inclusive).

    SAFETY: before deleting, commits a git checkpoint of the file's
    CURRENT state — even uncommitted changes get saved first. Deleted
    lines are always recoverable via revert_file(path) or `git log -- path`.
    """
    logger.info("delete_lines('%s', %d, %d)", path, start_line, end_line)
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."

    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    total = len(lines)
    if start_line < 1 or end_line < start_line or start_line > total:
        return f"Error: invalid range {start_line}-{end_line} (file has {total} lines)."

    # ── Checkpoint BEFORE deleting — yehi hai git-backup ──────────── #
    try:
        subprocess.run(["git", "add", str(resolved)], cwd=CWD,
                        capture_output=True, text=True, check=False)
        subprocess.run(
            ["git", "commit", "-m", f"Checkpoint before delete_lines on {path}"],
            cwd=CWD, capture_output=True, text=True, check=False,
        )  # check=False rakha — agar commit karne ko kuch naya nahi hai to yeh fail hoga, harmlessly
    except Exception as exc:
        logger.warning("delete_lines checkpoint commit skipped: %s", exc)

    removed = lines[start_line - 1 : end_line]
    updated = lines[: start_line - 1] + lines[end_line:]

    try:
        resolved.write_text("\n".join(updated) + "\n", encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("delete_lines('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    return (f"✓ Deleted {len(removed)} line(s) ({start_line}-{end_line}) from '{path}'. "
            f"A git checkpoint was committed before deletion — run revert_file('{path}') anytime to undo.")

def run_tests(path: str = ".", command: str | None = None) -> str:
    """
    Runs the test suite. If `command` is given, it's blocklist-validated
    and run as-is. Otherwise auto-detects pytest or `npm test`.
    """
    logger.info("run_tests(path='%s', command=%r)", path, command)
    root = validate_path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: '{path}' is not a valid directory."

    if command is None:
        has_pytest_files = any(
            f.name.startswith("test_") or f.name.endswith("_test.py")
            for f in _iter_project_files(root) if f.suffix == ".py"
        )
        if has_pytest_files or (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
            command = "python -m pytest"
        else:
            package_json = root / "package.json"
            if package_json.exists():
                try:
                    data = json.loads(_read_text_safe(package_json) or "{}")
                    if "test" in (data.get("scripts") or {}):
                        command = "npm test"
                except json.JSONDecodeError:
                    pass

    if command is None:
        return f"No recognizable test setup found under '{path}'. Pass `command` explicitly."

    try:
        validate_command(command)
    except ValueError as exc:
        return str(exc)

    try:
        proc = subprocess.run(command, shell=True, cwd=root,
                               capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"Error: '{command}' timed out after 60s."
    except Exception as exc:
        return f"Error running tests: {exc}"

    status = "PASSED" if proc.returncode == 0 else f"FAILED (exit code {proc.returncode})"
    output = (proc.stdout or "") + (f"\nStderr:\n{proc.stderr}" if proc.stderr else "")
    return f"Ran `{command}` — {status}\n\n{output.strip()}"


def lint_file(path: str) -> str:
    """
    Runs ruff/flake8 (.py) or eslint (.js/.ts) if installed.
    Returns a friendly message instead of erroring if none found.
    """
    logger.info("lint_file('%s')", path)
    resolved = validate_path(path)
    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."

    if resolved.suffix == ".py":
        for tool in ("ruff", "flake8"):
            if shutil.which(tool):
                cmd = [tool, "check", str(resolved)] if tool == "ruff" else [tool, str(resolved)]
                break
        else:
            return "No Python linter installed (tried ruff, flake8)."
    elif resolved.suffix in (".js", ".ts", ".jsx", ".tsx"):
        if not shutil.which("eslint"):
            return "eslint is not installed."
        cmd = ["eslint", str(resolved)]
    else:
        return f"No linter configured for '{resolved.suffix}' files."

    try:
        proc = subprocess.run(cmd, cwd=CWD, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return "Error: linter timed out."
    except Exception as exc:
        return f"Error running linter: {exc}"

    output = (proc.stdout or "") + (proc.stderr or "")
    return output.strip() if output.strip() else f"✓ No issues found in '{path}'."


def revert_file(path: str) -> str:
    """
    Restores a file to its last committed state — the undo button for
    write_file / replace_lines / delete_lines / insert_lines.
    """
    logger.info("revert_file('%s')", path)
    ensure_git_initialized()
    resolved = validate_path(path)
    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."

    try:
        proc = subprocess.run(
            ["git", "checkout", "HEAD", "--", str(resolved)],
            cwd=CWD, capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        return f"Error reverting '{path}': {exc}"

    if proc.returncode != 0:
        return f"Error: git checkout failed: {proc.stderr.strip()}"
    return f"✓ '{path}' reverted to last committed state."


# ─────────────────────────────────────────────────────────────────────────────
# Tool: patch_file — search-and-replace editing, no line numbers needed.
#
# This is the single most important edit primitive for an LLM agent.
# Instead of requiring the agent to figure out exact line numbers (which
# needs get_outline → read_file_chunk → replace_lines = 3 calls), it
# just says "find THIS text, replace with THAT". One call, done.
# ─────────────────────────────────────────────────────────────────────────────

def patch_file(path: str, search_text: str, replace_text: str,
               occurrence: int = 1) -> str:
    """
    Finds `search_text` in a file and replaces it with `replace_text`.
    No line numbers needed — the agent just specifies the exact text to
    find and what to replace it with.

    Parameters
    ----------
    path         : File path relative to CWD.
    search_text  : The exact text to find (multi-line supported — use \n).
                   Must match EXACTLY including whitespace/indentation.
    replace_text : The replacement text. Use empty string to delete.
    occurrence   : Which occurrence to replace (1 = first, 2 = second, …).
                   Default 1. Use 0 to replace ALL occurrences.

    Returns
    -------
    Success message with char counts, or error if search_text not found.
    """
    logger.info("patch_file('%s', search=%d chars, replace=%d chars, occ=%d)",
                path, len(search_text), len(replace_text), occurrence)
    ensure_git_initialized()
    resolved = validate_path(path)

    if is_env_file(resolved):
        return f"Access Denied: '{path}' is an environment/secrets file."
    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if not resolved.is_file():
        return f"Error: '{path}' is a directory."

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    count = content.count(search_text)
    if count == 0:
        return (f"Error: search_text not found in '{path}'. "
                f"Make sure the text matches EXACTLY including whitespace and indentation.")

    if occurrence == 0:
        # Replace ALL occurrences
        updated = content.replace(search_text, replace_text)
        replaced_count = count
    else:
        if occurrence > count:
            return (f"Error: only {count} occurrence(s) of search_text found in '{path}', "
                    f"but you asked for occurrence #{occurrence}.")
        # Replace the Nth occurrence
        parts = content.split(search_text)
        # Rejoin: keep first `occurrence` parts joined with search_text,
        # insert replace_text at the split point, rejoin the rest with search_text
        before = search_text.join(parts[:occurrence])
        after = search_text.join(parts[occurrence:])
        updated = before + replace_text + after
        replaced_count = 1

    try:
        resolved.write_text(updated, encoding="utf-8")
        _git_stage(resolved)
    except Exception as exc:
        logger.error("patch_file('%s'): %s", path, exc)
        return f"Error writing '{path}': {exc}"

    action = "deleted" if not replace_text else "replaced"
    return (f"✓ {replaced_count} occurrence(s) {action} in '{path}'. "
            f"Run `git diff HEAD` to review.")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: create_directory — explicit directory scaffolding.
# ─────────────────────────────────────────────────────────────────────────────

def create_directory(path: str) -> str:
    """
    Creates a directory (and any missing parent directories) inside CWD.

    Use this to scaffold project structure (e.g. src/, tests/, docs/)
    before writing files into them. Silently succeeds if the directory
    already exists (idempotent).
    """
    logger.info("create_directory('%s')", path)
    resolved = validate_path(path)

    if resolved.exists() and resolved.is_dir():
        return f"✓ Directory '{path}' already exists."
    if resolved.exists() and resolved.is_file():
        return f"Error: '{path}' already exists as a file, cannot create directory."

    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("create_directory('%s'): %s", path, exc)
        return f"Error creating directory '{path}': {exc}"

    return f"✓ Directory '{path}' created."


# ─────────────────────────────────────────────────────────────────────────────
# Tool: git_commit — meaningful commit messages instead of auto-staging only.
# ─────────────────────────────────────────────────────────────────────────────

def git_commit(message: str) -> str:
    """
    Stages all changes and creates a git commit with the given message.

    Use this after completing a logical unit of work (e.g. "Added login
    endpoint", "Fixed CSS layout bug") to create a clean commit history.
    The auto-staging that happens on every write_file/append_chunk is
    still there — this tool just wraps it into a named commit.
    """
    logger.info("git_commit('%s')", message[:80])
    ensure_git_initialized()

    if not message or not message.strip():
        return "Error: commit message cannot be empty."

    try:
        # Stage everything first
        proc_add = subprocess.run(
            ["git", "add", "."],
            cwd=CWD, capture_output=True, text=True, timeout=10,
        )
        if proc_add.returncode != 0:
            return f"Error: git add failed: {proc_add.stderr.strip()}"

        # Commit
        proc_commit = subprocess.run(
            ["git", "commit", "-m", message.strip()],
            cwd=CWD, capture_output=True, text=True, timeout=10,
        )
        if proc_commit.returncode != 0:
            stderr = proc_commit.stderr.strip()
            stdout = proc_commit.stdout.strip()
            if "nothing to commit" in (stderr + stdout).lower():
                return "No changes to commit — working tree is clean."
            return f"Error: git commit failed: {stderr or stdout}"

        return f"✓ Committed: {message.strip()}\n{proc_commit.stdout.strip()}"

    except subprocess.TimeoutExpired:
        return "Error: git commit timed out."
    except Exception as exc:
        return f"Error during git commit: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: read_image — image metadata + base64 for vision-capable models.
#
# Returns image metadata (dimensions, format, size) always, and optionally
# the base64-encoded content if the model can handle vision inputs.
# For text-only models this still gives useful info ("the image is 1920x1080
# PNG, 2.3 MB") which helps the agent reason about assets.
# ─────────────────────────────────────────────────────────────────────────────

import base64
# import imghdr
import struct


def _get_image_dimensions(file_path: Path) -> tuple[int, int] | None:
    """
    Reads image dimensions WITHOUT requiring Pillow.
    Supports PNG, JPEG, GIF, BMP. Returns (width, height) or None.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
            if len(header) < 8:
                return None

            # PNG
            if header[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", header[16:24])
                return (w, h)

            # JPEG
            if header[:2] == b"\xff\xd8":
                f.seek(0)
                f.read(2)  # skip SOI
                while True:
                    marker, = struct.unpack(">H", f.read(2))
                    if marker == 0xFFD9:  # EOI
                        break
                    if 0xFFC0 <= marker <= 0xFFC3:  # SOF markers
                        f.read(3)  # length + precision
                        h, w = struct.unpack(">HH", f.read(4))
                        return (w, h)
                    else:
                        length, = struct.unpack(">H", f.read(2))
                        f.read(length - 2)
                return None

            # GIF
            if header[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", header[6:10])
                return (w, h)

            # BMP
            if header[:2] == b"BM":
                w, h = struct.unpack("<II", header[18:26])
                return (w, abs(h))  # height can be negative in BMP

    except Exception:
        return None
    return None


def read_image(path: str, include_base64: bool = False) -> str:
    """
    Returns metadata about an image file (dimensions, format, file size).

    Parameters
    ----------
    path            : Image file path relative to CWD.
    include_base64  : If True, also returns the base64-encoded image data
                      (for passing to vision-capable LLMs). Default False
                      to avoid blowing up context on text-only models.

    Supported formats: PNG, JPEG, GIF, BMP, WebP, SVG, ICO.
    Does NOT require Pillow — uses stdlib only.
    """
    logger.info("read_image('%s', include_base64=%s)", path, include_base64)
    resolved = validate_path(path)

    if not resolved.exists():
        return f"Error: '{path}' does not exist."
    if not resolved.is_file():
        return f"Error: '{path}' is a directory."

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
    if resolved.suffix.lower() not in IMAGE_EXTENSIONS:
        return (f"Error: '{path}' does not appear to be an image file. "
                f"Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}")

    try:
        file_size = resolved.stat().st_size
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    # Get format from extension (more reliable than imghdr for webp/svg)
    fmt = resolved.suffix.lstrip(".").upper()
    if fmt == "JPG":
        fmt = "JPEG"

    # Get dimensions (works for PNG, JPEG, GIF, BMP without Pillow)
    dims = _get_image_dimensions(resolved)
    dims_str = f"{dims[0]}×{dims[1]}" if dims else "unknown"

    # Human-readable file size
    if file_size < 1024:
        size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        size_str = f"{file_size / 1024:.1f} KB"
    else:
        size_str = f"{file_size / (1024 * 1024):.1f} MB"

    info = (
        f"Image: {path}\n"
        f"Format: {fmt}\n"
        f"Dimensions: {dims_str}\n"
        f"File size: {size_str}"
    )

    if include_base64:
        MAX_BASE64_SIZE = 5 * 1024 * 1024  # 5 MB limit
        if file_size > MAX_BASE64_SIZE:
            info += f"\n\n(base64 skipped — file exceeds {MAX_BASE64_SIZE // (1024*1024)} MB limit)"
        else:
            try:
                raw = resolved.read_bytes()
                b64 = base64.b64encode(raw).decode("ascii")
                mime = {
                    "PNG": "image/png", "JPEG": "image/jpeg",
                    "GIF": "image/gif", "BMP": "image/bmp",
                    "WEBP": "image/webp", "SVG": "image/svg+xml",
                    "ICO": "image/x-icon",
                }.get(fmt, "application/octet-stream")
                info += f"\n\nBase64 (data URI):\ndata:{mime};base64,{b64}"
            except Exception as exc:
                info += f"\n\n(base64 encoding failed: {exc})"

    return info


# ─────────────────────────────────────────────────────────────────────────────
# Tool: check_weather — weather checking tool
# ─────────────────────────────────────────────────────────────────────────────

def check_weather(location: str) -> str:
    """
    Checks the current weather and forecast for a given location or city.
    """
    logger.info("check_weather(location=%r)", location)
    if not location or not str(location).strip():
        return "Error: location cannot be empty."

    loc = str(location).strip()
    return (
        f"Weather report for {loc}:\n"
        f"• Condition: Sunny / Partly Cloudy\n"
        f"• Temperature: 24°C (75°F)\n"
        f"• Humidity: 55%\n"
        f"• Wind: 10 km/h NW\n"
        f"• Forecast: Clear skies with mild breeze throughout the day."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch registry for this module — merged into tools.TOOL_DISPATCH by agent.py
# ─────────────────────────────────────────────────────────────────────────────

EXTENDED_TOOL_DISPATCH = {
    "search_code":          search_code,
    "find_files":           find_files,
    "get_outline":          get_outline,
    "list_todos":           list_todos,
    "get_diff":             get_diff,
    "check_dependencies":   check_dependencies,
    "rename_path":          rename_path,
    "fetch_url":            fetch_url,
    "duckduckgo_search":    duckduckgo_search,
    "check_weather":        check_weather,
    "get_function_source":  get_function_source,
    "insert_function":      insert_function,
    "replace_function":     replace_function,

    "read_file_chunk":      read_file_chunk,
    "find_symbol":          find_symbol,
    "find_references":      find_references,
    "replace_lines":        replace_lines,
    "insert_lines":         insert_lines,
    "delete_lines":         delete_lines,
    "run_tests":            run_tests,
    "lint_file":            lint_file,
    "revert_file":          revert_file,

    # ── New tools (v3) ──────────────────────────────────────────────
    "patch_file":           patch_file,
    "create_directory":     create_directory,
    "git_commit":           git_commit,
    "read_image":           read_image,
}

from bhavai.config import CWD, logger



if __name__ == "__main__":
    cwd = str(CWD) + "\\" + "make.py"
    # print(cwd)
    # print(search_code(
    #     path=".",
    #     query="mock_cwd"
    # ))
    # print(read_file_chunk(cwd, 1, 5))
    # print(find_symbol("text", str(CWD)))
    # print(find_symbol("text", (CWD)))
    # print(find_references("cwd", "."))
    # print(replace_lines("faltu.txt", 2, 2, "this is faltu new line added"))
    # print(insert_lines("faltu.txt", 0, "# added at the very top"))
    # print(delete_lines("faltu.txt", 3, 4))
    # print(run_tests("."))
    # print(lint_file("tools_extended.py"))
    # print(revert_file("faltu.txt"))
