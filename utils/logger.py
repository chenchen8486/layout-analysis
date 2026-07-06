"""统一日志配置模块。"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(
    name: str,
    level: str = "INFO",
    output_dir: str = "logs",
    reset: bool = False,
) -> logging.Logger:
    """配置并返回一个支持文件与控制台的 Logger。

    Args:
        name: Logger 名称。
        level: 日志级别，如 "DEBUG", "INFO", "WARNING", "ERROR"。
        output_dir: 日志文件输出目录。
        reset: 是否清空已有 Handler 并重新初始化。

    Returns:
        配置完成的 Logger 实例。
    """
    log_path = Path(output_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{name}_{timestamp}.log"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加 Handler；若 reset=True 则重新初始化
    if logger.handlers and not reset:
        return logger

    if reset:
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8-sig")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger
