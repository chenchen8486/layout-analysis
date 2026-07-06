"""PipelineTracker 单元测试。"""

import json
import tempfile
import time
import unittest
from pathlib import Path

from core.pipeline_tracker import PipelineTracker, StageStatus


class TestPipelineTracker(unittest.TestCase):
    """测试流水线状态追踪器的读写与增量判断逻辑。"""

    def setUp(self):
        """创建临时输出目录与模拟 PDF 文件。"""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmpdir.name) / "out"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pdf_path = Path(self.tmpdir.name) / "test.pdf"
        self.pdf_path.write_text("fake pdf content", encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_tracker_with_state(self, stage_status: str, mtime: float) -> PipelineTracker:
        """辅助方法：构造一个带有预设状态文件的 Tracker。"""
        tracker = PipelineTracker(self.output_dir)
        tracker._state["source_mtime"] = mtime
        tracker._state["stages"]["mineru"]["status"] = stage_status
        tracker._save_state()
        return tracker

    def test_initial_state(self):
        """新 Tracker 应生成初始状态文件，所有阶段为 pending。"""
        tracker = PipelineTracker(self.output_dir)
        self.assertTrue((self.output_dir / "pipeline_state.json").exists())
        overview = tracker.get_overview()
        self.assertEqual(overview["source_mtime"], 0.0)
        for stage in PipelineTracker.STAGES:
            self.assertEqual(overview["stages"][stage]["status"], "pending")

    def test_mark_stage_done(self):
        """标记 done 后应更新状态与时间戳。"""
        tracker = PipelineTracker(self.output_dir)
        tracker.mark_stage(self.pdf_path, "mineru", StageStatus.DONE)
        overview = tracker.get_overview()
        self.assertEqual(overview["stages"]["mineru"]["status"], "done")
        self.assertGreater(overview["source_mtime"], 0.0)

    def test_stage_needed_when_pending(self):
        """阶段为 pending 时应判定需要执行。"""
        tracker = PipelineTracker(self.output_dir)
        self.assertTrue(tracker.is_stage_needed(self.pdf_path, "mineru"))

    def test_stage_needed_when_done_and_unchanged(self):
        """阶段已完成且源文件未修改时应跳过。"""
        mtime = self.pdf_path.stat().st_mtime
        tracker = self._create_tracker_with_state("done", mtime)
        self.assertFalse(tracker.is_stage_needed(self.pdf_path, "mineru"))

    def test_stage_needed_when_source_updated(self):
        """源文件修改后应重新触发该阶段。"""
        old_mtime = self.pdf_path.stat().st_mtime
        tracker = self._create_tracker_with_state("done", old_mtime)
        time.sleep(0.1)
        self.pdf_path.write_text("updated content", encoding="utf-8")
        self.assertTrue(tracker.is_stage_needed(self.pdf_path, "mineru"))

    def test_mark_failed(self):
        """标记失败时应记录错误信息。"""
        tracker = PipelineTracker(self.output_dir)
        tracker.mark_stage(self.pdf_path, "layout", StageStatus.FAILED, error="解析异常")
        overview = tracker.get_overview()
        self.assertEqual(overview["stages"]["layout"]["status"], "failed")
        self.assertEqual(overview["stages"]["layout"]["error"], "解析异常")

    def test_all_done(self):
        """全部阶段 done 后 all_done 返回 True。"""
        tracker = PipelineTracker(self.output_dir)
        for stage in PipelineTracker.STAGES:
            tracker.mark_stage(self.pdf_path, stage, StageStatus.DONE)
        self.assertTrue(tracker.all_done())

    def test_all_done_with_skipped(self):
        """阶段 skipped 也应视为完成，all_done 返回 True。"""
        tracker = PipelineTracker(self.output_dir)
        tracker.mark_stage(self.pdf_path, "mineru", StageStatus.DONE)
        tracker.mark_stage(self.pdf_path, "layout", StageStatus.DONE)
        tracker.mark_stage(self.pdf_path, "translate", StageStatus.SKIPPED)
        self.assertTrue(tracker.all_done())

    def test_all_done_partial(self):
        """部分阶段未完成时返回 False。"""
        tracker = PipelineTracker(self.output_dir)
        tracker.mark_stage(self.pdf_path, "mineru", StageStatus.DONE)
        self.assertFalse(tracker.all_done())

    def test_invalid_stage_raises(self):
        """传入未知阶段应抛出 ValueError。"""
        tracker = PipelineTracker(self.output_dir)
        with self.assertRaises(ValueError):
            tracker.is_stage_needed(self.pdf_path, "unknown_stage")
        with self.assertRaises(ValueError):
            tracker.mark_stage(self.pdf_path, "unknown_stage", StageStatus.DONE)


if __name__ == "__main__":
    unittest.main()
