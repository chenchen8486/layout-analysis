# MinerU 版面分析与翻译流水线

基于 [MinerU](https://github.com/opendatalab/MinerU) 的 PDF 解析能力，集成 DeepSeek Chat API 翻译，实现从 PDF 到结构化版面分析再到多语言翻译的完整流水线。

## 核心目标

- 参数化输入输出，零硬编码路径。
- 支持单文件或整个文件夹的**批量转换**。
- **增量转换**：自动跳过已处理且源文件未变更的 PDF，失败后支持断点续传。
- 结构化解析版面元素（文本、标题、表格、图片等）。
- 支持 DeepSeek API 段落级批量翻译。
- 全链路日志追踪与单元测试覆盖。

## 环境配置

### 1. 虚拟环境

```bash
conda activate doc
```

### 2. 安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 3. 配置 MinerU 与 DeepSeek

编辑 `config/settings.yaml`：

```yaml
mineru:
  # 若 mineru.exe 已在 conda doc 环境或系统 PATH，可留空
  executable_path: ""
  backend: "pipeline"
  language: "ch"

deepseek:
  api_key: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com"
  max_retries: 3
  timeout: 60
  batch_size: 16

pipeline:
  # input_path 可以是单个 PDF 文件，也可以是包含多个 PDF 的文件夹
  input_path: "./data/"
  output_path: "./outputs/"
  # 扫描文件夹时是否递归子目录
  recursive: false
```

或通过环境变量设置：

```bash
set MINERU_PATH=C:\Users\chenc\anaconda3\envs\doc\Scripts\mineru.exe
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 快速启动

### 方式一：IDE 直接运行（推荐日常开发）

在 `config/settings.yaml` 的 `pipeline` 段配置好路径后，直接在 PyCharm / VS Code 中右键运行 `main.py`，无需输入任何命令行参数。

```yaml
pipeline:
  input_path: "./data/"           # 文件夹路径 → 批量转换
  output_path: "./outputs/"
```

### 方式二：命令行运行（适合脚本化、批处理）

命令行参数的优先级高于配置文件，可临时覆盖配置。

```bash
# 仅解析单个 PDF
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test"

# 解析整个文件夹（批量 + 增量）
python main.py -i "D:/docs/" -o "D:/outputs/"

# 递归扫描子目录
python main.py -i "D:/docs/" -o "D:/outputs/" -r

# 解析 + 翻译为英文
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" --translate --target-lang 英文

# 解析 + 翻译 + 生成翻译后 Markdown
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" -t --target-lang 英文 -m
```

## 输出目录结构

每个 PDF 对应一个独立的子目录，内部包含 MinerU 原始输出、版面分析摘要、翻译结果及状态追踪文件：

```text
outputs/
├── {pdf_stem_A}/
│   ├── pipeline_state.json          # 各阶段完成状态与源文件 mtime
│   ├── auto/                        # MinerU 原始输出
│   │   └── {stem}_content_list.json
│   ├── layout_summary.json          # 版面分析摘要
│   ├── translated_content.json      # 翻译结果（可选）
│   └── translated.md                # 翻译后 Markdown（可选）
├── {pdf_stem_B}/
│   └── ...
└── batch_summary.json               # 本次批量运行总览（成功/跳过/失败统计）
```

## 目录结构

```text
layout_analysis/
├── config/
│   ├── __init__.py
│   └── settings.yaml          # 全局配置
├── core/
│   ├── __init__.py
│   ├── mineru_engine.py       # MinerU CLI 封装
│   ├── layout_parser.py       # 版面分析结果解析
│   ├── pipeline_tracker.py    # 增量转换状态追踪
│   └── translator.py          # DeepSeek API 翻译
├── utils/
│   ├── __init__.py
│   └── logger.py              # 统一日志
├── tests/
│   ├── test_mineru_engine.py
│   ├── test_layout_parser.py
│   ├── test_pipeline_tracker.py
│   └── test_translator.py
├── docs/
│   ├── design.md              # 初始设计文档
│   └── design_incremental_batch.md  # 增量批量转换设计
├── main.py                    # 命令行入口
├── requirements.txt
└── README.md
```

## 程序框架与调用流程

```text
main.py
  │
  ├── config/settings.yaml  ← 加载配置
  │
  ├── collect_pdfs()        ← 扫描输入路径（文件或文件夹）
  │
  ├── core/pipeline_tracker.py  ← 检查每个 PDF 的各阶段状态
  │       └── pipeline_state.json
  │
  ├── core/mineru_engine.py  ← 调用 mineru.exe 生成解析结果
  │       └── {stem}/auto/
  │
  ├── core/layout_parser.py  ← 读取 content_list.json，提取版面元素
  │       └── layout_summary.json
  │
  ├── core/translator.py     ←（可选）DeepSeek 批量翻译
  │       └── translated_content.json、translated.md
  │
  └── batch_summary.json     ← 批量运行总览
```

## 增量转换机制

`PipelineTracker` 为每个 PDF 维护一个 `pipeline_state.json`，记录：

- `source_mtime`：上次成功处理时源文件的修改时间
- `stages`：MinerU 解析 / 版面分析 / 翻译 三个阶段的状态

**判断逻辑**：
1. 若阶段状态非 `done`，必须执行；
2. 若阶段已完成，但源文件在上次处理后又被修改过（`current_mtime > source_mtime`），则重新执行；
3. 否则跳过该阶段。

这意味着：
- 第一次运行会完整处理所有 PDF；
- 再次运行（未修改文件）会秒级跳过；
- 修改了某个 PDF 后再次运行，仅重新处理该文件；
- 某阶段失败后重跑，会从失败阶段继续，而非从头开始。

## 测试

```bash
# 运行全部单元测试
python -m unittest discover -s tests -v

# 单独运行某一模块
python -m unittest tests.test_pipeline_tracker -v
```

## 变更记录

- **2026-05-13**: 初始化工程结构，完成全部模块开发。
- **2026-05-13**: 支持 YAML 配置中 `r"..."` 原始字符串与 Windows 反斜杠路径。
- **2026-05-13**: 新增批量转换与增量转换能力，引入 `PipelineTracker` 状态追踪模块，支持文件夹输入、断点续传与批量汇总报告。
