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


if __name__ == "__main__":
    unittest.main()
