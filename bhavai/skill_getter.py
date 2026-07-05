from pathlib import Path

# def _parse_skill_header(skill_file: Path, max_desc_len: int = 160) -> tuple[str, str]:
#     lines = skill_file.read_text(encoding="utf-8").splitlines()

#     title = "Untitled Skill"
#     desc_lines = []
#     found_title = False

#     for line in lines:
#         stripped = line.strip()
#         if not found_title:
#             if stripped.startswith("#"):
#                 title = stripped.lstrip("#").replace("Skill:", "").strip()
#                 found_title = True
#             continue
#         if stripped.startswith("#"):
#             break  # next heading aa gaya, description khatam
#         if stripped:
#             desc_lines.append(stripped)

#     desc = " ".join(desc_lines).strip()
#     if len(desc) > max_desc_len:
#         desc = desc[:max_desc_len].rsplit(" ", 1)[0] + "..."

#     return title, desc or "(no description found)"
import re

_NAME_RE = re.compile(r'^name:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_DESC_RE = re.compile(r'^description:\s*"(.+?)"\s*$', re.MULTILINE | re.DOTALL)

def _parse_skill_header(skill_file: Path, max_desc_len: int = 220) -> tuple[str, str]:
    text = skill_file.read_text(encoding="utf-8")

    name_match = _NAME_RE.search(text)
    desc_match = _DESC_RE.search(text)

    title = name_match.group(1).strip() if name_match else skill_file.parent.name
    desc = desc_match.group(1).strip() if desc_match else "(no description found)"

    desc = " ".join(desc.split())  # multi-line description ko ek line mein flatten karo
    if len(desc) > max_desc_len:
        desc = desc[:max_desc_len].rsplit(" ", 1)[0] + "..."

    return title, desc




def discover_skills_from_dot_bhavai(cwd: Path) -> str:
    skills_dir = cwd / ".bhavai" / "skills"
    if not skills_dir.exists():
        return ""

    entries = []
    for skill_folder in sorted(skills_dir.iterdir()):
        skill_file = skill_folder / "SKILL.md"
        if not skill_file.is_file():
            continue
        title, desc = _parse_skill_header(skill_file)
        entries.append(
            f"- {skill_folder.name}: {title} — {desc}\n"
            f"  Full file: {skill_file}"
        )

    if not entries:
        return ""

    return (
    "AVAILABLE SKILLS:\n"
    + "\n".join(entries)
    + "\nIf a task matches a skill, read its SKILL.md first and follow it."
)



CWD = Path.cwd().resolve()
if __name__ == "__main__":
    print(discover_skills_from_dot_bhavai(CWD))
    pass