from pathlib import Path
import re
from bhavai.config import PROMPTS_DIR, ensure_prompts_dir

_NAME_RE = re.compile(r'^name:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_DESC_RE = re.compile(r'^description:\s*"(.+?)"\s*$', re.MULTILINE | re.DOTALL)


def _parse_skill_header(skill_file: Path, max_desc_len: int = 220) -> tuple[str, str]:
    """
    Parses title and description from frontmatter or markdown content.
    """
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        return skill_file.stem, "(error reading skill file)"

    name_match = _NAME_RE.search(text)
    desc_match = _DESC_RE.search(text)

    title = name_match.group(1).strip() if name_match else ""
    desc = desc_match.group(1).strip() if desc_match else ""

    # Fallback title: first markdown heading or filename
    if not title:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#"):
                title = s.lstrip("#").replace("Skill:", "").strip()
                break
        if not title:
            title = skill_file.stem

    # Fallback description: first paragraph after headings/frontmatter
    if not desc:
        in_fm = False
        desc_lines = []
        for line in text.splitlines():
            s = line.strip()
            if s == "---":
                in_fm = not in_fm
                continue
            if in_fm or s.startswith("#"):
                continue
            if s:
                desc_lines.append(s)
            elif desc_lines:
                break
        desc = " ".join(desc_lines).strip() if desc_lines else "(no description found)"

    desc = " ".join(desc.split())  # Flatten newlines/spaces
    if len(desc) > max_desc_len:
        desc = desc[:max_desc_len].rsplit(" ", 1)[0] + "..."

    return title, desc


def list_available_skills(cwd: Path = None) -> list[dict]:
    """
    Discovers all skill files in ~/.bhavai/config/prompts/ as well as
    any local workspace skills in cwd/.bhavai/skills/.
    """
    skills = []
    seen_paths = set()

    prompts_dir = ensure_prompts_dir()
    if prompts_dir.exists():
        for skill_file in sorted(prompts_dir.glob("*.md")):
            if skill_file.is_file() and skill_file.resolve() not in seen_paths:
                title, desc = _parse_skill_header(skill_file)
                skills.append({
                    "id": skill_file.stem,
                    "name": skill_file.stem,
                    "title": title,
                    "description": desc,
                    "path": skill_file,
                    "path_str": str(skill_file),
                })
                seen_paths.add(skill_file.resolve())

    if cwd:
        local_skills_dir = cwd / ".bhavai" / "skills"
        if local_skills_dir.exists():
            for skill_folder in sorted(local_skills_dir.iterdir()):
                skill_file = skill_folder / "SKILL.md"
                if skill_file.is_file() and skill_file.resolve() not in seen_paths:
                    title, desc = _parse_skill_header(skill_file)
                    skills.append({
                        "id": skill_folder.name,
                        "name": skill_folder.name,
                        "title": title,
                        "description": desc,
                        "path": skill_file,
                        "path_str": str(skill_file),
                    })
                    seen_paths.add(skill_file.resolve())

    return skills


def discover_skills_from_dot_bhavai(cwd: Path = None) -> str:
    """
    Returns the dynamic skill discovery instruction block for the system prompt.
    The main system prompt does not preload the full list of skills.
    Instead, it instructs the agent to check ~/.bhavai/config/prompts/ dynamically
    when faced with an unfamiliar command or capability.
    """
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "DYNAMIC SKILLS & UNFAMILIAR CAPABILITIES\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "If the user asks you to perform a task, run a command, or handle a capability that is not part of your standard file/code navigation tools:\n"
        "1. Check the skills directory inside `~/.bhavai/config/prompts/` (e.g. use `list_folder(path=\"~/.bhavai/config/prompts\")` or inspect candidate `<SkillName>.md` files).\n"
        "2. Match the user request against the available skill files by skill name or description.\n"
        "3. If a matching skill is found:\n"
        "   - Read that skill file using `read_file(path=\"~/.bhavai/config/prompts/<SkillName>.md\")`.\n"
        "   - Follow the instructions, tool mappings, and workflow described in that skill to select and execute the corresponding tool.\n"
        "   - Return the result to the user.\n"
        "4. If NO matching skill is found in `~/.bhavai/config/prompts/` by name or description:\n"
        "   - Do NOT guess, hallucinate, or execute unrelated tools.\n"
        "   - Call `final_answer` and inform the user that you cannot perform this task (\"I cannot perform this task\" / \"Mai yeh kaam nahi kar sakta\")."
    )


if __name__ == "__main__":
    from bhavai.config import CWD
    # print(discover_skills_from_dot_bhavai(CWD))
    print(list_available_skills(CWD))