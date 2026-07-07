"""MinerUEngine 单元测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.mineru_engine import MinerUEngine


class TestMinerUEngine(unittest.TestCase):
    """测试 MinerU 引擎的查找与调用逻辑。"""

    @patch.object(Path, "exists", return_value=True)
    @patch.object(Path, "resolve", return_value=Path("C:/fake/mineru.exe"))
    def test_resolve_executable_explicit(self, _mock_resolve, _mock_exists):
        """显式路径存在时应直接采用。"""
        engine = MinerUEngine(executable_path="C:/fake/mineru.exe")
        self.assertEqual(engine.executable, str(Path("C:/fake/mineru.exe")))

    @patch.dict(os.environ, {"MINERU_PATH": "D:/tools/mineru.exe"}, clear=False)
    @patch.object(Path, "exists", return_value=True)
    @patch.object(Path, "resolve", return_value=Path("D:/tools/mineru.exe"))
    def test_resolve_executable_env(self, _mock_resolve, _mock_exists):
        """环境变量 MINERU_PATH 应被识别。"""
        engine = MinerUEngine()
        self.assertIn("mineru", engine.executable.lower())

    @patch.object(Path, "exists", return_value=True)
    @patch.object(Path, "resolve", return_value=Path("C:/fake/mineru.exe"))
    def test_run_pdf_not_found(self, _mock_resolve, _mock_exists):
        """PDF 不存在时应抛出 FileNotFoundError。"""
        engine = MinerUEngine(executable_path="C:/fake/mineru.exe")
        with patch.object(Path, "exists", return_value=False):
            with self.assertRaises(FileNotFoundError):
                engine.run(Path("C:/fake/test.pdf"), Path("C:/fake/out"))

    def test_resolve_auto_dir_default(self):
        """存在 output_dir/stem/auto 时直接返回。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pdf = out / "sample.pdf"
            pdf.write_text("fake")
            (out / "sample" / "auto").mkdir(parents=True)

            result = MinerUEngine.resolve_auto_dir(pdf, out)
            self.assertEqual(result, out / "sample" / "auto")

    def test_resolve_auto_dir_nested(self):
        """不存在 auto 但存在 mode/auto 时返回第一个。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pdf = out / "sample.pdf"
            pdf.write_text("fake")
            (out / "sample" / "pipeline" / "auto").mkdir(parents=True)

            result = MinerUEngine.resolve_auto_dir(pdf, out)
            self.assertEqual(result, out / "sample" / "pipeline" / "auto")

    def test_resolve_auto_dir_fallback(self):
        """无 auto 目录时回退到 stem 目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pdf = out / "sample.pdf"
            pdf.write_text("fake")
            (out / "sample").mkdir(parents=True)

            result = MinerUEngine.resolve_auto_dir(pdf, out)
            self.assertEqual(result, out / "sample")


    @patch("core.mineru_engine.time.sleep")
    @patch.object(MinerUEngine, "_resolve_executable", return_value="C:/fake/mineru.exe")
    @patch("core.mineru_engine.subprocess.run")
    @patch.object(MinerUEngine, "resolve_auto_dir", return_value=Path("C:/fake/out/sample/auto"))
    def test_run_retry_success(self, _mock_resolve, mock_run, _mock_exec, _mock_sleep):
        """首次失败、二次成功时应重试并通过。"""
        engine = MinerUEngine(executable_path="C:/fake/mineru.exe", max_retries=3)

        first = MagicMock()
        first.returncode = 1
        first.stdout = ""
        first.stderr = "err"

        second = MagicMock()
        second.returncode = 0
        second.stdout = "ok"
        second.stderr = ""

        mock_run.side_effect = [first, second]

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "sample.pdf"
            pdf.write_text("fake")
            result = engine.run(pdf, Path(tmp) / "out")

        self.assertEqual(result, Path("C:/fake/out/sample/auto"))
        self.assertEqual(mock_run.call_count, 2)

    @patch("core.mineru_engine.time.sleep")
    @patch.object(MinerUEngine, "_resolve_executable", return_value="C:/fake/mineru.exe")
    @patch("core.mineru_engine.subprocess.run")
    def test_run_retry_exhausted(self, mock_run, _mock_exec, _mock_sleep):
        """全部尝试均失败时应抛出 RuntimeError。"""
        engine = MinerUEngine(executable_path="C:/fake/mineru.exe", max_retries=2)

        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = "err"
        mock_run.return_value = mock

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "sample.pdf"
            pdf.write_text("fake")
            with self.assertRaises(RuntimeError):
                engine.run(pdf, Path(tmp) / "out")

        self.assertEqual(mock_run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
