"""DeepSeek API 翻译模块。"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from utils.logger import setup_logger

logger = setup_logger("translator")


@dataclass
class TranslationResult:
    """单条翻译结果。"""

    original: str
    translated: str
    index: int = 0
    success: bool = True
    error: str = ""


class DeepSeekTranslator:
    """基于 DeepSeek Chat API 的文本翻译器。"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        max_retries: int = 3,
        timeout: int = 60,
        batch_size: int = 16,
    ) -> None:
        """初始化翻译器。

        Args:
            api_key: DeepSeek API Key。
            model: 模型名称，默认 deepseek-chat。
            base_url: API 基础地址。
            max_retries: 失败重试次数。
            timeout: 单次请求超时秒数。
            batch_size: 批量翻译时每批段落数上限。
        """
        if not api_key:
            raise ValueError("DeepSeek API Key 不能为空，请在 config/settings.yaml 中配置")

        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求并支持指数退避重试。

        Args:
            payload: 请求体。

        Returns:
            API 响应 JSON。

        Raises:
            RuntimeError: 超过最大重试次数仍失败。
        """
        url = f"{self.base_url}/chat/completions"
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                logger.warning(f"DeepSeek 请求失败（第 {attempt}/{self.max_retries} 次）: {exc}")
                if attempt < self.max_retries:
                    sleep_time = 2 ** attempt
                    logger.info(f"{sleep_time} 秒后重试...")
                    time.sleep(sleep_time)

        raise RuntimeError(
            f"DeepSeek API 请求失败，已重试 {self.max_retries} 次: {last_exception}"
        ) from last_exception

    def translate_single(self, text: str, target_lang: str = "英文") -> TranslationResult:
        """翻译单段文本。

        Args:
            text: 待翻译文本。
            target_lang: 目标语言描述，如 "英文", "Japanese"。

        Returns:
            翻译结果对象。
        """
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", index=0, success=True)

        system_prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}. "
            f"Preserve the original format (markdown, html tags, line breaks) as much as possible. "
            f"Only return the translated text without explanations."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
        }

        try:
            data = self._request(payload)
            content = data["choices"][0]["message"]["content"]
            return TranslationResult(original=text, translated=content.strip(), index=0, success=True)
        except Exception as exc:
            logger.error(f"翻译失败: {exc}", exc_info=True)
            return TranslationResult(
                original=text, translated="", index=0, success=False, error=str(exc)
            )

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str = "英文",
    ) -> List[TranslationResult]:
        """批量翻译文本列表，内部按 batch_size 切片。

        Args:
            texts: 待翻译文本列表。
            target_lang: 目标语言描述。

        Returns:
            与输入顺序对应的翻译结果列表。
        """
        results: List[TranslationResult] = []
        total = len(texts)
        logger.info(f"开始批量翻译，共 {total} 段文本，每批 {self.batch_size} 段")

        for start in range(0, total, self.batch_size):
            batch = texts[start : start + self.batch_size]
            batch_results = self._translate_batch_raw(batch, target_lang, start)
            results.extend(batch_results)
            logger.info(f"已完成 {min(start + self.batch_size, total)}/{total}")

        return results

    def _translate_batch_raw(
        self,
        batch: List[str],
        target_lang: str,
        offset: int,
    ) -> List[TranslationResult]:
        """翻译一个批次，使用分隔符策略合并请求以节省 Token。"""
        # 过滤空文本并建立索引映射
        indexed = [(i + offset, t) for i, t in enumerate(batch) if t and t.strip()]
        if not indexed:
            return [
                TranslationResult(original=t, translated="", index=i + offset, success=True)
                for i, t in enumerate(batch)
            ]

        # 使用特殊分隔符拼接文本
        separator = "\n\n---PARAGRAPH_BREAK---\n\n"
        combined = separator.join(t for _, t in indexed)

        system_prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}. "
            f"Preserve the original format (markdown, html tags, line breaks) as much as possible. "
            f"The text contains multiple paragraphs separated by '---PARAGRAPH_BREAK---'. "
            f"You must return the translated text with the exact same separators, one translated paragraph per original paragraph. "
            f"Do not add any extra explanation."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined},
            ],
            "temperature": 0.3,
        }

        try:
            data = self._request(payload)
            translated_combined = data["choices"][0]["message"]["content"]
            parts = translated_combined.split(separator)

            # 回填结果
            result_map: Dict[int, TranslationResult] = {}
            for idx, (orig_idx, orig_text) in enumerate(indexed):
                trans_text = parts[idx].strip() if idx < len(parts) else ""
                result_map[orig_idx] = TranslationResult(
                    original=orig_text,
                    translated=trans_text,
                    index=orig_idx,
                    success=True,
                )

            # 空文本回填
            for i, t in enumerate(batch):
                abs_idx = i + offset
                if abs_idx not in result_map:
                    result_map[abs_idx] = TranslationResult(
                        original=t, translated="", index=abs_idx, success=True
                    )

            return [result_map[i + offset] for i in range(len(batch))]

        except Exception as exc:
            logger.error(f"批次翻译失败（offset={offset}）: {exc}", exc_info=True)
            return [
                TranslationResult(
                    original=t, translated="", index=i + offset, success=False, error=str(exc)
                )
                for i, t in enumerate(batch)
            ]

    def save_results(
        self,
        results: List[TranslationResult],
        output_path: Path,
    ) -> None:
        """将翻译结果保存为 JSON 文件。"""
        data = [
            {
                "index": r.index,
                "original": r.original,
                "translated": r.translated,
                "success": r.success,
                "error": r.error,
            }
            for r in results
        ]
        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"翻译结果已保存: {output_path}")
