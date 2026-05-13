# 增量批量转换设计文档

## 1. 需求概述

- **批量输入**：`pipeline.input_path` 可配置为文件夹路径，程序自动扫描其中所有 `.pdf` 文件。
- **增量转换**：每个 PDF 在输出目录中有独立的子目录与状态文件，记录各阶段完成时间与源文件修改时间。若源文件未变更且阶段已成功，则直接跳过该阶段。
- **结果可识别**：通过 `pipeline_state.json` 即可知道哪些已转换、哪些未转换或失败。
- **全文 Markdown 翻译**：直接翻译 MinerU 生成的 `{stem}.md` 文件，保持 Markdown 语法、图片引用、URL、HTML 标签完全不变，译文输出到 `auto/{stem}_zh.md`。

## 2. 输出目录结构

```text
output_dir/
├── {pdf_stem_A}/
│   ├── pipeline_state.json          # 状态追踪文件
│   ├── auto/                        # MinerU 原始输出 + 翻译结果
│   │   ├── {stem}_content_list.json
│   │   ├── {stem}.md                # 原始 Markdown
│   │   ├── {stem}_zh.md             # 中文翻译 Markdown（可选）
│   │   └── images/                  # 提取的图片
│   └── layout_summary.json          # 版面分析摘要
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

    # Stage 3: Translate（可选，全文 Markdown 翻译）
    if translate and tracker.is_stage_needed(pdf_path, "translate"):
        try:
            # 查找 MinerU 生成的 {stem}.md
            md_path = auto_dir / f"{stem}.md"
            with open(md_path, "r") as f:
                md_content = f.read()
            
            # 全文翻译，要求保持 Markdown 语法、图片引用、URL 不变
            result = translator.translate_text(
                md_content,
                target_lang=target_lang,
                system_prompt=custom_prompt,
            )
            
            # 保存到 auto 目录，与原文并排
            translated_md_path = auto_dir / f"{stem}_zh.md"
            with open(translated_md_path, "w") as f:
                f.write(result.translated)
            
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

## 5. 配置说明

```yaml
pipeline:
  input_path: "./data/"          # 可以是文件或文件夹
  output_path: "./outputs/"
  translate: true                # 是否启用 DeepSeek 翻译
  save_markdown: true            # 是否保存翻译后的 Markdown
```

`settings.yaml` 采用精简策略，仅保留用户日常必改项（api_key、target_lang、input_path、output_path、translate、save_markdown）。其余参数（backend、language、model、base_url、max_retries、timeout、batch_size、temperature、max_workers）使用代码内置默认值，不在配置文件中暴露。

## 6. API Key 安全存储

- **不推荐**：将 `api_key` 直接写入 `config/settings.yaml` 并提交到 Git。
- **推荐**：在项目根目录创建 `.env` 文件，写入 `DEEPSEEK_API_KEY=sk-...`，`.env` 已加入 `.gitignore`，不会提交。
- **备选**：设置系统环境变量 `DEEPSEEK_API_KEY`。

读取优先级：`settings.yaml` 配置 > `.env` 文件 > 系统环境变量。

## 7. 翻译提效参数

| 参数 | 代码默认值 | 说明 |
|---|---|---|
| `batch_size` | 32 | 每批翻译段落数 |
| `temperature` | 0.1 | 生成温度，越低越稳定 |
| `max_workers` | 3 | 并发线程数，同时发送 batch 数量 |
| `max_retries` | 3 | 失败重试次数 |
| `timeout` | 60 | 单次请求超时秒数 |

## 8. 测试策略

- `test_pipeline_tracker.py`：覆盖状态读写、增量判断、源文件修改后重新触发。
- `test_translator.py`：覆盖构造、单条翻译、批量翻译、空文本处理。
- 保留既有单文件测试，确保向后兼容。
