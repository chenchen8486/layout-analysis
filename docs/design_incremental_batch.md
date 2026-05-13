# 增量批量转换设计文档

## 1. 需求概述

- **批量输入**：`pipeline.input_path` 可配置为文件夹路径，程序自动扫描其中所有 `.pdf` 文件。
- **增量转换**：每个 PDF 在输出目录中有独立的子目录与状态文件，记录各阶段完成时间与源文件修改时间。若源文件未变更且阶段已成功，则直接跳过该阶段。
- **结果可识别**：通过 `pipeline_state.json` 即可知道哪些已转换、哪些未转换或失败。

## 2. 输出目录结构

```text
output_dir/
├── {pdf_stem_A}/
│   ├── pipeline_state.json          # 状态追踪文件
│   ├── auto/                        # MinerU 原始输出
│   │   └── {stem}_content_list.json
│   ├── layout_summary.json          # 版面分析摘要
│   ├── translated_content.json      # 翻译结果（可选）
│   └── translated.md                # 翻译后 Markdown（可选）
├── {pdf_stem_B}/
│   └── ...
└── batch_summary.json               # 本次批量运行总览
```

## 3. PipelineTracker 状态追踪模块

### 3.1 状态文件格式 (`pipeline_state.json`)

```json
{
  "source_path": "D:/docs/example.pdf",
  "source_mtime": 1715587200.0,
  "stages": {
    "mineru": {"status": "done", "timestamp": "2026-05-13T10:00:00", "error": ""},
    "layout": {"status": "done", "timestamp": "2026-05-13T10:01:00", "error": ""},
    "translate": {"status": "skipped", "timestamp": "", "error": ""}
  }
}
```

状态枚举：`pending`（待执行）、`done`（已完成）、`skipped`（因配置或无需执行而跳过）、`failed`（失败）。

### 3.2 增量判断逻辑

```python
def is_stage_needed(source_path: Path, output_dir: Path, stage: str) -> bool:
    state = load_state(output_dir)
    current_mtime = source_path.stat().st_mtime
    stage_info = state["stages"].get(stage)

    if stage_info is None or stage_info["status"] != "done":
        return True
    if current_mtime > state["source_mtime"]:
        return True
    return False
```

即：**阶段未成功完成，或源文件在阶段完成后被修改过**，才需要重新执行。

### 3.3 接口设计

```python
class PipelineTracker:
    def __init__(self, output_dir: Path)
    def is_stage_needed(self, source_path: Path, stage: str) -> bool
    def mark_stage(self, source_path: Path, stage: str, status: str, error: str = "")
    def get_overview(self) -> Dict[str, Any]   # 返回各阶段状态汇总
```

## 4. 主流程改造 (main.py)

### 4.1 输入路径解析

- 若 `input_path` 是文件 → 单文件模式（兼容旧逻辑）。
- 若 `input_path` 是目录 → 批量模式：
  - 递归或非递归扫描所有 `.pdf`（默认非递归，可配置 `pipeline.recursive: true`）。
  - 生成 `(pdf_path, output_subdir)` 列表。

### 4.2 单 PDF 处理流程

```text
for pdf_path in pdf_list:
    tracker = PipelineTracker(output_subdir)

    # Stage 1: MinerU
    if tracker.is_stage_needed(pdf_path, "mineru"):
        try:
            engine.run(pdf_path, output_subdir)
            tracker.mark_stage(pdf_path, "mineru", "done")
        except Exception:
            tracker.mark_stage(pdf_path, "mineru", "failed", error=str(exc))
            continue

    # Stage 2: Layout
    if tracker.is_stage_needed(pdf_path, "layout"):
        try:
            layout_parser.parse()
            ...
            tracker.mark_stage(pdf_path, "layout", "done")
        except Exception:
            tracker.mark_stage(pdf_path, "layout", "failed", error=str(exc))
            continue

    # Stage 3: Translate（可选）
    if args.translate and tracker.is_stage_needed(pdf_path, "translate"):
        try:
            translator.translate_batch(...)
            ...
            tracker.mark_stage(pdf_path, "translate", "done")
        except Exception:
            tracker.mark_stage(pdf_path, "translate", "failed", error=str(exc))
```

### 4.3 最终汇总

全部 PDF 处理完毕后，输出统计：

```text
========================================
批量转换汇总
========================================
总计 PDF  : 10
成功完成  : 8
增量跳过  : 1
失败      : 1
详细日志见: logs/main_*.log
```

## 5. 配置变更

```yaml
pipeline:
  input_path: "./data/"          # 可以是文件或文件夹
  output_path: "./outputs/"
  recursive: false               # 扫描输入文件夹时是否递归子目录
```

## 6. 测试策略

- `test_pipeline_tracker.py`：覆盖状态读写、增量判断、源文件修改后重新触发。
- 更新 `test_mineru_engine.py`：验证输出目录参数适配新结构。
- 保留既有单文件测试，确保向后兼容。
