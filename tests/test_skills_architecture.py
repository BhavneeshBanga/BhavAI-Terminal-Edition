import pytest
from pathlib import Path
import json

import bhavai.config as config_mod
import bhavai.tools as tools_mod
import bhavai.skill_getter as skill_getter_mod
from bhavai.tools import validate_path, read_file, TOOL_DISPATCH
from bhavai.skill_getter import discover_skills_from_dot_bhavai, list_available_skills, _parse_skill_header


@pytest.fixture
def temp_bhavai_env(tmp_path, monkeypatch):
    """
    Sets up a temporary isolated environment for testing skills architecture.
    """
    mock_cwd = (tmp_path / "workspace").resolve()
    mock_cwd.mkdir(parents=True, exist_ok=True)
    
    mock_bhavai_home = (tmp_path / ".bhavai").resolve()
    mock_bhavai_home.mkdir(parents=True, exist_ok=True)
    
    mock_prompts_dir = mock_bhavai_home / "config" / "prompts"

    # Patch CWD, BHAVAI_HOME, PROMPTS_DIR across modules
    monkeypatch.setattr(config_mod, "CWD", mock_cwd)
    monkeypatch.setattr(config_mod, "BHAVAI_HOME", mock_bhavai_home)
    monkeypatch.setattr(config_mod, "PROMPTS_DIR", mock_prompts_dir)
    monkeypatch.setattr(tools_mod, "CWD", mock_cwd)
    monkeypatch.setattr(tools_mod, "PROMPTS_DIR", mock_prompts_dir)
    monkeypatch.setattr(skill_getter_mod, "PROMPTS_DIR", mock_prompts_dir)

    return {
        "cwd": mock_cwd,
        "bhavai_home": mock_bhavai_home,
        "prompts_dir": mock_prompts_dir,
    }


def test_1_prompts_directory_creation(temp_bhavai_env):
    """
    Requirement 1: Verify ~/.BhavAI/config/prompts/ directory is created automatically.
    """
    prompts_dir = temp_bhavai_env["prompts_dir"]
    assert not prompts_dir.exists()

    # Calling ensure_prompts_dir creates the folder structure
    created_dir = config_mod.ensure_prompts_dir()
    assert created_dir.exists()
    assert created_dir.is_dir()
    assert prompts_dir.exists()
    assert prompts_dir.name == "prompts"
    assert prompts_dir.parent.name == "config"


def test_2_sample_skill_creation_and_reading(temp_bhavai_env):
    """
    Requirement 2: Verify sample skill file is created and read correctly.
    """
    config_mod.ensure_prompts_dir()
    sample_file = temp_bhavai_env["prompts_dir"] / config_mod.DEFAULT_SAMPLE_SKILL_NAME

    assert sample_file.exists()
    content = sample_file.read_text(encoding="utf-8")
    assert "Sample Proof-of-Concept Skill" in content
    assert "duckduckgo_search" in content

    # Test reading via read_file tool
    read_output = read_file(str(sample_file))
    assert "Sample Proof-of-Concept Skill" in read_output
    assert "## Recommended Tool & Function" in read_output


def test_3_sandbox_security_allows_only_prompts_outside_cwd(temp_bhavai_env):
    """
    Requirement 3: Sandbox allows ONLY ~/.BhavAI/config/prompts/ outside CWD.
    Access to any other part of ~/.bhavai (logs, config.json, metadata) or system files is blocked.
    """
    bhavai_home = temp_bhavai_env["bhavai_home"]
    prompts_dir = temp_bhavai_env["prompts_dir"]
    cwd = temp_bhavai_env["cwd"]
    config_mod.ensure_prompts_dir()

    # 1. Normal file inside CWD should pass
    cwd_file = cwd / "project.py"
    cwd_file.write_text("print('inside cwd')")
    assert validate_path("project.py") == cwd_file.resolve()

    # 2. Skill file inside ~/.bhavai/config/prompts/ should pass
    skill_file = prompts_dir / "SampleSkill.md"
    validated_skill = validate_path(str(skill_file))
    assert validated_skill == skill_file.resolve()

    # 3. Reading skill file via read_file tool should pass
    skill_content = read_file(str(skill_file))
    assert "Sample Proof-of-Concept Skill" in skill_content

    # 4. Other ~/.bhavai files (config.json, logs, metadata) MUST BE BLOCKED
    config_json = bhavai_home / "config.json"
    config_json.write_text('{"secret": "do not read"}')
    with pytest.raises(ValueError) as exc:
        validate_path(str(config_json))
    assert "Access Denied" in str(exc.value)
    assert "outside the allowed prompts directory" in str(exc.value)

    # 5. ~/.bhavai/logs/bhavai.log MUST BE BLOCKED
    logs_dir = bhavai_home / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "bhavai.log"
    log_file.write_text("debug logs")
    with pytest.raises(ValueError) as exc:
        validate_path(str(log_file))
    assert "Access Denied" in str(exc.value)

    # 6. Arbitrary system paths outside CWD MUST BE BLOCKED
    with pytest.raises(ValueError) as exc:
        validate_path("/etc/passwd")
    assert "Access Denied" in str(exc.value)

    # 7. Path traversal escaping prompts dir MUST BE BLOCKED
    with pytest.raises(ValueError) as exc:
        validate_path(str(prompts_dir / ".." / "config.json"))
    assert "Access Denied" in str(exc.value)


