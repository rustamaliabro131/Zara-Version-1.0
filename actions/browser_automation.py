"""
actions/browser_automation.py — Autonomous Browser Control Engine for Zara.

Integrates persistent Playwright context, human simulation layers, and Gemini Vision
for end-to-end platform workflows:
- Upwork Bidder (proposal drafting, bid filling, submission)
- Amazon KDP Publisher (metadata, files upload, royalty pricing)
- Fiverr Gig Creator (title, category, search tags, description, pricing)
- Facebook Poster (feed / Creator Studio, text, media attachment, publishing)
- Daraz Shopper (search, review, cart)
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from gui.animated_avatar import push_state
from skills.browser_automation.upwork_bidder import submit_upwork_proposal
from skills.browser_automation.amazon_kdp_publisher import publish_kdp_ebook
from skills.browser_automation.fiverr_gig_creator import create_fiverr_gig
from skills.browser_automation.facebook_poster import post_to_facebook
from skills.browser_automation.daraz_shopper import shop_daraz

logger = logging.getLogger("zara.action.browser_automation")


def browser_automation(parameters: dict, player=None, speak=None) -> str:
    """
    Dispatcher for Zara's Autonomous Browser Control Engine.

    The workflow runs on BrowserCore's dedicated Playwright thread: the skills
    below drive a sync `page` object directly, and a sync Playwright connection
    may only be touched by the thread that owns it. Marshalling the whole
    workflow (not just the launch) keeps every page call on that thread and off
    Zara's asyncio loop, which is what raised "Playwright Sync API inside the
    asyncio loop" before.
    """
    from engine.browser_core import BrowserCore
    core = BrowserCore.get_instance()
    return core.run_on_browser_thread(
        lambda: _run_browser_automation(parameters, player, speak)
    )


def _run_browser_automation(parameters: dict, player=None, speak=None) -> str:
    """
    Executes tasks with human-like interactions, persistent logins, and vision fallbacks.
    Runs on BrowserCore's Playwright owner thread.
    """
    params = parameters or {}
    platform = str(params.get("platform") or "").lower().strip()
    action = str(params.get("action") or "").lower().strip()
    url = str(params.get("url") or "").strip()
    title = str(params.get("title") or "").strip()
    text = str(params.get("text") or "").strip()
    amount = str(params.get("amount") or params.get("price") or "").strip()
    keywords = params.get("keywords") or params.get("tags") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    manuscript_path = str(params.get("manuscript_path") or "").strip() or None
    cover_path = str(params.get("cover_path") or params.get("media_path") or "").strip() or None
    require_confirmation = bool(params.get("require_confirmation", False))

    def log(msg: str):
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"[BrowserEngine] {msg}")
            except Exception:
                pass

    log(f"Received request for platform='{platform}', action='{action}'")

    # 1. UPWORK WORKFLOW
    if "upwork" in platform or "bid" in action or ("upwork.com" in url):
        target_url = url or "https://www.upwork.com/nx/find-work/"
        if speak:
            speak("Opening Upwork in your browser. Preparing proposal submission.")
        return submit_upwork_proposal(
            job_url=target_url,
            proposal_text=text or None,
            bid_amount=amount or None,
            require_confirmation=require_confirmation,
            log_callback=log,
        )

    # 2. AMAZON KDP WORKFLOW
    elif "kdp" in platform or "amazon" in platform or "ebook" in action:
        if not title:
            title = text or "Autonomous Guide"
        if speak:
            speak(f"Accessing Amazon KDP dashboard to prepare publication for '{title}'.")
        return publish_kdp_ebook(
            title=title,
            subtitle=str(params.get("subtitle") or "") or None,
            description=text or None,
            author_first=str(params.get("author_first") or "Zara"),
            author_last=str(params.get("author_last") or "Assistant"),
            keywords=keywords or None,
            manuscript_path=manuscript_path,
            cover_path=cover_path,
            list_price=amount or "2.99",
            royalty_rate=str(params.get("royalty_rate") or "70%"),
            save_draft_only=bool(params.get("save_draft_only", True)),
            log_callback=log,
        )

    # 3. FIVERR WORKFLOW
    elif "fiverr" in platform or "gig" in action:
        gig_title = title or text or "develop python ai automation agents"
        if speak:
            speak(f"Opening Fiverr seller dashboard to create gig for '{gig_title}'.")
        return create_fiverr_gig(
            title=gig_title,
            category=str(params.get("category") or "Programming & Tech"),
            subcategory=str(params.get("subcategory") or "AI Applications"),
            tags=keywords or None,
            description=text or None,
            price=amount or "50",
            delivery_days=str(params.get("delivery_days") or "3"),
            save_draft_only=bool(params.get("save_draft_only", True)),
            log_callback=log,
        )

    # 4. FACEBOOK WORKFLOW
    elif "facebook" in platform or "fb" in platform or "post" in action:
        if speak:
            speak("Opening Facebook to publish your post.")
        return post_to_facebook(
            post_text=text or None,
            media_path=cover_path,
            topic=title or None,
            use_business_suite=bool(params.get("business_suite", False)),
            require_confirmation=require_confirmation,
            log_callback=log,
        )

    # 5. DARAZ WORKFLOW
    elif "daraz" in platform or "shop" in action or ("daraz." in url):
        search_query = title or text or params.get("query") or "electronics"
        if speak:
            speak(f"Opening Daraz to search for {search_query}.")
        return shop_daraz(
            search_query=str(search_query),
            action="buy_now" if action == "buy" else "add_to_cart",
            log_callback=log,
        )

    # Fallback / General URL Navigation
    elif url:
        from engine.browser_core import BrowserCore
        core = BrowserCore.get_instance()
        page = core.navigate(url)
        return f"Navigated to {url} using persistent browser session."

    else:
        return (
            "Please specify a valid platform ('upwork', 'amazon_kdp', 'fiverr', 'facebook', 'daraz') "
            "or provide a URL to automate."
        )


# ── Action schema for action_loader ───────────────────────────────────────────
TOOL = {
    "name": "browser_automation",
    "description": (
        "Full Autonomous Browser Control Engine for Zara using persistent Chrome user data, "
        "human-like mouse movements, organic scrolling, and Gemini Vision AI for DOM fallbacks. "
        "Use this tool for automated platform workflows: "
        "1) Upwork ('upwork'): Apply to jobs, generate proposals, set bid rates, submit bids. "
        "2) Amazon KDP ('amazon_kdp'): Fill eBook title, description, keywords, upload manuscript/cover, configure pricing. "
        "3) Fiverr ('fiverr'): Create and publish gigs, fill categories, tags, description, and pricing. "
        "4) Facebook ('facebook'): Compose and publish posts on Facebook or Meta Business Suite, attach media. "
        "5) Daraz ('daraz'): Search products, inspect listings, add items to cart."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "platform": {
                "type": "STRING",
                "description": "Target platform: 'upwork' | 'amazon_kdp' | 'fiverr' | 'facebook' | 'daraz'",
            },
            "action": {
                "type": "STRING",
                "description": "Task action: 'bid' | 'publish' | 'create_gig' | 'post' | 'shop' | 'navigate'",
            },
            "url": {
                "type": "STRING",
                "description": "Target URL (e.g. Upwork job URL, product link)",
            },
            "title": {
                "type": "STRING",
                "description": "Title for eBook, Fiverr gig, or post topic",
            },
            "text": {
                "type": "STRING",
                "description": "Proposal draft, post content, or gig description",
            },
            "amount": {
                "type": "STRING",
                "description": "Bid rate, eBook list price, or gig package price",
            },
            "keywords": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Search keywords or gig tags",
            },
            "manuscript_path": {
                "type": "STRING",
                "description": "Local file path to eBook manuscript (.docx, .epub, .pdf, .kpf)",
            },
            "cover_path": {
                "type": "STRING",
                "description": "Local file path to cover image or social post media (.jpg, .png)",
            },
            "require_confirmation": {
                "type": "BOOLEAN",
                "description": "Whether to pause for user confirmation before final financial/publication click",
            },
        },
        "required": ["platform"],
    },
    "handler": browser_automation,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
