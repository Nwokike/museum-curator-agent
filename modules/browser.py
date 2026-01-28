import asyncio
from playwright.async_api import async_playwright

class BrowserManager:
    """
    Manages a persistent Playwright session.
    """
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def launch(self):
        """Launches the stealth browser."""
        if self.page:
            return self.page

        self.playwright = await async_playwright().start()
        
        # We add arguments to avoid detection and crash in container environments.
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        self.page = await self.context.new_page()
        print("[Browser] 🕵️ Stealth Browser Launched")
        return self.page

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("[Browser] 🛑 Browser Closed")

# Global Instance
browser_instance = BrowserManager()