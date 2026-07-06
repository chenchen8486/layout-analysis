# 工程优化建议清单

> 本文档汇总当前代码、文档、测试与外部依赖中值得优化的问题。
> 创建时间：2026-07-06
> 最后更新：2026-07-06（根据当前代码实际状态刷新）

---

## 当前已完成的阻塞项

以下问题在本次会话中已解决，相关代码已通过测试。

### ✅ `core/pipeline_tracker.py` 已补全

- 文件已存在并实现：`PipelineTracker`、`StageStatus`、`StageInfo`。
- 支持 `mineru` / `layout` / `translate` 三阶段状态追踪。
- 单元测试 `tests/test_pipeline_tracker.py`（10 个用例）全部通过。

### ✅ `core/translator.py` 已补全

- 文件已存在并实现：`DeepSeekTranslator`、`TranslationResult`。
- 支持单条翻译、批量翻译、指数退避重试。
- 单元测试 `tests/test_translator.py`（4 个用例）全部通过。

### ✅ `config/settings.yaml` 已恢复为模板

- `input_path` / `output_path` 已置空，不再包含本地绝对路径。
- 已添加安全提示，引导使用 `.env` 或 `settings.local.yaml`。
- `main.py` 已支持 `settings.local.yaml` 覆盖 `settings.yaml`。

### ✅ `main.py` 可正常导入并运行

- 已导入 `PipelineTracker`、`StageStatus`、`DeepSeekTranslator`。
- 已接入增量流水线、分块并发翻译、状态保存与批量汇总。

---

## 一、仍待处理的工程完整度问题

### 1.1 文档与代码一致性

**现状**

- `docs/optimization_plan.md` 本身已滞后：仍把已实现的模块标记为“缺失”。
- `README.md` 与 `docs/design.md` 的目录结构、程序框架图虽已列出 `pipeline_tracker.py`、`translator.py`，但可能仍缺少对新增接口、配置覆盖、测试命令的最新描述。

**建议做法**

- 刷新本文档（本次更新即完成）。
- 同步检查 `README.md` 的「目录结构」「程序框架」「测试」「配置说明」段落。
- 同步 `docs/design.md` 的模块职责表。
- 如有接口变化，同步 `docs/design_incremental_batch.md`。

---

## 二、外部依赖治理

### 2.1 未锁定 MinerU 版本

**现状**

- `README.md` 指导用户 `pip install mineru`，但未说明推荐版本。
- `requirements.txt` 未写入 `mineru` 版本约束。

**影响**

- MinerU 升级后若 CLI 参数、输出目录结构或 JSON schema 变化，本工程可能在不知情的情况下失效。

**建议做法**

1. 在 `README.md` 增加「已验证兼容的 MinerU 版本」表格。
2. 在 conda 环境中固定安装，例如：

   ```bash
   pip install "mineru==0.10.x" -i https://pypi.tuna.tsinghua.edu.cn/simple/
   ```

3. 把 `mineru` 版本要求写入 `requirements.txt`：

   ```text
   # requirements.txt
   requests~=2.31.0
   pyyaml~=6.0.1
   python-dotenv~=1.0.0
   # 请按当前验证版本填写
   mineru==0.10.x
   ```

4. 可选：提供 `requirements-freeze.txt` 作为已知可工作的精确依赖快照，供 CI 或新成员复现环境。

### 2.2 MinerU 输出目录结构硬编码在多处

**现状**

- `MinerUEngine.run()` 与 `process_single_pdf()` 中均直接假定输出结构为 `output_dir/<stem>/auto/`。

**影响**

- MinerU 一旦调整输出目录命名，需要同时修改多处代码，容易遗漏。

**建议做法**

- 在 `MinerUEngine` 中把目录解析集中到单一方法：

  ```python
  def _resolve_auto_dir(self, pdf_path: Path, output_dir: Path) -> Path:
      auto_dir = output_dir / pdf_path.stem / "auto"
      if auto_dir.exists():
          return auto_dir
      # 兼容旧结构或未来结构
      return output_dir / pdf_path.stem
  ```

- `main.py` 中的路径推断统一调用该方法，避免重复实现。

### 2.3 缺少 MinerU 输出快照测试

**现状**

- 单元测试依赖临时构造的 JSON，未保存真实 MinerU 输出样本。

**影响**

- 升级 MinerU 后无法快速判断是解析器逻辑坏了，还是上游输出 schema 变了。

**建议做法**

- 在 `tests/fixtures/` 下维护一份脱敏的 MinerU 输出快照：

  ```text
  tests/
  ├── fixtures/
  │   └── sample_mineru_output/
  │       ├── sample_content_list.json
  │       ├── sample.md
  │       └── images/
  ```

- 每次 MinerU 升级后，用新版本跑样例 PDF，更新快照并跑回归测试。

---

## 三、代码质量与可维护性

### 3.1 `main.py` 职责过重

**现状**

- `main.py` 同时承担：参数解析、配置加载、路径处理、分块翻译、主流程编排、统计汇总。行数已超过 700 行。

**建议做法**

- 把非 CLI 专属逻辑下沉到 `core/`，但避免为一个函数新建模块（YAGNI）：
  - 分块策略 `_chunk_paragraphs`：暂时保留在 `main.py` 或移至 `core/translator.py` 作为私有方法；只有当出现多种分块策略时再拆分为独立模块。
  - 并发翻译 `_translate_chunks`：整合进 `core/translator.py`（如新增 `translate_markdown` 方法）。
  - 单 PDF 处理流程 `process_single_pdf`：独立为 `core/pipeline.py` 中的函数或类。
- `main.py` 只保留：参数解析、配置组装、引擎初始化、调用编排、退出码返回。

### 3.2 API Key 读取优先级 ✅ 已确认方案 B

