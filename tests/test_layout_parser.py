"""LayoutParser 单元测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from core.layout_parser import ElementType, LayoutElement, LayoutParser


class TestLayoutParser(unittest.TestCase):
    """测试版面解析器的各项能力。"""

    def setUp(self):
        """创建临时 MinerU 输出目录与 content_list.json。"""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.auto_dir = Path(self.tmpdir.name) / "test_pdf" / "auto"
        self.auto_dir.mkdir(parents=True)

        self.content_list = [
            {"type": "title", "text": "标题一", "page_idx": 0, "bbox": [1, 2, 3, 4]},
            {"type": "text", "text": "正文第一段", "page_idx": 0, "bbox": [5, 6, 7, 8]},
            {"type": "image", "img_path": "images/a.jpg", "page_idx": 0, "bbox": [9, 10, 11, 12]},
            {"type": "table", "table_body": "<table><tr><td>单元格</td></tr></table>", "page_idx": 1, "bbox": [13, 14, 15, 16]},
        ]

        with open(self.auto_dir / "test_pdf_content_list.json", "w", encoding="utf-8-sig") as f:
            json.dump(self.content_list, f, ensure_ascii=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_parse_count(self):
        """应正确解析出 4 个元素。"""
        parser = LayoutParser(self.auto_dir)
        elements = parser.parse()
        self.assertEqual(len(elements), 4)

    def test_filter_by_type(self):
        """按类型筛选应正确。"""
        parser = LayoutParser(self.auto_dir)
        parser.parse()
        titles = parser.filter_by_type(ElementType.TITLE)
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].text, "标题一")

    def test_filter_by_page(self):
        """按页码筛选应正确。"""
        parser = LayoutParser(self.auto_dir)
        parser.parse()
        page0 = parser.filter_by_page(0)
        self.assertEqual(len(page0), 3)

    def test_translatable(self):
        """可翻译元素应为 2 个（title + text）。"""
        parser = LayoutParser(self.auto_dir)
        parser.parse()
        trans = parser.get_translatable_elements()
        self.assertEqual(len(trans), 2)

    def test_summary(self):
        """统计摘要应包含正确信息。"""
        parser = LayoutParser(self.auto_dir)
        summary = parser.get_summary()
        self.assertEqual(summary["total_elements"], 4)
        self.assertEqual(summary["page_count"], 2)
        self.assertEqual(summary["translatable_count"], 2)


if __name__ == "__main__":
    unittest.main()
