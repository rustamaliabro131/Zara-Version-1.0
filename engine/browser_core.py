"""
engine/browser_core.py — Persistent Browser Core for Zara AI Assistant.

Uses Playwright (Python) to launch or attach to a persistent Chromium user context
pointing to the user's local Chrome User Data directory.
Retains active logins, session cookies, local storage across sessions
(Upwork, Fiverr, Facebook, Amazon KDP, Daraz).
Operates in visible (headless=False) and maximized window mode.
"""

from __future__ import annotations

import logging
import os
import platform
import queue
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Any

from playwright.sync_api import (
    sync_playwright,
    BrowserContext,
    Page,
    Playwright,
    Error as PlaywrightError,
)

from gui.animated_avatar import push_state, state_queue

logger = logging.getLogger("zara.browser_core")

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def get_default_chrome_user_data_dir() -> Path:
    """Return the default system path to Google Chrome's User Data directory."""
    home = Path.home()
    if _OS == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Google" / "Chrome" / "User Data"
        return home / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    elif _OS == "Darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    else:  # Linux
        return home / ".config" / "google-chrome"


def get_zara_isolated_profile_dir() -> Path:
    """Fallback persistent profile directory when primary Chrome profile is locked."""
    profile_dir = Path.home() / ".zara_browser_profile" / "chrome"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


