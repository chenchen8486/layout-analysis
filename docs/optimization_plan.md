# 工程优化建议清单

> 本文档汇总当前代码、文档、测试与外部依赖中已完成的优化项，以及暂缓的规划项。
> 创建时间：2026-07-06
> 最后更新：2026-07-06（文档收尾，标记全部已完成项）

---

## 执行摘要

本次优化周期中，所有 P0 / P1 / P2 工程项已全部完成并推送至 `origin/master`，共 38 个单元测试全部通过。P3 UI 议题按当前决策**暂缓**。

### 关键成果

- 补全 `core/pipeline_tracker.py` 与 `core/translator.py`，主流程可运行。
- `main.py` 瘦身约 160 行，翻译 / 分块逻辑下沉至 `core/translator.py`。
- `MinerUEngine` 集中处理输出目录推断，`main.py` 不再重复实现。
- 增加 `tests/fixtures/sample_mineru_output/` 快照与回归测试。
- 锁定 MinerU 兼容版本为 **3.4.2**，同步 README 与 `requirements.txt`。
- 修复 `setup_logger` 二次初始化时日志级别不更新的问题。
- `config/settings.yaml` 恢复为模板，`settings.local.yaml` 用于本地覆盖。

---

## 一、工程完整度

### 1.1 文档与代码一致性 ✅ 已完成

- `docs/optimization_plan.md` 已根据代码实际状态刷新。
- `README.md` 已同步目录结构、程序框架、配置说明、变更记录。
- `docs/design.md` 已更新模块职责表与调用流程图。
- `docs/design_incremental_batch.md` 中的 API Key 优先级与代码保持一致（方案 B）。

---

## 二、外部依赖治理

### 2.1 MinerU 版本锁定 ✅ 已完成

- README 已增加「已验证兼容的 MinerU 版本」表格，版本号 **3.4.2**，验证日期 2026-07-06。
- README 安装指引改为 `pip install "mineru==3.4.2"`。
- `requirements.txt` 已写入 `mineru==3.4.2`。

### 2.2 MinerU 输出目录推断 ✅ 已完成

- `MinerUEngine` 新增 `resolve_auto_dir()` 静态方法，统一推断 `output_dir/<stem>/auto/` 及其兼容路径。
- `main.py` 复用该方法，删除了重复的路径推断代码。

### 2.3 MinerU 输出快照测试 ✅ 已完成

- 新增 `tests/fixtures/sample_mineru_output/`，包含 `sample_content_list.json`、`sample.md`、`images/`。
- 新增 `TestLayoutParserWithFixture` 回归测试，覆盖快照解析、摘要、table_body、未知类型处理。

---

## 三、代码质量与可维护性

### 3.1 `main.py` 职责瘦身 ✅ 已完成

- `_chunk_paragraphs` 与 `_translate_chunks` 已迁移至 `core/translator.py`。
- `main.py` 翻译流程简化为调用 `translator.translate_markdown()`。
- 移除未使用的 `ThreadPoolExecutor` / `as_completed` 导入。

### 3.2 API Key 读取优先级 ✅ 已完成

- 采用方案 B：`settings.yaml > .env / 环境变量`。
- `docs/design_incremental_batch.md` 与 `main.py` 逻辑一致，无需修改。

### 3.3 `setup_logger` 二次初始化 ✅ 已完成

- `utils/logger.py` 新增 `reset` 参数，支持清空旧 Handler 并重新初始化。
- `main.py` 在配置加载后使用 `reset=True` 重新初始化 logger，确保日志级别生效。
- 新增 `tests/test_logger.py`，覆盖 Handler 去重、级别更新、reset 行为。

---

## 四、新增功能规划

### 4.1 UI 界面开发议题 ⏸ 暂缓

- 当前决策：暂缓 Gradio UI 开发。
- 原因：核心流水线、测试覆盖、文档同步已优先完成；UI 属于增强功能，待后续有明确需求时再议。
- 历史参考：`.cv-debate/Q-001.md` 中红蓝军辩论记录保留，若重启 UI 议题，优先遵循红军修正版原则（`core/` 零 Gradio 依赖、Protocol 进度回调、日志文件轮询等）。

---

## 五、任务清单

| 序号 | 任务 | 优先级 | 是否阻塞后续 | 状态 |
|-----|------|-------|------------|------|
| 1 | 补全 `core/pipeline_tracker.py` | P0 | 是 | ✅ 已完成 |
| 2 | 补全 `core/translator.py` | P0 | 是 | ✅ 已完成 |
| 3 | 验证 `main.py` 完整流水线可跑通 | P0 | 是 | ✅ 已完成 |
| 4 | 补齐 `tests/test_pipeline_tracker.py`、`tests/test_translator.py` | P0 | 否 | ✅ 已完成 |
| 5 | 恢复 `config/settings.yaml` 为模板，支持 `settings.local.yaml` 覆盖 | P1 | 否 | ✅ 已完成 |
| 6 | 同步 `README.md` / `docs/design.md` 与代码实际结构 | P1 | 否 | ✅ 已完成 |
| 7 | 统一 API Key 优先级并同步文档 | P1 | 否 | ✅ 已完成 |
| 8 | 整理 `main.py`，把翻译/分块逻辑下沉到 `core/translator.py` | P1 | 否 | ✅ 已完成 |
| 9 | 在 `MinerUEngine` 中集中处理输出目录推断 | P2 | 否 | ✅ 已完成 |
| 10 | 增加 `tests/fixtures/` MinerU 输出快照 | P2 | 否 | ✅ 已完成 |
| 11 | 在 README 中增加 MinerU 版本兼容性表格 | P2 | 否 | ✅ 已完成（版本 3.4.2） |
| 12 | 修复 `setup_logger` 二次初始化问题 | P2 | 否 | ✅ 已完成 |
| 13 | 决议并启动 UI 开发（可选） | P3 | 否 | ⏸ 暂缓 |

---

## 六、测试状态

```bash
python -m pytest tests/ -v
# 38 passed
```

---

## 附录：YAGNI

**YAGNI = You Aren't Gonna Need It（你不需要它）。**
敏捷开发原则：不要为「未来可能需要」而提前写代码。只实现当前明确需要的功能，避免过度设计。
