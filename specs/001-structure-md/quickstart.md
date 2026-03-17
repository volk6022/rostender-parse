# Quickstart: Adding a New Fallback

To add support for a new procurement platform fallback:

1. **Create the Strategy File**:
   Create a new file in `src/scraper/fallbacks/new_platform.py`.

2. **Implement the Strategy**:
   ```python
   from src.scraper.fallbacks.base import FallbackStrategy, register_fallback

   @register_fallback("new_platform")
   class NewPlatformStrategy(FallbackStrategy):
       async def extract_inn(self, page, url):
           # Navigation and parsing logic
           ...
           return inn
   ```

3. **Verify**:
   Run tests to ensure the new fallback is correctly detected and prioritized.
