"""版面分析结果解析模块。"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger("layout_parser")


class ElementType(str, Enum):
    """版面元素类型枚举。"""

    TEXT = "text"
    TITLE = "title"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    IMAGE = "image"
    TABLE = "table"
    OCR_TEXT = "ocr_text"
    INTERLINE_EQUATION = "interline_equation"
    FOOTNOTE = "footnote"
    UNKNOWN = "unknown"


@dataclass
class LayoutElement:
    """单个版面元素。"""

    element_type: ElementType
    text: str = ""
    page_idx: int = -1
    bbox: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_translatable(self) -> bool:
        """是否属于可直接翻译的文本类元素。"""
        return self.element_type in {
            ElementType.TEXT,
            ElementType.TITLE,
            ElementType.HEADER,
            ElementType.FOOTER,
            ElementType.OCR_TEXT,
            ElementType.INTERLINE_EQUATION,
        }


class LayoutParser:
    """解析 MinerU 输出的版面分析文件。"""

    def __init__(self, auto_dir: Path) -> None:
        """初始化解析器。

        Args:
            auto_dir: MinerU 输出目录（含 content_list.json 的目录）。
        """
        self.auto_dir = Path(auto_dir)
        self.content_list: List[Dict[str, Any]] = []
        self.elements: List[LayoutElement] = []

    def parse(self) -> List[LayoutElement]:
        """解析 content_list.json 并生成元素列表。

        Returns:
            版面元素列表。

        Raises:
            FileNotFoundError: content_list.json 不存在。
        """
        content_path = self.auto_dir / f"{self.auto_dir.parent.name}_content_list.json"
        # 兼容多种命名方式
        if not content_path.exists():
            candidates = list(self.auto_dir.glob("*_content_list.json"))
            if candidates:
                content_path = candidates[0]
            else:
                raise FileNotFoundError(
                    f"未找到 content_list.json，目录: {self.auto_dir}"
                )

        logger.info(f"解析版面文件: {content_path}")
        with open(content_path, "r", encoding="utf-8-sig") as f:
            self.content_list = json.load(f)

        self.elements = [self._to_element(item) for item in self.content_list]
        logger.info(f"共解析 {len(self.elements)} 个版面元素")
        return self.elements

    def _to_element(self, item: Dict[str, Any]) -> LayoutElement:
        """将原始字典转换为 LayoutElement。"""
        raw_type = item.get("type", "unknown")
        try:
            etype = ElementType(raw_type)
        except ValueError:
            etype = ElementType.UNKNOWN

        text = item.get("text", "")
        # table 的文本可能嵌套在 html 中，暂保留原结构
        if etype == ElementType.TABLE:
            text = item.get("table_body", "")

        meta: Dict[str, Any] = {}
        for key in ("img_path", "table_caption", "table_footnote", "text_level", "level"):
            if key in item:
                meta[key] = item[key]

        return LayoutElement(
            element_type=etype,
            text=text,
            page_idx=item.get("page_idx", -1),
            bbox=item.get("bbox", []),
            metadata=meta,
        )

    def filter_by_type(self, element_type: ElementType) -> List[LayoutElement]:
        """按类型筛选元素。"""
        return [e for e in self.elements if e.element_type == element_type]

    def filter_by_page(self, page_idx: int) -> List[LayoutElement]:
        """按页码筛选元素。"""
        return [e for e in self.elements if e.page_idx == page_idx]

    def get_translatable_elements(self) -> List[LayoutElement]:
        """获取所有可翻译的文本类元素。"""
        return [e for e in self.elements if e.is_translatable]

    def get_summary(self) -> Dict[str, Any]:
        """获取版面分析统计摘要。"""
        if not self.elements:
            self.parse()

        type_counts: Dict[str, int] = {}
        page_count = 0
        for e in self.elements:
            type_counts[e.element_type.value] = type_counts.get(e.element_type.value, 0) + 1
            if e.page_idx + 1 > page_count:
                page_count = e.page_idx + 1

        return {
            "total_elements": len(self.elements),
            "page_count": page_count,
            "type_distribution": type_counts,
            "translatable_count": len(self.get_translatable_elements()),
        }

    def save_summary(self, output_path: Path) -> None:
        """将摘要保存为 JSON 文件。"""
        summary = self.get_summary()
        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"版面摘要已保存: {output_path}")
