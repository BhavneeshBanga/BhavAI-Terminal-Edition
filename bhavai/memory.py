from bhavai.config import logger
from pathlib import Path


import json

class ConversationMemory:
    def __init__(self, max_chars: int = 100000):
        """
        Initializes memory with character limits.
        Approx 100,000 characters is roughly 25,000 tokens.
        """
        self.messages = []
        self.max_chars = max_chars

    def add_message(self, role: str, content: str):
        """Adds a message to the in-memory conversation log."""
        self.messages.append({"role": role, "content": content})
        logger.debug("Memory added message from role: %s (length: %d)", role, len(content))

    def add_image_message(self, role: str, text: str, image_paths: list[str]):
        self.messages.append({
            "role": role,
            "content": text,
            "images": image_paths,   # naya field
        })

    def clear(self):
        """Clears memory."""
        self.messages.clear()

    def save_to_file(self, path) -> None:
        """
        Saves the full conversation history as readable markdown.
        """
        lines = []
        for msg in self.messages:
            lines.append(f"### {msg['role'].upper()}\n\n{msg['content']}\n")
        Path(path).write_text("\n---\n\n".join(lines), encoding="utf-8")

    def save_to_json(self, path) -> None:
        """
        Saves conversation memory messages array into a JSON file.
        """
        Path(path).write_text(json.dumps(self.messages, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_from_json(self, path) -> bool:
        """
        Loads conversation memory messages array from a JSON file.
        Returns True if successful, False otherwise.
        """
        file_path = Path(path)
        if not file_path.exists():
            return False
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.messages = data
                return True
            elif isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
                self.messages = data["messages"]
                return True
        except Exception as e:
            logger.error("Failed to load session memory from %s: %s", path, e)
        return False



    def get_messages(self, system_prompt: str) -> list:
        """
        Compiles the messages list, including the system prompt.
        If history is too long, prunes intermediate entries while preserving
        the system prompt, initial user request, and recent context.
        """
        compiled = [{"role": "system", "content": system_prompt}]
        
        if not self.messages:
            return compiled
            
        # If total characters are under limits, return all
        total_chars = sum(len(m["content"]) for m in self.messages)
        if total_chars <= self.max_chars:
            compiled.extend(self.messages)
            return compiled
            
        logger.warning(
            "Conversation history exceeds limit (%d > %d chars). Pruning...",
            total_chars, self.max_chars
        )
        
        # Pruning logic:
        # Keep the very first user message (the original task)
        # Keep the last N messages that fit within the remaining character budget
        first_msg = None
        start_idx = 0
        if self.messages and self.messages[0]["role"] == "user":
            first_msg = self.messages[0]
            start_idx = 1
            
        # We budget chars for the system prompt and the first user message
        reserved_len = len(system_prompt) + (len(first_msg["content"]) if first_msg else 0)
        available_budget = self.max_chars - reserved_len
        
        # Accumulate messages from the end until budget is full
        recent_messages = []
        accumulated_len = 0
        
        for msg in reversed(self.messages[start_idx:]):
            msg_len = len(msg["content"])
            if accumulated_len + msg_len > available_budget:
                break
            recent_messages.insert(0, msg)
            accumulated_len += msg_len
            
        if first_msg:
            compiled.append(first_msg)
            
        # Add a placeholder notifying the model that older messages were truncated
        if len(recent_messages) < len(self.messages) - start_idx:
            compiled.append({
                "role": "user",
                "content": "... [System: Older conversation history truncated to save context window] ..."
            })
            
        compiled.extend(recent_messages)
        return compiled
