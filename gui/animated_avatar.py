"""
gui/animated_avatar.py — Animated GUI Avatar with state_queue integration for Zara.

Ties the Tkinter animated GIF loop and background thread state updates together.
Accepts tuples like ("STATE", "Analyzing"), ("STATE", "Speaking") on `state_queue`
and forwards them to Zara's AvatarEventBus and UI HUD.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

from gui.avatar import (
    IDLE,
    LISTENING,
    PROCESSING,
    RESEARCHING,
    WRITING,
    SPEAKING,
    IN_CALL,
    STATES,
    STATE_COLORS,
    AvatarController,
    AvatarEventBus,
    AvatarView,
    emit_avatar_state,
    normalize_state,
)

logger = logging.getLogger("zara.animated_avatar")

# Global thread-safe state queue for background tasks and automation routines
state_queue: queue.Queue = queue.Queue(maxsize=1024)

# Extended aliases for automation states
_AUTOMATION_STATE_MAP = {
    "ANALYZING": RESEARCHING,
    "ANALYSIS": RESEARCHING,
    "BROWSING": RESEARCHING,
    "READING": RESEARCHING,
    "SEARCHING": RESEARCHING,
    "TYPING": WRITING,
    "FILLING": WRITING,
    "PUBLISHING": WRITING,
    "SUBMITTING": WRITING,
    "CLICKING": PROCESSING,
    "NAVIGATING": PROCESSING,
    "SCROLLING": PROCESSING,
    "THINKING": PROCESSING,
    "PROCESSING": PROCESSING,
    "SPEAKING": SPEAKING,
    "IDLE": IDLE,
    "LISTENING": LISTENING,
    "IN_CALL": IN_CALL,
}


def push_state(state: str, level: float = 0.0) -> None:
    """Thread-safe push of a state update to state_queue."""
    try:
        state_queue.put_nowait(("STATE", state, level))
    except queue.Full:
        try:
            state_queue.get_nowait()
            state_queue.put_nowait(("STATE", state, level))
        except Exception:
            pass


def _process_state_message(item) -> tuple[str, float]:
    """Parse incoming state_queue items into (state_name, level)."""
    level = 0.0
    raw_state = IDLE

    if isinstance(item, tuple) or isinstance(item, list):
        if len(item) >= 2 and item[0] == "STATE":
            raw_state = str(item[1])
            if len(item) >= 3:
                try:
                    level = float(item[2])
                except (ValueError, TypeError):
                    level = 0.0
        elif len(item) == 1:
            raw_state = str(item[0])
    elif isinstance(item, str):
        raw_state = item
    elif isinstance(item, dict):
        raw_state = str(item.get("state", IDLE))
        level = float(item.get("level", 0.0))

    clean = raw_state.strip().upper()
    mapped = _AUTOMATION_STATE_MAP.get(clean)
    if mapped:
        return mapped, level
    return normalize_state(raw_state), level


def _state_drainer_loop() -> None:
    """Background worker draining state_queue and updating avatar bus."""
    while True:
        try:
            item = state_queue.get()
            if item is None:
                break
            norm_state, level = _process_state_message(item)
            emit_avatar_state(norm_state, level=level)
        except Exception as e:
            logger.debug(f"[AnimatedAvatar] State drain error: {e}")
        finally:
            try:
                state_queue.task_done()
            except Exception:
                pass


# Auto-start drainer thread
_drainer_thread = threading.Thread(
    target=_state_drainer_loop,
    name="zara-state-queue-drainer",
    daemon=True,
)
_drainer_thread.start()

__all__ = [
    "state_queue",
    "push_state",
    "AvatarController",
    "AvatarEventBus",
    "AvatarView",
    "emit_avatar_state",
    "IDLE",
    "LISTENING",
    "PROCESSING",
    "RESEARCHING",
    "WRITING",
    "SPEAKING",
    "IN_CALL",
    "STATES",
    "STATE_COLORS",
]
