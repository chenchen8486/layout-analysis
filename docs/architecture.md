# 版面分析与翻译流水线架构文档

本文档描述 MinerU 版面分析与 DeepSeek 翻译流水线的整体架构、模块职责、调用流程与关键设计决策。

---

## 1. 设计目标

- **配置驱动**：所有路径、密钥、模型参数外置到 `config/settings.yaml`，本地个人配置通过 `config/settings.local.yaml` 覆盖。
- **批量与增量**：支持单文件或文件夹输入；每个 PDF 拥有独立状态文件，源文件未变更且阶段已成功时自动跳过。
- **版面分析**：结构化读取 MinerU 输出的 `content_list.json`，提取文本、标题、表格、图片等元素并生成摘要。
- **全文翻译**：直接翻译 MinerU 生成的 `{stem}.md`，保持 Markdown 语法、图片引用、URL、HTML 标签不变。
- **可测试**：每个核心模块配套单元测试。

---

## 2. 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `config/settings.yaml` | 全局配置模板，提交到 Git |
| 本地覆盖 | `config/settings.local.yaml` | 本地个人路径 / 密钥覆盖，不提交 Git |
| 日志 | `utils/logger.py` | 统一日志（文件 + 控制台，utf-8-sig） |
| MinerU 引擎 | `core/mineru_engine.py` | 封装 CLI 调用、输出目录推断、流水线级重试 |
| 版面解析 | `core/layout_parser.py` | 解析 JSON 输出，提取可翻译元素，生成统计摘要 |
| 流水线追踪 | `core/pipeline_tracker.py` | 维护 `pipeline_state.json`，支持增量转换与断点续传 |
| 翻译器 | `core/translator.py` | 调用 DeepSeek API，支持单条、批量、Markdown 全文翻译与重试 |
| 入口 | `main.py` | CLI 入口，串联整条流水线 |
| 测试 | `tests/` | 各模块单元测试 |

---

## 3. 调用流程

```text
用户命令: python main.py --input xxx.pdf --output out/ --translate --target-lang 英文
    │
    ▼
加载 .env 中的环境变量（如 DEEPSEEK_API_KEY）
    │
    ▼
加载 config/settings.yaml，若存在则合并 config/settings.local.yaml
    │
    ▼
collect_pdfs(input_path) → 扫描输入路径（文件或文件夹）
    │
    ▼
for pdf_path in pdf_list:
    │
    ├── PipelineTracker(output_subdir) 检查 pipeline_state.json
    │       └── 阶段为 done 且源文件未变更则跳过
    │
    ├── MinerUEngine.run(input_pdf, output_dir)  [若 mineru 阶段需执行]
    │       └── subprocess.run(mineru.exe -p ... -o ... --backend pipeline)
    │       └── 生成 {stem}/auto/{stem}.md 与 {stem}_content_list.json
    │
    ├── LayoutParser.parse(auto_dir)  [若 layout 阶段需执行]
    │       └── 读取 *_content_list.json → List[LayoutElement]
    │       └── 生成 layout_summary.json
    │
    └── DeepSeekTranslator.translate_markdown(md_content, target_lang)  [若 translate 阶段需执行]
            └── 按语义长度分块 → 并发翻译 → 合并为完整 Markdown
            └── 保存 {stem}_zh.md（与原文并排）
    │
    ▼
保存 / 更新 batch_summary.json（成功 / 跳过 / 失败统计）
```

---

## 4. 输出目录结构

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

---

## 5. PipelineTracker 状态追踪

### 5.1 状态文件格式

`pipeline_state.json` 示例：

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

### 5.2 增量判断逻辑

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

### 5.3 接口设计

```python
class PipelineTracker:
    def __init__(self, output_dir: Path)
    def is_stage_needed(self, source_path: Path, stage: str) -> bool
    def mark_stage(self, source_path: Path, stage: str, status: str, error: str = "")
    def get_overview(self) -> Dict[str, Any]
```

---

## 6. 主流程改造要点

### 6.1 输入路径解析

- 若 `input_path` 是文件 → 单文件模式（兼容旧逻辑）。
- 若 `input_path` 是目录 → 批量模式：
  - 默认非递归扫描所有 `.pdf`；
  - 可配置 `pipeline.recursive: true` 递归子目录。

### 6.2 单 PDF 处理流程

```text
for pdf_path in pdf_list:
    tracker = PipelineTracker(output_subdir)

    # Stage 1: MinerU
    if tracker.is_stage_needed(pdf_path, "mineru"):
        try:
            engine.run(pdf_path, output_subdir)
            tracker.mark_stage(pdf_path, "mineru", "done")
        except Exception as exc:
            tracker.mark_stage(pdf_path, "mineru", "failed", error=str(exc))
            continue

    # Stage 2: Layout
    if tracker.is_stage_needed(pdf_path, "layout"):
        try:
            layout_parser.parse()
            tracker.mark_stage(pdf_path, "layout", "done")
        except Exception as exc:
            tracker.mark_stage(pdf_path, "layout", "failed", error=str(exc))
            continue

    # Stage 3: Translate（可选，全文 Markdown 翻译）
    if translate and tracker.is_stage_needed(pdf_path, "translate"):
        try:
            md_path = auto_dir / f"{stem}.md"
            md_content = md_path.read_text(encoding="utf-8")
            result = translator.translate_text(
                md_content,
                target_lang=target_lang,
                system_prompt=custom_prompt,
            )
            translated_md_path = auto_dir / f"{stem}_zh.md"
            translated_md_path.write_text(result.translated, encoding="utf-8")
            tracker.mark_stage(pdf_path, "translate", "done")
        except Exception as exc:
            tracker.mark_stage(pdf_path, "translate", "failed", error=str(exc))
```

