# MinerU 工程化封装设计文档

## 1. 设计目标

将原始的 `test_mineru.py` 脚本工程化，实现：
- **配置驱动**：所有路径、密钥、模型参数外置到 `config/settings.yaml`。
- **版面分析解析**：结构化读取 MinerU 输出的 `content_list.json`，提取文本、标题、表格、图片等元素。
- **翻译流水线**：集成 DeepSeek Chat API，支持段落级批量翻译、重试与结果回写。
- **可测试**：每个核心模块配套单元测试。

## 2. 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `config/settings.yaml` | MinerU 路径、DeepSeek API Key、日志级别等 |
| 日志 | `utils/logger.py` | 统一日志（文件 + 控制台，utf-8-sig） |
| MinerU 引擎 | `core/mineru_engine.py` | 封装 CLI 调用，自动查找可执行文件 |
| 版面解析 | `core/layout_parser.py` | 解析 JSON 输出，提取可翻译元素，生成统计摘要 |
| 翻译器 | `core/translator.py` | 调用 DeepSeek API，支持批量、重试、分隔符策略 |
| 入口 | `main.py` | CLI 入口，串联整条流水线 |
| 测试 | `tests/` | 各模块单元测试 |

## 3. 调用流程

```text
用户命令: python main.py --input xxx.pdf --output out/ --translate --target-lang 英文
    │
    ▼
加载 config/settings.yaml
    │
    ▼
MinerUEngine.run(input_pdf, output_dir)
    └── subprocess.run(mineru.exe -p ... -o ... --backend pipeline)
    │
    ▼
LayoutParser.parse(auto_dir)
    └── 读取 *_content_list.json → List[LayoutElement]
    │
    ▼
（若 --translate）
DeepSeekTranslator.translate_batch(texts, target_lang)
    └── 按 batch_size 切片 → 拼接为单请求（---PARAGRAPH_BREAK--- 分隔）
    └── 指数退避重试 → 拆分回段落级结果
    │
    ▼
保存结果：
    - output_dir/translated_content.json
    - output_dir/layout_summary.json
```

## 4. 关键设计决策

### 4.1 可执行文件查找优先级
1. `config/settings.yaml` 显式指定
2. 当前激活的 conda 环境 `Scripts/mineru.exe`
3. 环境变量 `MINERU_PATH`
4. 系统 `PATH`

### 4.2 批量翻译分隔符策略
为节省 API Token 与请求次数，将同一批段落用 `\n\n---PARAGRAPH_BREAK---\n\n` 拼接为单条请求，并在 System Prompt 中要求模型保持分隔符不变。返回后按相同分隔符拆分。

### 4.3 重试机制
采用指数退避（2^attempt 秒），应对 DeepSeek API 偶发的网络抖动或限流。

## 5. 变更记录

- **2026-05-13**: 初始化工程结构，完成 core / utils / config / tests / docs / main.py 全部模块。
