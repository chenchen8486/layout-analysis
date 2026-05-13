"""MinerU 版面分析与翻译流水线入口。

使用示例:
    # 仅解析单个 PDF
    python main.py --input test.pdf --output ./out

    # 解析整个文件夹（批量 + 增量）
    python main.py --input ./data/ --output ./outputs/

    # 解析 + 翻译为英文
    python main.py --input test.pdf --output ./out --translate --target-lang 英文

    # 指定自定义配置
    python main.py --input test.pdf --output ./out --config config/settings.yaml
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.layout_parser import LayoutParser
from core.mineru_engine import MinerUEngine
from core.pipeline_tracker import PipelineTracker, StageStatus
from core.translator import DeepSeekTranslator
from utils.logger import setup_logger

logger = setup_logger("main")


def _preprocess_yaml_raw(text: str) -> str:
    """预处理 YAML 文本，支持 r'...' / r\"...\" 原始字符串语法。

    将 r\"...\" 替换为 '...'（单引号），避免 YAML 双引号中的反斜杠转义问题。
    """
    # r"..." -> '...'
    text = re.sub(r'r"([^"]*)"', r"'\1'", text)
    # r'...' -> '...'
    text = re.sub(r"r'([^']*)'", r"'\1'", text)
    return text


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载 YAML 配置文件。

    Args:
        config_path: 配置文件路径；None 则使用默认路径。

    Returns:
        配置字典。

    Raises:
        RuntimeError: YAML 格式非法或包含不可打印转义字符时抛出，并给出修复提示。
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return {}

    with open(config_path, "r", encoding="utf-8-sig") as f:
        raw_text = f.read()

    # 支持 r"..." / r'...' 原始字符串
    raw_text = _preprocess_yaml_raw(raw_text)

    try:
        config = yaml.safe_load(raw_text) or {}
    except yaml.reader.ReaderError as exc:
        err_msg = (
            f"配置文件解析失败，检测到不可打印字符（通常是 Windows 路径中的反斜杠被当作转义符）。\n"
            f"错误位置: 第 {exc.position + 1} 个字符附近\n"
            f"修复方案（任选其一）：\n"
            f"1. 路径前加 r 前缀:  input_path: r\"D:\\\\project\\\\...\"\n"
            f"2. 改用单引号:      input_path: 'D:\\\\project\\\\...'\n"
            f"3. 去掉引号:        input_path: D:\\\\project\\\\...\n"
            f"4. 反斜杠改斜杠:    input_path: D:/project/..."
        )
        logger.error(err_msg)
        raise RuntimeError(err_msg) from exc

    # 对已知路径字段统一将反斜杠转为正斜杠，兼容 Windows 路径复制习惯
    path_keys = [
        ("pipeline", "input_path"),
        ("pipeline", "output_path"),
        ("mineru", "executable_path"),
    ]
    for section, key in path_keys:
        if section in config and isinstance(config[section], dict):
            val = config[section].get(key)
            if isinstance(val, str):
                config[section][key] = val.replace("\\", "/")

    return config


def collect_pdfs(input_path: Path, recursive: bool = False) -> List[Path]:
    """收集待处理的 PDF 文件列表。

    Args:
        input_path: 输入路径，可以是单个 PDF 文件或包含 PDF 的目录。
        recursive: 若为 True，递归扫描子目录中的 PDF。

    Returns:
        按文件名排序的 PDF 路径列表。

    Raises:
        ValueError: 输入路径既不是 PDF 也不是目录。
    """
    input_path = Path(input_path)

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        logger.info(f"单文件模式: {input_path}")
        return [input_path]

    if input_path.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdfs = sorted(input_path.glob(pattern))
        logger.info(f"批量模式: 从 {input_path} 扫描到 {len(pdfs)} 个 PDF")
        if not pdfs:
            logger.warning(f"目录中未找到 PDF 文件: {input_path}")
        return pdfs

    raise ValueError(f"输入路径必须是 PDF 文件或目录: {input_path}")


def _build_markdown_lines(
    elements: List[Any],
    translated_map: Optional[Dict[int, str]] = None,
) -> List[str]:
    """根据版面元素列表生成 Markdown 行。

    Args:
        elements: LayoutElement 列表。
        translated_map: 索引到译文的映射；None 则使用原文。

    Returns:
        Markdown 字符串行列表。
    """
    md_lines: List[str] = []
    for idx, elem in enumerate(elements):
        text = translated_map.get(idx, elem.text) if translated_map else elem.text
        if not text:
            text = elem.text

        if elem.element_type.value == "title":
            md_lines.append(f"# {text}\n")
        elif elem.element_type.value in ("header", "footer", "page_number"):
            md_lines.append(f"*{text}*\n")
        else:
            md_lines.append(f"{text}\n")
    return md_lines


def get_pdf_meta_dir(pdf_path: Path, output_path: Path) -> Path:
    """计算单个 PDF 对应的元数据子目录。

    若 output_path 的目录名恰好与 PDF 主文件名一致（兼容旧单文件用法），
    则直接复用该目录，避免嵌套。

    Args:
        pdf_path: PDF 文件路径。
        output_path: 用户指定的总输出目录。

    Returns:
        该 PDF 专属的结果子目录。
    """
    if output_path.name == pdf_path.stem:
        return output_path
    return output_path / pdf_path.stem


def process_single_pdf(
    pdf_path: Path,
    output_path: Path,
    engine: MinerUEngine,
    translator: Optional[DeepSeekTranslator],
    target_lang: str,
    save_markdown: bool,
) -> Tuple[bool, str]:
    """处理单个 PDF 的完整流水线（MinerU → 版面分析 → 翻译）。

    Args:
        pdf_path: PDF 文件路径。
        output_path: 总输出目录。
        engine: 已初始化的 MinerU 引擎。
        translator: 已初始化的翻译器；None 表示不翻译。
        target_lang: 目标语言。
        save_markdown: 是否保存 Markdown。

    Returns:
        (是否成功, 错误信息)
    """
    pdf_meta_dir = get_pdf_meta_dir(pdf_path, output_path)
    pdf_meta_dir.mkdir(parents=True, exist_ok=True)
    tracker = PipelineTracker(pdf_meta_dir)

    logger.info(f"开始处理: {pdf_path.name} -> {pdf_meta_dir}")

    # ---- 阶段 1: MinerU 解析 ----
    if tracker.is_stage_needed(pdf_path, "mineru"):
        try:
            auto_dir = engine.run(pdf_path, output_path)
            tracker.mark_stage(pdf_path, "mineru", StageStatus.DONE)
        except Exception as exc:
            logger.critical(f"[{pdf_path.name}] MinerU 解析失败: {exc}", exc_info=True)
            tracker.mark_stage(pdf_path, "mineru", StageStatus.FAILED, error=str(exc))
            return False, str(exc)
    else:
        # 复用已有的 MinerU 输出目录
        auto_dir = output_path / pdf_path.stem / "auto"
        if not auto_dir.exists():
            candidates = list((output_path / pdf_path.stem).glob("*/auto"))
            if candidates:
                auto_dir = candidates[0]
            else:
                err = f"[{pdf_path.name}] 跳过 MinerU，但未找到已有输出目录"
                logger.error(err)
                return False, err

    # ---- 阶段 2: 版面分析 ----
    layout_parser: Optional[LayoutParser] = None
    if tracker.is_stage_needed(pdf_path, "layout"):
        try:
            layout_parser = LayoutParser(auto_dir)
            layout_parser.parse()
            summary = layout_parser.get_summary()
            logger.info(f"[{pdf_path.name}] 版面分析摘要: {json.dumps(summary, ensure_ascii=False)}")

            summary_path = pdf_meta_dir / "layout_summary.json"
            layout_parser.save_summary(summary_path)
            tracker.mark_stage(pdf_path, "layout", StageStatus.DONE)
        except Exception as exc:
            logger.error(f"[{pdf_path.name}] 版面分析失败: {exc}", exc_info=True)
            tracker.mark_stage(pdf_path, "layout", StageStatus.FAILED, error=str(exc))
            return False, str(exc)
    else:
        # 增量跳过：仍需解析以用于后续 Markdown 生成
        try:
            layout_parser = LayoutParser(auto_dir)
            layout_parser.parse()
        except Exception:
            layout_parser = None

    # 无论是否翻译，都先保存原始 Markdown
    if layout_parser is not None:
        original_md_path = pdf_meta_dir / "original.md"
        original_lines = _build_markdown_lines(layout_parser.elements)
        with open(original_md_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(original_lines))
        logger.info(f"[{pdf_path.name}] 原始 Markdown 已保存: {original_md_path}")

    # ---- 阶段 3: DeepSeek 翻译（可选） ----
    if translator is not None:
        if tracker.is_stage_needed(pdf_path, "translate"):
            try:
                if layout_parser is None:
                    layout_parser = LayoutParser(auto_dir)
                    layout_parser.parse()
                translatable = layout_parser.get_translatable_elements()
                if not translatable:
                    logger.warning(f"[{pdf_path.name}] 未找到可翻译文本，跳过翻译")
                    tracker.mark_stage(pdf_path, "translate", StageStatus.SKIPPED)
                else:
                    texts = [e.text for e in translatable]
                    logger.info(f"[{pdf_path.name}] 待翻译文本段数: {len(texts)}")

                    results = translator.translate_batch(texts, target_lang=target_lang)
                    translated_path = pdf_meta_dir / "translated_content.json"
                    translator.save_results(results, translated_path)

                    success_count = sum(1 for r in results if r.success)
                    logger.info(f"[{pdf_path.name}] 翻译完成: {success_count}/{len(results)} 成功")

                    if save_markdown:
                        translated_map = {
                            idx: results[idx].translated
                            for idx in range(len(results))
                            if idx < len(results) and results[idx].success
                        }
                        md_lines = _build_markdown_lines(translatable, translated_map)
                        md_path = pdf_meta_dir / "translated.md"
                        with open(md_path, "w", encoding="utf-8-sig") as f:
                            f.write("\n".join(md_lines))
                        logger.info(f"[{pdf_path.name}] 翻译 Markdown 已保存: {md_path}")

                    tracker.mark_stage(pdf_path, "translate", StageStatus.DONE)
            except Exception as exc:
                logger.error(f"[{pdf_path.name}] 翻译失败: {exc}", exc_info=True)
                tracker.mark_stage(pdf_path, "translate", StageStatus.FAILED, error=str(exc))
                return False, str(exc)
    else:
        tracker.mark_stage(pdf_path, "translate", StageStatus.SKIPPED)

    logger.info(f"[{pdf_path.name}] 全部阶段处理完毕")
    return True, ""


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
        type=Path,
        default=None,
        help="待解析的 PDF 文件或文件夹路径；未指定时使用配置文件中的 pipeline.input_path",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="解析结果输出目录；未指定时使用配置文件中的 pipeline.output_path",
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
        default=None,
        help="翻译目标语言（默认 英文，也可通过配置文件 deepseek.target_lang 设置）",
    )
    parser.add_argument(
        "--save-markdown", "-m",
        action="store_true",
        help="是否额外生成翻译后的 Markdown 文件",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="扫描输入文件夹时递归子目录（仅在输入为目录时生效）",
    )
    return parser


def main() -> int:
    """主流程入口。

    Returns:
        退出码，0 表示成功。
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    # 若后续需要重新初始化日志级别，提前声明 global
    global logger

    # 加载配置
    config = load_config(args.config)
    pipeline_cfg = config.get("pipeline", {})
    mineru_cfg = config.get("mineru", {})
    deepseek_cfg = config.get("deepseek", {})
    log_cfg = config.get("logging", {})

    # 项目根目录，用于将配置文件中的相对路径解析为绝对路径
    project_root = Path(__file__).resolve().parent

    # ---- 输入 / 输出路径回退（命令行 > 配置文件） ----
    input_path: Optional[Path] = args.input
    if input_path is None:
        cfg_input = pipeline_cfg.get("input_path", "")
        if cfg_input:
            input_path = Path(cfg_input)

    if input_path is None or str(input_path) == "." or str(input_path) == "":
        logger.error(
            "未指定输入路径。请通过以下方式之一设置：\n"
            "1. 命令行参数: --input / -i\n"
            "2. 配置文件: config/settings.yaml 的 pipeline.input_path"
        )
        return 1

    if not input_path.is_absolute():
        input_path = project_root / input_path

    output_path: Optional[Path] = args.output
    if output_path is None:
        cfg_output = pipeline_cfg.get("output_path", "")
        if cfg_output:
            output_path = Path(cfg_output)

    if output_path is None or str(output_path) == "." or str(output_path) == "":
        logger.error(
            "未指定输出目录。请通过以下方式之一设置：\n"
            "1. 命令行参数: --output / -o\n"
            "2. 配置文件: config/settings.yaml 的 pipeline.output_path"
        )
        return 1

    if not output_path.is_absolute():
        output_path = project_root / output_path

    # 回写到 args，保证后续代码统一通过 args 访问
    args.input = input_path
    args.output = output_path

    # 重新初始化日志级别（若配置文件中指定）
    if log_cfg.get("level"):
        logger = setup_logger("main", level=log_cfg["level"], output_dir=log_cfg.get("output_dir", "logs"))

    # 环境变量兼容：自动设置 HF 国内镜像（与原始脚本保持一致）
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # 参数优先级：命令行 > 配置文件 > 默认值
    mineru_exe = mineru_cfg.get("executable_path") or None
    backend = args.backend or mineru_cfg.get("backend", "pipeline")
    language = args.language or mineru_cfg.get("language", "ch")
    recursive = args.recursive or pipeline_cfg.get("recursive", False)

    # 翻译开关与目标语言同样支持配置文件
    translate = args.translate or pipeline_cfg.get("translate", False)
    target_lang = args.target_lang or deepseek_cfg.get("target_lang", "英文")
    save_markdown = args.save_markdown or pipeline_cfg.get("save_markdown", False)

    # 若环境变量存在 DEEPSEEK_API_KEY，也纳入备选
    deepseek_api_key = (
        deepseek_cfg.get("api_key")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    )

    # ---- 收集 PDF 列表 ----
    try:
        pdf_files = collect_pdfs(input_path, recursive=recursive)
    except ValueError as exc:
        logger.error(str(exc))
        return 1

    if not pdf_files:
        logger.error(f"未找到任何 PDF 文件: {input_path}")
        return 1

    logger.info("=" * 50)
    logger.info(f"输入路径 : {args.input}")
    logger.info(f"输出目录 : {args.output}")
    logger.info(f"PDF 数量 : {len(pdf_files)}")
    logger.info(f"后端模式 : {backend}")
    logger.info(f"文档语言 : {language}")
    logger.info(f"启用翻译 : {translate}")
    if translate:
        logger.info(f"目标语言 : {target_lang}")
    logger.info("=" * 50)

    # ---- 初始化共享引擎与翻译器 ----
    try:
        engine = MinerUEngine(
            executable_path=mineru_exe,
            backend=backend,
            language=language,
        )
    except Exception as exc:
        logger.critical(f"MinerU 引擎初始化失败: {exc}", exc_info=True)
        return 1

    translator: Optional[DeepSeekTranslator] = None
    if translate:
        if not deepseek_api_key:
            logger.error(
                "启用翻译但未找到 DeepSeek API Key。"
                "请在 config/settings.yaml 的 deepseek.api_key 中配置，"
                "或设置环境变量 DEEPSEEK_API_KEY。"
            )
            return 1
        translator = DeepSeekTranslator(
            api_key=deepseek_api_key,
            model=deepseek_cfg.get("model", "deepseek-chat"),
            base_url=deepseek_cfg.get("base_url", "https://api.deepseek.com"),
            max_retries=deepseek_cfg.get("max_retries", 3),
            timeout=deepseek_cfg.get("timeout", 60),
            batch_size=deepseek_cfg.get("batch_size", 16),
        )

    # ---- 批量处理 ----
    stats = {
        "total": len(pdf_files),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    for idx, pdf_path in enumerate(pdf_files, start=1):
        logger.info(f"\n--- [{idx}/{len(pdf_files)}] 处理 {pdf_path.name} ---")
        success, error = process_single_pdf(
            pdf_path=pdf_path,
            output_path=args.output,
            engine=engine,
            translator=translator,
            target_lang=target_lang,
            save_markdown=save_markdown,
        )

        tracker = PipelineTracker(get_pdf_meta_dir(pdf_path, args.output))
        all_done = tracker.all_done(["mineru", "layout"] + (["translate"] if translate else []))

        if success and all_done:
            # 进一步判断是否真正执行了（而非全部跳过）
            overview = tracker.get_overview()
            has_skip = any(
                overview["stages"].get(s, {}).get("status") == "skipped"
                for s in overview["stages"]
            )
            if has_skip:
                stats["skipped"] += 1
            else:
                stats["success"] += 1
        elif all_done:
            # 可能部分阶段跳过但整体无错误
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

        stats["details"].append({
            "file": pdf_path.name,
            "success": success,
            "error": error,
            "stages": tracker.get_overview()["stages"],
        })

    # ---- 保存批量汇总 ----
    batch_summary_path = args.output / "batch_summary.json"
    with open(batch_summary_path, "w", encoding="utf-8-sig") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # ---- 终端汇总报告 ----
    logger.info("\n" + "=" * 50)
    logger.info("批量转换汇总")
    logger.info("=" * 50)
    logger.info(f"总计 PDF  : {stats['total']}")
    logger.info(f"成功完成  : {stats['success']}")
    logger.info(f"增量跳过  : {stats['skipped']}")
    logger.info(f"失败      : {stats['failed']}")
    logger.info(f"详细日志见: logs/main_*.log")
    logger.info("=" * 50)

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
