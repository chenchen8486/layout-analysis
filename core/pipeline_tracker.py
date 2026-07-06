"""流水线状态追踪模块，支持增量转换。"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger("pipeline_tracker")


class StageStatus(str, Enum):
    """阶段状态枚举。"""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class StageInfo:
    """单个阶段的执行信息。"""

    status: StageStatus = StageStatus.PENDING
    timestamp: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "StageInfo":
        return cls(
            status=StageStatus(data.get("status", "pending")),
            timestamp=data.get("timestamp", ""),
            error=data.get("error", ""),
        )


class PipelineTracker:
    """追踪单个 PDF 在流水线中的各阶段状态，实现增量转换。

    每个 PDF 的输出目录下会生成 ``pipeline_state.json``，记录：
    - 源文件路径与修改时间
    - MinerU 解析、版面分析、翻译三个阶段的执行状态

    若源文件在上次阶段完成后被修改，则该阶段需要重新执行。
    """

    STATE_FILENAME = "pipeline_state.json"
    STAGES = ("mineru", "layout", "translate")

    def __init__(self, output_dir: Path) -> None:
        """初始化追踪器。

        Args:
            output_dir: 该 PDF 对应的输出子目录（如 ``outputs/{stem}/``）。
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / self.STATE_FILENAME
        self._state = self._load_state()
        self._save_state()

    def _load_state(self) -> Dict[str, Any]:
        """读取已有状态文件，若不存在则返回初始结构。"""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"状态文件读取失败，将重建: {exc}")

        return {
            "source_path": "",
            "source_mtime": 0.0,
            "stages": {s: StageInfo().to_dict() for s in self.STAGES},
        }

    def _save_state(self) -> None:
        """将当前状态持久化到磁盘。"""
        with open(self.state_path, "w", encoding="utf-8-sig") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def is_stage_needed(self, source_path: Path, stage: str) -> bool:
        """判断某阶段是否需要执行。

        需要执行的条件：
        1. 阶段状态非 ``done``；
        2. 或源文件在上次记录后被修改过。

        Args:
            source_path: 原始 PDF 文件路径。
            stage: 阶段名称（``mineru`` / ``layout`` / ``translate``）。

        Returns:
            True 表示需要执行，False 可跳过。
        """
        if stage not in self.STAGES:
            raise ValueError(f"未知阶段: {stage}，可选: {self.STAGES}")

        current_mtime = source_path.stat().st_mtime
        stage_info = StageInfo.from_dict(self._state["stages"].get(stage, {}))

        if stage_info.status != StageStatus.DONE:
            logger.info(f"阶段 [{stage}] 未完成（状态: {stage_info.status.value}），需要执行")
            return True

        recorded_mtime = self._state.get("source_mtime", 0.0)
        if current_mtime > recorded_mtime:
            logger.info(
                f"阶段 [{stage}] 已完成，但源文件已更新 "
                f"({current_mtime:.0f} > {recorded_mtime:.0f})，需要重新执行"
            )
            return True

        logger.info(f"阶段 [{stage}] 已是最新，跳过")
        return False

    def mark_stage(
        self,
        source_path: Path,
        stage: str,
        status: StageStatus,
        error: str = "",
    ) -> None:
        """标记某阶段的执行结果。

        若标记为 ``done``，会同步更新 ``source_mtime`` 为当前源文件修改时间，
        确保后续增量判断准确。

        Args:
            source_path: 原始 PDF 文件路径。
            stage: 阶段名称。
            status: 目标状态。
            error: 失败时的错误信息。
        """
        if stage not in self.STAGES:
            raise ValueError(f"未知阶段: {stage}")

        self._state["source_path"] = str(source_path.resolve())
        self._state["stages"][stage] = StageInfo(
            status=status,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            error=error,
        ).to_dict()

        if status == StageStatus.DONE:
            self._state["source_mtime"] = source_path.stat().st_mtime

        self._save_state()
        logger.info(f"阶段 [{stage}] 标记为 {status.value}")

    def get_overview(self) -> Dict[str, Any]:
        """获取当前 PDF 的各阶段状态概览。

        Returns:
            包含 ``source_path``、``source_mtime``、``stages`` 的字典。
        """
        return dict(self._state)

    def all_done(self, stages_to_check: Optional[List[str]] = None) -> bool:
        """检查指定阶段是否全部完成或跳过。

        Args:
            stages_to_check: 待检查的阶段列表；None 则检查全部阶段。

        Returns:
            全部完成或跳过返回 True，否则 False。
        """
        targets = stages_to_check or list(self.STAGES)
        for stage in targets:
            info = StageInfo.from_dict(self._state["stages"].get(stage, {}))
            if info.status not in (StageStatus.DONE, StageStatus.SKIPPED):
                return False
        return True
