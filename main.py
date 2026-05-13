"""MinerU 版面分析与翻译流水线入口。

使用示例:
    # 仅解析 PDF
    python main.py --input test.pdf --output ./out

    # 解析 + 翻译为英文
    python main.py --input test.pdf --output ./out --translate --target-lang 英文

    # 指定自定义配置
    python main.py --input test.pdf --output ./out --config config/settings.yaml
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.layout_parser import LayoutParser
from core.mineru_engine import MinerUEngine
from core.translator import DeepSeekTranslator
from utils.logger import setup_logger

logger = setup_logger("main")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载 YAML 配置文件。

    Args:
        config_path: 配置文件路径；None 则使用默认路径。

    Returns:
        配置字典。
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return {}

    with open(config_path, "r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}


def build_argument_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="MinerU 版面分析与 DeepSeek 翻译流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
环境变量:
  MINERU_PATH    MinerU 可执行文件路径（优先级低于配置文件）
  CONDA_PREFIX   自动识别 conda 环境内的 mineru.exe
  DEEPSEEK_API_KEY   DeepSeek API Key（优先级低于配置文件）
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="待解析的 PDF 文件路径",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        type=Path,
        help="解析结果输出目录",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="配置文件路径（默认 config/settings.yaml）",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="MinerU 后端模式（默认 pipeline）",
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default=None,
        help="文档语言（默认 ch）",
    )
    parser.add_argument(
        "--translate", "-t",
        action="store_true",
        help="是否启用 DeepSeek 翻译",
    )
    parser.add_argument(
        "--target-lang",
        type=str,
        default="英文",
        help="翻译目标语言（默认 英文）",
    )
    parser.add_argument(
        "--save-markdown", "-m",
        action="store_true",
        help="是否额外生成翻译后的 Markdown 文件",
    )
    return parser


def main() -> int:
    """主流程入口。

    Returns:
        退出码，0 表示成功。
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    mineru_cfg = config.get("mineru", {})
    deepseek_cfg = config.get("deepseek", {})
    log_cfg = config.get("logging", {})

    # 重新初始化日志级别（若配置文件中指定）
    if log_cfg.get("level"):
        global logger
        logger = setup_logger("main", level=log_cfg["level"], output_dir=log_cfg.get("output_dir", "logs"))

    # 环境变量兼容：自动设置 HF 国内镜像（与原始脚本保持一致）
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # 参数优先级：命令行 > 配置文件 > 默认值
    mineru_exe = mineru_cfg.get("executable_path") or None
    backend = args.backend or mineru_cfg.get("backend", "pipeline")
    language = args.language or mineru_cfg.get("language", "ch")

    # 若环境变量存在 DEEPSEEK_API_KEY，也纳入备选
    deepseek_api_key = (
        deepseek_cfg.get("api_key")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    )

    logger.info("=" * 50)
    logger.info(f"输入 PDF : {args.input}")
    logger.info(f"输出目录 : {args.output}")
    logger.info(f"后端模式 : {backend}")
    logger.info(f"文档语言 : {language}")
    logger.info(f"启用翻译 : {args.translate}")
    if args.translate:
        logger.info(f"目标语言 : {args.target_lang}")
    logger.info("=" * 50)

    # ---- 阶段 1: MinerU 解析 ----
    try:
        engine = MinerUEngine(
            executable_path=mineru_exe,
            backend=backend,
            language=language,
        )
        auto_dir = engine.run(args.input, args.output)
    except Exception as exc:
        logger.critical(f"MinerU 解析失败: {exc}", exc_info=True)
        return 1

    # ---- 阶段 2: 版面分析 ----
    try:
        layout_parser = LayoutParser(auto_dir)
        elements = layout_parser.parse()
        summary = layout_parser.get_summary()
        logger.info(f"版面分析摘要: {json.dumps(summary, ensure_ascii=False)}")

        summary_path = Path(args.output) / "layout_summary.json"
        layout_parser.save_summary(summary_path)
    except Exception as exc:
        logger.error(f"版面分析解析失败: {exc}", exc_info=True)
        return 1

    # ---- 阶段 3: DeepSeek 翻译（可选） ----
    if args.translate:
        if not deepseek_api_key:
            logger.error(
                "启用翻译但未找到 DeepSeek API Key。"
                "请在 config/settings.yaml 的 deepseek.api_key 中配置，"
                "或设置环境变量 DEEPSEEK_API_KEY。"
            )
            return 1

        try:
            translatable = layout_parser.get_translatable_elements()
            if not translatable:
                logger.warning("未找到可翻译的文本元素，跳过翻译")
                return 0

            texts = [e.text for e in translatable]
            logger.info(f"待翻译文本段数: {len(texts)}")

            translator = DeepSeekTranslator(
                api_key=deepseek_api_key,
                model=deepseek_cfg.get("model", "deepseek-chat"),
                base_url=deepseek_cfg.get("base_url", "https://api.deepseek.com"),
                max_retries=deepseek_cfg.get("max_retries", 3),
                timeout=deepseek_cfg.get("timeout", 60),
                batch_size=deepseek_cfg.get("batch_size", 16),
            )

            results = translator.translate_batch(texts, target_lang=args.target_lang)

            # 保存翻译结果
            translated_path = Path(args.output) / "translated_content.json"
            translator.save_results(results, translated_path)

            # 统计
            success_count = sum(1 for r in results if r.success)
            logger.info(f"翻译完成: {success_count}/{len(results)} 成功")

            # 可选：生成翻译后的 Markdown
            if args.save_markdown:
                md_lines: list[str] = []
                for idx, elem in enumerate(translatable):
                    if idx < len(results) and results[idx].success:
                        translated_text = results[idx].translated
                    else:
                        translated_text = elem.text

                    if elem.element_type.value == "title":
                        md_lines.append(f"# {translated_text}\n")
                    elif elem.element_type.value in ("header", "footer", "page_number"):
                        md_lines.append(f"*{translated_text}*\n")
                    else:
                        md_lines.append(f"{translated_text}\n")

                md_path = Path(args.output) / "translated.md"
                with open(md_path, "w", encoding="utf-8-sig") as f:
                    f.write("\n".join(md_lines))
                logger.info(f"翻译 Markdown 已保存: {md_path}")

        except Exception as exc:
            logger.error(f"翻译阶段失败: {exc}", exc_info=True)
            return 1

    logger.info("全部流程执行完毕")
    return 0


if __name__ == "__main__":
    sys.exit(main())
