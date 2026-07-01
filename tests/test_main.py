import os
import unittest
from unittest.mock import patch

import main


class EnsurePlaywrightBrowsersTests(unittest.TestCase):
    def test_uses_pyinstaller_driver_when_frozen(self):
        with patch.object(main.sys, "_MEIPASS", "C:/bundle", create=True), \
             patch("main.os.path.exists", return_value=True), \
             patch("main.subprocess.run") as run_mock:
            main._ensure_playwright_browsers()

        self.assertEqual(
            run_mock.call_args.args[0],
            [os.path.normpath(os.path.join("C:/bundle", "playwright", "driver", "playwright.cmd")), "install", "chromium"],
        )

    def test_uses_python_module_when_not_frozen(self):
        with patch.object(main.sys, "_MEIPASS", None, create=True), \
             patch.object(main.sys, "executable", "C:/Python/python.exe"), \
             patch("main.subprocess.run") as run_mock:
            main._ensure_playwright_browsers()

        self.assertEqual(
            run_mock.call_args.args[0],
            ["C:/Python/python.exe", "-m", "playwright", "install", "chromium"],
        )


if __name__ == "__main__":
    unittest.main()
