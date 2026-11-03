"""
skills/browser_automation/amazon_kdp_publisher.py — Autonomous Amazon KDP eBook Publisher.

Workflow:
1. Accesses Amazon KDP Bookshelf dashboard using persistent Chrome session.
2. Fills eBook metadata (Title, Subtitle, Author, Description, Rights, Keywords).
3. Attaches local manuscript and cover artwork.
4. Human scrolls through pricing and royalty selections (35% vs 70%, USD list price).
5. Saves as draft or triggers publication with state_queue status updates.
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, List, Callable

from core import gemini
from engine.browser_core import BrowserCore
from engine.human_browser import HumanBrowser
from engine.browser_vision import BrowserVision
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.kdp_publisher")


def _generate_kdp_description(title: str, topic_or_summary: str) -> str:
    """Generate engaging Amazon book description with bullet points."""
    prompt = (
        f"You are a bestselling book marketer for Amazon Kindle.\n"
        f"Title: {title}\n"
        f"Topic / Summary: {topic_or_summary}\n\n"
        f"Write a high-converting Amazon KDP book description formatted with HTML tags "
        f"(<b>, <i>, <p>, <ul>, <li>). Include a hook, bullet points of key takeaways, "
        f"and a strong call-to-action."
    )
    desc = gemini.text(prompt, tier=gemini.SMART, default="")
    if not desc:
        desc = (
            f"<p><b>{title}</b> is your definitive guide to mastering essential insights and strategies.</p>"
            f"<p>Whether you are starting out or looking to elevate your understanding, this book delivers "
            f"practical, actionable knowledge you can apply immediately.</p>"
            f"<ul><li>In-depth breakdown of core concepts</li><li>Real-world strategies and examples</li>"
            f"<li>Step-by-step guidance designed for results</li></ul>"
            f"<p><i>Scroll up and get your copy today!</i></p>"
        )
    return desc.strip()


def publish_kdp_ebook(
    title: str,
    subtitle: Optional[str] = None,
    description: Optional[str] = None,
    author_first: str = "Zara",
    author_last: str = "Author",
    keywords: Optional[List[str]] = None,
    manuscript_path: Optional[str] = None,
    cover_path: Optional[str] = None,
    list_price: str = "2.99",
    royalty_rate: str = "70%",
    save_draft_only: bool = True,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Autonomous Amazon KDP publication routine.
    """
    def log(msg: str):
        logger.info(f"[KDPPublisher] {msg}")
        if log_callback:
            try:
                log_callback(f"[KDP] {msg}")
            except Exception:
                pass

    log(f"Starting Amazon KDP publication process for: '{title}'")
    push_state("Analyzing")

    core = BrowserCore.get_instance()
    page = core.get_active_page()
    human = HumanBrowser(page)
    vision = BrowserVision(page, human)

    try:
        # Step 1: Navigate to KDP Bookshelf
        kdp_url = "https://kdp.amazon.com/en_US/bookshelf"
        page = core.navigate(kdp_url)
        time.sleep(random.uniform(2.5, 4.0))

        if "signin" in page.url.lower() or "ap/signin" in page.url.lower():
            msg = "Amazon KDP sign-in detected. Please log in on the browser window to continue."
            log(msg)
            push_state("Idle")
            return msg

        log("Observing KDP bookshelf...")
        human.human_observe(1.5)

        # Step 2: Click "Create" or "+ Kindle eBook"
        create_selectors = [
            'a[href*="title-setup"]:has-text("Create")',
            'button:has-text("Create")',
            'a:has-text("Create")',
            'span:has-text("Create")',
            'a[id*="create-title"]',
        ]
        log("Navigating to title creation...")
        vision.smart_click(
            selectors=create_selectors,
            visual_fallback_description="Create new title yellow or orange button",
        )
        time.sleep(random.uniform(2.0, 3.5))

        # Check if eBook button appears on creation modal
        ebook_btn_selectors = [
            'button[id*="kindle-button"]',
            'a:has-text("Create eBook")',
            'button:has-text("Create eBook")',
            'span:has-text("Create eBook")',
            'div:has-text("Kindle eBook")',
        ]
        vision.smart_click(
            selectors=ebook_btn_selectors,
            visual_fallback_description="Create Kindle eBook action button",
        )
        time.sleep(random.uniform(2.0, 3.0))

        # --- TAB 1: KINDLE EBOOK DETAILS ---
        log("Filling eBook Title and Subtitle...")
        push_state("Writing")
        title_selectors = ['input[name*="title"]', 'input[id*="title"]', '#data-print-book-title']
        vision.smart_fill(title_selectors, "Book title input text field", title)

        if subtitle:
            sub_selectors = ['input[name*="subtitle"]', 'input[id*="subtitle"]']
            vision.smart_fill(sub_selectors, "Book subtitle input text field", subtitle)

        # Author name
        log("Setting author details...")
        first_name_selectors = ['input[name*="first_name"]', 'input[id*="author-first-name"]', 'input[name*="authorFirstName"]']
        last_name_selectors = ['input[name*="last_name"]', 'input[id*="author-last-name"]', 'input[name*="authorLastName"]']
        vision.smart_fill(first_name_selectors, "Author first name field", author_first)
        vision.smart_fill(last_name_selectors, "Author last name field", author_last)

        # Description
        log("Setting book description...")
        if not description:
            description = _generate_kdp_description(title, subtitle or title)

        desc_selectors = [
            'textarea[id*="description"]',
            'div[contenteditable="true"]',
            'textarea[name*="description"]',
        ]
        vision.smart_fill(desc_selectors, "Book description rich text area", description)

        # Publishing Rights
        log("Selecting copyright ownership...")
        human.human_scroll(distance_px=450, reading_pauses=True)
        rights_selectors = [
            'input[value="CR"]',
            'input[id*="copyright-radio-btn"]',
            'label:has-text("I own the copyright")',
        ]
        vision.smart_click(rights_selectors, "I own the copyright radio option")

        # Keywords (up to 7)
        if not keywords:
            keywords = [
                title.lower(),
                "guide",
                "handbook",
                "practical strategies",
                "bestseller",
            ]

        log(f"Entering {len(keywords)} search keywords...")
        human.human_scroll(distance_px=350, reading_pauses=True)
        for i, kw in enumerate(keywords[:7]):
            kw_selectors = [
                f'input[id*="keywords-{i}"]',
                f'input[name*="keywords[{i}]"]',
                f'input[id*="keyword"][tabindex="{i+1}"]',
            ]
            vision.smart_fill(kw_selectors, f"Search keyword box #{i+1}", kw)
            time.sleep(0.15)

        # Save and Continue to Content Tab
        log("Saving eBook details and proceeding to Content...")
        save_continue_selectors = [
            'button[id*="save-and-continue"]',
            'input[id*="save-and-continue"]',
            'button:has-text("Save and Continue")',
        ]
        human.human_scroll(distance_px=400, reading_pauses=True)
        vision.smart_click(save_continue_selectors, "Save and Continue primary yellow button")
        time.sleep(random.uniform(3.5, 6.0))

        # --- TAB 2: MANUSCRIPT & COVER FILES ---
        if manuscript_path and os.path.exists(manuscript_path):
            log(f"Uploading manuscript from: {manuscript_path}...")
            push_state("Writing")
            file_inputs = page.query_selector_all('input[type="file"]')
            if file_inputs:
                file_inputs[0].set_input_files(manuscript_path)
                log("Manuscript file selected. Waiting for initial processing...")
                time.sleep(random.uniform(3.0, 5.0))
            else:
                log("Locating manuscript upload trigger via vision...")
                vision.click("Upload eBook manuscript button")
                time.sleep(1.0)

        if cover_path and os.path.exists(cover_path):
            log(f"Uploading cover image from: {cover_path}...")
            file_inputs = page.query_selector_all('input[type="file"]')
            if len(file_inputs) > 1:
                file_inputs[1].set_input_files(cover_path)
            else:
                vision.smart_click(
                    ['button:has-text("Upload a cover")', 'span:has-text("Upload a cover")'],
                    "Upload a cover you already have button",
                )
            time.sleep(random.uniform(2.5, 4.0))

        # Continue to Pricing
        human.human_scroll(distance_px=600, reading_pauses=True)
        vision.smart_click(save_continue_selectors, "Save and Continue to pricing button")
        time.sleep(random.uniform(3.0, 5.0))

        # --- TAB 3: PRICING & ROYALTIES ---
        log(f"Setting royalty plan ({royalty_rate}) and list price (${list_price})...")
        push_state("Analyzing")
        human.human_scroll(distance_px=300, reading_pauses=True)

        # Select royalty radio
        if "70" in royalty_rate:
            vision.smart_click(
                ['input[value="70%"]', 'input[id*="royalty-70"]', 'label:has-text("70% Plan")'],
                "70 percent royalty option radio button",
            )
        else:
            vision.smart_click(
                ['input[value="35%"]', 'input[id*="royalty-35"]', 'label:has-text("35% Plan")'],
                "35 percent royalty option radio button",
            )

        # List price field
        price_selectors = [
            'input[id*="price-input"]',
            'input[name*="list_price"]',
            'input[data-qa*="price"]',
            'input[placeholder*="0.00"]',
        ]
        vision.smart_fill(price_selectors, "Amazon.com USD list price text box", list_price)

        # Human scroll down pricing grid to inspect international royalties
        log("Inspecting worldwide pricing grid...")
        human.human_scroll(distance_px=500, reading_pauses=True)
        human.human_observe(1.5)

        # Save as Draft or Publish
        if save_draft_only:
            log("Saving as Draft on KDP...")
            draft_selectors = [
                'button[id*="save-draft"]',
                'button:has-text("Save as Draft")',
                'span:has-text("Save as Draft")',
            ]
            vision.smart_click(draft_selectors, "Save as Draft grey button")
            push_state("Idle")
            res = f"Amazon KDP eBook '{title}' successfully saved as draft! Review anytime in your bookshelf."
            log(res)
            return res
        else:
            log("Publishing eBook to Kindle store...")
            publish_selectors = [
                'button[id*="publish"]',
                'button:has-text("Publish Your Kindle eBook")',
                'span:has-text("Publish Your Kindle eBook")',
            ]
            vision.smart_click(publish_selectors, "Publish Your Kindle eBook yellow button")
            push_state("Idle")
            res = f"Amazon KDP eBook '{title}' submitted for publication!"
            log(res)
            return res

    except Exception as e:
        logger.error(f"[KDPPublisher] Error in KDP publishing: {e}", exc_info=True)
        push_state("Idle")
        return f"Amazon KDP automation encountered an issue: {e}"
