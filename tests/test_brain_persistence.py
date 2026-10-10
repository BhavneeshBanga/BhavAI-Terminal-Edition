import json
import pytest
import inspect
from pathlib import Path
from bhavai.config import BHAVAI_HOME, BRAIN_DIR, ensure_brain_dir
from bhavai.memory import ConversationMemory
from bhavai.agent import _run_agent_loop, run_agent_loop_plan, run_agent_loop_autonomous

def test_max_steps_default_60():
    """Verify max_steps defaults to 60 across all agent loop entry points."""
    sig_core = inspect.signature(_run_agent_loop)
    assert sig_core.parameters["max_steps"].default == 60

    sig_plan = inspect.signature(run_agent_loop_plan)
    assert sig_plan.parameters["max_steps"].default == 60

    sig_auto = inspect.signature(run_agent_loop_autonomous)
    assert sig_auto.parameters["max_steps"].default == 60

def test_brain_directory_creation():
    """Verify ensure_brain_dir creates ~/.bhavai/brain directory."""
    path = ensure_brain_dir()
    assert path.exists()
    assert path.is_dir()
    assert path == BHAVAI_HOME / "brain"

def test_conversation_memory_json_save_and_load(tmp_path):
    """Verify ConversationMemory save_to_json and load_from_json roundtrip."""
    mem = ConversationMemory()
    mem.add_message("user", "Hello BhavAI!")
    mem.add_message("assistant", "Hello! How can I assist you?")

    json_path = tmp_path / "test_hash.json"
    mem.save_to_json(json_path)

    assert json_path.exists()
    saved_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(saved_data) == 2
    assert saved_data[0]["content"] == "Hello BhavAI!"

    new_mem = ConversationMemory()
    assert len(new_mem.messages) == 0
    success = new_mem.load_from_json(json_path)
    assert success is True
    assert len(new_mem.messages) == 2
    assert new_mem.messages[0]["role"] == "user"
    assert new_mem.messages[1]["content"] == "Hello! How can I assist you?"
