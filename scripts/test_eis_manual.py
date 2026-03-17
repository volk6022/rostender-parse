import asyncio
from playwright.async_api import async_playwright
from src.scraper.unified_fallback import unified_fallback_extract_inn
from loguru import logger


async def main():
    async with async_playwright() as p:
        # Launch browser with devtools enabled so MCP can connect if needed,
        # though here we are using it programmatically.
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Test URL - a real EIS page (or one that looks like it)
        # We'll use a known URL or just observe behavior.
        test_url = "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0373200000324000570"
        source_urls = f"eis:{test_url}"

        logger.info(f"Testing EIS fallback with URL: {test_url}")

        # We want to test the fallback behavior when the request fails or is blocked.
        # But first, let's see it working (or failing naturally).
        inn = await unified_fallback_extract_inn(page, source_urls)
        logger.info(f"Resulting INN: {inn}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
