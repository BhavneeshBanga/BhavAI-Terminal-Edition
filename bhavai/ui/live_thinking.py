import threading
import time
import math
import re
from typing import Optional
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.style import Style

from bhavai.ui.shimmer import COLOR_PRESETS, _shimmer_frame

console = Console()


def extract_partial_thought(raw_text: str) -> Optional[str]:
    """
    Extracts the thought text in real time from streaming LLM output.
    Supports:
      1. Reasoning models: <think>...</think>
      2. JSON schema: {"thought": "..."}
      3. XML tool_call with pre-text reasoning or tool name
      4. Plain natural language reasoning
    """
    if not raw_text or not raw_text.strip():
        return None

    # 1. Check for <think> tags (DeepSeek-R1 / Qwen / thinking models)
    if "<think>" in raw_text:
        start = raw_text.find("<think>") + len("<think>")
        end = raw_text.find("</think>", start)
        if end != -1:
            return raw_text[start:end].strip()
        else:
            return raw_text[start:].strip()

    # 2. Check for JSON "thought" key
    m = re.search(r'"thought"\s*:\s*"', raw_text)
    if m:
        start_idx = m.end()
        thought_chars = []
        i = start_idx
        n = len(raw_text)
        while i < n:
            ch = raw_text[i]
            if ch == '\\':
                if i + 1 < n:
                    next_ch = raw_text[i + 1]
                    if next_ch == 'n':
                        thought_chars.append('\n')
                    elif next_ch == '"':
                        thought_chars.append('"')
                    elif next_ch == '\\':
                        thought_chars.append('\\')
                    elif next_ch == 't':
                        thought_chars.append('\t')
                    else:
                        thought_chars.append(next_ch)
                    i += 2
                    continue
                else:
                    break
            elif ch == '"':
                break
            else:
                thought_chars.append(ch)
            i += 1

        thought_str = "".join(thought_chars).strip()
        if thought_str:
            return thought_str

    # 3. Check for XML <tool_call>
    if "<tool_call>" in raw_text:
        idx = raw_text.find("<tool_call>")
        pre_text = raw_text[:idx].strip()
        if pre_text:
            return pre_text
        
        # Extract tool name from <tool_call>tool_name
        tool_snippet = raw_text[idx + len("<tool_call>"):].strip().split('\n')[0].strip()
        if tool_snippet and not tool_snippet.startswith("<"):
            return f"Selecting tool: {tool_snippet}..."

    # 4. If plain reasoning text before JSON or other tags
    if not raw_text.lstrip().startswith("{") and not raw_text.lstrip().startswith("<"):
        # Take up to 200 chars or until a tag/brace
        end_idx = min(
            raw_text.find("{") if "{" in raw_text else len(raw_text),
            raw_text.find("<") if "<" in raw_text else len(raw_text),
        )
        plain = raw_text[:end_idx].strip()
        if plain:
            return plain

    return None


class LiveThinkingDisplay:
    """
    Combines live streaming thought extraction with the classic ShimmerStatus animation.
    
    While tokens are streaming:
    - If thought text is available, shows a live updating panel with the thinking text
      AND the shimmering 'Thinking…' indicator at the bottom.
    - If thought text is not yet generated, shows the shimmering 'Thinking…' animation.
    """

    def __init__(self, shimmer_text_str: str = "Thinking…", shimmer_color: str = "grey", delay: float = 0.03):
        self.shimmer_text_str = shimmer_text_str
        self.base_color, self.peak_color = COLOR_PRESETS.get(shimmer_color, COLOR_PRESETS["grey"])
        self.delay = delay
        self.width = 6.0
        self.steps_per_char = 3

        self._raw_tokens = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._latest_thought = ""

    def on_token(self, token: str) -> None:
        """Callback passed to the LLM streaming call."""
        with self._lock:
            self._raw_tokens.append(token)
            accumulated = "".join(self._raw_tokens)
            thought = extract_partial_thought(accumulated)
            if thought:
                self._latest_thought = thought

    def _render(self, step: int, total_steps: int, start: float):
        center = start + (step / self.steps_per_char)
        shimmer_widget = _shimmer_frame(
            self.shimmer_text_str,
            self.base_color,
            self.peak_color,
            center,
            self.width,
        )

        with self._lock:
            thought = self._latest_thought

        if thought:
            panel = Panel(
                f"[dim italic]{thought}[/dim italic]",
                title="[bold]💭 BhavAI Thinking[/bold]",
                title_align="left",
                border_style="dim",
            )
            return Group(panel, shimmer_widget)
        else:
            return shimmer_widget

    def _run(self):
        n = len(self.shimmer_text_str)
        start, end = -self.width, n + self.width
        total_steps = int((end - start) * self.steps_per_char)
        step = 0

        with Live(console=console, refresh_per_second=25, transient=True) as live:
            while not self._stop_event.is_set():
                renderable = self._render(step, total_steps, start)
                live.update(renderable)
                time.sleep(self.delay)
                step = (step + 1) % total_steps

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        return False
