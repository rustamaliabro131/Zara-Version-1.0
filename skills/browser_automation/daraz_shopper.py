"""
skills/browser_automation/daraz_shopper.py — Autonomous Daraz Shopping Assistant.

Workflow:
1. Navigates to Daraz (daraz.pk / daraz.com) using persistent Chrome context.
2. Searches for target item with human typing.
3. Observes search results with organic scrolling.
4. Clicks the top-rated matching product and scrolls through specs/reviews.
5. Clicks 'Add to Cart' or 'Buy Now'.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional, Callable

from engine.browser_core import BrowserCore
from engine.human_browser import HumanBrowser
from engine.browser_vision import BrowserVision
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.daraz_shopper")


def shop_daraz(
    search_query: str,
    action: str = "add_to_cart",
    domain: str = "pk",
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Autonomous Daraz shopping workflow.
    """
    def log(msg: str):
        logger.info(f"[DarazShopper] {msg}")
        if log_callback:
            try:
                log_callback(f"[Daraz] {msg}")
            except Exception:
                pass

    log(f"Starting Daraz search for: '{search_query}'")
    push_state("Analyzing")

    core = BrowserCore.get_instance()
    page = core.get_active_page()
    human = HumanBrowser(page)
    vision = BrowserVision(page, human)

    try:
        # Step 1: Open Daraz
        daraz_url = f"https://www.daraz.{domain}"
        page = core.navigate(daraz_url)
        time.sleep(random.uniform(2.5, 4.0))

        # Close any promotional popup if present
        popup_selectors = [
            'div[class*="popup"] button',
            'span[class*="close"]',
            'i[class*="close"]',
            'div[class*="dialog"] [class*="close"]',
        ]
        for p_sel in popup_selectors:
            try:
                btn = page.query_selector(p_sel)
                if btn and btn.is_visible():
                    btn.click()
                    break
            except Exception:
                pass

        # Step 2: Search item
        log(f"Searching for '{search_query}'...")
        push_state("Writing")
        search_selectors = [
            'input[id="q"]',
            'input[type="search"]',
            'input[placeholder*="Search in Daraz"]',
            'input[placeholder*="Search"]',
        ]
        vision.smart_fill(
            selectors=search_selectors,
            visual_fallback_description="Search bar at top of Daraz",
            text=search_query,
            clear_first=True,
        )
        page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        time.sleep(random.uniform(2.5, 4.0))

        # Step 3: Browse search results with human scrolling
        log("Browsing search results...")
        push_state("Analyzing")
        human.human_scroll(distance_px=650, reading_pauses=True)
        human.human_observe(1.5)

        # Step 4: Click first product item
        log("Selecting top product listing...")
        product_selectors = [
            'div[data-tracking="product-card"] a',
            'div[class*="gridItem"] a',
            'div[class*="box--"] a',
            'a[href*="/products/"]',
        ]
        clicked = vision.smart_click(
            selectors=product_selectors,
            visual_fallback_description="First product listing card or image",
        )
        time.sleep(random.uniform(3.0, 5.0))

        # Switch to new page if Daraz opened product in new tab
        if len(core.get_context().pages) > 1:
            page = core.get_context().pages[-1]
            human = HumanBrowser(page)
            vision = BrowserVision(page, human)

        # Step 5: Read product details
        log("Examining product specifications and pricing...")
        human.human_scroll(distance_px=500, reading_pauses=True)
        human.human_observe(1.5)

        # Step 6: Add to Cart or Buy Now
        if action == "buy_now":
            log("Clicking 'Buy Now'...")
            buy_selectors = [
                'button:has-text("Buy Now")',
                'button[class*="buy-now"]',
                'span:has-text("Buy Now")',
            ]
            vision.smart_click(buy_selectors, "Orange Buy Now button")
            res = f"Clicked 'Buy Now' for '{search_query}' on Daraz. Please proceed to payment."
        else:
            log("Clicking 'Add to Cart'...")
            cart_selectors = [
                'button:has-text("Add to Cart")',
                'button[class*="add-to-cart"]',
                'span:has-text("Add to Cart")',
            ]
            vision.smart_click(cart_selectors, "Add to Cart button")
            res = f"Successfully added '{search_query}' to your Daraz cart!"

        push_state("Idle")
        log(res)
        return res

    except Exception as e:
        logger.error(f"[DarazShopper] Error in Daraz workflow: {e}", exc_info=True)
        push_state("Idle")
        return f"Daraz automation encountered an issue: {e}"