### 6.3 最终汇总

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

---

## 7. 配置说明

`config/settings.yaml` 采用精简策略，仅保留用户日常必改项：

```yaml
mineru:
  executable_path: ""   # 显式指定 mineru 可执行文件路径
  max_retries: 3        # MinerU 解析失败时的最大尝试次数

deepseek:
  api_key: ""           # 不推荐直接填写，优先使用 .env
  target_lang: "中文"

pipeline:
  input_path: "./data/"
  output_path: "./outputs/"
  translate: true
  save_markdown: true
  recursive: false

logging:
  level: "INFO"
```

其余参数（`backend`、`language`、`model`、`base_url`、`max_retries`、`timeout`、`batch_size`、`temperature`、`max_workers`）使用代码内置默认值，不在配置文件中暴露，但可通过 `settings.yaml` 的 `deepseek` 段覆盖。

### 7.1 API Key 安全存储

- **不推荐**：将 `api_key` 直接写入 `config/settings.yaml` 并提交到 Git。
- **推荐**：在项目根目录创建 `.env` 文件，写入 `DEEPSEEK_API_KEY=sk-...`，`.env` 已加入 `.gitignore`。
- **备选**：设置系统环境变量 `DEEPSEEK_API_KEY`。

读取优先级：`settings.yaml` 配置 > `.env` 文件 / 系统环境变量。

> 说明：`.env` 文件通过 `python-dotenv` 加载后，会与系统环境变量合并为同一优先级。若 `settings.yaml` 中 `api_key` 为空，则优先使用 `.env` 或环境变量；若 `settings.yaml` 中填写了密钥，则优先使用配置文件中的值。

---

## 8. 翻译提效参数

| 参数 | 代码默认值 | 说明 |
|---|---|---|
| `batch_size` | 32 | 每批翻译段落数 |
| `temperature` | 0.1 | 生成温度，越低越稳定 |
| `max_workers` | 3 | 并发线程数，同时发送 batch 数量 |
| `max_retries` | 3 | 失败重试次数 |
| `timeout` | 60 | 单次请求超时秒数 |

---

## 9. 关键设计决策

### 9.1 可执行文件查找优先级

1. `config/settings.yaml` 显式指定
2. 当前激活的 conda 环境 `Scripts/mineru.exe`
3. 环境变量 `MINERU_PATH`
4. 系统 `PATH`

### 9.2 批量翻译分隔符策略

为节省 API Token 与请求次数，将同一批段落用 `\n\n---PARAGRAPH_BREAK---\n\n` 拼接为单条请求，并在 System Prompt 中要求模型保持分隔符不变。返回后按相同分隔符拆分。

### 9.3 DeepSeek 重试机制

采用指数退避（`2^attempt` 秒），应对 DeepSeek API 偶发的网络抖动或限流。

### 9.4 输出目录推断

`MinerUEngine` 集中处理 MinerU 输出目录推断，统一解析 `output_dir/<stem>/auto/` 及其兼容路径，`main.py` 不复实现。

---

## 10. 测试策略

- `test_mineru_engine.py`：覆盖可执行文件查找、输出目录推断、重试逻辑。
- `test_layout_parser.py`：覆盖快照解析、摘要生成、未知类型处理。
- `test_pipeline_tracker.py`：覆盖状态读写、增量判断、源文件修改后重新触发。
- `test_translator.py`：覆盖构造、单条翻译、批量翻译、空文本处理。

运行全部测试：

```bash
python -m unittest discover -s tests -v
```

---

## 11. 变更记录

- **2026-07-07**: 合并 `docs/design.md` 与 `docs/design_incremental_batch.md` 为 `docs/architecture.md`；删除 `docs/optimization_plan.md`；P3 UI 议题移入 README「未来规划」。
- **2026-07-07**: 为 `MinerUEngine.run()` 增加流水线级重试机制，默认最多尝试 3 次；支持通过 `config/settings.yaml` 的 `mineru.max_retries` 调整。
- **2026-07-06**: 锁定 MinerU 兼容版本为 3.4.2，更新 README 安装指引与 `requirements.txt`。
- **2026-07-06**: 补全 `core/pipeline_tracker.py` 与 `core/translator.py`；`main.py` 支持 `settings.local.yaml` 本地覆盖；翻译逻辑从 `main.py` 下沉至 `core/translator.py`。
- **2026-05-13**: 初始化工程结构，完成 core / utils / config / tests / docs / main.py 全部模块。
