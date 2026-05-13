# MinerU 版面分析与翻译流水线

基于 [MinerU](https://github.com/opendatalab/MinerU) 的 PDF 解析能力，集成 DeepSeek Chat API 翻译，实现从 PDF 到结构化版面分析再到多语言翻译的完整流水线。

## 核心目标

- 参数化输入输出，零硬编码路径。
- 支持单文件或整个文件夹的**批量转换**。
- **增量转换**：自动跳过已处理且源文件未变更的 PDF，失败后支持断点续传。
- 结构化解析版面元素（文本、标题、表格、图片等）。
- 支持 DeepSeek API **全文 Markdown 翻译**，保持原有格式、图片引用、表格结构不变。
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

#### 3.1 编辑 `config/settings.yaml`（常用配置）

```yaml
mineru:
  # 若 mineru.exe 不在 conda doc 环境或系统 PATH，请填写绝对路径
  executable_path: ""

deepseek:
  # 推荐将 API Key 写入 .env 文件（DEEPSEEK_API_KEY=...），避免泄露
  # 若此处留空，程序会自动读取 .env 或环境变量
  api_key: ""
  # 翻译目标语言：中文、英文、日文 等
  target_lang: "中文"

pipeline:
  # 输入路径：单个 PDF 文件，或包含多个 PDF 的文件夹
  input_path: "D:/project/python_release/avation_doc/input"
  # 输出路径：解析与翻译结果存放目录
  output_path: "D:/project/python_release/avation_doc/output"
  # 是否启用 DeepSeek 翻译（false = 仅解析，不翻译）
  translate: true
  # 是否保存翻译后的 Markdown 文件
  save_markdown: true

logging:
  # 日志级别：DEBUG / INFO / WARNING / ERROR
  level: "INFO"
```

#### 3.2 配置 `.env` 文件（推荐，安全存储 API Key）

在项目根目录创建 `.env` 文件：

```bash
# DeepSeek API Key（此文件已加入 .gitignore，不会被提交）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 3.3 或通过环境变量设置

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
  translate: true
  save_markdown: true
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

# 解析 + 翻译为中文
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" -t --target-lang 中文 -m
```

## 输出目录结构

每个 PDF 对应一个独立的子目录，内部包含 MinerU 原始输出、版面分析摘要、翻译结果及状态追踪文件：

```text
outputs/
├── {pdf_stem_A}/
│   ├── pipeline_state.json          # 各阶段完成状态与源文件 mtime
│   ├── auto/                        # MinerU 原始输出 + 翻译结果
│   │   ├── {stem}_content_list.json # 版面元素列表
│   │   ├── {stem}.md                # 原始 Markdown（MinerU 生成）
│   │   ├── {stem}_zh.md             # 中文翻译 Markdown（保持原格式、图片引用不变）
│   │   └── images/                  # 提取的图片
│   └── layout_summary.json          # 版面分析摘要
├── {pdf_stem_B}/
│   └── ...
└── batch_summary.json               # 本次批量运行总览（成功/跳过/失败统计）
```

## 目录结构

```text
layout_analysis/
├── config/
│   ├── __init__.py
│   └── settings.yaml          # 全局配置（精简版，仅常用参数）
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
├── .env                       # DeepSeek API Key（已加入 .gitignore）
├── main.py                    # 命令行入口
├── requirements.txt
└── README.md
```

## 程序框架与调用流程

```text
main.py
  │
  ├── .env                    ← 加载环境变量（DEEPSEEK_API_KEY）
  │
  ├── config/settings.yaml    ← 加载配置（translate、target_lang 等）
  │
  ├── collect_pdfs()          ← 扫描输入路径（文件或文件夹）
  │
  ├── core/pipeline_tracker.py  ← 检查每个 PDF 的各阶段状态
  │       └── pipeline_state.json
  │
  ├── core/mineru_engine.py   ← 调用 mineru.exe 生成解析结果
  │       └── {stem}/auto/
  │           └── {stem}.md（原始 Markdown）
  │
  ├── core/layout_parser.py   ← 读取 content_list.json，提取版面元素
  │       └── layout_summary.json
  │
  ├── core/translator.py      ←（可选）DeepSeek Markdown 全文翻译
  │       └── 直接翻译 {stem}.md 全文，输出 {stem}_zh.md
  │       └── 保持 Markdown 语法、图片引用、URL、HTML 标签不变
  │
  └── batch_summary.json      ← 批量运行总览
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

### 如何强制重新翻译已完成的 PDF？

由于翻译策略可能更新（如从段落重建改为全文 Markdown 翻译），需要重置翻译状态：

```bash
# 重置所有 PDF 的 translate 阶段状态
python -c "
import json, glob
for path in glob.glob('outputs/*/pipeline_state.json'):
    with open(path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    data['stages']['translate']['status'] = 'pending'
    data['stages']['translate']['timestamp'] = ''
    with open(path, 'w', encoding='utf-8-sig') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'已重置: {path}')
"
```

## 翻译提效参数（代码内置默认值）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `batch_size` | 32 | 每批翻译段落数，增大可减少请求次数 |
| `temperature` | 0.1 | 生成温度，越低输出越稳定、确定性越高 |
| `max_workers` | 3 | 并发线程数，同时发送 3 个 batch |
| `max_retries` | 3 | 失败重试次数 |
| `timeout` | 60 | 单次请求超时秒数 |

如需调整，可在 `config/settings.yaml` 的 `deepseek` 段下添加对应项（如 `batch_size: 48`），代码会自动读取。不常用参数保持代码默认值即可。

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
- **2026-05-13**: 翻译策略改为直接对 MinerU 生成的 Markdown 全文翻译，保持原有格式、图片引用、表格结构不变，译文输出到 `auto/{stem}_zh.md`，与原文并排存放。
- **2026-05-13**: 精简 `settings.yaml`，仅保留 7 个常用参数，其余使用代码内置默认值。
- **2026-05-13**: 将 DeepSeek API Key 从 `settings.yaml` 迁移到 `.env` 文件，避免敏感凭证提交到 Git。
- **2026-05-13**: 翻译提效优化：`batch_size` 16→32、`temperature` 0.3→0.1、`translate_batch` 改为 `ThreadPoolExecutor` 并发执行（max_workers=3）。
