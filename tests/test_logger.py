"""日志工具单元测试。"""

import logging
import tempfile
import unittest
from pathlib import Path

from utils.logger import setup_logger


class TestSetupLogger(unittest.TestCase):
    """测试 setup_logger 的 Handler 管理与级别更新。"""

    def tearDown(self):
        """关闭并清理测试创建的 logger handler。"""
        logger = logging.getLogger("test_logger")
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

    def test_setup_logger_creates_handlers(self):
        """首次调用应创建文件 + 控制台 Handler。"""
        with tempfile.TemporaryDirectory() as tmp:
            logger = setup_logger("test_logger", output_dir=tmp)
            try:
                self.assertEqual(len(logger.handlers), 2)
                self.assertTrue(any(isinstance(h, logging.FileHandler) for h in logger.handlers))
                self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in logger.handlers))
            finally:
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()

    def test_setup_logger_no_duplicate_handlers(self):
        """不带 reset 重复调用，Handler 数量不变。"""
        with tempfile.TemporaryDirectory() as tmp:
            logger = setup_logger("test_logger", output_dir=tmp)
            try:
                first_count = len(logger.handlers)

                logger2 = setup_logger("test_logger", output_dir=tmp)
                self.assertEqual(len(logger2.handlers), first_count)
            finally:
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()

    def test_setup_logger_level_updated_without_reset(self):
        """不带 reset 重复调用，日志级别仍应更新。"""
        with tempfile.TemporaryDirectory() as tmp:
            logger = setup_logger("test_logger", level="INFO", output_dir=tmp)
            try:
                self.assertEqual(logger.level, logging.INFO)

                logger = setup_logger("test_logger", level="DEBUG", output_dir=tmp)
                self.assertEqual(logger.level, logging.DEBUG)
            finally:
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()

    def test_setup_logger_reset_clears_handlers(self):
        """reset=True 时应清空旧 Handler 并添加新 Handler。"""
        with tempfile.TemporaryDirectory() as tmp:
            logger = setup_logger("test_logger", output_dir=tmp)
            try:
                old_handlers = list(logger.handlers)

                logger = setup_logger("test_logger", level="DEBUG", output_dir=tmp, reset=True)
                new_handlers = list(logger.handlers)

                self.assertEqual(len(new_handlers), 2)
                self.assertNotEqual(old_handlers, new_handlers)
            finally:
                for handler in old_handlers + list(logger.handlers):
                    handler.close()
                logger.handlers.clear()


if __name__ == "__main__":
    unittest.main()
