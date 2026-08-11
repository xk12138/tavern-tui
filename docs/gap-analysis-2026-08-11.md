# 功能缺口分析 · 2026-08-11

> 从**三种真实用户视角**审视 Tavern 项目在设计文档之外还缺什么。

---

## 背景

Tavern 目前有三份高质量设计文档:

- `DESIGN.md` —— 引擎架构、四角色 LLM、状态模型、里程碑
- `USAGE.md` —— 玩家侧使用手册
- `WORLD_BUILDING.md` —— 世界作者手册

**代码几乎为零**。本次分析回答一个问题:如果从"文档承诺"到"用户能用",还差哪些东西?

---

## 用户画像

| 用户 | 关心什么 | 一次典型任务 |
|---|---|---|
| **P · 玩家** | 装上就能玩,体验沉浸 | `pip install tavern && tavern` → 玩两小时 |
| **W · 世界作者** | 快速写世界、能验证、能分享 | 写 `world.toml` → 校验 → 分发给朋友 |
| **M · 维护者/贡献者** | 好上手贡献、测试覆盖、CI | Fork → 改代码 → PR → CI 绿 |

---

## 功能缺口清单

### P · 玩家侧(USAGE.md 已承诺)

| 缺口 | 状态 | 优先级 |
|---|---|---|
| `tavern` CLI 入口本身 | 缺 | P0(阻断一切) |
| 首次启动向导(provider / api key / world) | 缺 | P2 |
| 世界选择器 UI | 缺 | P2 |
| 角色创建流程(模板 + 自由描述) | 缺 | P3 |
| 输入前缀解析:`"..."` `*...*` `/...` `:...` | 缺 | P3 |
| 全部 `/` 系统指令(15 个) | 缺 | P3~P4 |
| 死亡分支 [R] [T] [Q] | 缺 | P3 |
| Textual 三分区 TUI + 打字机效果 | 缺 | P4 |
| 快捷键(Ctrl+P / Ctrl+R / Space 翻页) | 缺 | P4 |
| `/export novel` 小说导出 | 缺 | P5 |

### W · 世界作者侧(WORLD_BUILDING.md 已承诺)

| 缺口 | 状态 | 优先级 |
|---|---|---|
| **`tavern validate <path>` 校验** | **✅ v0.1.0** | **P0** |
| worldpack loader + schema 定义 | ✅ v0.1.0 | P0 |
| `tavern install <path>` | **✅ v0.2.0** | P1 |
| `tavern list` / `tavern uninstall` | **✅ v0.2.0** | P1 |
| `tavern config init/show/check/path` | **✅ v0.3.0** | P2 |
| `tavern search`(社区索引) | 缺 | P5(需中心仓库) |
| 引导式"从零创建世界" | 缺 | P4(需 LLM) |

### M · 维护者侧(DESIGN.md 已规划)

| 缺口 | 状态 | 优先级 |
|---|---|---|
| Python 项目骨架 `pyproject.toml` | ✅ 本次交付 | P0 |
| `src/tavern/` 目录结构 | ✅ 本次交付(部分) | P0 |
| LLM Provider 抽象层 + 4 种 adapter | 缺 | P2 |
| Narrator / Extractor / Director / Memory Keeper | 缺 | P3 |
| SQLite 存档层 | 缺 | P3 |
| 向量记忆库(chromadb/sqlite-vss) | 缺 | P4 |
| Orchestrator 回合循环 | 缺 | P3 |
| Textual TUI 层 | 缺 | P4 |
| CI 配置 | 缺 | P1 |
| 单元测试基础设施 | ✅ 本次交付 | P1 |
| README + LICENSE | 缺 | P1 |

---

## 优先级评估方法

按 `独立可交付性 × 用户即刻价值 × 后续依赖前置度` 排序:

**P0 · 立刻能干、无依赖、后续里程碑的地基**
1. **项目骨架 + worldpack loader + `tavern validate`** ← v0.1.0

**P1 · P0 完成后可立即做**
2. `tavern install/list/uninstall` + `~/.config/tavern/` 目录 ← v0.2.0
3. README / LICENSE / CI

**P2 · 需要用户 API key + Provider 抽象**
4. **LLM 配置管理**(`tavern config`)← v0.3.0
5. **LLM Provider 抽象层 + `tavern play` REPL(Echo + Anthropic)**← v0.4.0
6. 更多 provider(OpenAI/DeepSeek/Ollama/Custom)
7. 首次启动向导(`tavern init`)—— 目前用 `tavern config init` 兑现

**P3 · M0 里程碑核心**
7. Orchestrator 回合循环
8. Narrator + Extractor 双调用
9. 死亡分支
10. SQLite 存档
11. 输入解析 + 基础 `/` 指令

**P4+ · TUI / 记忆 / 高级功能**
12. Textual TUI
13. 长期记忆 / 向量库
14. Director / Memory Keeper
15. 小说导出

---

## 本次选定:P0 · worldpack loader + validator

### 为什么是它

1. **无 LLM 依赖**:纯静态,单元测试跑得动
2. **立刻兑现承诺**:WORLD_BUILDING.md §八 明文说"写完之后跑一下 `tavern validate`"
3. **是所有里程碑的地基**:M0 要 load minimal-tavern,M4 要 install/validate
4. **世界作者立刻能用**:他们目前只能"闭眼写"
5. **可完整测试 + 真跑**:5 分钟就能演示"改完 → 秒知对错"

### 交付物

- `src/tavern/` Python 包骨架
- `src/tavern/worldpack/` schema + loader + validator + diagnostics + tokens
- `src/tavern/cli.py` + `tavern validate` 子命令
- `examples/minimal-tavern/` + `examples/example-jianghu/` 参考世界包
- `tests/` 35 个测试,worldpack 覆盖率 97%,总 77%
- `docs/PRD-worldpack-validate.md` 产品需求
- `docs/CHANGELOG.md`(下一份)
- 本文件

### 不做

- `tavern install` / `search` / `config check` —— 归入 P1
- LLM 相关一切 —— 归入 P2+
- `--json` 输出 —— 归入 P1
