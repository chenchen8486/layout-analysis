# MinerU 版面分析与翻译流水线

基于 [MinerU](https://github.com/opendatalab/MinerU) 的 PDF 解析能力，集成 DeepSeek Chat API 翻译，实现从 PDF 到结构化版面分析再到多语言翻译的完整流水线。

## 核心目标

- 参数化输入输出，零硬编码路径。
- 支持单文件或整个文件夹的**批量转换**。
- **增量转换**：自动跳过已处理且源文件未变更的 PDF，失败后支持断点续传。
- 结构化解析版面元素（文本、标题、表格、图片等）。
- 支持 DeepSeek API **全文 Markdown 翻译**，保持原有格式、图片引用、表格结构不变。
- 全链路日志追踪与单元测试覆盖。

---

## 前置依赖

本项目**不是** MinerU 本身，而是调用 MinerU CLI 的上层流水线。因此你需要**先独立安装 MinerU**，并确保命令行可以执行 `mineru`。

### 1. 安装 MinerU CLI

请参考官方仓库：[https://github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU)

推荐方式（conda 环境）：

```bash
# 创建并激活 conda 环境（官方推荐 Python 3.10）
conda create -n doc python=3.10 -y
conda activate doc

# 安装 MinerU（推荐固定到已验证版本 3.4.2）
pip install "mineru==3.4.2" -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 验证安装
mineru --help
```

> **Windows 用户注意**：安装完成后，请在当前 conda `doc` 环境下执行 `mineru --help`，确认能正常输出帮助信息。如果提示找不到命令，请检查 conda 环境的 `Scripts/` 目录是否在 PATH 中。

### 2. 安装本项目的 Python 依赖

```bash
# 同样建议在 doc 环境下执行
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

依赖清单：
- `requests` — HTTP 请求库
- `pyyaml` — YAML 配置解析
- `python-dotenv` — 从 `.env` 文件加载环境变量

---

## MinerU 源码位置与本工程更新策略

### 原始 MinerU 代码工程位置

本流水线参考并调用了本地 MinerU 源码工程中的能力，原始代码仓库位于：

```text
D:\project\ai_tools\MinerU-master
```

> 注意：本工程**不是** MinerU 的 fork，而是调用 `mineru` CLI 的上层封装。因此日常开发不需要修改 MinerU 源码，只需确保本地 MinerU 可执行文件可用即可。

### 当 MinerU 仓库更新时，如何同步到本工程

MinerU 升级后，真正影响本工程的只有三个**耦合面**：

| 耦合面 | 本工程受影响位置 | 检查方法 |
|---|---|---|
| CLI 参数协议 | `core/mineru_engine.py` 的 `cmd` 列表 | `mineru --help`、官方 Release Notes |
| 输出目录结构 | `MinerUEngine.run()` 的目录推断 | 用样例 PDF 跑一次，检查是否仍为 `<stem>/auto/` |
| `content_list.json` / `.md` schema | `core/layout_parser.py`、`main.py` | 对比新旧输出 JSON 字段 |

推荐更新流程：

1. **锁定当前版本**  
   在 `requirements.txt` 中固定 MinerU 版本，例如：  
   ```text
   mineru==0.10.x
   ```  
   并在本工程 README 中记录「已验证兼容版本」。

2. **隔离环境验证新版**  
   在独立 conda 环境安装新版 MinerU：  
   ```bash
   conda create -n mineru-test python=3.10 -y
   conda activate mineru-test
   pip install "mineru==x.y.z" -i https://pypi.tuna.tsinghua.edu.cn/simple/
   ```  
   用样例 PDF 跑解析，观察输出目录与 JSON 字段变化。

3. **按需修改本工程**  
   - CLI 参数变了 → 修改 `core/mineru_engine.py`
   - 输出目录变了 → 修改 `MinerUEngine._resolve_auto_dir()`
   - JSON / Markdown schema 变了 → 修改 `core/layout_parser.py` / `main.py`

4. **更新测试快照**  
   将新版 MinerU 的样例输出复制到 `tests/fixtures/sample_mineru_output/`，并运行回归测试：  
   ```bash
   python -m unittest discover -s tests -v
   ```

5. **更新兼容性记录**  
   在 README 的「已验证兼容的 MinerU 版本」表中追加新版本与验证日期。

### 已验证兼容的 MinerU 版本

| 本工程版本 | MinerU 版本 | 验证日期 | 备注 |
|-----------|------------|---------|------|
| 0.1.0     | 3.4.2      | 2026-07-06 | 基于 `D:\project\ai_tools\MinerU-master` 源码版本验证 |

---

## 本工程与本地深度学习模型的关系

### 本工程不直接加载本地模型

`layout_analysis` 本身**不直接调用**任何本地深度学习模型。它通过 `core/mineru_engine.py` 调用 MinerU CLI，由 MinerU 内部完成版面分析、OCR、公式识别、表格识别等任务。本工程只负责解析 MinerU 输出的 JSON 与 Markdown。

因此：

- 本工程目录下**没有** `.pth` / `.safetensors` / `.onnx` 等模型文件。
- 所有模型文件都在 MinerU 的模型缓存目录中。
- `core/translator.py` 中的 DeepSeek 仅用于 Markdown 翻译，**不用于 OCR 或版面分析**。

### MinerU 内部使用的模型

MinerU 3.4.2 默认从 Hugging Face 仓库 `opendatalab/PDF-Extract-Kit-1.0` 下载模型。已验证的模型清单如下：

| 任务 | 模型 / 目录 | 说明 |
|------|------------|------|
| 版面分析 | `models/Layout/PP-DocLayoutV2` | PP-DocLayoutV2 版面分析模型 |
| OCR | `models/OCR/paddleocr_torch` | PaddleOCR PyTorch 版本 |
| 公式识别 | `models/MFR/unimernet_hf_small_2503` | UniMERNet 公式识别模型 |
| 文档方向分类 | `models/OriCls/paddle_orientation_classification` | Paddle 方向分类模型 |
| 表格分类 | `models/TabCls/paddle_table_cls` | 表格/非表格分类模型 |
| 表格结构识别 | `models/TabRec/SlanetPlus` | SLANet+ 表格结构识别 |
| 表格单元格识别 | `models/TabRec/UnetStructure` | UNet 表格单元格定位 |

### 模型文件在本机的默认位置

MinerU 使用 `huggingface_hub.snapshot_download` 下载模型，默认缓存到 Hugging Face 缓存目录。以当前环境为例，完整路径为：

```text
C:\Users\chenc\.cache\huggingface\hub\
└── models--opendatalab--PDF-Extract-Kit-1.0/
    └── snapshots/
        └── d1336ee3c2975a8b26c4b09ff39dc6b593d34141/
            └── models/
                ├── Layout/PP-DocLayoutV2/
                │   ├── config.json
                │   ├── model.safetensors
                │   └── preprocessor_config.json
                ├── OCR/paddleocr_torch/
                │   ├── ch_PP-OCRv4_rec_server_doc_infer.pth
                │   ├── ch_PP-OCRv5_det_infer.pth
                │   └── ch_PP-OCRv5_rec_infer.pth
                ├── MFR/unimernet_hf_small_2503/
                │   ├── config.json
                │   ├── model.safetensors
                │   ├── tokenizer.json
                │   └── tokenizer_config.json
                ├── OriCls/paddle_orientation_classification/
                ├── TabCls/paddle_table_cls/
                └── TabRec/
                    ├── SlanetPlus/
                    └── UnetStructure/
```

> 注意：`snapshots/` 下的哈希文件夹名称会随 MinerU 版本或模型更新而变化。如果你配置了 `HF_HOME` 环境变量，缓存目录会移到 `HF_HOME/hub/` 下。

### 如何自定义模型缓存位置

如需把模型放到其他磁盘（如空间更大的 D 盘），可在运行 MinerU 前设置环境变量：

```bash
# Windows (PowerShell)
$env:HF_HOME = "D:/huggingface_cache"

# Linux / macOS
export HF_HOME="/path/to/huggingface_cache"
```

设置后，MinerU 会自动将新模型下载到指定目录。

---

## Linux / macOS 适配说明

本项目代码基于 `pathlib` 与标准库实现，**完全支持 Linux 与 macOS**。Windows 用户可直接按后续章节操作；Linux / macOS 用户请额外注意以下三点差异即可：

### 1. 配置文件中的路径写法

`config/settings.yaml` 中的 `input_path` 与 `output_path` 请使用 Linux 绝对路径或相对路径：

```yaml
pipeline:
  input_path: "/home/用户名/data/input"
  output_path: "/home/用户名/data/output"
```

> 相对路径（如 `./my_pdfs`）在任何平台均通用。

### 2. MinerU 可执行文件路径

Linux / macOS 下 conda 环境的可执行文件位于 `bin/` 目录，且没有 `.exe` 后缀。若程序提示「未找到 MinerU」，请在 `config/settings.yaml` 中显式指定：

```yaml
mineru:
  executable_path: "/home/用户名/anaconda3/envs/doc/bin/mineru"
```

> 若已将 conda `doc` 环境激活，且 `mineru --help` 能正常输出，则通常无需额外配置，程序会通过系统 PATH 自动找到。

### 3. `.env` 文件创建

Linux / macOS 下使用终端命令创建：

```bash
touch .env
```

然后用任意文本编辑器（如 `vim`、`nano`、`gedit`）写入 `DEEPSEEK_API_KEY=sk-...` 即可。

---

## 快速开始（手把手三步跑通）

### 第一步：获取代码

```bash
git clone https://github.com/chenchen8486/layout-analysis.git
cd layout-analysis
```

### 第二步：配置 API Key（翻译必需）

在项目根目录创建 `.env` 文件：

```bash
# Windows: 直接新建文件
notepad .env

# Linux / macOS:
touch .env
```

写入你的 DeepSeek API Key：

```text
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> **如何获取 API Key？**
> 1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)
> 2. 注册 / 登录账号
> 3. 进入「API Keys」页面，点击「创建 API Key」
> 4. 复制以 `sk-` 开头的密钥，粘贴到 `.env` 文件中
> 5. 请妥善保管，**不要提交到 Git**（`.env` 已加入 `.gitignore`）

### 第三步：配置输入输出路径

打开 `config/settings.yaml`，修改 `pipeline` 段：

```yaml
pipeline:
  # 输入路径：单个 PDF 文件，或包含多个 PDF 的文件夹
  input_path: "D:/your_data/input"
  # 输出路径：解析与翻译结果存放目录（会自动创建）
  output_path: "D:/your_data/output"
  # 是否启用 DeepSeek 翻译（false = 仅解析，不翻译）
  translate: true
  # 是否保存翻译后的 Markdown 文件
  save_markdown: true
```

**路径配置示例**：

| 场景 | `input_path` 写法 | `output_path` 写法 |
|---|---|---|
| 单文件 | `D:/data/report.pdf` | `D:/outputs/report` |
| 文件夹（批量） | `D:/data/pdfs` | `D:/outputs` |
| 相对路径（项目内） | `./my_pdfs` | `./my_outputs` |

> **Windows 路径建议**：使用正斜杠 `/`（如 `D:/data/input`），或加 `r` 前缀（如 `r"D:\data\input"`）。直接使用反斜杠 `\` 会导致 YAML 解析失败。

### 运行

配置完成后，在 PyCharm / VS Code 中直接右键运行 `main.py`，或在终端执行：

```bash
python main.py
```

程序会自动读取 `config/settings.yaml` 和 `.env`，无需额外命令行参数。

---

## 完整配置指南

### `config/settings.yaml` 逐项说明

```yaml
# ── MinerU 配置 ──
mineru:
  # 【可选】显式指定 mineru.exe 的绝对路径
  # 留空时程序自动按以下顺序查找：
  #   1. conda doc 环境的 Scripts/mineru.exe
  #   2. 环境变量 MINERU_PATH
  #   3. 系统 PATH
  executable_path: ""

# ── DeepSeek 翻译配置 ──
deepseek:
  # 【不推荐】直接把 API Key 写在这里。优先使用 .env 文件。
  # 读取优先级：settings.yaml > .env 文件 / 系统环境变量
  # 如果此处留空，程序自动读取 .env 文件或系统环境变量的 DEEPSEEK_API_KEY
  api_key: ""

  # 翻译目标语言，支持：中文、英文、日文、韩文、法文、德文
  target_lang: "中文"

# ── 流水线配置 ──
pipeline:
  # 输入路径（必填）：PDF 文件或包含 PDF 的文件夹
  input_path: ""

  # 输出路径（必填）：结果存放目录，不存在会自动创建
  output_path: ""

  # 是否启用翻译（true/false）
  translate: true

  # 是否保存翻译后的 Markdown
  save_markdown: true

  # 【可选】扫描文件夹时递归子目录
  recursive: false

# ── 日志配置 ──
logging:
  # 日志级别：DEBUG / INFO / WARNING / ERROR
  # DEBUG 会输出最详细的信息，适合排错
  level: "INFO"
```

> **本地覆盖配置**：如需保留个人路径或密钥且不提交到 Git，可在 `config/` 下创建 `settings.local.yaml`。程序会自动加载它，并覆盖 `settings.yaml` 中的同名配置。该文件已加入 `.gitignore`。

### 不修改代码的情况下调整翻译参数

在 `config/settings.yaml` 的 `deepseek` 段下添加以下任一项即可覆盖代码默认值：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `model` | `deepseek-chat` | 使用的模型名称 |
| `base_url` | `https://api.deepseek.com` | API 基础地址 |
| `batch_size` | 32 | 每批翻译段落数 |
| `temperature` | 0.1 | 生成温度，越低越稳定 |
| `max_workers` | 3 | 并发线程数 |
| `max_retries` | 3 | 失败重试次数 |
| `timeout` | 60 | 单次请求超时（秒） |

示例：

```yaml
deepseek:
  api_key: ""
  target_lang: "中文"
  batch_size: 48
  temperature: 0.05
```

---

## 运行方式详解

### 方式一：IDE 直接运行（推荐日常开发）

在 `config/settings.yaml` 的 `pipeline` 段配置好路径后，直接在 PyCharm / VS Code 中右键运行 `main.py`，无需输入任何命令行参数。

### 方式二：命令行运行（适合脚本化、批处理）

命令行参数的优先级高于配置文件，可临时覆盖配置。

```bash
# 仅解析单个 PDF
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test"

# 解析整个文件夹（批量 + 增量）
python main.py -i "D:/docs/" -o "D:/outputs/"

# 递归扫描子目录
python main.py -i "D:/docs/" -o "D:/outputs/" -r

# 解析 + 翻译为中文，并保存 Markdown
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" -t --target-lang 中文 -m

# 仅解析，不翻译
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" --no-translate
```

常用命令行参数：

| 参数 | 简写 | 说明 |
|---|---|---|
| `--input` | `-i` | 输入 PDF 文件或文件夹路径 |
| `--output` | `-o` | 输出目录路径 |
| `--config` | `-c` | 指定自定义配置文件路径 |
| `--translate` | `-t` | 启用翻译 |
| `--target-lang` | | 翻译目标语言 |
| `--save-markdown` | `-m` | 保存翻译后的 Markdown |
| `--recursive` | `-r` | 递归扫描子目录 |

---

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

---

## 目录结构

```text
layout_analysis/
├── config/
│   ├── __init__.py
│   ├── settings.yaml          # 全局配置模板（提交到 Git）
│   └── settings.local.yaml    # 本地覆盖配置（已加入 .gitignore）
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

---

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

---

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

---

## 常见问题排查

### Q1: 报错「未找到 MinerU 可执行文件」

**原因**：当前环境没有安装 MinerU，或不在 PATH 中。

**解决**：
1. 确认已激活 conda `doc` 环境：`conda activate doc`
2. 验证安装：`mineru --help`
3. 若仍报错，在 `config/settings.yaml` 中显式指定路径：

   **Windows**：
   ```yaml
   mineru:
     executable_path: "C:/Users/xxx/anaconda3/envs/doc/Scripts/mineru.exe"
   ```

   **Linux / macOS**：
   ```yaml
   mineru:
     executable_path: "/home/xxx/anaconda3/envs/doc/bin/mineru"
   ```

### Q2: 报错「启用翻译但未找到 DeepSeek API Key」

**原因**：`.env` 文件不存在，或文件中的 Key 名称写错。

**解决**：
1. 确认项目根目录存在 `.env` 文件
2. 确认内容为 `DEEPSEEK_API_KEY=sk-...`（不是 `api_key=` 或其他名称）
3. 确认没有多余的空格或引号

### Q3: 配置文件解析失败，提示「不可打印字符」

**原因**：Windows 路径中的反斜杠 `\` 在 YAML 双引号字符串内被当作转义符。

**解决**（任选其一）：
- 路径前加 `r` 前缀：`input_path: r"D:\data\input"`
- 改用单引号：`input_path: 'D:\data\input'`
- 反斜杠改斜杠：`input_path: D:/data/input`

### Q4: 翻译后的 Markdown 内容缺失

**原因**：早期版本使用全文一次性翻译，当 PDF 内容过长时，API 输出会被截断。

**解决**：
- 请确保使用的是最新代码（已改为分块并发翻译，每块约 3000 字符，默认 3 线程并发）
- 如仍有问题，尝试减小 `batch_size` 或增大 `timeout`

### Q5: 如何只解析不翻译？

两种方法：
1. 修改 `config/settings.yaml`：`translate: false`
2. 命令行覆盖：`python main.py -i ./input -o ./output --no-translate`

---

## 测试

```bash
# 运行全部单元测试
python -m unittest discover -s tests -v

# 单独运行某一模块
python -m unittest tests.test_pipeline_tracker -v
```

---

## 变更记录

- **2026-07-06**: 新增「本工程与本地深度学习模型的关系」章节，说明 MinerU 内部模型清单与本机缓存路径。
- **2026-07-06**: 锁定 MinerU 兼容版本为 3.4.2，更新 README 安装指引与 `requirements.txt`。
- **2026-07-06**: 补全 `core/pipeline_tracker.py` 与 `core/translator.py`；`main.py` 支持 `settings.local.yaml` 本地覆盖；翻译逻辑从 `main.py` 下沉至 `core/translator.py`。
- **2026-05-14**: 完善 README，补充 MinerU 安装指引、.env 配置步骤、路径示例、常见问题排查。
- **2026-05-13**: 初始化工程结构，完成全部模块开发。
- **2026-05-13**: 支持 YAML 配置中 `r"..."` 原始字符串与 Windows 反斜杠路径。
- **2026-05-13**: 新增批量转换与增量转换能力，引入 `PipelineTracker` 状态追踪模块，支持文件夹输入、断点续传与批量汇总报告。
- **2026-05-13**: 翻译策略改为直接对 MinerU 生成的 Markdown 全文翻译，保持原有格式、图片引用、表格结构不变，译文输出到 `auto/{stem}_zh.md`，与原文并排存放。
- **2026-05-13**: 精简 `settings.yaml`，仅保留 7 个常用参数，其余使用代码内置默认值。
- **2026-05-13**: 将 DeepSeek API Key 从 `settings.yaml` 迁移到 `.env` 文件，避免敏感凭证提交到 Git。
- **2026-05-13**: 翻译提效优化：`batch_size` 16→32、`temperature` 0.3→0.1、`translate_batch` 改为 `ThreadPoolExecutor` 并发执行（max_workers=3）。