**现状**

- `docs/design_incremental_batch.md` 第 6 节声明读取优先级：

  ```text
  settings.yaml 配置 > .env 文件 / 系统环境变量
  ```

- `main.py` 实际逻辑是：

  ```python
  deepseek_api_key = (
      deepseek_cfg.get("api_key")          # settings.yaml
      or os.environ.get("DEEPSEEK_API_KEY")  # 环境变量（含 .env 加载后的变量）
      or ""
  )
  ```

- `.env` 与系统环境变量平级，整体作为第二优先级；`settings.yaml` 优先级最高。

**已确认**

- 采用**方案 B**：保持当前代码逻辑 `settings.yaml > .env / 环境变量`，文档已对齐，无需修改。

### 3.3 `setup_logger` 存在重复 Handler 风险

**现状**

- `utils/logger.py` 通过 `if logger.handlers: return logger` 避免重复，但若同一进程内以不同 `level` 多次调用 `setup_logger`，第一次的 Handler 不会更新。

**影响**

- `main.py` 在配置加载后可能重新初始化日志级别，但 Handler 仍是首次创建的级别。

**推荐做法**

- 让 `setup_logger` 支持 `level` 更新，并在 `main.py` 配置加载后用正确级别重新初始化：

  ```python
  # utils/logger.py
  def setup_logger(
      name: str,
      level: str = "INFO",
      output_dir: str = "logs",
      reset: bool = False,
  ) -> logging.Logger:
      logger = logging.getLogger(name)
      logger.setLevel(getattr(logging, level.upper(), logging.INFO))
      if logger.handlers and not reset:
          return logger
      if reset:
          logger.handlers.clear()
      # ... 重新添加 handler
  ```

  ```python
  # main.py
  if log_cfg.get("level"):
      logger = setup_logger(
          "main",
          level=log_cfg["level"],
          output_dir=log_cfg.get("output_dir", "logs"),
          reset=True,
      )
  ```

---

## 四、新增功能规划（来自 `.cv-debate/Q-001`）

### 4.1 UI 界面开发议题

**现状**

- `.cv-debate/Q-001.md` 已就「是否构建 Gradio UI」进行红蓝军辩论，但尚未形成决议。

**核心分歧**

- 蓝军：Gradio + Pydantic 全反射自动生成表单，工期 15h。
- 红军：批判核心层耦合 Gradio、反射生成器代码缺陷、日志线程安全问题，建议修正版 MVA，工期 24h。

**红军修正版核心原则**（简述）

- `core/` 零 Gradio 依赖，通过 `Protocol` 暴露进度回调。
- 日志采用文件轮询（`gr.Timer` 每秒读取日志文件），不直接操作 UI 组件。
- watchdog 只做任务入队，实际消费由独立队列处理。
- 配置表单半自动生成：单层字段用反射，嵌套面板手写。

**建议做法**

- 在工程可运行、测试覆盖完整之后，再启动 UI。
- 若决定做，优先遵循红军修正版原则。

---

## 五、建议开发顺序

按优先级排序，建议按以下顺序逐个完成：

| 序号 | 任务 | 优先级 | 是否阻塞后续 | 状态 |
|-----|------|-------|------------|------|
| 1 | 补全 `core/pipeline_tracker.py` | P0 | 是 | ✅ 已完成 |
| 2 | 补全 `core/translator.py` | P0 | 是 | ✅ 已完成 |
| 3 | 验证 `main.py` 完整流水线可跑通 | P0 | 是 | ✅ 已完成 |
| 4 | 补齐 `tests/test_pipeline_tracker.py`、`tests/test_translator.py` | P0 | 否 | ✅ 已完成 |
| 5 | 恢复 `config/settings.yaml` 为模板，支持 `settings.local.yaml` 覆盖 | P1 | 否 | ✅ 已完成 |
| 6 | 同步 `README.md` / `docs/design.md` 与代码实际结构 | P1 | 否 | ✅ 已完成 |
| 7 | 统一 API Key 优先级并同步文档 | P1 | 否 | ✅ 已确认方案 B，文档与代码已对齐 |
| 8 | 整理 `main.py`，把翻译/分块逻辑下沉到 `core/translator.py` | P1 | 否 | ✅ 已完成 |
| 9 | 在 `MinerUEngine` 中集中处理输出目录推断 | P2 | 否 | ✅ 已完成 |
| 10 | 增加 `tests/fixtures/` MinerU 输出快照 | P2 | 否 | ✅ 已完成 |
| 11 | 在 README 中增加 MinerU 版本兼容性表格 | P2 | 否 | ⏳ 待做 |
| 12 | 修复 `setup_logger` 二次初始化问题 | P2 | 否 | ⏳ 待做 |
| 13 | 决议并启动 UI 开发（可选） | P3 | 否 | ⏳ 暂缓 |

---

## 六、待确认事项

请确认以下问题，确认后我将按顺序进入下一步：

1. ✅ **API Key 优先级**：已确认方案 B（`settings.yaml > .env / 环境变量`）。
2. **是否继续处理 P1 项：同步 README / design.md 与代码实际结构？**
3. **是否继续处理 P1 项：把 `_translate_chunks` / `_chunk_paragraphs` 下沉到 `core/translator.py`？**
4. **UI 议题是否继续暂缓，等核心流水线稳定后再议？**

---

## 附录：YAGNI

**YAGNI = You Aren't Gonna Need It（你不需要它）。**
敏捷开发原则：不要为「未来可能需要」而提前写代码。只实现当前明确需要的功能，避免过度设计。例如 `_chunk_paragraphs` 目前只有一种分块策略，就没有必要为它单独建一个 `utils/chunking.py` 模块；等到真的需要多种分块策略时，再拆也不迟。
