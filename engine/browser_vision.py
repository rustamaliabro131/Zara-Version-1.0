"""
engine/browser_vision.py — Vision-Assisted DOM Operations for Zara Browser Engine.

Captures screenshots of the active browser viewport when encountering dynamic or
unfamiliar elements. Sends viewport images to Gemini Vision API (gemini-2.5-flash)
to detect exact element coordinates or bounding boxes when DOM selector matches fail.
Integrates with HumanBrowser to deliver fluid, natural mouse interactions.
"""

from __future__ import annotations

import io
import json
import logging
import random
import time
from typing import Optional, Tuple, List, Dict, Any, Union

from PIL import Image
from playwright.sync_api import Page, Locator, ElementHandle

from core import gemini
from engine.human_browser import HumanBrowser
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.browser_vision")


class BrowserVision:
    """
    Vision-assisted locator and interaction engine powered by Gemini Vision API.
    """

    def __init__(self, page: Page, human_browser: Optional[HumanBrowser] = None):
        self.page = page
        self.human = human_browser or HumanBrowser(page)

    def capture_viewport(self) -> Tuple[bytes, int, int]:
        """
        Capture current browser viewport as PNG bytes and return (bytes, width, height).
        """
        screenshot_bytes = self.page.screenshot(type="png", full_page=False)
        img = Image.open(io.BytesIO(screenshot_bytes))
        width, height = img.size
        return screenshot_bytes, width, height

    def locate_element_coords(
        self,
        element_description: str,
        timeout_ms: int = 20000,
    ) -> Optional[Dict[str, int]]:
        """
        Send viewport screenshot to Gemini Vision API (gemini-2.5-flash) to find the element.
        Returns pixel coordinate dict: {'x': int, 'y': int, 'width': int, 'height': int, 'center_x': int, 'center_y': int}
        """
        push_state("Analyzing")
        logger.info(f"[BrowserVision] Visually searching for: '{element_description}'")

        try:
            screenshot_bytes, img_w, img_h = self.capture_viewport()

            prompt = (
                f"You are a computer vision assistant for a web browser automation agent.\n"
                f"Analyze this web page screenshot and locate the following element:\n"
                f"'{element_description}'\n\n"
                f"Task: Identify the exact bounding box for this element in normalized coordinates (0 to 1000).\n"
                f"Return ONLY valid JSON matching this schema:\n"
                f"{{\n"
                f'  "found": true,\n'
                f'  "box_2d": [ymin, xmin, ymax, xmax],\n'
                f'  "confidence": 0.95,\n'
                f'  "reason": "Brief description of the detected element"\n'
                f"}}\n"
                f"If the element is definitely not visible on the screen, return:\n"
                f'{{"found": false, "reason": "why not found"}}\n'
                f"Do not include explanation text outside the JSON."
            )

            # Build Gemini API request with image part
            from google.genai import types as gtypes

            image_part = gtypes.Part.from_bytes(data=screenshot_bytes, mime_type="image/png")
            contents = [prompt, image_part]

            # Request through Gemini Smart ladder (gemini-2.5-flash)
            resp = gemini.call(contents, tier="gemini-2.5-flash", timeout_ms=timeout_ms)
            if resp is None or not getattr(resp, "text", None):
                # Fallback to general SMART ladder
                resp = gemini.call(contents, tier=gemini.SMART, timeout_ms=timeout_ms)

            if resp is None or not getattr(resp, "text", None):
                logger.warning(f"[BrowserVision] Vision API returned empty response for '{element_description}'")
                push_state("Idle")
                return None

            raw_text = resp.text.strip()
            # Extract JSON block
            if "{" in raw_text and "}" in raw_text:
                json_str = raw_text[raw_text.find("{") : raw_text.rfind("}") + 1]
                data = json.loads(json_str)
            else:
                data = json.loads(raw_text)

            if not data.get("found", False) and "box_2d" not in data:
                logger.warning(f"[BrowserVision] Element '{element_description}' not found on screen: {data.get('reason')}")
                push_state("Idle")
                return None

            # Parse bounding box [ymin, xmin, ymax, xmax] in 0-1000 scale
            box = data.get("box_2d")
            if not box or len(box) != 4:
                # Check for alternative direct x,y coordinates
                if "x" in data and "y" in data:
                    cx = int(data["x"])
                    cy = int(data["y"])
                    return {
                        "x": cx - 20,
                        "y": cy - 10,
                        "width": 40,
                        "height": 20,
                        "center_x": cx,
                        "center_y": cy,
                    }
                push_state("Idle")
                return None

            ymin, xmin, ymax, xmax = box
            # Denormalize to actual pixel values
            px_x = int((xmin / 1000.0) * img_w)
            px_y = int((ymin / 1000.0) * img_h)
            px_w = max(4, int(((xmax - xmin) / 1000.0) * img_w))
            px_h = max(4, int(((ymax - ymin) / 1000.0) * img_h))

            center_x = px_x + px_w // 2
            center_y = px_y + px_h // 2

            logger.info(
                f"[BrowserVision] ✅ Found '{element_description}' at ({center_x}, {center_y}) "
                f"[box: {px_x},{px_y} {px_w}x{px_h}]"
            )

            push_state("Idle")
            return {
                "x": px_x,
                "y": px_y,
                "width": px_w,
                "height": px_h,
                "center_x": center_x,
                "center_y": center_y,
            }

        except Exception as e:
            logger.error(f"[BrowserVision] Vision detection failed for '{element_description}': {e}")
            push_state("Idle")
            return None

    def click(self, element_description: str) -> bool:
        """
        Locates element visually using Gemini Vision API and performs human-like click.
        """
        coords = self.locate_element_coords(element_description)
        if not coords:
            return False

        # Randomize target within central 60% of bounding box
        target_x = coords["x"] + coords["width"] * random.uniform(0.2, 0.8)
        target_y = coords["y"] + coords["height"] * random.uniform(0.25, 0.75)

        logger.info(f"[BrowserVision] Executing human click at ({target_x:.1f}, {target_y:.1f})")
        self.human.mouse.click_at(target_x, target_y)
        return True

    def type_text(self, element_description: str, text: str, clear_first: bool = True) -> bool:
        """
        Locates input field visually, focuses it, and types with human cadence.
        """
        coords = self.locate_element_coords(element_description)
        if not coords:
            return False

        target_x = coords["x"] + coords["width"] * random.uniform(0.2, 0.8)
        target_y = coords["y"] + coords["height"] * random.uniform(0.3, 0.7)

        logger.info(f"[BrowserVision] Focusing field at ({target_x:.1f}, {target_y:.1f}) for typing")
        self.human.mouse.click_at(target_x, target_y)
        time.sleep(random.uniform(0.15, 0.3))

        # Use human typing engine directly on active element
        push_state("Writing")
        if clear_first:
            import sys
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            self.page.keyboard.press(f"{modifier}+A")
            time.sleep(0.1)
            self.page.keyboard.press("Backspace")
            time.sleep(0.15)

        for char in text:
            delay = random.uniform(0.05, 0.15)
            if char in ".?!":
                delay += 0.25
            elif char in ",;:- ":
                delay += 0.1
            self.page.keyboard.type(char)
            time.sleep(delay)

        push_state("Idle")
        return True

    def smart_click(
        self,
        selectors: Union[str, List[str]],
        visual_fallback_description: str,
        timeout_ms: int = 5000,
    ) -> bool:
        """
        Attempts standard DOM selector click first; if not found or obscured,
        falls back to Gemini Vision API detection and click.
        """
        if isinstance(selectors, str):
            selectors = [selectors]

        # 1. Try DOM selectors
        for sel in selectors:
            try:
                elem = self.page.query_selector(sel)
                if elem and elem.is_visible():
                    logger.info(f"[BrowserVision] DOM selector match: '{sel}'")
                    if self.human.human_click(elem):
                        return True
            except Exception as e:
                logger.debug(f"[BrowserVision] Selector check '{sel}' error: {e}")

        # 2. Fall back to Vision API
        logger.info(
            f"[BrowserVision] All DOM selectors failed. Falling back to Gemini Vision for '{visual_fallback_description}'..."
        )
        return self.click(visual_fallback_description)

    def smart_fill(
        self,
        selectors: Union[str, List[str]],
        visual_fallback_description: str,
        text: str,
        clear_first: bool = True,
    ) -> bool:
        """
        Attempts DOM selector fill first; falls back to Gemini Vision.
        """
        if isinstance(selectors, str):
            selectors = [selectors]

        # 1. Try DOM selectors
        for sel in selectors:
            try:
                elem = self.page.query_selector(sel)
                if elem and elem.is_visible():
                    logger.info(f"[BrowserVision] DOM selector match for input: '{sel}'")
                    if self.human.human_type(elem, text, clear_first=clear_first):
                        return True
            except Exception as e:
                logger.debug(f"[BrowserVision] Selector input '{sel}' error: {e}")

        # 2. Fall back to Vision API
        logger.info(
            f"[BrowserVision] All DOM input selectors failed. Engaging Gemini Vision for '{visual_fallback_description}'..."
        )
        return self.type_text(visual_fallback_description, text, clear_first=clear_first)
