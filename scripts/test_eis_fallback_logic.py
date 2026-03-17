import asyncio
from playwright.async_api import async_playwright
from src.scraper.unified_fallback import unified_fallback_extract_inn
from loguru import logger
from unittest.mock import patch


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 1. Test success case (mocked content)
        test_url = "https://zakupki.gov.ru/test_success"
        source_urls = f"eis:{test_url}"

        # We simulate a successful load with INN
        async def mock_goto_success(p, url):
            await p.set_content("<html><body>ИНН: 7701234567</body></html>")
            return None

        logger.info("--- Testing EIS fallback Success Case ---")
        with patch(
            "src.scraper.fallbacks.eis.safe_goto", side_effect=mock_goto_success
        ):
            inn = await unified_fallback_extract_inn(page, source_urls)
            logger.info(f"Resulting INN: {inn}")
            assert inn == "7701234567"

        # 2. Test failure case (e.g. timeout or blocked)
        logger.info("--- Testing EIS fallback Failure/Fallback Case ---")

        async def mock_goto_fail(p, url):
            raise Exception("Connection timeout (simulated)")

        # Add a second source to see fallback in action
        source_urls_multi = f"eis:{test_url},gpb:https://etpgpb.ru/procedure/1"

        async def mock_gpb_extract(p, url):
            return "9988776655"

        with patch("src.scraper.fallbacks.eis.safe_goto", side_effect=mock_goto_fail):
            with patch(
                "src.scraper.fallbacks.gpb.GPBFallback.extract_inn",
                side_effect=mock_gpb_extract,
            ):
                inn = await unified_fallback_extract_inn(page, source_urls_multi)
                logger.info(f"Resulting INN after EIS failure: {inn}")
                assert inn == "9988776655"

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
