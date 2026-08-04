"""
Bracketed-paste (Ctrl+V) ko intercept karke check karta hai ki
clipboard mein image hai ya text. Image hone par disk pe save
karke placeholder buffer mein insert karta hai, text hone par
(ya text jo kisi image file ka path ho) uske hisaab se handle karta hai.
"""
import uuid
import time
from pathlib import Path
from typing import Optional
import base64
import mimetypes

from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings
from PIL import ImageGrab

from bhavai.config import logger

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

def encode_image_to_base64(filepath: str) -> dict:
    """Gemini API ke liye image ko base64 + mime_type format mein return karta hai."""
    mime_type, _ = mimetypes.guess_type(filepath)
    if not mime_type:
        mime_type = "image/png"

    with open(filepath, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return {"mime_type": mime_type, "data": data}

def _looks_like_image_path(text: str) -> Optional[str]:
    """
    Agar pasted text ek valid, existing image file ka path hai,
    to uska clean path return karta hai, warna None.
    """
    candidate = text.strip().strip('"').strip("'")
    if not candidate.lower().endswith(IMAGE_EXTENSIONS):
        return None
    try:
        p = Path(candidate)
        if p.exists() and p.is_file():
            return str(p)
    except Exception:
        pass
    return None

def build_paste_keybindings(cwd: Path, on_image_pasted=None, paste_line_threshold: int = 5) -> KeyBindings:
    """
    cwd            : project root, images yahan .bhavai/pasted_images mein save honge
    on_image_pasted: optional callback(filepath)
    paste_line_threshold: is line count se zyada hone par text collapse hoga
    """
    kb = KeyBindings()
    paste_dir = cwd / ".bhavai" / "pasted_images"

    paste_store: dict[int, str] = {}
    paste_counter = {"n": 0}

    @kb.add(Keys.BracketedPaste)
    def _(event):
        buf = event.app.current_buffer
        text = (event.data or "").replace("\r\n", "\n").replace("\r", "\n")

        try:
            # Step 1: clipboard mein actual image bytes check karo
            clip_content = None
            try:
                clip_content = ImageGrab.grabclipboard()
            except Exception as e:
                logger.debug(f"grabclipboard failed: {e}")
                clip_content = None

            if clip_content is not None and hasattr(clip_content, "save"):
                paste_dir.mkdir(parents=True, exist_ok=True)
                filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
                filepath = paste_dir / filename
                clip_content.save(filepath)
                buf.insert_text(f"Pasted Image [{filepath}]")
                if on_image_pasted:
                    on_image_pasted(str(filepath))
                return

            if isinstance(clip_content, list) and clip_content:
                first = str(clip_content[0])
                if first.lower().endswith(IMAGE_EXTENSIONS):
                    buf.insert_text(f"Pasted Image [{first}]")
                    if on_image_pasted:
                        on_image_pasted(first)
                    return

            # Step 2: pasted text kisi image file ka path toh nahi?
            image_path = _looks_like_image_path(text)
            if image_path:
                buf.insert_text(f"Pasted Image [{image_path}]")
                if on_image_pasted:
                    on_image_pasted(image_path)
                return

            # Step 3: plain text — line count zyada hai toh collapse karo
            line_count = text.count("\n") + 1
            if line_count > paste_line_threshold:
                paste_counter["n"] += 1
                idx = paste_counter["n"]
                paste_store[idx] = text
                placeholder = f"[Pasted text #{idx} +{line_count} lines]"
                buf.insert_text(placeholder)
            else:
                buf.insert_text(text)

        except Exception as e:
            # LAST RESORT: kuch bhi galat ho, kam se kam fallback paste toh ho
            logger.exception(f"paste handler crashed: {e}")
            try:
                buf.insert_text(text)
            except Exception:
                pass

    def get_and_reset_bursts():
        # Bracketed paste handler upar hi collapse kar deta hai,
        # isliye ab burst-based fallback ki zaroorat nahi — empty rakha
        # hai sirf main.py ke saath backward-compat ke liye.
        return []

    return kb, paste_store, paste_counter, get_and_reset_bursts