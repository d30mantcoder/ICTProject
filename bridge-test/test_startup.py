"""Real missing-browser regression, followed by successful launch after recovery."""
import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from fastapi import HTTPException

import app


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_browser_and_retry(self):
        app.pool = app.BrowserPool()
        session = app.BridgeSession()
        original_cache = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        try:
            with tempfile.TemporaryDirectory(prefix='bridge-empty-cache-') as empty:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = empty
                # Driver reads browser location at startup. This cache really has no browser.
                with self.assertRaises(HTTPException) as failure:
                    await session.navigate(app.Navigate(destination='demo'))
                self.assertEqual(failure.exception.status_code, 503)
                self.assertIn('Chromium не установлен', failure.exception.detail)
                self.assertIn('-m playwright install chromium', failure.exception.detail)
                self.assertIsNone(app.pool.browser)
                self.assertIsNone(session.page)
                await app.pool.playwright.stop()
                app.pool.playwright = None
            if original_cache is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = original_cache
            # The same app can recover on a later attempt using this user's actual installation.
            page = await session.ensure_page()
            await page.set_content('<title>Recovered</title><main>Browser works</main>')
            self.assertEqual(await page.title(), 'Recovered')
            self.assertTrue(await page.screenshot())
        finally:
            if original_cache is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = original_cache
            if app.pool.browser:
                await app.pool.browser.close()
            if app.pool.playwright:
                await app.pool.playwright.stop()
            app.pool.browser = session.context = session.page = app.pool.playwright = None
            await session.reset_browser()


if __name__ == '__main__':
    unittest.main(verbosity=2)
