# bhavai/llm/__init__.py
from bhavai.llm.factory import get_provider
from bhavai.config import logger

def provider_needs_chunking() -> bool:
    """agent.py isko use karega system prompt conditional banane ke liye."""
    return get_provider().needs_chunking_instruction

def query_llm(messages: list, calls: int = 0, temperature: float = 0.0) -> str:
    content, _ = get_provider().call(messages, temperature=temperature, calls=calls)
    return content

# bhavai/llm/__init__.py — end mein add karo

def call_sarvam(messages: list) -> str:
    """
    Backward-compat shim — purana `call_sarvam()` import jo scripts/initialize_markdown.py
    jaisi files use karti hain, ab config-driven provider system se route hota hai.
    """
    return query_llm(messages)

def query_llm_with_continuation(messages: list, calls: int = 0, temperature: float = 0.0, max_rounds: int = 6) -> str:
    CONTINUATION_PROMPT = (
        "Continue exactly from where you left off. Do NOT repeat any content already written. "
        "Resume mid-word or mid-token if needed. Output only the continuation, nothing else."
    )
    provider = get_provider()
    full_output, history = "", list(messages)
    for round_num in range(1, max_rounds + 1):
        content, stop_reason = provider.call(history, temperature=temperature, calls=calls)
        full_output += content
        if stop_reason != "max_tokens":
            break
        history.append({"role": "assistant", "content": content})
        history.append({"role": "user", "content": CONTINUATION_PROMPT})
    return full_output