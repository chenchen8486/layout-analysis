"""DeepSeekTranslator 单元测试。"""

import unittest
from unittest.mock import MagicMock, patch

from core.translator import DeepSeekTranslator, TranslationResult


class TestDeepSeekTranslator(unittest.TestCase):
    """测试翻译器的构造与请求逻辑。"""

    def test_init_empty_key_raises(self):
        """空 API Key 应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            DeepSeekTranslator(api_key="")

    def test_translate_single_success(self):
        """模拟成功响应应返回翻译结果。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": " Hello world "}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(translator.session, "post", return_value=mock_response):
            result = translator.translate_single("你好世界", target_lang="英文")
            self.assertTrue(result.success)
            self.assertEqual(result.translated, "Hello world")

    def test_translate_single_empty_text(self):
        """空文本应直接返回空结果，不发起请求。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        result = translator.translate_single("", target_lang="英文")
        self.assertTrue(result.success)
        self.assertEqual(result.translated, "")

    def test_translate_batch_empty(self):
        """空列表应返回空结果列表。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        results = translator.translate_batch([], target_lang="英文")
        self.assertEqual(len(results), 0)

    def test_chunk_paragraphs_basic(self):
        """段落按 max_chars 分块，不拆分单个段落。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        paragraphs = ["a" * 100, "b" * 100, "c" * 100]
        chunks = translator._chunk_paragraphs(paragraphs, max_chars=250)
        self.assertEqual(len(chunks), 2)
        self.assertIn("a" * 100, chunks[0])
        self.assertIn("b" * 100, chunks[0])
        self.assertIn("c" * 100, chunks[1])

    def test_chunk_paragraphs_single_under_limit(self):
        """单段未超限时作为一个块。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        paragraphs = ["short text"]
        chunks = translator._chunk_paragraphs(paragraphs, max_chars=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "short text")

    def test_translate_markdown_empty(self):
        """空 Markdown 直接返回原内容。"""
        translator = DeepSeekTranslator(api_key="fake-key")
        result = translator.translate_markdown("", target_lang="英文")
        self.assertEqual(result, "")

    def test_translate_markdown_success(self):
        """模拟分块翻译成功，结果按原分隔符合并。"""
        translator = DeepSeekTranslator(api_key="fake-key")

        def fake_translate(text, target_lang, system_prompt=""):
            # 模拟翻译器按 chunk 翻译，chunk 内部可能包含多个段落
            translated = "\n\n".join(f"[translated]{p}" for p in text.split("\n\n"))
            return TranslationResult(
                original=text,
                translated=translated,
                success=True,
            )

        with patch.object(translator, "translate_text", side_effect=fake_translate):
            result = translator.translate_markdown("para1\n\npara2", target_lang="英文")

        self.assertEqual(result, "[translated]para1\n\n[translated]para2")

    def test_translate_markdown_failure_keeps_original(self):
        """翻译失败时保留原文。"""
        translator = DeepSeekTranslator(api_key="fake-key")

        def fake_translate(text, target_lang, system_prompt=""):
            return TranslationResult(
                original=text,
                translated="",
                success=False,
                error="mock error",
            )

        with patch.object(translator, "translate_text", side_effect=fake_translate):
            result = translator.translate_markdown("keep me", target_lang="英文")

        self.assertEqual(result, "keep me")


if __name__ == "__main__":
    unittest.main()
