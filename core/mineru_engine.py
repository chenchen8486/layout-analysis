"""MinerU CLI 调用引擎。"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger("mineru_engine")


class MinerUEngine:
    """封装 MinerU 可执行文件的调用逻辑。"""

    def __init__(
        self,
        executable_path: Optional[str] = None,
        backend: str = "pipeline",
        language: str = "ch",
    ) -> None:
        """初始化引擎。

        Args:
            executable_path: MinerU 可执行文件路径；None 则自动查找。
            backend: 解析后端，默认 pipeline。
            language: 文档语言，默认中文 ch。
        """
        self.backend = backend
        self.language = language
        self.executable = self._resolve_executable(executable_path)

    def _resolve_executable(self, explicit: Optional[str]) -> str:
        """按优先级解析 MinerU 可执行文件路径。

        优先级：
        1. 显式传入路径
        2. conda doc 环境 Scripts/mineru.exe
        3. 环境变量 MINERU_PATH
        4. 系统 PATH 搜索

        Args:
            explicit: 显式指定的路径。

        Returns:
            可执行文件绝对路径。

        Raises:
            RuntimeError: 所有查找方式均失败时抛出。
        """
        if explicit:
            p = Path(explicit)
            if p.exists():
                return str(p.resolve())
            logger.warning(f"显式指定的 MinerU 路径不存在: {explicit}")

        # 2. conda doc 环境
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            candidate = Path(conda_prefix) / "Scripts" / "mineru.exe"
            if candidate.exists():
                logger.info(f"从 conda 环境定位到 MinerU: {candidate}")
                return str(candidate.resolve())

        # 3. 环境变量
        env_path = os.environ.get("MINERU_PATH")
        if env_path and os.path.exists(env_path):
            logger.info(f"从环境变量 MINERU_PATH 定位到 MinerU: {env_path}")
            return str(Path(env_path).resolve())

        # 4. PATH 搜索
        exe_name = "mineru.exe" if os.name == "nt" else "mineru"
        found = shutil.which(exe_name)
        if found:
            logger.info(f"从系统 PATH 定位到 MinerU: {found}")
            return str(Path(found).resolve())

        err = (
            "未找到 MinerU 可执行文件。请通过以下任一方式指定：\n"
            "1. 配置文件 config/settings.yaml 的 mineru.executable_path\n"
            "2. 环境变量 MINERU_PATH\n"
            "3. 激活包含 mineru 的 conda 环境（如 doc）\n"
            "4. 将 mineru 加入系统 PATH"
        )
        logger.error(err)
        raise RuntimeError(err)

    def run(self, pdf_path: Path, output_dir: Path) -> Path:
        """执行 MinerU 解析任务。

        Args:
            pdf_path: 待解析的 PDF 文件路径。
            output_dir: 解析结果输出目录。

        Returns:
            MinerU 实际写入的子目录路径（通常为 output_dir/<pdf_stem>/auto/）。

        Raises:
            RuntimeError: MinerU 进程返回非零退出码。
            FileNotFoundError: PDF 文件不存在。
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.executable,
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "--backend", self.backend,
            "-l", self.language,
        ]

        logger.info(f"启动 MinerU: {' '.join(cmd)}")
        logger.info(f"工作目录: {output_dir}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=os.environ,
                cwd=str(output_dir),
            )
        except FileNotFoundError as exc:
            logger.error(f"无法执行 {self.executable}，请确认 MinerU 已正确安装")
            raise RuntimeError("MinerU 可执行文件无法启动") from exc

        logger.info(f"MinerU 返回码: {result.returncode}")
        if result.stdout:
            logger.info(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"STDERR:\n{result.stderr}")

        if result.returncode != 0:
            raise RuntimeError(
                f"MinerU 进程异常退出（返回码 {result.returncode}），详见日志"
            )

        # MinerU 默认输出结构：output_dir/<stem>/<mode>/
        auto_dir = output_dir / pdf_path.stem / "auto"
        if auto_dir.exists():
            logger.info(f"MinerU 输出目录: {auto_dir}")
            return auto_dir

        logger.warning(f"未找到预期的 auto 子目录，返回上级目录: {output_dir / pdf_path.stem}")
        return output_dir / pdf_path.stem
