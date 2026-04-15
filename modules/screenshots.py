"""
screenshots.py — Manages a Playwright browser instance for running SEO checks.
"""

import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError


async def _goto_with_fallback(page: Page, url: str, timeout_ms: int):
    """
    Navigate to a URL with networkidle, falling back to 'load' then
    'domcontentloaded' if it times out. Prevents pages with many async
    scripts from blocking the whole check.
    """
    try:
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        try:
            await page.goto(url, wait_until="load", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)


class ScreenshotTaker:
    """
    Async context manager that manages a Playwright browser instance for SEO checks.

    Usage:
        async with ScreenshotTaker(timeout_ms=15000) as taker:
            seo_data  = await taker.check_seo(url)
            site_data = await taker.check_site_seo(url)
    """

    def __init__(self, timeout_ms: int = 15000):
        self.timeout_ms  = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--no-zygote",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-default-apps",
                "--disable-sync",
                "--no-first-run",
                "--mute-audio",
                "--hide-scrollbars",
                "--blink-settings=imagesEnabled=true",
            ],
        )
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ── SEO Checks ──────────────────────────────────────────────────────────────

    async def check_site_seo(self, url: str) -> dict:
        """
        Loads the homepage and checks site-level signals:
        language, favicon, social preview (OG tags), Twitter card.
        """
        from modules.seo_checker import check_site_seo

        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await _goto_with_fallback(page, url, self.timeout_ms)
            result = await check_site_seo(page, url)
        finally:
            await page.close()
            await context.close()
        return result

    async def check_seo(self, url: str) -> dict:
        """
        Loads a page and checks page-level SEO signals.
        """
        from modules.seo_checker import check_seo

        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await _goto_with_fallback(page, url, self.timeout_ms)
            result = await check_seo(page, url)
        finally:
            await page.close()
            await context.close()
        return result
