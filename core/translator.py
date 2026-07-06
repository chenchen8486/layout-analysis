"""DeepSeek API 翻译模块。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        batch_size: int = 32,
        temperature: float = 0.1,
        max_workers: int = 3,
    ) -> None:
        """初始化翻译器。

        Args:
            api_key: DeepSeek API Key。
            model: 模型名称，默认 deepseek-chat。
            base_url: API 基础地址。
            max_retries: 失败重试次数。
            timeout: 单次请求超时秒数。
            batch_size: 批量翻译时每批段落数上限（默认 32）。
            temperature: 生成温度，越低越稳定（默认 0.1）。
            max_workers: 并发线程数，控制同时发送的 batch 数量（默认 3）。
        """
        if not api_key:
            raise ValueError("DeepSeek API Key 不能为空，请在 config/settings.yaml 中配置")

        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self.temperature = temperature
        self.max_workers = max(1, max_workers)
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

    def translate_text(
        self,
        text: str,
        target_lang: str = "英文",
        system_prompt: Optional[str] = None,
    ) -> TranslationResult:
        """翻译任意文本，支持自定义 system prompt。

        Args:
            text: 待翻译文本。
            target_lang: 目标语言描述，如 "英文", "Japanese"。
            system_prompt: 自定义系统提示；None 则使用默认翻译提示。

        Returns:
            翻译结果对象。
        """
        if not text or not text.strip():
            return TranslationResult(original=text, translated="", index=0, success=True)

        if system_prompt is None:
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
            "temperature": self.temperature,
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

    def translate_single(self, text: str, target_lang: str = "英文") -> TranslationResult:
        """翻译单段文本（快捷方式，使用默认提示词）。"""
        return self.translate_text(text, target_lang=target_lang)

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str = "英文",
    ) -> List[TranslationResult]:
        """批量翻译文本列表，内部按 batch_size 切片并并发执行。

        Args:
            texts: 待翻译文本列表。
            target_lang: 目标语言描述。

        Returns:
            与输入顺序对应的翻译结果列表。
        """
        total = len(texts)
        logger.info(
            f"开始批量翻译，共 {total} 段文本，每批 {self.batch_size} 段，"
            f"并发 {self.max_workers} 个 batch，temperature={self.temperature}"
        )

        if total == 0:
            return []

        # 拆分为多个 batch
        batches: List[tuple[int, List[str]]] = []
        for start in range(0, total, self.batch_size):
            batch = texts[start : start + self.batch_size]
            batches.append((start, batch))

        # 并发执行
        results: List[Optional[TranslationResult]] = [None] * total

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_start = {
                executor.submit(self._translate_batch_raw, batch, target_lang, start): start
                for start, batch in batches
            }

            for future in as_completed(future_to_start):
                start = future_to_start[future]
                try:
                    batch_results = future.result()
                    for idx, result in enumerate(batch_results):
                        actual_idx = start + idx
                        if actual_idx < len(results):
                            results[actual_idx] = result
                    logger.info(f"已完成 {min(start + self.batch_size, total)}/{total}")
                except Exception as exc:
                    logger.error(f"批次翻译失败（start={start}）: {exc}", exc_info=True)
                    for i in range(start, min(start + self.batch_size, len(texts))):
                        results[i] = TranslationResult(
                            original=texts[i],
                            translated="",
                            index=i,
                            success=False,
                            error=str(exc),
                        )

        # 兜底：确保所有位置都有结果
        for i in range(total):
            if results[i] is None:
                results[i] = TranslationResult(
                    original=texts[i],
                    translated="",
                    index=i,
                    success=False,
                    error="未知错误",
                )

        return [r for r in results if r is not None]

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
            "temperature": self.temperature,
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

    @staticmethod
    def _chunk_paragraphs(paragraphs: List[str], max_chars: int = 3000) -> List[str]:
        """将段落列表按字符数分块，不拆分单个段落。

        Args:
            paragraphs: Markdown 按空行拆分后的段落列表。
            max_chars: 每块最大字符数（默认 3000，约 1500 tokens）。

        Returns:
            分块后的字符串列表，每块包含一个或多个完整段落。
        """
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len > max_chars and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_len = para_len
            else:
                current_chunk.append(para)
                current_len += para_len

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _translate_chunks(
        self,
        chunks: List[str],
        target_lang: str,
        system_prompt: str,
    ) -> List[str]:
        """并发翻译多个 Markdown 分块，保持结果顺序。

        Args:
            chunks: 待翻译的 Markdown 分块列表。
            target_lang: 目标语言。
            system_prompt: 自定义系统提示。

        Returns:
            与 chunks 顺序对应的译文列表；失败或异常时保留原文。
        """
        if not chunks:
            return []

        total = len(chunks)
        logger.info(f"分块并发翻译，共 {total} 块，并发 {self.max_workers}")

        results: List[Optional[str]] = [None] * total

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    self.translate_text,
                    chunk,
                    target_lang,
                    system_prompt,
                ): idx
                for idx, chunk in enumerate(chunks)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    if result.success:
                        results[idx] = result.translated
                        logger.info(f"块 {idx + 1}/{total} 翻译完成")
                    else:
                        logger.error(f"块 {idx + 1}/{total} 翻译失败: {result.error}")
                        results[idx] = chunks[idx]
                except Exception as exc:
                    logger.error(f"块 {idx + 1}/{total} 翻译异常: {exc}", exc_info=True)
                    results[idx] = chunks[idx]

        for i in range(total):
            if results[i] is None:
                results[i] = chunks[i]

        return [r for r in results if r is not None]

    def translate_markdown(
        self,
        content: str,
        target_lang: str = "英文",
        system_prompt: Optional[str] = None,
        max_chars: int = 3000,
    ) -> str:
        """翻译 Markdown 全文，按段落分块并发翻译，失败时保留原文。

        Args:
            content: Markdown 原文。
            target_lang: 目标语言描述，如 "英文", "中文"。
            system_prompt: 自定义系统提示；None 使用默认 Markdown 翻译提示。
            max_chars: 每块最大字符数，默认 3000。

        Returns:
            翻译后的 Markdown 字符串。
        """
        if not content or not content.strip():
            return content

        if system_prompt is None:
            system_prompt = (
                f"You are a professional translator. "
                f"Translate the following Markdown text into {target_lang}. "
                f"CRITICAL REQUIREMENTS:\n"
                f"1. Preserve ALL Markdown syntax exactly (headings, lists, tables, code blocks, etc.)\n"
                f"2. Do NOT modify any image references like ![alt](path) or image paths\n"
                f"3. Do NOT modify any URL links like [text](url)\n"
                f"4. Do NOT modify any HTML tags\n"
                f"5. Only translate natural language text content\n"
                f"6. Return the complete translated text, keeping the same structure"
            )

        paragraphs = content.split("\n\n")
        chunks = self._chunk_paragraphs(paragraphs, max_chars=max_chars)
        logger.info(f"Markdown 共分 {len(chunks)} 块进行翻译")

        translated_chunks = self._translate_chunks(chunks, target_lang, system_prompt)
        return "\n\n".join(translated_chunks)

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
