"""
engine/human_browser.py — Human Simulation Layer for Zara Browser Automation.

Implements realistic human anti-bot behavior:
- Cubic Bézier mouse movement curves with hand tremor jitter
- Variable typing delays (50ms - 150ms per keystroke) with punctuation pauses
- Organic scrolling routines with reading pauses and micro-reversals
- Human-like click routines targeting randomized inner bounding boxes
"""

from __future__ import annotations

import logging
import math
import random
import time
from typing import Optional, Union, Tuple, List

from playwright.sync_api import Page, ElementHandle, Locator

from gui.animated_avatar import push_state

logger = logging.getLogger("zara.human_browser")


class HumanMouse:
    """Simulates realistic human mouse trajectories and interactions."""

    def __init__(self, page: Page):
        self.page = page
        self.current_x = random.randint(100, 300)
        self.current_y = random.randint(100, 300)

    @staticmethod
    def _bezier_point(
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
        t: float,
    ) -> Tuple[float, float]:
        """Calculate a point along a cubic Bézier curve at parameter t in [0, 1]."""
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        return x, y

    def move_to(
        self,
        target_x: float,
        target_y: float,
        steps: Optional[int] = None,
        duration: Optional[float] = None,
    ) -> None:
        """
        Move mouse along a curved Bézier path from current position to target,
        incorporating velocity ramps and realistic hand micro-tremors.
        """
        start_x, start_y = self.current_x, self.current_y
        dist = math.hypot(target_x - start_x, target_y - start_y)

        if dist < 4:
            self.page.mouse.move(target_x, target_y)
            self.current_x, self.current_y = target_x, target_y
            return

        if steps is None:
            steps = max(15, min(60, int(dist / 15)))

        if duration is None:
            # Approx 250ms to 700ms depending on distance
            duration = max(0.25, min(0.75, dist / 800.0 + random.uniform(0.1, 0.25)))

        # Generate randomized Bézier control points
        dx = target_x - start_x
        dy = target_y - start_y

        # Perpendicular normal vector for arching deviation
        norm_x = -dy / (dist + 1e-5)
        norm_y = dx / (dist + 1e-5)

        deviation_magnitude = random.uniform(dist * 0.1, dist * 0.25) * random.choice([-1, 1])

        p0 = (start_x, start_y)
        p1 = (
            start_x + dx * 0.25 + norm_x * deviation_magnitude + random.uniform(-10, 10),
            start_y + dy * 0.25 + norm_y * deviation_magnitude + random.uniform(-10, 10),
        )
        p2 = (
            start_x + dx * 0.75 + norm_x * (deviation_magnitude * 0.6) + random.uniform(-10, 10),
            start_y + dy * 0.75 + norm_y * (deviation_magnitude * 0.6) + random.uniform(-10, 10),
        )
        p3 = (target_x, target_y)

        step_delay = duration / float(steps)

        for i in range(1, steps + 1):
            raw_t = i / float(steps)
            # Smooth ease-in-out S-curve profile
            t = raw_t * raw_t * (3.0 - 2.0 * raw_t)

            bx, by = self._bezier_point(p0, p1, p2, p3, t)

            # Micro-tremor noise (hand jitter), diminishing near destination
            jitter_scale = (1.0 - raw_t) * 1.5
            jx = bx + random.gauss(0, jitter_scale)
            jy = by + random.gauss(0, jitter_scale)

            try:
                self.page.mouse.move(jx, jy)
            except Exception:
                pass

            time.sleep(max(0.002, step_delay + random.uniform(-0.002, 0.003)))

        # Final exact coordinate
        self.page.mouse.move(target_x, target_y)
        self.current_x, self.current_y = target_x, target_y

    def click_at(
        self,
        x: float,
        y: float,
        button: str = "left",
        hover_delay: Optional[float] = None,
    ) -> None:
        """Move human-like to coordinates, hover briefly, and click."""
        self.move_to(x, y)

        if hover_delay is None:
            hover_delay = random.uniform(0.06, 0.18)
        time.sleep(hover_delay)

        click_press_duration = random.uniform(0.04, 0.09)
        self.page.mouse.down(button=button)  # type: ignore
        time.sleep(click_press_duration)
        self.page.mouse.up(button=button)  # type: ignore

        time.sleep(random.uniform(0.08, 0.22))