class BrowserCore:
    """
    Manages a persistent, visible Chromium browser instance using Playwright.
    Provides session reuse, active page access, and anti-bot stealth configurations.
    """

    _instance: Optional["BrowserCore"] = None
    _lock = threading.Lock()

    def __init__(self, user_data_dir: Optional[str] = None, headless: bool = False):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._active_page: Optional[Page] = None
        self._is_running = False

        # Sync Playwright is bound to the thread that starts it: its connection
        # cannot be used from another thread ("Cannot switch to a different
        # thread"), and starting it on a thread that is running an asyncio loop
        # raises "Playwright Sync API inside the asyncio loop". Zara dispatches
        # its tools from an asyncio session, so every Playwright call is
        # confined to this one dedicated owner thread — which never runs a loop
        # — and marshalled onto it from wherever the caller happens to be.
        self._owner: Optional[threading.Thread] = None
        self._requests: "queue.Queue[tuple]" = queue.Queue()
        self._owner_lock = threading.Lock()

    def _ensure_owner(self) -> None:
        """Start the dedicated Playwright thread, once."""
        with self._owner_lock:
            if self._owner is not None and self._owner.is_alive():
                return
            self._requests = queue.Queue()
            self._owner = threading.Thread(
                target=self._owner_loop, daemon=True, name="zara-playwright",
            )
            self._owner.start()

    def _owner_loop(self) -> None:
        """The only thread permitted to touch the sync Playwright API.

        It runs no event loop, so sync_playwright() is legal here, and it is the
        sole owner of the connection, so no call can cross threads. Requests are
        (fn, box); the box carries the result or the exception back to the
        caller and an Event to release it.
        """
        while True:
            item = self._requests.get()
            if item is None:
                break
            fn, box = item
            try:
                box["val"] = fn()
            except BaseException as e:      # noqa: BLE001 — re-raised on the caller
                box["err"] = e
            finally:
                box["event"].set()

    def _on_owner_thread(self) -> bool:
        return threading.current_thread() is self._owner

    def _marshall(self, fn: Callable[[], Any], timeout: float = 300.0) -> Any:
        """Run `fn` on the owner thread unless we are already on it.

        The re-entrancy check matters: a workflow running on the owner thread
        calls back into methods like navigate(), and marshalling there would
        deadlock the owner against itself.
        """
        if self._on_owner_thread():
            return fn()
        self._ensure_owner()
        box: dict = {"event": threading.Event()}
        self._requests.put((fn, box))
        if not box["event"].wait(timeout):
            raise TimeoutError(f"Browser operation timed out after {timeout:.0f}s")
        if box.get("err") is not None:
            raise box["err"]
        return box.get("val")

    def run_on_browser_thread(self, fn: Callable[[], Any], timeout: float = 600.0) -> Any:
        """Run a whole browser workflow on the owner thread.

        The automation skills hold onto the returned `page` and drive it with
        sync calls, so the entire workflow — not just individual calls — has to
        execute where the Playwright connection lives. Public so the action
        layer can dispatch onto the owner thread without importing internals.
        """
        return self._marshall(fn, timeout)

    @classmethod
    def get_instance(cls, user_data_dir: Optional[str] = None, headless: bool = False) -> "BrowserCore":
        with cls._lock:
            if cls._instance is None or not cls._instance.is_active():
                cls._instance = cls(user_data_dir=user_data_dir, headless=headless)
            return cls._instance

    def is_active(self) -> bool:
        """Check if browser context is running and still has open pages.

        Callable from any thread: touching the context from a foreign thread
        raises "Cannot switch to a different thread", so off the owner thread we
        trust the running flag and let the owner thread revalidate the pages.
        """
        if not self._is_running or self._context is None:
            return False
        if not self._on_owner_thread():
            return True
        try:
            pages = self._context.pages
            return len(pages) > 0
        except Exception:
            return False

    def launch(
        self,
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        use_chrome_channel: bool = True,
    ) -> BrowserContext:
        """Launch or attach to the persistent browser context, on the owner thread."""
        return self._marshall(
            lambda: self._launch_impl(user_data_dir, headless, use_chrome_channel)
        )

    def _launch_impl(
        self,
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        use_chrome_channel: bool = True,
    ) -> BrowserContext:
        """
        Launch or attach to persistent browser context.
        Attempts to use real Chrome User Data, with graceful fallback if locked.
        Must run on the owner thread.
        """
        with self._lock:
            if self.is_active():
                return self._context  # type: ignore

            push_state("Processing")
            logger.info("[BrowserCore] Starting Playwright engine...")

            if self._playwright is None:
                self._playwright = sync_playwright().start()

            # Determine profile directory
            target_profile: Path
            if user_data_dir:
                target_profile = Path(user_data_dir)
            elif self.user_data_dir:
                target_profile = Path(self.user_data_dir)
            else:
                default_profile = get_default_chrome_user_data_dir()
                if default_profile.exists():
                    target_profile = default_profile
                else:
                    target_profile = get_zara_isolated_profile_dir()

            logger.info(f"[BrowserCore] Target profile directory: {target_profile}")

            # Stealth & maximized args
            launch_args = [
                "--start-maximized",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-features=IsolateOrigins,site-per-process",
            ]

            # Try launching with specified profile
            context = None
            tried_fallback = False

            while context is None:
                try:
                    kwargs: dict[str, Any] = {
                        "user_data_dir": str(target_profile),
                        "headless": headless,
                        "args": launch_args,
                        "no_viewport": True,
                        "ignore_default_args": ["--enable-automation"],
                    }

                    if use_chrome_channel:
                        try:
                            context = self._playwright.chromium.launch_persistent_context(
                                channel="chrome", **kwargs
                            )
                        except Exception as channel_err:
                            logger.warning(
                                f"[BrowserCore] Chrome channel launch failed ({channel_err}); falling back to default chromium."
                            )
                            context = self._playwright.chromium.launch_persistent_context(**kwargs)
                    else:
                        context = self._playwright.chromium.launch_persistent_context(**kwargs)

                except PlaywrightError as pe:
                    err_msg = str(pe).lower()
                    if (
                        "close" in err_msg
                        or "lock" in err_msg
                        or "processsingleton" in err_msg
                        or "user data directory is already in use" in err_msg
                    ) and not tried_fallback:
                        logger.warning(
                            f"[BrowserCore] Primary profile {target_profile} is locked by an active Chrome process. "
                            f"Falling back to Zara persistent profile."
                        )
                        target_profile = get_zara_isolated_profile_dir()
                        tried_fallback = True
                    else:
                        logger.error(f"[BrowserCore] Failed to launch browser context: {pe}")
                        raise pe

            self._context = context
            self._is_running = True

            # Ensure at least one page is open and configured
            if not self._context.pages:
                self._active_page = self._context.new_page()
            else:
                self._active_page = self._context.pages[0]

            # Anti-detection stealth injections
            try:
                self._active_page.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.chrome = {
                        runtime: {}
                    };
                    """
                )
            except Exception as e:
                logger.debug(f"[BrowserCore] Stealth script injection notice: {e}")

            push_state("Idle")
            logger.info("[BrowserCore] Browser successfully launched and ready.")
            return self._context

    def get_context(self) -> BrowserContext:
        """Get or initialize the persistent browser context (any thread)."""
        return self._marshall(
            lambda: self._context
            if self.is_active()
            else self._launch_impl(self.user_data_dir, self.headless)
        )

    def get_active_page(self) -> Page:
        """Get the current active page or create one (any thread)."""
        return self._marshall(self._get_active_page_impl)

    def _get_active_page_impl(self) -> Page:
        ctx = self._context if self.is_active() else self._launch_impl(
            self.user_data_dir, self.headless)
        if not ctx.pages:
            self._active_page = ctx.new_page()
        else:
            # Prefer last focused or first page
            self._active_page = ctx.pages[-1]
        return self._active_page

    def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 45000,
    ) -> Page:
        """Navigate active page to URL with state notifications (any thread)."""
        return self._marshall(
            lambda: self._navigate_impl(url, wait_until, timeout)
        )

    def _navigate_impl(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 45000,
    ) -> Page:
        page = self._get_active_page_impl()
        push_state("Analyzing")
        logger.info(f"[BrowserCore] Navigating to: {url}")
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as e:
            logger.warning(f"[BrowserCore] Navigation warning on {url}: {e}")
        return page

    def close(self) -> None:
        """Safely close context and stop Playwright (any thread)."""
        self._marshall(self._close_impl)

    def _close_impl(self) -> None:
        with self._lock:
            push_state("Processing")
            try:
                if self._context:
                    self._context.close()
            except Exception as e:
                logger.debug(f"[BrowserCore] Context close: {e}")
            finally:
                self._context = None
                self._active_page = None
                self._is_running = False

            try:
                if self._playwright:
                    self._playwright.stop()
            except Exception as e:
                logger.debug(f"[BrowserCore] Playwright stop: {e}")
            finally:
                self._playwright = None

            push_state("Idle")
            logger.info("[BrowserCore] Browser closed.")

    def __enter__(self) -> Page:
        self.launch(headless=self.headless)
        return self.get_active_page()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Keep open for inspection or close on explicit call
        pass


def get_logged_in_browser(
    user_data_dir: Optional[str] = None,
    headless: bool = False,
) -> BrowserContext:
    """
    Connects to persistent user profile so cookies/logins stay active.
    Opens browser pointing to default or specified Chrome profile data directory.
    Operates in visible mode with maximized window.
    """
    core = BrowserCore.get_instance(user_data_dir=user_data_dir, headless=headless)
    return core.get_context()


def get_active_page() -> Page:
    """Convenience helper to retrieve the active browser page."""
    core = BrowserCore.get_instance()
    return core.get_active_page()
