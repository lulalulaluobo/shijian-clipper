import unittest

from poc.server import INDEX_PATH


class WebPageTests(unittest.TestCase):
    def test_has_json_config_form_without_browser_storage(self):
        page = INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn('id="fns-config"', page)
        self.assertIn('id="article-url"', page)
        self.assertIn('id="target-dir"', page)
        self.assertIn('fetch("/api/clip"', page)
        self.assertNotIn("localStorage", page)
        self.assertNotIn("sessionStorage", page)
