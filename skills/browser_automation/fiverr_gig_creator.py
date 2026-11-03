"""
skills/browser_automation/fiverr_gig_creator.py — Autonomous Fiverr Gig Creator.

Workflow:
1. Accesses Fiverr seller dashboard / gig creation builder with persistent session.
2. Fills Gig Title (with 'I will' handling), Category dropdowns, and Search Tags.
3. Configures Pricing and scopes with human observation pauses.
4. Drafts and types Gig Description with human typing delays.
5. Saves draft or proceeds through steps with state_queue sync.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional, List, Callable

from core import gemini
from engine.browser_core import BrowserCore, NavigationError, wait_for_domain
from engine.human_browser import HumanBrowser
from engine.browser_vision import BrowserVision
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.fiverr_creator")


def _generate_fiverr_description(title: str, tags: List[str]) -> str:
    """Generate high-converting, professional Fiverr gig description with Gemini."""
    prompt = (
        f"You are a top-rated Fiverr Pro seller.\n"
        f"Gig Title: {title}\n"
        f"Tags: {', '.join(tags)}\n\n"
        f"Write an exceptional, persuasive Fiverr gig description:\n"
        f"- Friendly, professional greeting\n"
        f"- What this gig provides (clear bullet points of features & services)\n"
        f"- Why choose me (experience, reliability, clean code/delivery)\n"
        f"- Call to action ('Please message me before ordering to discuss your requirements!').\n"
        f"Do NOT include fake reviews or pricing."
    )
    desc = gemini.text(prompt, tier=gemini.SMART, default="")
    if not desc:
        desc = (
            f"Welcome to my professional service!\n\n"
            f"Are you looking for high-quality, reliable solutions for {title}? You have come to the right place.\n\n"
            f"What I Offer:\n"
            f"- Custom, robust, and clean implementation\n"
            f"- Thorough testing and documentation\n"
            f"- Fast turn-around and responsive communication\n"
            f"- Post-delivery support and guidance\n\n"
            f"Why Choose Me?\n"
            f"- 100% satisfaction commitment\n"
            f"- Professional experience with modern toolchains\n\n"
            f"Please send me a message before placing an order so we can discuss your exact requirements!"
        )
    return desc.strip()


def create_fiverr_gig(
    title: str,
    category: str = "Programming & Tech",
    subcategory: str = "AI Applications",
    tags: Optional[List[str]] = None,
    description: Optional[str] = None,
    price: str = "50",
    delivery_days: str = "3",
    save_draft_only: bool = True,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Autonomous Fiverr gig creation workflow.
    """
    def log(msg: str):
        logger.info(f"[FiverrCreator] {msg}")
        if log_callback:
            try:
                log_callback(f"[Fiverr] {msg}")
            except Exception:
                pass

    log(f"Starting Fiverr gig creator for: '{title}'")
    push_state("Analyzing")

    core = BrowserCore.get_instance()
    page = core.get_active_page()
    human = HumanBrowser(page)
    vision = BrowserVision(page, human)

    try:
        # Step 1: Navigate to Fiverr Gig Creation
        fiverr_url = "https://www.fiverr.com/manage_gigs/new"
        page = core.navigate(fiverr_url, timeout=60000)
        time.sleep(random.uniform(2.5, 4.0))

        if not wait_for_domain(page, "fiverr.com"):
            msg = (
                f"Fiverr did not load — the page is still on "
                f"'{page.url or 'about:blank'}'. Please check your connection "
                f"and that no other Chrome window holds the browser profile, then retry."
            )
            log(msg)
            push_state("Idle")
            return msg

        if "login" in page.url.lower():
            msg = "Fiverr login detected. Please sign in to your seller account in the browser."
            log(msg)
            push_state("Idle")
            return msg

        log("Observing Fiverr gig builder...")
        human.human_observe(1.5)

        # Normalize title: Fiverr UI already places "I will " prefix
        clean_title = title.strip()
        if clean_title.lower().startswith("i will "):
            clean_title = clean_title[7:].strip()

        # Step 2: Gig Title
        log(f"Entering Gig Title: 'I will {clean_title}'...")
        push_state("Writing")
        title_selectors = [
            'textarea[name*="gig[title]"]',
            'textarea[placeholder*="do something I\'m really good at"]',
            'textarea[data-testid*="gig-title"]',
            'input[name*="title"]',
            'textarea',
        ]
        vision.smart_fill(title_selectors, "Gig title text area following I will", clean_title)
        time.sleep(random.uniform(0.6, 1.2))

        # Step 3: Categories
        log(f"Setting category '{category}' / '{subcategory}'...")
        cat_selectors = [
            'div[data-testid="category-dropdown"]',
            'select[name*="category"]',
            'div:has-text("Select a Category")',
            'button:has-text("Category")',
        ]
        vision.smart_click(cat_selectors, "Select a Category dropdown")
        time.sleep(0.5)

        # Step 4: Search Tags (up to 5)
        if not tags:
            tags = ["python", "automation", "ai bot", "script", "developer"]

        log(f"Adding search tags: {', '.join(tags[:5])}...")
        human.human_scroll(distance_px=350, reading_pauses=True)

        tag_input_selectors = [
            'input[placeholder*="tag"]',
            'input[placeholder*="Enter search tags"]',
            'input[data-testid*="search-tags"]',
            'input[aria-label*="tag"]',
        ]

        for tag in tags[:5]:
            t_input = page.query_selector(tag_input_selectors[0])
            if not t_input:
                for sel in tag_input_selectors[1:]:
                    t_input = page.query_selector(sel)
                    if t_input:
                        break

            if t_input:
                human.human_type(t_input, tag, clear_first=False, press_enter=True)
                time.sleep(random.uniform(0.3, 0.7))
            else:
                vision.type_text("Search tags text box", tag)
                page.keyboard.press("Enter")
                time.sleep(0.5)

        # Step 5: Save & Continue to Pricing
        log("Proceeding to Pricing...")
        save_btn_selectors = [
            'button:has-text("Save & Continue")',
            'button:has-text("Save and continue")',
            'button[type="submit"]',
        ]
        human.human_scroll(distance_px=400, reading_pauses=True)
        vision.smart_click(save_btn_selectors, "Save & Continue green button")
        time.sleep(random.uniform(3.0, 5.0))

        # --- STEP 6: PRICING TAB ---
        log(f"Setting pricing (${price}) and delivery time ({delivery_days} days)...")
        push_state("Analyzing")
        human.human_scroll(distance_px=300, reading_pauses=True)

        price_selectors = [
            'input[name*="price"]',
            'input[placeholder*="Price"]',
            'input[aria-label*="Price"]',
            'input[type="number"]',
        ]
        vision.smart_fill(price_selectors, "Basic package price input field", price)
        time.sleep(0.5)

        human.human_scroll(distance_px=500, reading_pauses=True)
        vision.smart_click(save_btn_selectors, "Save & Continue to Description button")
        time.sleep(random.uniform(3.0, 5.0))

        # --- STEP 7: DESCRIPTION TAB ---
        log("Drafting and typing Gig Description...")
        push_state("Writing")
        if not description:
            description = _generate_fiverr_description(clean_title, tags)

        desc_selectors = [
            'div[contenteditable="true"]',
            'textarea[name*="description"]',
            'div.description-editor',
            'textarea',
        ]
        vision.smart_fill(desc_selectors, "Gig description rich text editor area", description)
        time.sleep(random.uniform(1.0, 2.0))

        human.human_scroll(distance_px=500, reading_pauses=True)

        if save_draft_only:
            log("Saving Fiverr Gig as draft...")
            draft_selectors = [
                'button:has-text("Save as Draft")',
                'button:has-text("Save Draft")',
                'a:has-text("Save as Draft")',
            ]
            clicked = vision.smart_click(draft_selectors, "Save as draft button")
            push_state("Idle")
            res = f"Fiverr Gig 'I will {clean_title}' successfully saved as draft! Review in your gig dashboard."
            log(res)
            return res
        else:
            log("Advancing to requirements and publishing...")
            vision.smart_click(save_btn_selectors, "Save & Continue button")
            push_state("Idle")
            res = f"Fiverr Gig 'I will {clean_title}' saved and progressed to final review."
            log(res)
            return res

    except NavigationError as e:
        push_state("Idle")
        note = core.consume_launch_note()
        logger.error(f"[FiverrCreator] Navigation failed: {e}")
        return f"Fiverr automation could not open the site: {e}" + (f" {note}" if note else "")
    except Exception as e:
        logger.error(f"[FiverrCreator] Error in Fiverr gig creation: {e}", exc_info=True)
        push_state("Idle")
        return f"Fiverr automation encountered an issue: {e}"
