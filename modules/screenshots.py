"""
screenshots.py — Takes full-page screenshots using Playwright at
multiple viewport sizes, and runs SEO checks on loaded pages.
"""

import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class ScreenshotTaker:
    """
    Async context manager that manages a Playwright browser instance.

    Usage:
        async with ScreenshotTaker(viewports, timeout_ms) as taker:
            png_bytes = await taker.take_screenshot(url, viewport)
            seo_data  = await taker.check_seo(url)
    """

    def __init__(self, viewports: list[dict], timeout_ms: int = 15000):
        self.viewports   = viewports
        self.timeout_ms  = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ── Screenshot ──────────────────────────────────────────────────────────────

    async def take_screenshot(self, url: str, viewport: dict) -> bytes:
        """
        Navigates to url at the given viewport and returns a full-page PNG.

        viewport: {"name": "Desktop", "width": 1440, "height": 900}
        """
        context = await self._browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            await self._dismiss_overlays(page)
            await asyncio.sleep(0.5)  # brief pause for animations to settle
            png_bytes = await page.screenshot(full_page=True, type="png")
        finally:
            await context.close()
        return png_bytes

    # ── SEO Check ───────────────────────────────────────────────────────────────

    async def check_seo(self, url: str) -> dict:
        """
        Loads the page at desktop width and runs the SEO checker on it.
        Imports seo_checker here to avoid circular imports.
        """
        from modules.seo_checker import check_seo

        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            result = await check_seo(page, url)
        finally:
            await context.close()
        return result

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _dismiss_overlays(self, page: Page):
        """
        Attempts to close common cookie banners / GDPR modals
        so they don't appear in screenshots.
        """
        selectors = [
            "button[id*='accept']",
            "button[class*='accept']",
            "button[class*='cookie']",
            "button[aria-label*='Accept']",
            "[data-testid*='cookie-accept']",
            ".cookie-banner button",
            "#cookie-consent button",
        ]
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=500)
                    await asyncio.sleep(0.3)
                    break
            except Exception:
                pass
