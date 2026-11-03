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

# A page that never left about:blank after a goto means navigation did not
# happen — a locked profile, a hung load, or a dead context. Callers must be
# able to tell that apart from a real page, so navigate() raises this instead
# of silently returning a blank page for the skills to click at.
BLANK_URLS = ("about:blank", "", "chrome://newtab/", "chrome://new-tab-page/")

# Domains that only show a login wall; the skills detect these themselves, so
# reaching one counts as a successful navigation.
LOGIN_MARKERS = ("login", "signin", "sign-in", "ap/signin")


class NavigationError(RuntimeError):
    """Raised when a page could not be navigated to a real URL."""


def _looks_blank(url: str) -> bool:
    u = (url or "").strip().lower()
    return u in BLANK_URLS or u.startswith("about:") or u.startswith("chrome://")


def wait_for_domain(page: "Page", domain: str, timeout: int = 30000) -> bool:
    """Wait until `page.url` is on `domain` (or a login wall on it).

    Skills call this after navigate() and before touching elements: acting on a
    page that is still about:blank is the blank-page hang. Returns True once the
    URL matches, False on timeout, and never raises — the caller decides what a
    miss means.
    """
    needle = (domain or "").strip().lower()
    if not needle:
        return not _looks_blank(page.url)
    deadline = time.monotonic() + max(0, timeout) / 1000.0
    while True:
        url = (page.url or "").lower()
        if needle in url or any(m in url for m in LOGIN_MARKERS):
            return True
        if time.monotonic() >= deadline:
            return False
        try:
            page.wait_for_timeout(250)
        except Exception:
            return False


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


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID exists (POSIX; harmless guess on Windows)."""
    if pid <= 0:
        return False
    try:
        if _OS == "Windows":
            import subprocess
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def profile_in_use(profile_dir: Path) -> Optional[int]:
    """Return the PID holding Chrome's profile lock, or None if it is free.

    A running Chrome holds the profile open: Playwright's launch_persistent_context
    then either fails or (worse) hands off to the running browser and returns a
    context that never navigates, leaving the page on about:blank. Chrome signals
    this with a SingletonLock symlink whose target is "<hostname>-<pid>"; on
    Windows the lock file itself carries the PID.
    """
    try:
        lock = profile_dir / "SingletonLock"
        if lock.is_symlink():
            target = os.readlink(lock)
            pid = int(str(target).rsplit("-", 1)[-1])
            return pid if _pid_alive(pid) else None
        win_lock = profile_dir / "lockfile"
        if win_lock.exists():
            try:
                pid = int(win_lock.read_text(errors="ignore").strip() or 0)
            except (ValueError, OSError):
                pid = 0
            return pid if pid and _pid_alive(pid) else None
    except (OSError, ValueError):
        pass
    return None


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

        # Human-readable note about the last launch (e.g. "profile was locked,
        # used the Zara profile instead"). Skills read and clear it so the user
        # hears *why* their logins may be missing, instead of guessing.
        self.last_launch_note: Optional[str] = None

    def consume_launch_note(self) -> Optional[str]:
        """Return and clear the last launch note (any thread)."""
        note, self.last_launch_note = self.last_launch_note, None
        return note

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

            # If a Chrome instance already holds this profile, launching it would
            # hand off to the running browser and yield a context that never
            # navigates (the about:blank hang). Detect that up front and use the
            # Zara profile, telling the user why their logins may not appear.
            lock_pid = profile_in_use(target_profile)
            if lock_pid is not None:
                fallback = get_zara_isolated_profile_dir()
                note = (
                    f"Chrome (PID {lock_pid}) already has the profile at "
                    f"{target_profile} open, so Zara opened its own browser "
                    f"profile instead. Your saved logins for this profile will "
                    f"not be available; close Chrome and retry to reuse them."
                )
                logger.warning(f"[BrowserCore] {note}")
                self.last_launch_note = note
                target_profile = fallback

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
                        note = (
                            f"Chrome already has the profile at {target_profile} "
                            f"open, so Zara opened its own browser profile instead. "
                            f"Your saved logins for this profile will not be "
                            f"available; close Chrome and retry to reuse them."
                        )
                        logger.warning(f"[BrowserCore] {note}")
                        self.last_launch_note = note
                        target_profile = get_zara_isolated_profile_dir()
                        tried_fallback = True
                    else:
                        logger.error(f"[BrowserCore] Failed to launch browser context: {pe}")
                        raise pe

            self._context = context
            self._is_running = True

            # Stealth on the context so every page it opens carries it, not just
            # whichever page happened to exist at launch time.
            try:
                self._context.add_init_script(
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

            # Select the page to drive. A persistent profile restores its tabs,
            # so pages[0] can be a stale blank tab; prefer a real one.
            self._active_page = self._pick_page(self._context)

            push_state("Idle")
            logger.info("[BrowserCore] Browser successfully launched and ready.")
            return self._context

    @staticmethod
    def _pick_page(context: BrowserContext) -> Page:
        """Return a usable page, preferring one that is not about:blank."""
        pages = context.pages
        if not pages:
            return context.new_page()
        for page in reversed(pages):
            try:
                if not _looks_blank(page.url):
                    return page
            except Exception:
                continue
        return pages[-1]

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
        # Reuse the cached page when it is still open, so a workflow's page does
        # not change under it between calls.
        cached = self._active_page
        if cached is not None:
            try:
                if not cached.is_closed():
                    return cached
            except Exception:
                pass
        ctx = self._context if self.is_active() else self._launch_impl(
            self.user_data_dir, self.headless)
        self._active_page = self._pick_page(ctx)
        return self._active_page

    def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
        attempts: int = 2,
    ) -> Page:
        """Navigate the active page to `url` (any thread).

        Raises NavigationError when the page is still blank afterwards, so a
        locked profile or a dead load surfaces as a clear message instead of a
        blank page the skills would silently click at.
        """
        return self._marshall(
            lambda: self._navigate_impl(url, wait_until, timeout, attempts)
        )

    def _navigate_impl(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
        attempts: int = 2,
    ) -> Page:
        page = self._get_active_page_impl()
        push_state("Analyzing")

        last_err: Optional[Exception] = None
        for attempt in range(1, max(1, attempts) + 1):
            logger.info(
                f"[BrowserCore] Navigating to: {url} "
                f"(attempt {attempt}/{max(1, attempts)}, timeout={timeout}ms)"
            )
            try:
                page.goto(url, wait_until=wait_until, timeout=timeout)
            except Exception as e:
                last_err = e
                logger.warning(
                    f"[BrowserCore] Navigation attempt {attempt} failed on {url}: {e}"
                )
                # A page that is gone cannot be retried on; get a fresh one.
                try:
                    if page.is_closed():
                        self._active_page = None
                        page = self._get_active_page_impl()
                except Exception:
                    pass
                continue

            if not _looks_blank(page.url):
                logger.info(f"[BrowserCore] Landed on: {page.url}")
                return page

            logger.warning(
                f"[BrowserCore] Navigation to {url} left the page on "
                f"'{page.url or 'about:blank'}'."
            )

        note = self.last_launch_note
        detail = f" ({last_err})" if last_err else ""
        hint = f" {note}" if note else ""
        raise NavigationError(
            f"Could not navigate to {url}: the page stayed on "
            f"about:blank{detail}.{hint}"
        )

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