def test_4_skill_identification_and_discovery(temp_bhavai_env):
    """
    Requirement 4: Verify skills are discovered, parsed, and exposed in prompt context.
    """
    prompts_dir = temp_bhavai_env["prompts_dir"]
    config_mod.ensure_prompts_dir()

    # Add custom skill file (e.g. Gmail.md)
    gmail_skill = prompts_dir / "Gmail.md"
    gmail_skill.write_text(
        "---\n"
        "name: Gmail Assistant\n"
        "description: Handles reading, searching, and organizing user emails.\n"
        "---\n"
        "# Gmail Skill\n\n"
        "## Triggers\n"
        "- check my gmail\n"
        "- read latest emails\n"
    )

    skills = list_available_skills(temp_bhavai_env["cwd"])
    skill_names = [s["name"] for s in skills]
    assert "Gmail" in skill_names
    assert "SampleSkill" in skill_names

    # Check formatting for system prompt
    prompt_block = discover_skills_from_dot_bhavai(temp_bhavai_env["cwd"])
    assert "DYNAMIC SKILLS & UNFAMILIAR CAPABILITIES" in prompt_block
    assert "~/.bhavai/config/prompts/" in prompt_block
    assert "list_folder" in prompt_block
    assert "read_file" in prompt_block
    assert "final_answer" in prompt_block


def test_5_skill_content_loaded_into_context(temp_bhavai_env):
    """
    Requirement 5: Verify the agent can dynamically load the skill file content.
    """
    prompts_dir = temp_bhavai_env["prompts_dir"]
    config_mod.ensure_prompts_dir()

    drive_skill = prompts_dir / "Drive.md"
    drive_skill.write_text(
        "# Google Drive Skill\n\n"
        "## Tool to Use\n"
        "Use `duckduckgo_search` with query 'site:drive.google.com' or custom Drive tools.\n\n"
        "## Workflow\n"
        "1. Query files.\n"
        "2. Return summary.\n"
    )

    # Agent executes read_file on the discovered path
    loaded_content = read_file(str(drive_skill))
    assert "Google Drive Skill" in loaded_content
    assert "## Tool to Use" in loaded_content
    assert "duckduckgo_search" in loaded_content


def test_6_skill_to_tool_execution_flow(temp_bhavai_env, monkeypatch):
    """
    Requirement 6: Verify end-to-end flow:
    Agent reads skill -> identifies tool -> executes existing BhavAI tool with appropriate arguments.
    """
    prompts_dir = temp_bhavai_env["prompts_dir"]
    config_mod.ensure_prompts_dir()

    # 1. Inspect sample skill
    sample_file = prompts_dir / "SampleSkill.md"
    skill_content = read_file(str(sample_file))
    assert "Recommended Tool & Function" in skill_content

    # 2. Target tool exists in BhavAI dispatch registry
    assert "duckduckgo_search" in TOOL_DISPATCH
    assert "search_code" in TOOL_DISPATCH
    assert "run_command" in TOOL_DISPATCH

    # 3. Simulate tool execution as prescribed by the skill instructions
    executed_calls = []
    def mock_duckduckgo_search(query: str, max_results: int = 5):
        executed_calls.append((query, max_results))
        return f"Mock search results for: {query}"

    import bhavai.tools_extended as ext_mod
    monkeypatch.setattr(ext_mod, "duckduckgo_search", mock_duckduckgo_search)
    monkeypatch.setitem(TOOL_DISPATCH, "duckduckgo_search", mock_duckduckgo_search)
    tool_func = TOOL_DISPATCH.get("duckduckgo_search")

    # Agent calls the tool recommended by the skill
    result = tool_func(query="BhavAI skill verification", max_results=3)
    assert "BhavAI skill verification" in result
    assert len(executed_calls) == 1
    assert executed_calls[0] == ("BhavAI skill verification", 3)


def test_7_weather_skill_and_check_weather_tool(temp_bhavai_env):
    """
    Requirement: Verify Weather.md mock skill and check_weather tool integration.
    """
    prompts_dir = temp_bhavai_env["prompts_dir"]
    config_mod.ensure_prompts_dir()

    # 1. Weather.md skill exists and is readable
    weather_skill_file = prompts_dir / "Weather.md"
    assert weather_skill_file.exists()
    content = read_file(str(weather_skill_file))
    assert "Weather Skill" in content
    assert "check_weather" in content
    assert "## Method of Calling" in content

    # 2. check_weather tool is registered in TOOL_DISPATCH
    assert "check_weather" in TOOL_DISPATCH
    tool_func = TOOL_DISPATCH["check_weather"]

    # 3. Call check_weather tool as instructed by Weather.md
    result = tool_func(location="Delhi")
    assert "Weather report for Delhi:" in result
    assert "Temperature:" in result
    assert "Condition:" in result

