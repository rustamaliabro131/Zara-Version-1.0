"""
skills/browser_automation/upwork_bidder.py — Autonomous Upwork Proposal Submitter.

Workflow:
1. Navigates to Upwork job URL using persistent Chrome profile (active session).
2. Reads job specifications and optionally generates a tailored proposal via Gemini.
3. Fills bid rates and types proposal with human-like delays.
4. Performs optional confirmation check before clicking "Submit Proposal".
5. Emits real-time avatar states to state_queue.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional, Callable

from core import gemini
from engine.browser_core import BrowserCore
from engine.human_browser import HumanBrowser
from engine.browser_vision import BrowserVision
from gui.animated_avatar import push_state

logger = logging.getLogger("zara.upwork_bidder")


def _generate_upwork_proposal(job_title: str, job_desc: str) -> str:
    """Generate a high-converting, professional proposal draft using Gemini."""
    prompt = (
        f"You are a top-rated freelance specialist submitting a proposal on Upwork.\n"
        f"Job Title: {job_title}\n"
        f"Job Details: {job_desc}\n\n"
        f"Write a compelling, concise, and professional cover letter (under 200 words):\n"
        f"- Hook the client with immediate understanding of their problem\n"
        f"- Mention relevant experience and concrete implementation approach\n"
        f"- Ask 1-2 thoughtful clarifying questions\n"
        f"- Professional call to action. Do NOT use generic placeholders like [Your Name]."
    )
    draft = gemini.text(prompt, tier=gemini.SMART, default="")
    if not draft:
        draft = (
            f"Hi,\n\nI reviewed your project '{job_title}' carefully. "
            f"I have extensive experience delivering reliable, high-performance solutions "
            f"tailored to these exact requirements. I can get started immediately and ensure "
            f"clean, fully documented results with regular milestones.\n\n"
            f"Looking forward to discussing the specifics.\n\nBest regards,"
        )
    return draft.strip()


def submit_upwork_proposal(
    job_url: str,
    proposal_text: Optional[str] = None,
    bid_amount: Optional[str] = None,
    require_confirmation: bool = False,
    confirmation_callback: Optional[Callable[[], bool]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Autonomous Upwork proposal workflow.
    """
    def log(msg: str):
        logger.info(f"[UpworkBidder] {msg}")
        if log_callback:
            try:
                log_callback(f"[Upwork] {msg}")
            except Exception:
                pass

    log(f"Starting Upwork workflow for: {job_url}")
    push_state("Analyzing")

    core = BrowserCore.get_instance()
    page = core.get_active_page()
    human = HumanBrowser(page)
    vision = BrowserVision(page, human)

    try:
        # Step 1: Navigate to Job URL
        page = core.navigate(job_url)
        time.sleep(random.uniform(2.0, 3.5))

        # Check if login is needed
        if "login" in page.url.lower():
            msg = "Upwork login page detected. Please complete login in the opened browser window."
            log(msg)
            push_state("Idle")
            return msg

        # Observe the page like a human reading job specs
        log("Reading job requirements...")
        human.human_scroll(distance_px=random.randint(400, 700), reading_pauses=True)
        human.human_observe(random.uniform(1.5, 3.0))

        # Extract job title and description if generating proposal
        job_title = ""
        job_desc = ""
        try:
            t_elem = page.query_selector("header h1, h2.h3, h1")
            if t_elem:
                job_title = t_elem.inner_text().strip()
            d_elem = page.query_selector("div.job-description, [data-test='job-description-text'], section p")
            if d_elem:
                job_desc = d_elem.inner_text().strip()[:1000]
        except Exception:
            pass

        # If on view job page, click 'Apply Now' or 'Submit a Proposal'
        apply_selectors = [
            'a[data-qa="apply-button"]',
            'button[data-qa="apply-button"]',
            'a:has-text("Apply Now")',
            'button:has-text("Apply Now")',
            'a:has-text("Submit a Proposal")',
            'button:has-text("Submit a Proposal")',
        ]

        if not ("apply" in page.url.lower() or "proposals/job" in page.url.lower()):
            log("Clicking 'Apply Now'...")
            clicked = vision.smart_click(
                selectors=apply_selectors,
                visual_fallback_description="Apply Now or Submit a Proposal green button",
            )
            if clicked:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                time.sleep(random.uniform(2.5, 4.0))

        # Step 2: Prepare Proposal Content
        if not proposal_text:
            log("Drafting tailored proposal with Gemini...")
            push_state("Analyzing")
            proposal_text = _generate_upwork_proposal(job_title or "Upwork Project", job_desc or "")

        # Step 3: Fill Bid Amount / Hourly Rate if provided
        if bid_amount:
            log(f"Entering bid rate: {bid_amount}...")
            rate_selectors = [
                'input[data-test="currency-input"]',
                'input[aria-labelledby*="rate"]',
                'input[name*="rate"]',
                'input[id*="charge-rate"]',
                'input[type="number"]',
            ]
            vision.smart_fill(
                selectors=rate_selectors,
                visual_fallback_description="Hourly rate or Bid amount numeric input field",
                text=str(bid_amount),
            )
            time.sleep(random.uniform(0.5, 1.2))

        # Step 4: Scroll down to Cover Letter section
        log("Scrolling to cover letter section...")
        human.human_scroll(distance_px=500, reading_pauses=True)

        # Step 5: Fill Cover Letter
        log("Typing proposal cover letter...")
        cover_letter_selectors = [
            'textarea[aria-labelledby*="cover-letter"]',
            'textarea[data-qa="cover-letter-textarea"]',
            'textarea[data-test="cover-letter-text"]',
            'div[contenteditable="true"][data-qa*="cover-letter"]',
            'textarea',
        ]
        vision.smart_fill(
            selectors=cover_letter_selectors,
            visual_fallback_description="Cover letter proposal multi-line text area",
            text=proposal_text,
            clear_first=True,
        )
        time.sleep(random.uniform(1.0, 2.0))

        # Scroll to bottom
        human.human_scroll(distance_px=600, reading_pauses=True)

        # Step 6: Confirmation check
        submit_btn_selectors = [
            'button[data-qa="btn-submit"]',
            'button[data-test="btn-submit"]',
            'button:has-text("Submit Proposal")',
            'button:has-text("Send for")',
        ]

        if require_confirmation:
            log("Proposal filled. Awaiting user confirmation before clicking Submit...")
            push_state("Speaking")
            if confirmation_callback:
                confirmed = confirmation_callback()
                if not confirmed:
                    push_state("Idle")
                    return "Proposal filled as draft. Submission cancelled by user."
            else:
                # If no callback provided, leave as draft for manual review
                push_state("Idle")
                return "Proposal filled in browser. Review and click 'Submit' whenever ready."

        # Step 7: Click Submit
        log("Submitting proposal...")
        pushed = vision.smart_click(
            selectors=submit_btn_selectors,
            visual_fallback_description="Submit Proposal green primary button",
        )

        push_state("Idle")
        if pushed:
            msg = f"Upwork proposal successfully submitted for '{job_title or 'Job'}'!"
            log(msg)
            return msg
        else:
            return "Proposal typed into form. Please inspect browser to complete final submission."

    except Exception as e:
        logger.error(f"[UpworkBidder] Error during proposal submission: {e}", exc_info=True)
        push_state("Idle")
        return f"Upwork automation encountered an issue: {e}"
