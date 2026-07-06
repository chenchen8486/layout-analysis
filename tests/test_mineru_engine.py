"""MinerUEngine 单元测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