class HumanBrowser:
    """
    High-level controller providing human interactions for a Playwright Page.
    """

    def __init__(self, page: Page):
        self.page = page
        self.mouse = HumanMouse(page)

    def human_click(
        self,
        target: Union[str, ElementHandle, Locator],
        timeout: int = 15000,
        wait_after: Optional[float] = None,
    ) -> bool:
        """
        Locates element, moves mouse along natural curve to randomized point inside
        its bounds, hovers, and clicks.
        """
        push_state("Processing")
        try:
            element = None
            if isinstance(target, str):
                element = self.page.wait_for_selector(target, timeout=timeout, state="visible")
            elif isinstance(target, Locator):
                element = target.element_handle(timeout=timeout)
            elif isinstance(target, ElementHandle):
                element = target

            if not element:
                logger.warning(f"[HumanBrowser] Element not found for click: {target}")
                return False

            # Scroll element into viewport smoothly if needed
            try:
                element.scroll_into_view_if_needed(timeout=5000)
                time.sleep(random.uniform(0.15, 0.35))
            except Exception:
                pass

            box = element.bounding_box()
            if not box:
                logger.warning(f"[HumanBrowser] Could not get bounding box for: {target}")
                return False

            # Target inner safe bounds (15% to 85% of dimensions)
            tx = box["x"] + box["width"] * random.uniform(0.2, 0.8)
            ty = box["y"] + box["height"] * random.uniform(0.25, 0.75)

            logger.info(f"[HumanBrowser] Human clicking element at ({tx:.1f}, {ty:.1f})")
            self.mouse.click_at(tx, ty)

            if wait_after is None:
                wait_after = random.uniform(0.25, 0.6)
            time.sleep(wait_after)
            return True

        except Exception as e:
            logger.error(f"[HumanBrowser] Failed human_click on {target}: {e}")
            return False

    def human_type(
        self,
        target: Union[str, ElementHandle, Locator],
        text: str,
        clear_first: bool = True,
        min_delay_ms: int = 50,
        max_delay_ms: int = 150,
        press_enter: bool = False,
    ) -> bool:
        """
        Clicks element to gain focus, optionally clears existing content,
        and types text with natural rhythm and inter-key variations.
        """
        push_state("Writing")
        try:
            # Focus field with a human click
            clicked = self.human_click(target)
            if not clicked:
                # Fallback to direct focus if human click failed
                try:
                    if isinstance(target, str):
                        self.page.focus(target)
                except Exception:
                    pass

            time.sleep(random.uniform(0.15, 0.35))

            if clear_first:
                # Select all and delete
                is_mac = sys.platform == "darwin"
                modifier = "Meta" if is_mac else "Control"
                self.page.keyboard.press(f"{modifier}+A")
                time.sleep(random.uniform(0.08, 0.15))
                self.page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.1, 0.25))

            logger.info(f"[HumanBrowser] Typing text ({len(text)} chars) with human cadence...")

            # Type character-by-character with cadence variation
            for i, char in enumerate(text):
                # Base typing delay: 50ms - 150ms
                delay = random.uniform(min_delay_ms / 1000.0, max_delay_ms / 1000.0)

                # Natural pauses at sentence boundaries, punctuation, and spaces
                if char in ".?!":
                    delay += random.uniform(0.2, 0.45)
                elif char in ",;:-":
                    delay += random.uniform(0.1, 0.25)
                elif char == " ":
                    delay += random.uniform(0.04, 0.12)
                elif char == "\n":
                    delay += random.uniform(0.3, 0.6)

                # Rare momentary hesitation (simulating reading/thinking)
                if i > 0 and random.random() < 0.03:
                    time.sleep(random.uniform(0.25, 0.55))

                self.page.keyboard.type(char)
                time.sleep(delay)

            time.sleep(random.uniform(0.2, 0.4))

            if press_enter:
                time.sleep(random.uniform(0.1, 0.25))
                self.page.keyboard.press("Enter")
                time.sleep(random.uniform(0.3, 0.7))

            push_state("Idle")
            return True

        except Exception as e:
            logger.error(f"[HumanBrowser] Failed human_type on {target}: {e}")
            push_state("Idle")
            return False

    def human_scroll(
        self,
        distance_px: int = 600,
        direction: str = "down",
        steps: Optional[int] = None,
        reading_pauses: bool = True,
    ) -> None:
        """
        Organic page scrolling that breaks total scroll into variable chunks,
        pauses intermittently as if reading/observing content, and occasionally
        performs slight micro-reversals before deciding on next actions.
        """
        push_state("Analyzing")
        logger.info(f"[HumanBrowser] Human scrolling {direction} by ~{distance_px}px...")

        sign = 1 if direction.lower() == "down" else -1
        remaining = abs(distance_px)

        if steps is None:
            # 80px - 220px per scroll burst
            steps = max(2, int(remaining / random.randint(120, 240)))

        avg_chunk = remaining / float(steps)

        for s in range(steps):
            # Chunk with variation
            chunk = int(avg_chunk * random.uniform(0.7, 1.35))
            chunk = min(chunk, remaining)
            remaining -= chunk

            delta_y = sign * chunk
            try:
                self.page.mouse.wheel(0, delta_y)
            except Exception:
                # Fallback JS scroll if wheel fails
                self.page.evaluate(f"window.scrollBy(0, {delta_y})")

            # Pause between scroll chunks
            chunk_pause = random.uniform(0.08, 0.25)
            time.sleep(chunk_pause)

            # Organic reading pause (30% chance or if reading_pauses enabled)
            if reading_pauses and (random.random() < 0.35 or s == steps // 2):
                read_time = random.uniform(0.6, 2.0)
                logger.debug(f"[HumanBrowser] Reading pause for {read_time:.2f}s...")
                # Small cursor drift during reading
                try:
                    drift_x = self.mouse.current_x + random.uniform(-40, 40)
                    drift_y = self.mouse.current_y + random.uniform(-20, 20)
                    self.mouse.move_to(
                        max(50, min(1200, drift_x)),
                        max(50, min(800, drift_y)),
                        steps=8,
                        duration=0.3,
                    )
                except Exception:
                    pass
                time.sleep(read_time)

            # 10% chance of an organic slight back-scroll (human re-reading)
            if random.random() < 0.12 and s > 0:
                reverse_delta = -sign * random.randint(40, 110)
                try:
                    self.page.mouse.wheel(0, reverse_delta)
                except Exception:
                    pass
                time.sleep(random.uniform(0.2, 0.5))

            if remaining <= 0:
                break

        time.sleep(random.uniform(0.3, 0.8))
        push_state("Idle")

    def human_observe(self, seconds: Optional[float] = None) -> None:
        """
        Pauses and observes viewport, with subtle human gaze mouse repositioning.
        """
        push_state("Analyzing")
        if seconds is None:
            seconds = random.uniform(1.2, 2.8)

        logger.info(f"[HumanBrowser] Observing viewport for {seconds:.2f}s...")
        half = seconds / 2.0
        time.sleep(half)

        try:
            # Slight eye tracking shift
            gx = random.randint(250, 950)
            gy = random.randint(200, 650)
            self.mouse.move_to(gx, gy, steps=12, duration=0.4)
        except Exception:
            pass

        time.sleep(seconds - half)
        push_state("Idle")

    def scroll_into_view_human(self, target: Union[str, ElementHandle, Locator]) -> bool:
        """Scrolls target element into view with human-like motion."""
        try:
            element = None
            if isinstance(target, str):
                element = self.page.query_selector(target)
            elif isinstance(target, Locator):
                element = target.element_handle()
            elif isinstance(target, ElementHandle):
                element = target

            if not element:
                return False

            element.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.2, 0.45))
            return True
        except Exception as e:
            logger.debug(f"[HumanBrowser] scroll_into_view error: {e}")
            return False
