import threading
import time
import math
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.style import Style

console = Console()

COLOR_PRESETS = {
    "blue":   ((70, 110, 220), (255, 255, 255)),
    "yellow": ((180, 140, 0), (255, 240, 130)),
    "green":  ((30, 120, 60), (140, 255, 170)),
    "red":    ((150, 30, 30), (255, 140, 140)),
    "purple": ((90, 40, 150), (220, 170, 255)),
    "orange": ((180, 80, 0), (255, 190, 100)),
}


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(round(lerp(a, b, t)) for a, b in zip(c1, c2))


def _shimmer_frame(text, base_color, peak_color, center, width):
    t = Text()
    for j, ch in enumerate(text):
        dist = abs(j - center)
        intensity = math.exp(-(dist ** 2) / (2 * (width / 3) ** 2))
        r, g, b = lerp_color(base_color, peak_color, intensity)
        t.append(ch, style=Style(color=f"rgb({r},{g},{b})", bold=intensity > 0.55))
    return t


def shimmer_text(text, color="blue", delay=0.02, loops=2, width=6.0, steps_per_char=3):
    """One-shot blocking shimmer (unchanged behavior) — use for fixed-duration flashes."""
    if color not in COLOR_PRESETS:
        raise ValueError(f"Unknown color '{color}'. Choose from: {list(COLOR_PRESETS)}")
    base_color, peak_color = COLOR_PRESETS[color]
    n = len(text)
    start, end = -width, n + width
    total_steps = int((end - start) * steps_per_char)

    with Live(console=console, refresh_per_second=7) as live:
        for _ in range(loops):
            for step in range(total_steps):
                center = start + (step / steps_per_char)
                live.update(_shimmer_frame(text, base_color, peak_color, center, width))
                time.sleep(delay)
        r, g, b = base_color
        live.update(Text(text, style=Style(color=f"rgb({r},{g},{b})", bold=True)))


class ShimmerStatus:
    """
    Drop-in replacement for `console.status(...)`.
    Runs the shimmer animation on a background thread for as long as the
    `with` block is open, then stops and clears the line.

    Usage:
        with ShimmerStatus("Thinking…", color="blue"):
            do_slow_thing()
    """

    def __init__(self, text, color="blue", delay=0.02, width=6.0, steps_per_char=3):
        if color not in COLOR_PRESETS:
            raise ValueError(f"Unknown color '{color}'. Choose from: {list(COLOR_PRESETS)}")
        self.text = text
        self.base_color, self.peak_color = COLOR_PRESETS[color]
        self.delay = delay
        self.width = width
        self.steps_per_char = steps_per_char
        self._stop_event = threading.Event()
        self._thread = None
        self._live = None

    def _run(self):
        n = len(self.text)
        start, end = -self.width, n + self.width
        total_steps = int((end - start) * self.steps_per_char)
        step = 0
        with Live(console=console, refresh_per_second=120, transient=True) as live:
            self._live = live
            while not self._stop_event.is_set():
                center = start + (step / self.steps_per_char)
                live.update(_shimmer_frame(self.text, self.base_color, self.peak_color, center, self.width))
                time.sleep(self.delay)
                step = (step + 1) % total_steps

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
        return False  # don't suppress exceptions