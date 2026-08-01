# bhavai/llm/base.py
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    name: str = ""
    max_output_tokens: int = 4096
    needs_chunking_instruction: bool = False   # ← yeh flag SYSTEM_PROMPT decide karega

    @abstractmethod
    def call(self, messages: list, temperature: float = 0.0, calls: int = 0) -> tuple[str, str]:
        """Returns (content, stop_reason)."""
        raise NotImplementedError