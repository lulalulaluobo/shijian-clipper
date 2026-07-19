import unittest

from poc.server import ATTACHMENT_INDEX_PATH, INDEX_PATH


class WebPageTests(unittest.TestCase):
    def test_has_clip_form_without_browser_storage(self):
        page = INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn('id="clip-form"', page)
        self.assertIn('id="article-url"', page)
        self.assertIn('id="markdown-output"', page)
        self.assertIn('fetch("/api/clip"', page)
        # 不再有 FNS 相关字段
        self.assertNotIn("fns-config", page)
        self.assertNotIn("target-dir", page)
        self.assertNotIn("localStorage", page)
        self.assertNotIn("sessionStorage", page)

    def test_has_attachment_poc_page_without_browser_storage(self):
        page = ATTACHMENT_INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn('id="attachment-form"', page)
        self.assertIn('id="attachment-file"', page)
        self.assertIn('fetch("/api/attachment"', page)
        # 不再有 FNS 相关字段
        self.assertNotIn("fns-config", page)
        self.assertNotIn("target-dir", page)
        self.assertNotIn("localStorage", page)
        self.assertNotIn("sessionStorage", page)
