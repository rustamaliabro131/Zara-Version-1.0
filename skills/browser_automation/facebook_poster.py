"""
skills/browser_automation/facebook_poster.py — Autonomous Facebook / Creator Studio Poster.

Workflow:
1. Navigates to Facebook feed or Meta Business Suite using persistent Chrome profile.
2. Clicks 'What's on your mind' / 'Create post' with human movement.
3. Types or pastes generated post copy with human typing simulation.
4. Attaches media assets (photos/videos) if provided.
5. Triggers publication or presents confirmation check with state_queue updates.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Optional, Callable

from core import gemini
from engine.browser_core import BrowserCore, NavigationError, wait_for_domain
from engine.human_browser import HumanBrowser
from engine.browser_vision import BrowserVision
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.facebook_poster")


def _generate_social_post(topic: str) -> str:
    """Generate an engaging Facebook post with hashtags and emojis."""
    prompt = (
        f"You are a social media copywriter.\n"
        f"Topic: {topic}\n\n"
        f"Write an engaging, high-reach Facebook post (2-4 concise paragraphs):\n"
        f"- Attention-grabbing opening hook\n"
        f"- Value-packed insights\n"
        f"- Engaging question to spark comments\n"
        f"- 3-5 relevant hashtags."
    )
    copy = gemini.text(prompt, tier=gemini.SMART, default="")
    if not copy:
        copy = (
            f"🚀 Exciting insights on {topic}!\n\n"
            f"Embracing modern technology and smart workflows allows us to accomplish more "
            f"in less time while focusing on what truly matters.\n\n"
            f"What has been your biggest takeaway this week? Drop your thoughts in the comments below!\n\n"
            f"#Innovation #Productivity #TechTrends"
        )
    return copy.strip()


def post_to_facebook(
    post_text: Optional[str] = None,
    media_path: Optional[str] = None,
    topic: Optional[str] = None,
    use_business_suite: bool = False,
    require_confirmation: bool = False,
    confirmation_callback: Optional[Callable[[], bool]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Autonomous Facebook posting workflow.
    """
    def log(msg: str):
        logger.info(f"[FacebookPoster] {msg}")
        if log_callback:
            try:
                log_callback(f"[Facebook] {msg}")
            except Exception:
                pass

    log("Starting Facebook posting workflow...")
    push_state("Analyzing")

    core = BrowserCore.get_instance()
    page = core.get_active_page()
    human = HumanBrowser(page)
    vision = BrowserVision(page, human)

    try:
        # Determine target URL
        target_url = "https://business.facebook.com/latest/home" if use_business_suite else "https://www.facebook.com"
        page = core.navigate(target_url, timeout=60000)
        time.sleep(random.uniform(2.5, 4.0))

        # A page still on about:blank means the load never happened (locked
        # profile, dead context); acting on it would silently do nothing.
        if not wait_for_domain(page, "facebook.com"):
            msg = (
                f"Facebook did not load — the page is still on "
                f"'{page.url or 'about:blank'}'. Please check your connection "
                f"and that no other Chrome window holds the browser profile, then retry."
            )
            log(msg)
            push_state("Idle")
            return msg

        if "login" in page.url.lower():
            msg = "Facebook login detected. Please sign in via the browser window."
            log(msg)
            push_state("Idle")
            return msg

        log("Observing Facebook interface...")
        human.human_observe(1.5)

        # Prepare post content if not provided
        if not post_text:
            log("Generating post copy with Gemini...")
            push_state("Writing")
            post_text = _generate_social_post(topic or "AI and Productivity")

        # Step 1: Open post creation modal
        log("Clicking post creation prompt...")
        create_post_selectors = [
            'div[role="button"]:has-text("What\'s on your mind")',
            'span:has-text("What\'s on your mind")',
            'div[role="button"]:has-text("Create post")',
            'span:has-text("Create post")',
            'div[aria-label*="What\'s on your mind"]',
        ]
        vision.smart_click(
            selectors=create_post_selectors,
            visual_fallback_description="What's on your mind input trigger box",
        )
        time.sleep(random.uniform(2.0, 3.5))

        # Step 2: Locate post text editor
        log("Typing post content...")
        push_state("Writing")
        editor_selectors = [
            'div[role="textbox"][contenteditable="true"]',
            'div[aria-label*="What\'s on your mind"]',
            'div[contenteditable="true"]',
            'textarea',
        ]
        vision.smart_fill(
            selectors=editor_selectors,
            visual_fallback_description="Create Post text input box",
            text=post_text,
            clear_first=False,
        )
        time.sleep(random.uniform(1.0, 2.0))

        # Step 3: Attach Media if supplied
        if media_path and os.path.exists(media_path):
            log(f"Attaching media asset: {media_path}...")
            file_inputs = page.query_selector_all('input[type="file"]')
            attached = False
            for f_in in file_inputs:
                accept = f_in.get_attribute("accept") or ""
                if "image" in accept or "video" in accept or not accept:
                    try:
                        f_in.set_input_files(media_path)
                        attached = True
                        break
                    except Exception:
                        pass

            if not attached:
                # Try clicking photo/video icon
                photo_icon_selectors = [
                    'div[aria-label="Photo/video"]',
                    'div[role="button"]:has-text("Photo/video")',
                    'span:has-text("Photo/video")',
                ]
                vision.smart_click(photo_icon_selectors, "Photo/video attachment button")
                time.sleep(1.0)
                file_inputs = page.query_selector_all('input[type="file"]')
                if file_inputs:
                    file_inputs[-1].set_input_files(media_path)

            log("Media attached. Awaiting upload preview...")
            time.sleep(random.uniform(3.0, 5.0))

        # Human observation of composed post
        human.human_observe(1.5)

        # Step 4: Optional confirmation gate
        if require_confirmation:
            log("Post is composed. Awaiting confirmation before publishing...")
            push_state("Speaking")
            if confirmation_callback:
                if not confirmation_callback():
                    push_state("Idle")
                    return "Facebook post composed as draft. Publication cancelled by user."
            else:
                push_state("Idle")
                return "Facebook post composed in browser. Click 'Post' whenever you are ready."

        # Step 5: Click Post / Publish
        log("Publishing post...")
        post_btn_selectors = [
            'div[aria-label="Post"][role="button"]',
            'button:has-text("Post")',
            'div[role="button"]:has-text("Post")',
            'button:has-text("Publish")',
            'div[role="button"]:has-text("Publish")',
        ]
        pushed = vision.smart_click(
            selectors=post_btn_selectors,
            visual_fallback_description="Blue Post or Publish action button",
        )

        push_state("Idle")
        if pushed:
            msg = "Facebook post successfully published!"
            log(msg)
            return msg
        else:
            return "Facebook post composed in window. Please click Post to finish."

    except NavigationError as e:
        push_state("Idle")
        note = core.consume_launch_note()
        logger.error(f"[FacebookPoster] Navigation failed: {e}")
        return f"Facebook automation could not open the site: {e}" + (f" {note}" if note else "")
    except Exception as e:
        logger.error(f"[FacebookPoster] Error in Facebook poster: {e}", exc_info=True)
        push_state("Idle")
        return f"Facebook automation encountered an issue: {e}"
