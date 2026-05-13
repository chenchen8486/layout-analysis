# MinerU 版面分析与翻译流水线

基于 [MinerU](https://github.com/opendatalab/MinerU) 的 PDF 解析能力，集成 DeepSeek Chat API 翻译，实现从 PDF 到结构化版面分析再到多语言翻译的完整流水线。

## 核心目标

- 参数化输入输出，零硬编码路径。
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
  # 默认输入输出路径；支持相对路径（基于项目根目录）或绝对路径
  # 配置后可直接在 IDE 中右键运行 main.py，无需命令行参数
  input_path: "./data/test.pdf"
  output_path: "./outputs/test"
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
  input_path: "./data/test.pdf"      # 相对路径基于项目根目录
  output_path: "./outputs/test"
```

### 方式二：命令行运行（适合脚本化、批处理）

命令行参数的优先级高于配置文件，可临时覆盖配置。

```bash
# 仅解析 PDF
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test"

# 解析 + 翻译为英文
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" --translate --target-lang 英文

# 解析 + 翻译 + 生成翻译后 Markdown
python main.py -i "D:/docs/test.pdf" -o "D:/outputs/test" -t --target-lang 英文 -m
```

## 目录结构

```
layout_analysis/
├── config/
│   ├── __init__.py
│   └── settings.yaml          # 全局配置
├── core/
│   ├── __init__.py
│   ├── mineru_engine.py       # MinerU CLI 封装
│   ├── layout_parser.py       # 版面分析结果解析
│   └── translator.py          # DeepSeek API 翻译
├── utils/
│   ├── __init__.py
│   └── logger.py              # 统一日志
├── tests/
│   ├── test_mineru_engine.py
│   ├── test_layout_parser.py
│   └── test_translator.py
├── docs/
│   └── design.md              # 设计文档
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
  ├── core/mineru_engine.py  ← 调用 mineru.exe 生成解析结果
  │       └── subprocess.run(mineru -p pdf -o dir --backend pipeline)
  │
  ├── core/layout_parser.py  ← 读取 content_list.json，提取版面元素
  │       └── 输出 layout_summary.json
  │
  └── core/translator.py     ←（可选）DeepSeek 批量翻译
          └── 输出 translated_content.json、translated.md
```

## 测试

```bash
# 运行全部单元测试
python -m unittest discover -s tests -v

# 单独运行某一模块
python -m unittest tests.test_layout_parser -v
```

## 变更记录

- **2026-05-13**: 初始化工程结构，完成全部模块开发。
