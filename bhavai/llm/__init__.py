from typing import Callable, Optional
from bhavai.llm.factory import get_provider
from bhavai.config import logger

def provider_needs_chunking() -> bool:
    """agent.py isko use karega system prompt conditional banane ke liye."""
    return get_provider().needs_chunking_instruction

def query_llm(messages: list, calls: int = 0, temperature: float = 0.0) -> str:
    content, _ = get_provider().call(messages, temperature=temperature, calls=calls)
    return content

def query_llm_stream(
    messages: list,
    calls: int = 0,
    temperature: float = 0.0,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    content, _ = get_provider().stream(messages, temperature=temperature, calls=calls, on_token=on_token)
    return content

def call_sarvam(messages: list) -> str:
    """
    Backward-compat shim — purana `call_sarvam()` import jo scripts/initialize_markdown.py
    jaisi files use karti hain, ab config-driven provider system se route hota hai.
    """
    return query_llm(messages)

def query_llm_with_continuation(messages: list, calls: int = 0, temperature: float = 0.0, max_rounds: int = 6) -> str:
    return query_llm_with_continuation_stream(messages, calls=calls, temperature=temperature, max_rounds=max_rounds, on_token=None)

def query_llm_with_continuation_stream(
    messages: list,
    calls: int = 0,
    temperature: float = 0.0,
    max_rounds: int = 6,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    CONTINUATION_PROMPT = (
        "Continue exactly from where you left off. Do NOT repeat any content already written. "
        "Resume mid-word or mid-token if needed. Output only the continuation, nothing else."
    )
    provider = get_provider()
    full_output, history = "", list(messages)
    for round_num in range(1, max_rounds + 1):
        content, stop_reason = provider.stream(history, temperature=temperature, calls=calls, on_token=on_token)
        full_output += content
        if stop_reason != "max_tokens":
            break
        history.append({"role": "assistant", "content": content})
        history.append({"role": "user", "content": CONTINUATION_PROMPT})
    return full_output