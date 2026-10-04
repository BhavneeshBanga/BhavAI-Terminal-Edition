# bhavai/llm/base.py
from abc import ABC, abstractmethod
from typing import Callable, Optional

class LLMProvider(ABC):
    name: str = ""
    max_output_tokens: int = 4096
    needs_chunking_instruction: bool = False   # ← yeh flag SYSTEM_PROMPT decide karega

    @abstractmethod
    def call(self, messages: list, temperature: float = 0.0, calls: int = 0) -> tuple[str, str]:
        """Returns (content, stop_reason)."""
        raise NotImplementedError

    def stream(
        self,
        messages: list,
        temperature: float = 0.0,
        calls: int = 0,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> tuple[str, str]:
        """
        Streams response from the LLM, invoking `on_token(token_str)` for each chunk.
        Default implementation falls back to `call()` and passes full content to on_token.
        """
        content, stop_reason = self.call(messages, temperature=temperature, calls=calls)
        if on_token and content:
            on_token(content)
        return content, stop_reason